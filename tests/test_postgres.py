"""Run explicitly against a dedicated test database, never a production database."""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import headers, start
from fastapi.testclient import TestClient
from relay.api import create_app
from relay.config import Settings
from relay.db import Approval, Database, Execution, Workspace, locked, now
from relay.maintenance import cleanup
from relay.worker import Worker
from sqlalchemy import select

pytestmark = pytest.mark.skipif(
    not os.getenv("RELAY_TEST_POSTGRES_URL"), reason="Dedicated PostgreSQL test URL not supplied"
)


def test_postgres_checkpoint_approval_race_and_large_workspace_cleanup(tmp_path):
    url = os.environ["RELAY_TEST_POSTGRES_URL"]
    settings = Settings(
        database_url=url,
        checkpoint_url=url.replace("postgresql+psycopg://", "postgresql://"),
        provider="fixture",
        max_executions=50,
        data_dir=tmp_path,
    )
    db = Database(url)
    with TestClient(create_app(settings, db)) as client:
        assert client.post("/api/auth/demo").status_code == 200
        worker = Worker(settings, db)
        ids = [start(client) for _ in range(16)]
        for _ in ids:
            worker.tick()
        id = ids[0]
        detail = client.get(f"/api/executions/{id}").json()
        assert detail["status"] == "waiting_approval", detail
        aid = detail["approvals"][0]["id"]
        with ThreadPoolExecutor(2) as pool:
            results = list(
                pool.map(
                    lambda _: client.post(
                        f"/api/approvals/{aid}/decide",
                        headers=headers(),
                        json={"decision": "approve"},
                    ),
                    range(2),
                )
            )
        assert sorted(r.status_code for r in results) == [200, 409]
        Worker(settings, db).tick()
        assert client.get(f"/api/executions/{id}").json()["status"] == "completed"
        # Demonstrate refresh after a previously-loaded row waits on a lock.
        with db.sessions() as stale:
            before = stale.get(Execution, ids[1])
            assert before.status == "waiting_approval"
            with db.transaction() as other:
                other.get(Execution, ids[1]).status = "cancelled"
            assert locked(stale, Execution, ids[1]).status == "cancelled"
        with db.transaction() as session:
            run = session.get(Execution, id)
            session.get(Workspace, run.workspace_id).expires_at = now() - 7200
        assert cleanup(settings, db) >= 1
        with db.sessions() as session:
            assert not session.scalars(select(Execution).where(Execution.id.in_(ids))).all()
            assert not session.scalars(select(Approval).where(Approval.execution_id.in_(ids))).all()
    db.engine.dispose()
