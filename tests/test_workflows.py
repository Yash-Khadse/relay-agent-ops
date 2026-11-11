from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import approve, headers, start
from relay.db import Approval, Artifact, Job, now
from relay.worker import Worker
from sqlalchemy import select


@pytest.mark.parametrize("template", ["research", "support", "content"])
def test_complete_workflows_and_persisted_events(system, template):
    client, worker, db, settings = system
    id = start(client, template)
    assert worker.tick()
    run = client.get(f"/api/executions/{id}").json()
    assert run["status"] == "waiting_approval", run
    assert not run["artifacts"]
    events = client.get(f"/api/executions/{id}/events").json()
    assert any(e["kind"] == "handoff" for e in events)
    assert {e["node"] for e in events if e["kind"] == "node_completed"} >= {
        "analysis",
        "risk",
        "review",
    }
    assert [e["id"] for e in events] == sorted({e["id"] for e in events})
    assert approve(client, id).status_code == 200
    # New worker and API instance read saved state: no in-memory checkpoint dependency.
    replacement = Worker(settings)
    assert replacement.tick()
    refreshed = client.get(f"/api/executions/{id}").json()
    assert refreshed["status"] == "completed", refreshed
    assert len(refreshed["artifacts"]) == 1
    result = client.get(f"/api/artifacts/{refreshed['artifacts'][0]['id']}/download")
    assert "Deterministic integration demo" in result.text
    if template == "support":
        assert refreshed["ticket"]["status"] == "draft_approved"
    metric = client.get("/api/metrics").json()
    assert metric["completed"] == 1 and metric["llm_calls"] == 0
    assert metric["node_latency"]
    replacement.db.engine.dispose()


def test_reject_never_finalizes(system):
    client, worker, db, _ = system
    id = start(client)
    worker.tick()
    approve(client, id, "reject", "Not acceptable")
    worker.tick()
    run = client.get(f"/api/executions/{id}").json()
    assert run["status"] == "rejected"
    assert run["artifacts"] == []


def test_revision_new_approval_and_bounded_limit(system):
    client, worker, db, _ = system
    id = start(client, config={"max_revisions": 1})
    worker.tick()
    assert approve(client, id, "revise", "Please emphasize uncertainty").status_code == 200
    worker.tick()
    run = client.get(f"/api/executions/{id}").json()
    assert run["status"] == "waiting_approval"
    assert run["revision"] == 1
    assert len(run["approvals"]) == 2
    assert "Please emphasize uncertainty" in run["approvals"][-1]["draft"]
    assert approve(client, id, "revise", "Again").status_code == 422
    assert approve(client, id).status_code == 200
    worker.tick()
    assert client.get(f"/api/executions/{id}").json()["status"] == "completed"


def test_idempotency_and_concurrent_approval(system):
    client, worker, db, _ = system
    request_headers = headers()
    body = {
        "template_id": "research",
        "topic": "Research topic",
        "brief": "A grounded report on source documents",
    }
    first = client.post("/api/executions", headers=request_headers, json=body)
    second = client.post("/api/executions", headers=request_headers, json=body)
    assert first.json()["id"] == second.json()["id"]
    assert (
        client.post(
            "/api/executions", headers=request_headers, json={**body, "topic": "Different topic"}
        ).status_code
        == 409
    )
    worker.tick()
    id = first.json()["id"]
    approval = client.get(f"/api/executions/{id}").json()["approvals"][0]
    route = f"/api/approvals/{approval['id']}/decide"
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(
                lambda _: client.post(route, headers=headers(), json={"decision": "approve"}),
                range(2),
            )
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    worker.tick()
    # Queue redelivery cannot create a second artifact.
    with db.transaction() as session:
        job = session.scalar(
            select(Job).where(Job.execution_id == id, Job.dedupe_key.like("approval:%"))
        )
        job.status, job.available_at = "queued", now()
    worker.tick()
    with db.sessions() as session:
        assert len(session.scalars(select(Artifact).where(Artifact.execution_id == id)).all()) == 1


def test_duplicate_decision_same_key_is_idempotent(system):
    client, worker, _, _ = system
    id = start(client)
    worker.tick()
    aid = client.get(f"/api/executions/{id}").json()["approvals"][0]["id"]
    h = headers()
    assert (
        client.post(
            f"/api/approvals/{aid}/decide", headers=h, json={"decision": "approve"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/approvals/{aid}/decide", headers=h, json={"decision": "approve"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/approvals/{aid}/decide", headers=h, json={"decision": "reject"}
        ).status_code
        == 409
    )


def test_approval_expiration(system):
    client, worker, db, _ = system
    id = start(client)
    worker.tick()
    with db.transaction() as session:
        approval = session.scalar(select(Approval).where(Approval.execution_id == id))
        approval.expires_at = now() - 1
    assert approve(client, id).status_code == 409
    worker.tick()
    run = client.get(f"/api/executions/{id}").json()
    assert run["status"] == "timed_out" and run["artifacts"] == []


def test_cancel_and_pause_resume(system):
    client, worker, _, _ = system
    id = start(client)
    assert client.post(f"/api/executions/{id}/pause").status_code == 200
    worker.tick()
    assert client.get(f"/api/executions/{id}").json()["status"] == "paused"
    assert client.post(f"/api/executions/{id}/resume").status_code == 200
    worker.tick()
    assert client.get(f"/api/executions/{id}").json()["status"] == "waiting_approval"
    assert client.post(f"/api/executions/{id}/cancel").status_code == 200
    assert approve(client, id).status_code == 409
    assert client.get(f"/api/executions/{id}").json()["artifacts"] == []


def test_expired_worker_lease_recovers(system):
    client, worker, db, settings = system
    id = start(client)
    worker.claim()
    with db.transaction() as session:
        job = session.scalar(select(Job).where(Job.execution_id == id))
        job.lease_until = now() - 1
    Worker(settings, db).tick()
    assert client.get(f"/api/executions/{id}").json()["status"] == "waiting_approval"


def test_cursor_replay(system):
    client, worker, _, _ = system
    id = start(client)
    before = client.get(f"/api/executions/{id}/events").json()
    worker.tick()
    later = client.get(f"/api/executions/{id}/events?after={before[-1]['id']}").json()
    assert all(e["id"] > before[-1]["id"] for e in later)
