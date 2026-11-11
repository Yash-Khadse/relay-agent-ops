import uuid

import pytest
from fastapi.testclient import TestClient
from relay.api import create_app
from relay.config import Settings
from relay.db import Database
from relay.worker import Worker


@pytest.fixture
def system(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'metadata.db'}",
        checkpoint_url=f"sqlite:///{tmp_path / 'checkpoints.db'}",
        data_dir=tmp_path,
        provider="fixture",
        max_executions=50,
    )
    db = Database(settings.database_url)
    app = create_app(settings, db)
    with TestClient(app) as client:
        assert client.post("/api/auth/demo").status_code == 200
        yield client, Worker(settings, db), db, settings
    db.engine.dispose()


def headers():
    return {"Idempotency-Key": str(uuid.uuid4())}


def start(client, template="research", **extra):
    response = client.post(
        "/api/executions",
        headers=headers(),
        json={
            "template_id": template,
            "topic": "Compare support platforms",
            "brief": "Compare the supplied documents and produce a grounded report.",
            **extra,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def approve(client, id, decision="approve", comment=""):
    approval = client.get(f"/api/executions/{id}").json()["approvals"][-1]
    return client.post(
        f"/api/approvals/{approval['id']}/decide",
        headers=headers(),
        json={"decision": decision, "comment": comment},
    )
