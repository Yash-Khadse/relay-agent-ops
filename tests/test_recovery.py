import multiprocessing
import socket

import pytest
from conftest import approve, start
from relay.admin import provision
from relay.db import Approval, Artifact, Execution, Workspace, now
from relay.engine import WorkflowEngine
from relay.maintenance import cleanup
from relay.mcp_tools import MCPRegistry, MCPServer
from relay.worker import run_claim
from sqlalchemy import select


def test_resume_after_actual_process_exit(system):
    client, worker, db, settings = system
    id = start(client)
    claim = worker.claim()
    child = multiprocessing.get_context("spawn").Process(
        target=run_claim, args=(settings.model_dump(), claim)
    )
    child.start()
    child.join(45)
    if child.is_alive():
        child.terminate()
        child.join()
        pytest.fail("Child worker did not exit")
    assert child.exitcode == 0
    assert client.get(f"/api/executions/{id}").json()["status"] == "waiting_approval"
    approve(client, id)
    worker.tick()
    assert client.get(f"/api/executions/{id}").json()["status"] == "completed"


def test_retry_failed_finalization_does_not_duplicate_artifact(system, monkeypatch):
    client, worker, db, _ = system
    id = start(client)
    worker.tick()
    approve(client, id)
    original = WorkflowEngine.finalize

    def fail_after_commit(engine, state):
        original(engine, state)
        raise ValueError("injected process boundary failure")

    monkeypatch.setattr(WorkflowEngine, "finalize", fail_after_commit)
    worker.tick()
    assert client.get(f"/api/executions/{id}").json()["status"] == "failed"
    assert client.post(f"/api/executions/{id}/cancel").status_code == 409
    monkeypatch.setattr(WorkflowEngine, "finalize", original)
    assert client.post(f"/api/executions/{id}/retry").status_code == 200
    worker.tick()
    with db.sessions() as session:
        assert len(session.scalars(select(Artifact).where(Artifact.execution_id == id)).all()) == 1
    assert client.get(f"/api/executions/{id}").json()["status"] == "completed"


def test_cleanup_only_expired_demo_workspace(system):
    client, worker, db, settings = system
    id = start(client)
    worker.tick()
    permanent = provision(db, "Permanent")
    with db.transaction() as session:
        run = session.get(Execution, id)
        session.get(Workspace, run.workspace_id).expires_at = now() - 7200
    assert cleanup(settings, db) == 1
    with db.sessions() as session:
        assert session.get(Execution, id) is None
        assert session.get(Workspace, permanent["workspace_id"]) is not None
        assert not session.scalars(select(Approval)).all()


def test_mcp_allowlist_and_private_address_denied(monkeypatch):
    server = MCPServer(
        "research", "https://example.com/mcp", frozenset({"search"}), frozenset({"workspace"})
    )
    registry = MCPRegistry([server])
    with pytest.raises(PermissionError):
        registry.authorize("research", "delete", "workspace", "owner")
    with pytest.raises(PermissionError):
        registry.authorize("research", "search", "another-workspace", "owner")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(PermissionError):
        registry.authorize("research", "search", "workspace", "owner")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443))],
    )
    assert registry.authorize("research", "search", "workspace", "operator") is server
