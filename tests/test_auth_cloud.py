import json

from conftest import start
from relay.admin import provision
from relay.cloud import dispatch
from relay.db import Job, now
from sqlalchemy import select


def test_access_code_consumed_once_and_role_preserved(system):
    client, _, db, _ = system
    info = provision(db, "Auditor", "viewer")
    client.post("/api/auth/logout")
    response = client.post("/api/auth/login", json={"code": info["access_code"]})
    assert response.status_code == 200
    assert response.json()["role"] == "viewer"
    assert client.get("/api/auth/me").json()["workspace_id"] == info["workspace_id"]
    assert client.post("/api/auth/login", json={"code": info["access_code"]}).status_code == 401
    assert (
        client.post(
            "/api/sources", json={"title": "No permission", "content": "Not allowed to create"}
        ).status_code
        == 403
    )


def test_outbox_delivery_reclaims_stale_dispatch(system):
    client, _, db, settings = system
    id = start(client)
    delivered = []

    class SQS:
        def send_message(self, **kwargs):
            delivered.append(json.loads(kwargs["MessageBody"]))

    assert dispatch(settings, db, SQS()) == 1
    assert dispatch(settings, db, SQS()) == 0
    with db.transaction() as session:
        job = session.scalar(select(Job).where(Job.execution_id == id))
        job.dispatched_at = now() - settings.lease_seconds - 1
    assert dispatch(settings, db, SQS()) == 1
    assert delivered[0] == delivered[1]
