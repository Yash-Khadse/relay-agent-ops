from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from .auth import issue_session, rate_limit, require, user
from .config import Settings
from .contracts import DecisionInput, ExecutionInput, LoginInput, SourceInput
from .db import (
    AccessCode,
    Approval,
    Artifact,
    Database,
    Event,
    Execution,
    Job,
    LoginSession,
    Source,
    Ticket,
    User,
    Workspace,
    digest,
    emit,
    iso,
    locked,
    now,
    serialize,
    uid,
)
from .engine import TERMINAL
from .providers import measured_usage
from .templates import AGENTS, BUNDLED_SOURCES, TEMPLATES


def owned(session, model, id, current):
    row = session.scalar(
        select(model).where(model.id == id, model.workspace_id == current.workspace_id)
    )
    if row is None:
        raise HTTPException(404, "Resource not found")
    return row


def execution_json(row):
    return serialize(row, ("request_key", "request_hash", "sources", "owner_id"))


def approval_json(session, row):
    result = serialize(row)
    result["topic"] = session.get(Execution, row.execution_id).topic
    return result


def idempotency(
    value: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> str:
    return value


def create_app(settings: Settings | None = None, db: Database | None = None) -> FastAPI:
    settings = settings or Settings()
    db = db or Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        db.initialize()
        yield

    app = FastAPI(title="Relay workflow API", version="0.1.0", lifespan=lifespan)
    app.state.db, app.state.settings = db, settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )

    @app.middleware("http")
    async def security(request: Request, call_next):
        correlation_id = uid()
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (
                origin
                and origin not in settings.cors_origins
                and origin != str(request.base_url).rstrip("/")
            ):
                return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    {"detail": "Cross-site mutations are not allowed"}, status_code=403
                )
            length = request.headers.get("content-length")
            if length and (not length.isdigit() or int(length) > 150000):
                return JSONResponse({"detail": "Request too large"}, status_code=413)
            # Enforce bounds even for chunked requests without Content-Length.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 150000:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "X-Correlation-ID": correlation_id,
                "Cache-Control": "no-store",
            }
        )
        return response

    @app.exception_handler(IntegrityError)
    async def conflict(request, exc):
        return JSONResponse(
            {"detail": "Concurrent request conflict; refresh and retry"}, status_code=409
        )

    @app.get("/api/health")
    def health():
        with db.sessions() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "version": "0.1.0"}

    @app.post("/api/auth/demo")
    def demo(request: Request, response: Response):
        if not settings.demo_enabled:
            raise HTTPException(403, "Demo sign-in disabled")
        with db.transaction() as session:
            # No proxy headers trusted for limits.
            rate_limit(session, "demo-global", 100, 3600)
            rate_limit(
                session,
                "demo:" + digest(request.client.host if request.client else "unknown"),
                10,
                3600,
            )
            workspace = Workspace(expires_at=now() + settings.session_hours * 3600)
            session.add(workspace)
            session.flush()
            current = User(workspace_id=workspace.id)
            session.add(current)
            session.flush()
            token = issue_session(session, current, settings.session_hours)
            result = serialize(current) | {"expires_at": iso(workspace.expires_at)}
        response.set_cookie(
            "relay_session",
            token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.session_hours * 3600,
            path="/",
        )
        return result

    @app.post("/api/auth/login")
    def login(body: LoginInput, request: Request, response: Response):
        # Separate transaction so invalid attempts still consume their rate allowance.
        with db.transaction() as session:
            rate_limit(
                session,
                "login:" + digest(request.client.host if request.client else "unknown"),
                20,
                3600,
            )
        with db.transaction() as session:
            code = session.scalar(
                select(AccessCode)
                .where(AccessCode.token_hash == digest(body.code))
                .with_for_update()
            )
            if not code or code.expires_at <= now():
                raise HTTPException(401, "Access code is invalid or expired")
            current = session.get(User, code.user_id)
            if not current:
                raise HTTPException(401, "Account unavailable")
            session.delete(code)
            token = issue_session(session, current, settings.session_hours)
            result = serialize(current) | {"expires_at": iso(now() + settings.session_hours * 3600)}
        response.set_cookie(
            "relay_session",
            token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.session_hours * 3600,
            path="/",
        )
        return result

    @app.get("/api/auth/me")
    def me(current: User = Depends(user)):
        with db.sessions() as session:
            workspace = session.get(Workspace, current.workspace_id)
            if workspace is None:
                raise HTTPException(401, "Workspace unavailable")
            return serialize(current) | {"expires_at": iso(workspace.expires_at)}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        with db.transaction() as session:
            record = session.get(LoginSession, digest(request.cookies.get("relay_session", "")))
            if record:
                session.delete(record)
        response.delete_cookie("relay_session", path="/")
        return {"ok": True}

    @app.get("/api/settings")
    def configuration(current: User = Depends(user)):
        return {
            "provider": settings.provider,
            "model": settings.model or "deterministic-fixture",
            "configured": settings.configured,
            "crew_enabled": settings.crew_enabled,
            "demo_mode": settings.provider == "fixture",
            "max_executions": settings.max_executions,
            "version": "0.1.0",
        }

    @app.get("/api/workflow-templates")
    def templates(current: User = Depends(user)):
        return TEMPLATES

    @app.get("/api/agents")
    def agents(current: User = Depends(user)):
        return AGENTS

    @app.get("/api/sources")
    def sources(current: User = Depends(user)):
        with db.sessions() as session:
            return BUNDLED_SOURCES + [
                serialize(s)
                for s in session.scalars(
                    select(Source).where(Source.workspace_id == current.workspace_id)
                )
            ]

    @app.post("/api/sources", status_code=201)
    def add_source(body: SourceInput, current: User = Depends(require("run"))):
        if "\x00" in body.content:
            raise HTTPException(422, "Binary data is not accepted")
        with db.transaction() as session:
            locked(session, Workspace, current.workspace_id)
            count = session.scalar(
                select(func.count())
                .select_from(Source)
                .where(Source.workspace_id == current.workspace_id)
            )
            if count >= 20:
                raise HTTPException(429, "Workspace source limit reached")
            row = Source(workspace_id=current.workspace_id, **body.model_dump())
            session.add(row)
            session.flush()
            return serialize(row)

    @app.post("/api/executions", status_code=202)
    def create_execution(
        body: ExecutionInput,
        key: str = Depends(idempotency),
        current: User = Depends(require("run")),
    ):
        if body.config.crew_enabled and (
            not settings.crew_enabled or settings.provider == "fixture"
        ):
            raise HTTPException(422, "CrewAI requires an enabled live configuration")
        fingerprint = digest(body.model_dump_json())
        with db.transaction() as session:
            workspace = locked(session, Workspace, current.workspace_id)
            if (
                settings.provider != "fixture"
                and workspace.expires_at
                and not settings.public_live_enabled
            ):
                raise HTTPException(403, "Live demo inference is disabled by the administrator")
            existing = session.scalar(
                select(Execution).where(
                    Execution.workspace_id == current.workspace_id, Execution.request_key == key
                )
            )
            if existing:
                if existing.request_hash != fingerprint:
                    raise HTTPException(409, "Idempotency key already used with different input")
                return execution_json(existing)
            if workspace.execution_count >= settings.max_executions:
                raise HTTPException(429, "Workspace execution allowance exhausted")
            rate_limit(session, "global-executions", settings.global_daily_executions, 86400)
            available = {s["id"]: s for s in BUNDLED_SOURCES}
            available.update(
                {
                    s.id: serialize(s)
                    for s in session.scalars(
                        select(Source).where(Source.workspace_id == current.workspace_id)
                    )
                }
            )
            ids = body.source_ids or [s["id"] for s in BUNDLED_SOURCES]
            if any(id not in available for id in ids):
                raise HTTPException(404, "Source not found")
            selected = [available[id] for id in dict.fromkeys(ids)]
            if sum(len(s["content"]) for s in selected) > 48000:
                raise HTTPException(422, "Combined source context exceeds 48000 characters")
            run = Execution(
                workspace_id=current.workspace_id,
                owner_id=current.id,
                request_key=key,
                request_hash=fingerprint,
                template_id=body.template_id,
                topic=body.topic,
                brief=body.brief,
                config=body.config.model_dump(),
                sources=selected,
                mode=settings.provider,
            )
            session.add(run)
            session.flush()
            session.add(Job(execution_id=run.id, dedupe_key="start"))
            workspace.execution_count += 1
            if body.template_id == "support":
                session.add(
                    Ticket(
                        execution_id=run.id, workspace_id=current.workspace_id, subject=body.topic
                    )
                )
            emit(
                session,
                run.id,
                "queued",
                "Execution queued",
                actor=current.id,
                template_id=run.template_id,
            )
            return execution_json(run)

    @app.get("/api/executions")
    def executions(
        search: str = "",
        status: str = "",
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        current: User = Depends(user),
    ):
        with db.sessions() as session:
            query = select(Execution).where(Execution.workspace_id == current.workspace_id)
            if search:
                query = query.where(Execution.topic.icontains(search, autoescape=True))
            if status:
                query = query.where(Execution.status == status)
            return [
                execution_json(r)
                for r in session.scalars(
                    query.order_by(Execution.created_at.desc()).offset(offset).limit(limit)
                )
            ]

    @app.get("/api/executions/{id}")
    def execution(id: str, current: User = Depends(user)):
        with db.sessions() as session:
            row = owned(session, Execution, id, current)
            approvals = session.scalars(
                select(Approval).where(Approval.execution_id == id).order_by(Approval.revision)
            ).all()
            artifacts = session.scalars(select(Artifact).where(Artifact.execution_id == id)).all()
            ticket = session.scalar(select(Ticket).where(Ticket.execution_id == id))
            return execution_json(row) | {
                "approvals": [approval_json(session, a) for a in approvals],
                "artifacts": [serialize(a, ("content",)) for a in artifacts],
                "ticket": serialize(ticket) if ticket else None,
            }

    @app.get("/api/executions/{id}/events")
    def events(id: str, after: int = Query(0, ge=0), current: User = Depends(user)):
        with db.sessions() as session:
            owned(session, Execution, id, current)
            return [
                serialize(e)
                for e in session.scalars(
                    select(Event)
                    .where(Event.execution_id == id, Event.id > after)
                    .order_by(Event.id)
                    .limit(500)
                )
            ]

    @app.post("/api/executions/{id}/{operation}")
    def control(id: str, operation: str, current: User = Depends(require("run"))):
        if operation not in {"cancel", "retry", "pause", "resume"}:
            raise HTTPException(404, "Unknown operation")
        with db.transaction() as session:
            owned(session, Execution, id, current)
            run = locked(session, Execution, id)
            if operation == "cancel":
                if run.status in TERMINAL:
                    if run.status == "cancelled":
                        return execution_json(run)
                    raise HTTPException(409, "Execution already finished")
                if session.scalar(select(Artifact).where(Artifact.execution_id == id)):
                    raise HTTPException(409, "Approved finalization has already committed")
                run.status, run.completed_at = "cancelled", now()
                for a in session.scalars(
                    select(Approval).where(
                        Approval.execution_id == id, Approval.status == "pending"
                    )
                ):
                    a.status = "cancelled"
            elif operation == "pause":
                if run.status not in {"queued", "running", "paused"}:
                    raise HTTPException(409, "Execution cannot be paused in its current state")
                run.pause_requested = True
                if run.status == "queued":
                    run.status = "paused"
            else:
                expected = "failed" if operation == "retry" else "paused"
                if run.status != expected:
                    raise HTTPException(409, f"Only {expected} executions can {operation}")
                rate_limit(session, f"control:{id}", 5, 3600)
                run.pause_requested, run.status, run.error = False, "queued", None
                # For queued-before-start pause there is deliberately no checkpoint.
                started = session.scalar(
                    select(Event.id)
                    .where(Event.execution_id == id, Event.kind == "node_started")
                    .limit(1)
                )
                session.add(
                    Job(
                        execution_id=id,
                        dedupe_key=f"{operation}:{uid()}",
                        payload={"require_checkpoint": bool(started)},
                    )
                )
            run.updated_at = now()
            emit(session, id, operation, f"{operation} requested", actor=current.id)
            return execution_json(run)

    @app.get("/api/approvals")
    def approvals(
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        current: User = Depends(user),
    ):
        with db.sessions() as session:
            return [
                approval_json(session, a)
                for a in session.scalars(
                    select(Approval)
                    .where(Approval.workspace_id == current.workspace_id)
                    .order_by(Approval.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ]

    @app.post("/api/approvals/{id}/decide")
    def decide(
        id: str,
        body: DecisionInput,
        key: str = Depends(idempotency),
        current: User = Depends(require("approve")),
    ):
        with db.transaction() as session:
            row = owned(session, Approval, id, current)
            # Lock execution before approval everywhere to keep authorization/finalization serialized.
            run = locked(session, Execution, row.execution_id)
            approval = locked(session, Approval, id)
            if approval.status == "decided":
                if (
                    approval.request_key == key
                    and approval.decision == body.decision
                    and approval.comment == body.comment
                ):
                    return approval_json(session, approval)
                raise HTTPException(409, "Approval already decided")
            if approval.status != "pending" or run.status != "waiting_approval":
                raise HTTPException(409, "Approval is no longer actionable")
            if approval.expires_at <= now():
                raise HTTPException(409, "Approval expired")
            if body.decision == "revise" and (
                not body.comment.strip() or approval.revision >= run.config["max_revisions"]
            ):
                raise HTTPException(
                    422, "Revisions require a comment and remaining revision allowance"
                )
            approval.status, approval.decision, approval.comment = (
                "decided",
                body.decision,
                body.comment,
            )
            approval.decided_by, approval.decided_at, approval.request_key = current.id, now(), key
            run.status, run.updated_at = "queued", now()
            session.add(
                Job(
                    execution_id=run.id,
                    dedupe_key=f"approval:{id}",
                    payload={"approval_id": id, "decision": body.decision},
                )
            )
            emit(
                session,
                run.id,
                "approval_decided",
                f"Human decision: {body.decision}",
                node="approval",
                actor=current.id,
                approval_id=id,
                decision=body.decision,
            )
            return approval_json(session, approval)

    @app.get("/api/artifacts")
    def artifacts(
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        current: User = Depends(user),
    ):
        with db.sessions() as session:
            return [
                serialize(a, ("content",))
                for a in session.scalars(
                    select(Artifact)
                    .where(Artifact.workspace_id == current.workspace_id)
                    .order_by(Artifact.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ]

    @app.get("/api/artifacts/{id}/download")
    def download(id: str, current: User = Depends(user)):
        with db.sessions() as session:
            artifact = owned(session, Artifact, id, current)
            return Response(
                artifact.content,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f'attachment; filename="relay-{artifact.id}.md"',
                    "Content-Security-Policy": "default-src 'none'; sandbox",
                },
            )

    @app.get("/api/metrics")
    def metrics(current: User = Depends(user)):
        with db.sessions() as session:
            runs = session.scalars(
                select(Execution).where(Execution.workspace_id == current.workspace_id)
            ).all()
            ids = [r.id for r in runs]
            records = session.scalars(select(Event).where(Event.execution_id.in_(ids))).all()
            pending = session.scalar(
                select(func.count())
                .select_from(Approval)
                .where(
                    Approval.workspace_id == current.workspace_id,
                    Approval.status == "pending",
                    Approval.expires_at > now(),
                )
            )
            daily: dict = defaultdict(lambda: {"total": 0, "completed": 0, "failed": 0})
            by_template: dict = defaultdict(lambda: {"total": 0, "completed": 0})
            latency: dict = defaultdict(list)
            for run in runs:
                day = datetime.fromtimestamp(run.created_at, UTC).strftime("%Y-%m-%d")
                daily[day]["total"] += 1
                by_template[run.template_id]["total"] += 1
                if run.status == "completed":
                    daily[day]["completed"] += 1
                    by_template[run.template_id]["completed"] += 1
                if run.status in {"failed", "timed_out"}:
                    daily[day]["failed"] += 1
            for event in records:
                if event.kind == "node_completed" and "duration_ms" in event.data:
                    latency[event.node].append(event.data["duration_ms"])
            durations = [
                r.completed_at - r.created_at
                for r in runs
                if r.status == "completed" and r.completed_at
            ]
            calls, input_tokens, output_tokens = measured_usage(db, ids)
            calls = sum(r.model_calls for r in runs)
            return {
                "total": len(runs),
                "completed": sum(r.status == "completed" for r in runs),
                "failed": sum(r.status in {"failed", "timed_out"} for r in runs),
                "pending_approvals": pending,
                "average_duration_seconds": sum(durations) / len(durations) if durations else 0,
                "llm_calls": calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost_usd": 0 if settings.provider == "fixture" else None,
                "by_template": [{"template_id": k, **v} for k, v in by_template.items()],
                "daily": [{"date": k, **v} for k, v in sorted(daily.items())],
                "node_latency": [
                    {"node": k, "average_ms": sum(v) / len(v)} for k, v in latency.items()
                ],
                "retries": sum(e.kind == "retry" for e in records),
            }

    if settings.static_dir and Path(settings.static_dir).is_dir():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="web")
    return app


app = create_app()
