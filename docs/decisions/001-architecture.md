# ADR001: Durable graph with explicit human authorization

Status: accepted for Relay0.1 implementation.

## Context

Workflow requests can outlive HTTP requests and pause for human review. Agent outputs may be invalid, sources may contain hostile instructions, and workers/queues may deliver work more than once. The application needs inspectable state, bounded model usage, and authorization that survives restarts.

## Decision

Use FastAPI for authenticated workspace/API operations; SQLAlchemy metadata for runs, events, jobs, approval records and artifacts; LangGraph version1.0 plus SQLite/PostgreSQL checkpoints for graph execution. Keep scheduling outside the request process. Use a transactional database job outbox locally, with optional scheduled SQS dispatch on AWS.

LangGraph owns routing, parallelism, review/revision, interruption and resume. Optional CrewAI collaboration is bounded to research and uses the same validated budgeted provider boundary. Fixture mode is explicit and does not masquerade as model inference.

Persist the graph interrupt before materializing the pending approval. Record human decision and resume job atomically. Revalidate recorded approval ID/decision and exact content hash inside the resumed graph, then again at artifact finalization. Use lease fencing, execution locks, dedupe keys, and unique artifact constraints to tolerate redelivery. Missing resume checkpoints fail closed.

## Consequences

The design supports restartable human-supervised workflows and operational event history without keeping requests open. SQLite provides a low-friction local path; PostgreSQL is required for the Lambda/shared path. At-least-once scheduling can repeat model calls after crashes; no global exactly-once inference claim is made. Separate metadata/checkpoint stores require ordering/reconciliation and consistent backup practices rather than distributed transactions.

The implementation intentionally excludes arbitrary user-edited graphs, shell tools, automatic external customer actions, and unbounded agent delegation. API-only access-code provisioning is not offered; local administrators assign roles/workspaces. Managed SSO, schema migration tooling, externally integrated MCP retrieval, production observability, and cloud verification remain future work.
