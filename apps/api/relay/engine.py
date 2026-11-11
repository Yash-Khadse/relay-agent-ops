"""Version 1 graph. Checkpoints are authoritative for routing and node outputs."""

import time
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from opentelemetry import trace
from sqlalchemy import select

from .config import Settings
from .contracts import AnalysisResult, DraftResult, Handoff, ResearchResult, ReviewResult
from .crew import research_crew
from .db import Approval, Artifact, Database, Execution, Ticket, digest, emit, locked, now
from .providers import Provider
from .tools import authorize_tool, validate_evidence

tracer = trace.get_tracer("relay.orchestrator")
TERMINAL = {"completed", "cancelled", "rejected", "timed_out"}


class Stopped(RuntimeError):
    pass


class Paused(RuntimeError):
    pass


class State(TypedDict, total=False):
    execution_id: str
    template_id: str
    topic: str
    brief: str
    sources: list[dict]
    config: dict
    revision: int
    feedback: str
    plan: list[str]
    research: dict
    analysis: dict
    risk: dict
    draft: dict
    review: dict
    decision: dict
    artifact_id: str


@contextmanager
def checkpointer(settings: Settings):
    if settings.checkpoint_url.startswith("sqlite:///"):
        from langgraph.checkpoint.sqlite import SqliteSaver

        path = settings.checkpoint_url.removeprefix("sqlite:///")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with SqliteSaver.from_conn_string(path) as saver:
            saver.setup()
            yield saver
    else:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row

        with Connection.connect(
            settings.checkpoint_url, autocommit=True, prepare_threshold=0, row_factory=dict_row
        ) as connection:
            postgres_saver = PostgresSaver(connection)
            # Serialize first-start migrations across independently starting workers.
            connection.execute("SELECT pg_advisory_lock(1380273241)")
            try:
                postgres_saver.setup()
            finally:
                connection.execute("SELECT pg_advisory_unlock(1380273241)")
            yield postgres_saver


