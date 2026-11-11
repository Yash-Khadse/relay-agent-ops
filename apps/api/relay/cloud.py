"""AWS delivery adapters. PostgreSQL jobs remain the transactional outbox."""

import json

import boto3
from mangum import Mangum
from sqlalchemy import or_, select

from .api import app
from .config import Settings
from .db import Database, Job, now
from .worker import Worker

api_handler = Mangum(app)


def dispatch(settings: Settings, db: Database, sqs) -> int:
    sent = 0
    with db.transaction() as session:
        jobs = session.scalars(
            select(Job)
            .where(
                or_(
                    (Job.status == "queued") & (Job.available_at <= now()),
                    (Job.status == "running") & (Job.lease_until < now()),
                ),
                or_(
                    Job.dispatched_at.is_(None), Job.dispatched_at < now() - settings.lease_seconds
                ),
            )
            .order_by(Job.available_at)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for job in jobs:
            # Send before marking: a crash may duplicate delivery; claim and execution locks handle it.
            sqs.send_message(
                QueueUrl=settings.sqs_queue_url, MessageBody=json.dumps({"job_id": job.id})
            )
            job.dispatched_at = now()
            sent += 1
    return sent


def dispatcher_handler(event, context):
    settings = Settings()
    db = Database(settings.database_url)
    db.initialize()
    try:
        Worker(settings, db).expire_approvals()
        from .maintenance import cleanup

        cleanup(settings, db)
        return {"dispatched": dispatch(settings, db, boto3.client("sqs"))}
    finally:
        db.engine.dispose()


def worker_handler(event, context):
    settings = Settings()
    if settings.database_url.startswith("sqlite") or settings.checkpoint_url.startswith("sqlite"):
        raise RuntimeError("Lambda workers require persistent PostgreSQL metadata and checkpoints")
    worker = Worker(settings)
    failures = []
    try:
        for record in event.get("Records", []):
            try:
                payload = json.loads(record["body"])
                worker.tick(str(payload["job_id"]))
            except Exception:
                failures.append({"itemIdentifier": record["messageId"]})
        return {"batchItemFailures": failures}
    finally:
        worker.db.engine.dispose()
