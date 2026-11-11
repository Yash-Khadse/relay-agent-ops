# Résumé and portfolio notes

Describe the shipped implementation and evidence without implying business adoption, live model superiority, or a deployed AWS service.

## Suggested bullets

- Built Relay, a React/TypeScript and FastAPI workflow operations application with LangGraph checkpoints, versioned graph execution, event tracing, and human approval gates.
- Implemented exact-draft approval validation, workspace-scoped authorization, idempotent creation/decisions, durable job leases, and checkpoint-aware recovery.
- Added bounded structured-output model adapters and optional CrewAI researcher/critic collaboration, with deterministic fixtures for repeatable integration testing.
- Delivered a responsive operations UI, authenticated artifact downloads, automated API/browser tests, and opt-in container/AWS deployment assets.

Only add numbers derived from retained test/evaluation artifacts, and label the environment/sample. Avoid claims such as reduced cost by a percentage, improved accuracy, production scale, real customers, or successful AWS deployment unless separately measured and documented.

## Demonstration sequence

1. Explain fixture mode: deterministic integration, no live AI call.
2. Show actual template graph and source selection.
3. Start a run and inspect parallel analysis/risk, handoff events, and review.
4. Request a revision with context; show a new approval/revision.
5. Approve the exact draft and download the artifact.
6. Show metrics, role enforcement tests, and persistence/recovery design.
7. Discuss optional provider/Crew/cloud paths and their verification limits.

The support example updates a local ticket and stores an approved response draft; do not describe it as sending a real customer response. The sample product comparisons are fictional. The MCP adapter is a separate experimental module rather than a connected UI feature.

## Interview tradeoffs

Explain why LangGraph owns durable lifecycle while CrewAI is confined to one node, why approval records and checkpoint state both matter, how the outbox handles at-least-once delivery, what an exact-draft hash protects, why model-call budgets reserve conservatively, and why SQLite is a local default while PostgreSQL is needed in shared/serverless deployment. Acknowledge the absence of managed identity, schema migrations, semantic-quality benchmarking, and verified cloud operation.