class WorkflowEngine:
    def __init__(self, settings: Settings, db: Database, execution_id: str):
        self.settings, self.db, self.execution_id = settings, db, execution_id
        self.provider = Provider(settings, db, execution_id)
        self.started = time.monotonic()

    def guard(self):
        if time.monotonic() - self.started > self.settings.max_run_seconds:
            raise TimeoutError("Execution time budget exhausted")
        with self.db.sessions() as session:
            run = session.get(Execution, self.execution_id)
            if not run or run.status in TERMINAL:
                raise Stopped("Execution stopped")
            if run.pause_requested:
                raise Paused("Execution paused at a node boundary")

    def node(self, name, agent, fn):
        def execute(state: State):
            self.guard()
            started = time.monotonic()
            with self.db.transaction() as session:
                run = locked(session, Execution, self.execution_id)
                if run.status in TERMINAL:
                    raise Stopped("Execution stopped")
                run.current_node, run.updated_at = name, now()
                emit(
                    session,
                    self.execution_id,
                    "node_started",
                    f"{name} started",
                    node=name,
                    agent=agent,
                    revision=state.get("revision", 0),
                )
            with tracer.start_as_current_span(
                f"workflow.{name}",
                attributes={"execution.id": self.execution_id, "workflow.node": name},
            ):
                result = fn(state)
            with self.db.transaction() as session:
                emit(
                    session,
                    self.execution_id,
                    "node_completed",
                    f"{name} completed",
                    node=name,
                    agent=agent,
                    duration_ms=round((time.monotonic() - started) * 1000),
                    revision=state.get("revision", 0),
                )
            return result

        return execute

    def handoff(self, state, source, target, task, output_schema):
        message = Handoff(
            workflow_id=self.execution_id,
            current_node=target,
            source_agent=source,
            target_agent=target,
            task=task,
            context={
                "template_id": state["template_id"],
                "revision": state.get("revision", 0),
                "source_ids": [s["id"] for s in state["sources"]],
            },
            output_schema=output_schema,
            timeout_seconds=self.settings.model_timeout_seconds,
            permissions=["scoped_sources"],
            correlation_id=self.execution_id,
        )
        with self.db.transaction() as session:
            emit(
                session,
                self.execution_id,
                "handoff",
                task,
                node=target,
                agent=source,
                handoff=message.model_dump(),
            )

    def plan(self, state):
        self.handoff(
            state,
            "supervisor",
            "research",
            "Extract evidence from approved source snapshot",
            "ResearchResult",
        )
        return {
            "plan": [
                "Retrieve sources",
                "Extract evidence",
                "Analyze and assess risk in parallel",
                "Draft",
                "Independent review",
                "Human approval",
                "Export",
            ],
            "revision": 0,
            "feedback": "",
        }

    def research(self, state):
        authorize_tool("retrieve_documents", "research")
        with self.db.transaction() as session:
            emit(
                session,
                self.execution_id,
                "tool",
                "Retrieved scoped document snapshot",
                node="research",
                agent="research",
                tool="retrieve_documents",
                source_ids=[s["id"] for s in state["sources"]],
            )
        context = {k: state[k] for k in ("topic", "brief", "sources", "template_id")}
        result = (
            research_crew(self.provider, context)
            if state["config"].get("crew_enabled")
            else self.provider.generate(ResearchResult, context, "research")
        )
        validate_evidence(result, state["sources"])
        self.handoff(state, "research", "analysis", "Compare grounded findings", "AnalysisResult")
        self.handoff(
            state, "research", "risk", "Assess sensitive content and action scope", "RiskResult"
        )
        return {"research": result.model_dump()}

    def analysis(self, state):
        result = self.provider.generate(
            AnalysisResult,
            {k: state[k] for k in ("topic", "brief", "template_id", "research")},
            "analysis",
        )
        return {"analysis": result.model_dump()}

    def risk(self, state):
        text = (state["topic"] + " " + state["brief"]).lower()
        flags = [
            word
            for word in (
                "refund",
                "delete",
                "password",
                "financial",
                "medical",
                "legal",
                "compromise",
            )
            if word in text
        ]
        return {
            "risk": {
                "level": "high" if flags else "low",
                "flags": flags,
                "requires_approval": True,
                "policy": "All finalization requires authenticated human approval; external side effects disabled.",
            }
        }

    def draft(self, state):
        self.handoff(
            state,
            "analysis",
            "writer",
            "Draft a cited deliverable incorporating review feedback",
            "DraftResult",
        )
        context = {
            k: state[k]
            for k in ("topic", "brief", "template_id", "research", "analysis", "risk", "feedback")
        }
        draft = self.provider.generate(DraftResult, context, "draft")
        allowed = {s["id"] for s in state["sources"]}
        if not set(draft.source_ids).issubset(allowed):
            raise ValueError("Draft cites an unauthorized source")
        return {"draft": draft.model_dump()}

    def review(self, state):
        self.handoff(
            state,
            "writer",
            "reviewer",
            "Independently review the draft against evidence",
            "ReviewResult",
        )
        result = self.provider.generate(
            ReviewResult,
            {k: state[k] for k in ("draft", "research", "brief", "template_id")},
            "review",
        )
        if not state["draft"]["source_ids"] and state["research"]["evidence"]:
            result.passed = False
            result.issues.append("Draft is missing evidence citations")
        return {"review": result.model_dump()}

    def approval(self, state):
        # No DB side effect before interrupt: worker materializes the request after checkpoint save.
        decision = interrupt(
            {
                "kind": "approval",
                "revision": state["revision"],
                "draft": state["draft"]["markdown"],
                "risk": state["risk"]["level"],
                "review": state["review"],
            }
        )
        with self.db.sessions() as session:
            record = session.scalar(
                select(Approval).where(
                    Approval.execution_id == self.execution_id,
                    Approval.revision == state["revision"],
                )
            )
            if (
                not record
                or record.status != "decided"
                or record.decision != decision.get("decision")
                or record.id != decision.get("approval_id")
            ):
                raise PermissionError("Resume command does not match a recorded authorization")
            if record.content_hash != digest(state["draft"]["markdown"]):
                raise PermissionError("Approved draft differs from checkpoint")
            return {
                "decision": {
                    "decision": record.decision,
                    "comment": record.comment,
                    "approval_id": record.id,
                }
            }

    def revise(self, state):
        revision = state["revision"] + 1
        if revision > state["config"]["max_revisions"]:
            raise ValueError("Revision budget exhausted")
        feedback = state.get("decision", {}).get("comment") or "; ".join(state["review"]["issues"])
        with self.db.transaction() as session:
            run = locked(session, Execution, self.execution_id)
            run.revision = revision
        return {"revision": revision, "feedback": feedback, "decision": {}}

    def finalize(self, state):
        with self.db.transaction() as session:
            run = locked(session, Execution, self.execution_id)
            if run.status in TERMINAL:
                raise Stopped("Execution stopped")
            approval = session.scalar(
                select(Approval).where(
                    Approval.execution_id == self.execution_id,
                    Approval.revision == state["revision"],
                )
            )
            if (
                not approval
                or approval.status != "decided"
                or approval.decision != "approve"
                or approval.content_hash != digest(state["draft"]["markdown"])
            ):
                raise PermissionError("Finalization requires approval of this exact draft")
            authorize_tool("export", "execution", approved=True)
            artifact = session.scalar(
                select(Artifact).where(Artifact.execution_id == self.execution_id)
            )
            if artifact is None:
                artifact = Artifact(
                    execution_id=self.execution_id,
                    workspace_id=run.workspace_id,
                    title=state["draft"]["title"],
                    content=state["draft"]["markdown"],
                    content_hash=approval.content_hash,
                )
                session.add(artifact)
                session.flush()
                emit(
                    session,
                    self.execution_id,
                    "artifact",
                    "Approved artifact saved",
                    node="finalize",
                    agent="execution",
                    artifact_id=artifact.id,
                    content_hash=artifact.content_hash,
                    tool="export",
                )
            ticket = session.scalar(select(Ticket).where(Ticket.execution_id == self.execution_id))
            if ticket:
                ticket.status, ticket.response = "draft_approved", artifact.content
                ticket.category, ticket.priority = (
                    state["analysis"]["category"],
                    state["analysis"]["priority"],
                )
            # Completion status is projected by worker after graph checkpoint commits.
            return {"artifact_id": artifact.id}

    def reject(self, state):
        with self.db.transaction() as session:
            run = locked(session, Execution, self.execution_id)
            if run.status not in TERMINAL:
                run.status, run.completed_at = "rejected", now()
                ticket = session.scalar(
                    select(Ticket).where(Ticket.execution_id == self.execution_id)
                )
                if ticket:
                    ticket.status = "rejected"
        return {}

    def compile(self, saver):
        graph = StateGraph(State)
        agents = {
            "plan": "supervisor",
            "research": "research",
            "analysis": "analysis",
            "risk": "risk",
            "draft": "writer",
            "review": "reviewer",
            "approval": "approver",
            "revise": "writer",
            "finalize": "execution",
            "reject": "supervisor",
        }
        for name, agent in agents.items():
            graph.add_node(name, self.node(name, agent, getattr(self, name)))
        graph.add_edge(START, "plan")
        graph.add_edge("plan", "research")
        graph.add_edge("research", "analysis")
        graph.add_edge("research", "risk")
        graph.add_edge(["analysis", "risk"], "draft")
        graph.add_edge("draft", "review")
        graph.add_conditional_edges(
            "review",
            lambda s: (
                "revise"
                if not s["review"]["passed"] and s["revision"] < s["config"]["max_revisions"]
                else "approval"
            ),
            {"revise": "revise", "approval": "approval"},
        )
        graph.add_conditional_edges(
            "approval",
            lambda s: {"approve": "finalize", "reject": "reject", "revise": "revise"}[
                s["decision"]["decision"]
            ],
            {name: name for name in ("finalize", "reject", "revise")},
        )
        graph.add_edge("revise", "draft")
        graph.add_edge("finalize", END)
        graph.add_edge("reject", END)
        return graph.compile(checkpointer=saver)
