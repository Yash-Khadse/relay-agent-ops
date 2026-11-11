import hashlib
import secrets
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def now() -> float:
    return datetime.now(UTC).timestamp()


def uid() -> str:
    return secrets.token_hex(16)


def iso(value: float | None) -> str | None:
    return datetime.fromtimestamp(value, UTC).isoformat() if value else None


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120), default="Demo workspace")
    created_at: Mapped[float] = mapped_column(Float, default=now)
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_count: Mapped[int] = mapped_column(Integer, default=0)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="Demo operator")
    role: Mapped[str] = mapped_column(String(20), default="owner")


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[float] = mapped_column(Float)


class AccessCode(Base):
    __tablename__ = "access_codes"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[float] = mapped_column(Float)


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (UniqueConstraint("workspace_id", "request_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    request_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    template_id: Mapped[str] = mapped_column(String(30))
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    topic: Mapped[str] = mapped_column(String(160))
    brief: Mapped[str] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    current_node: Mapped[str | None] = mapped_column(String(60), nullable=True)
    mode: Mapped[str] = mapped_column(String(30), default="fixture")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float, default=now)
    updated_at: Mapped[float] = mapped_column(Float, default=now)
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("execution_id", "dedupe_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id"), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[float] = mapped_column(Float, default=now)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dispatched_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("execution_id", "revision"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    draft: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    risk: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[float] = mapped_column(Float, default=now)
    expires_at: Mapped[float] = mapped_column(Float)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decided_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    request_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id"), unique=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(80), default="text/markdown")
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float, default=now)
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    producer: Mapped[str] = mapped_column(String(40), default="execution")
    version: Mapped[str] = mapped_column(String(20), default="1.0")


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    node: Mapped[str | None] = mapped_column(String(60), nullable=True)
    agent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    message: Mapped[str] = mapped_column(String(1000))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float, default=now)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="user")


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id"), unique=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    subject: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(30), default="open")
    category: Mapped[str] = mapped_column(String(80), default="general")
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    response: Mapped[str] = mapped_column(Text, default="")


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[float] = mapped_column(Float)


class Database:
    def __init__(self, url: str):
        sqlite = url.startswith("sqlite")
        if sqlite and ":memory:" not in url:
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30} if sqlite else {},
            pool_pre_ping=True,
        )
        if sqlite:

            @event.listens_for(self.engine, "connect")
            def pragmas(connection, _):
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA foreign_keys=ON")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self):
        Base.metadata.create_all(self.engine)

    @contextmanager
    def transaction(self):
        with self.sessions() as session:
            if self.engine.dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise


def locked(session: Session, model, id: str):
    return session.scalar(
        select(model)
        .where(model.id == id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def emit(
    session: Session, execution_id: str, kind: str, message: str, *, node=None, agent=None, **data
):
    session.add(
        Event(
            execution_id=execution_id,
            kind=kind,
            message=message[:1000],
            node=node,
            agent=agent,
            data=data,
        )
    )


def digest(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def serialize(row: Base, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    result = {}
    for column in row.__table__.columns:
        if column.name in exclude:
            continue
        value = getattr(row, column.name)
        result[column.name] = iso(value) if column.name.endswith("_at") else value
    return result
