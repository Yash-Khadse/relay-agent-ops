"""Database-backed queue, fenced leases, cross-process execution locks and crash recovery."""

import logging
import multiprocessing
import time
from contextlib import contextmanager
from typing import Any

from filelock import FileLock, Timeout
from langgraph.types import Command
from sqlalchemy import or_, select, text

from .config import Settings
from .db import Approval, Artifact, Database, Execution, Job, digest, emit, locked, now, uid
from .engine import TERMINAL, Paused, Stopped, WorkflowEngine, checkpointer
from .providers import BudgetExceeded

logger = logging.getLogger("relay.worker")


@contextmanager
def execution_lock(db: Database, settings: Settings, execution_id: str):
    if db.engine.dialect.name == "postgresql":
        # Session-level advisory lock is released even if a process dies.
        key = int(digest(execution_id)[:15], 16)
        with db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            if not acquired:
                raise Timeout(execution_id)
            try:
                yield
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
    else:
        directory = settings.data_dir / "locks"
        directory.mkdir(parents=True, exist_ok=True)
        with FileLock(directory / f"{execution_id}.lock", timeout=0):
            yield


class Worker:
    def __init__(self, settings: Settings, db: Database | None = None):
        self.settings = settings
        self.db = db or Database(settings.database_url)
        self.db.initialize()

    def claim(self, job_id: str | None = None):
        with self.db.transaction() as session:
            query = (
                select(Job)
                .where(
                    or_(
                        (Job.status == "queued") & (Job.available_at <= now()),
                        (Job.status == "running") & (Job.lease_until < now()),
                    )
                )
                .order_by(Job.available_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job_id:
                query = query.where(Job.id == job_id)
            job = session.scalar(query)
            if not job:
                return None
            job.status, job.lease_token = "running", uid()
            job.lease_until, job.attempts = now() + self.settings.lease_seconds, job.attempts + 1
            return job.id, job.execution_id, job.lease_token

    def tick(self, job_id: str | None = None) -> bool:
        self.expire_approvals()
        claim = self.claim(job_id)
        if not claim:
            return False
        claimed_id, execution_id, token = claim
        try:
            with execution_lock(self.db, self.settings, execution_id):
                self.process(claimed_id, execution_id, token)
        except Timeout:
            # An older process still holds the execution lock. Let its durable work finish.
            with self.db.transaction() as session:
                job = locked(session, Job, claimed_id)
                if job.lease_token == token:
                    job.status, job.available_at = "queued", now() + 5
                    job.attempts -= 1
        return True

    def process(self, job_id, execution_id, token):
        with self.db.transaction() as session:
            run, job = locked(session, Execution, execution_id), locked(session, Job, job_id)
            if job.lease_token != token:
                return
            if run.status in TERMINAL:
                job.status = "done"
                return
            if run.pause_requested:
                run.status, job.status = "paused", "done"
                return
            if job.attempts > self.settings.max_job_attempts:
                job.status, run.status, run.error = (
                    "dead",
                    "failed",
                    "Worker recovery retry budget exhausted",
                )
                emit(session, execution_id, "failed", run.error)
                return
            run.status, run.updated_at, run.error = "running", now(), None
            payload = job.payload
            initial = {
                "execution_id": run.id,
                "template_id": run.template_id,
                "topic": run.topic,
                "brief": run.brief,
                "sources": run.sources,
                "config": run.config,
            }
            if run.version != "1.0":
                job.status, run.status, run.error = "dead", "failed", "Unsupported graph version"
                return
            emit(
                session, execution_id, "running", "Worker acquired execution", attempt=job.attempts
            )
        try:
            with checkpointer(self.settings) as saver:
                engine = WorkflowEngine(self.settings, self.db, execution_id)
                graph = engine.compile(saver)
                config = {
                    "configurable": {"thread_id": execution_id},
                    "recursion_limit": 50,
                    "max_concurrency": 2,
                }
                snapshot = graph.get_state(config)
                if payload.get("approval_id") and not snapshot.values:
                    raise ValueError(
                        "Missing checkpoint for approved execution; refusing to restart"
                    )
                if snapshot.values:
                    pending = any(task.interrupts for task in snapshot.tasks)
                    if pending and not payload.get("approval_id"):
                        with self.db.sessions() as session:
                            recorded = session.scalar(
                                select(Approval).where(
                                    Approval.execution_id == execution_id,
                                    Approval.revision == snapshot.values.get("revision", 0),
                                    Approval.status == "decided",
                                )
                            )
                            if recorded:
                                payload = {
                                    "approval_id": recorded.id,
                                    "decision": recorded.decision,
                                }
                    value: Any = (
                        Command(resume=payload) if payload.get("approval_id") and pending else None
                    )
                    if snapshot.next:
                        graph.invoke(value, config, durability="sync")
                else:
                    # Retry/resume jobs must never silently restart if persistence was lost.
                    if payload.get("require_checkpoint"):
                        raise ValueError("Missing checkpoint; cannot safely resume")
                    graph.invoke(initial, config, durability="sync")
                snapshot = graph.get_state(config)
                with self.db.transaction() as session:
                    run, job = (
                        locked(session, Execution, execution_id),
                        locked(session, Job, job_id),
                    )
                    if job.lease_token != token:
                        return
                    job.status = "done"
                    if run.status in TERMINAL:
                        return
                    if any(t.interrupts for t in snapshot.tasks):
                        revision = snapshot.values["revision"]
                        approval = session.scalar(
                            select(Approval).where(
                                Approval.execution_id == execution_id, Approval.revision == revision
                            )
                        )
                        if not approval:
                            draft = snapshot.values["draft"]["markdown"]
                            session.add(
                                Approval(
                                    execution_id=execution_id,
                                    workspace_id=run.workspace_id,
                                    revision=revision,
                                    draft=draft,
                                    content_hash=digest(draft),
                                    risk=snapshot.values["risk"]["level"],
                                    expires_at=now() + run.config["approval_hours"] * 3600,
                                )
                            )
                            emit(
                                session,
                                execution_id,
                                "approval_requested",
                                "Draft awaits authenticated human review",
                                node="approval",
                                review=snapshot.values["review"],
                                revision=revision,
                            )
                        run.status, run.current_node = "waiting_approval", "approval"
                    elif not snapshot.next:
                        if not session.scalar(
                            select(Artifact).where(Artifact.execution_id == execution_id)
                        ):
                            raise ValueError("Graph ended without an approved artifact")
                        run.status, run.completed_at = "completed", now()
                        emit(
                            session,
                            execution_id,
                            "completed",
                            "Workflow completed",
                            node="finalize",
                        )
                    run.updated_at = now()
        except Exception as exc:
            with self.db.transaction() as session:
                run, job = locked(session, Execution, execution_id), locked(session, Job, job_id)
                if job.lease_token != token:
                    return
                if run.status in TERMINAL or isinstance(exc, Stopped):
                    job.status = "done"
                    return
                if isinstance(exc, Paused):
                    run.status, job.status = "paused", "done"
                    emit(session, execution_id, "paused", "Paused at a safe node boundary")
                else:
                    # Never persist exception strings from SDKs: they may contain credentials/prompts.
                    error = (
                        "Usage budget exhausted"
                        if isinstance(exc, BudgetExceeded)
                        else f"{type(exc).__name__}: execution failed; inspect server diagnostics and configuration"
                    )
                    run.error, run.updated_at = error, now()
                    retryable = not isinstance(
                        exc, (PermissionError, ValueError, BudgetExceeded, TimeoutError)
                    )
                    if retryable and job.attempts < self.settings.max_job_attempts:
                        job.status, job.available_at = "queued", now() + 2**job.attempts
                        run.status = "queued"
                        emit(
                            session,
                            execution_id,
                            "retry",
                            "Retry scheduled from checkpoint",
                            error_type=type(exc).__name__,
                            attempt=job.attempts,
                        )
                    else:
                        run.status = "timed_out" if isinstance(exc, TimeoutError) else "failed"
                        job.status = "dead"
                        emit(session, execution_id, "failed", error, error_type=type(exc).__name__)
                    logger.warning(
                        "execution_failed",
                        extra={"execution_id": execution_id, "error_type": type(exc).__name__},
                    )

    def expire_approvals(self):
        # Always acquire execution before approval, matching decide/finalize lock order.
        with self.db.sessions() as session:
            expired = [
                (a.id, a.execution_id)
                for a in session.scalars(
                    select(Approval).where(
                        Approval.status == "pending", Approval.expires_at < now()
                    )
                )
            ]
        with self.db.transaction() as session:
            for approval_id, execution_id in expired:
                run = locked(session, Execution, execution_id)
                approval = locked(session, Approval, approval_id)
                if not approval or approval.status != "pending" or approval.expires_at >= now():
                    continue
                approval.status = "expired"
                if run.status == "waiting_approval":
                    run.status, run.completed_at = "timed_out", now()
                    emit(
                        session,
                        run.id,
                        "approval_expired",
                        "Approval deadline elapsed; no action executed",
                    )


def main():
    from .telemetry import configure_logging

    configure_logging()
    worker = Worker(Settings())
    logger.info("worker_started")
    last_cleanup = 0.0
    while True:
        if time.monotonic() - last_cleanup > 3600:
            from .maintenance import cleanup

            cleanup(worker.settings, worker.db)
            last_cleanup = time.monotonic()
        worker.expire_approvals()
        claim = worker.claim()
        if not claim:
            time.sleep(1)
            continue
        process = multiprocessing.get_context("spawn").Process(
            target=run_claim, args=(worker.settings.model_dump(), claim)
        )
        process.start()
        process.join(worker.settings.max_run_seconds + 10)
        if process.is_alive():
            process.terminate()
            process.join(10)
            with worker.db.transaction() as session:
                run = locked(session, Execution, claim[1])
                job = locked(session, Job, claim[0])
                if job.lease_token == claim[2] and run.status not in TERMINAL:
                    # A committed artifact must recover its graph projection, not be declared cancelled.
                    if session.scalar(select(Artifact.id).where(Artifact.execution_id == run.id)):
                        job.status, job.available_at = "queued", now()
                    else:
                        job.status, run.status = "dead", "timed_out"
                        run.error = "Worker wall-clock deadline exceeded"
                        emit(session, run.id, "failed", run.error)


def run_claim(settings_data, claim):
    worker = Worker(Settings(**settings_data))
    try:
        with execution_lock(worker.db, worker.settings, claim[1]):
            worker.process(*claim)
    except Timeout:
        with worker.db.transaction() as session:
            job = locked(session, Job, claim[0])
            if job.lease_token == claim[2]:
                job.status, job.available_at = "queued", now() + 5
                job.attempts -= 1
    finally:
        worker.db.engine.dispose()


if __name__ == "__main__":
    main()
