"""Bound retention for expired anonymous workspaces; permanent workspace data is untouched."""

from contextlib import ExitStack, contextmanager

from filelock import Timeout
from sqlalchemy import delete, select, text

from .db import (
    AccessCode,
    Approval,
    Artifact,
    Database,
    Event,
    Execution,
    Job,
    LoginSession,
    RateBucket,
    Source,
    Ticket,
    User,
    Workspace,
    digest,
    emit,
    locked,
    now,
)
from .engine import checkpointer
from .worker import execution_lock


@contextmanager
def cleanup_locks(db, settings, ids):
    if db.engine.dialect.name == "postgresql":
        # All advisory locks share one connection regardless of workspace size.
        with db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            acquired = []
            try:
                for id in ids:
                    key = int(digest(id)[:15], 16)
                    if not connection.scalar(
                        text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
                    ):
                        raise Timeout(id)
                    acquired.append(key)
                yield
            finally:
                for key in acquired:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
    else:
        with ExitStack() as stack:
            for id in ids:
                stack.enter_context(execution_lock(db, settings, id))
            yield


def cleanup(settings, db: Database) -> int:
    with db.sessions() as session:
        candidates = list(
            session.scalars(
                select(Workspace.id).where(Workspace.expires_at < now() - 3600).limit(100)
            )
        )
    removed = 0
    # Initialize checkpoint migrations before opening metadata transactions.
    # PostgreSQL concurrent index creation can wait for those transactions.
    if candidates:
        with checkpointer(settings):
            pass
    for workspace_id in candidates:
        with db.transaction() as session:
            workspace = locked(session, Workspace, workspace_id)
            if not workspace or not workspace.expires_at or workspace.expires_at >= now() - 3600:
                continue
            runs = session.scalars(
                select(Execution).where(Execution.workspace_id == workspace_id)
            ).all()
            busy = False
            for run in runs:
                active = session.scalar(
                    select(Job.id)
                    .where(
                        Job.execution_id == run.id, Job.status == "running", Job.lease_until > now()
                    )
                    .limit(1)
                )
                if active:
                    run.status = "cancelled"
                    emit(session, run.id, "cancelled", "Anonymous workspace retention elapsed")
                    busy = True
            if busy:
                continue
            ids = [run.id for run in runs]
            # Expired sessions cannot submit new jobs. Locks exclude stale live workers.
            with ExitStack() as stack:
                try:
                    stack.enter_context(cleanup_locks(db, settings, ids))
                except Timeout:
                    continue
                with checkpointer(settings) as saver:
                    for id in ids:
                        saver.delete_thread(id)
                for model in (Event, Job, Approval, Artifact, Ticket):
                    session.execute(delete(model).where(model.execution_id.in_(ids)))
                session.execute(delete(Execution).where(Execution.workspace_id == workspace_id))
                session.execute(delete(Source).where(Source.workspace_id == workspace_id))
                users = select(User.id).where(User.workspace_id == workspace_id)
                session.execute(delete(LoginSession).where(LoginSession.user_id.in_(users)))
                session.execute(delete(AccessCode).where(AccessCode.user_id.in_(users)))
                session.execute(delete(User).where(User.workspace_id == workspace_id))
                session.delete(workspace)
                removed += 1
    with db.transaction() as session:
        session.execute(delete(LoginSession).where(LoginSession.expires_at < now()))
        session.execute(delete(AccessCode).where(AccessCode.expires_at < now()))
        session.execute(delete(RateBucket).where(RateBucket.expires_at < now()))
    return removed
