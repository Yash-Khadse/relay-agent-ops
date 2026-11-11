# Relay implementation plan

Specification: supplied MASTER BUILD PROMPT, implemented as one modular application.

Architecture: FastAPI submits durable database jobs; a separate worker invokes a versioned LangGraph with persistent SQLite/PostgreSQL checkpoints. CrewAI is bounded to research synthesis. Approvals are compare-and-set transactions that enqueue resumption. Side effects are local database artifacts with unique execution keys. React polls persisted resources.

## Acceptance checkpoints
1. Contracts and storage: strict schemas, tenant-scoped queries, opaque expiring sessions, transactionally queued runs.
2. Execution: three templates, structured handoffs, parallel analysis/risk, checkpoint recovery, bounded retries, cancellation, pause, approved-only finalization.
3. Providers and tools: explicit offline fixture mode; configured Ollama/Groq/Gemini; optional bounded CrewAI; allowlisted tools; no arbitrary filesystem/network access.
4. UI: landing, dashboard, templates/graph inspection, executions, detail, approval inbox, agents, analytics, artifacts, settings; persisted polling with clear loading/error/empty states.
5. Delivery: tests for restart, approval races/replay, revisions/rejection, isolation, budgets, artifacts; locked dependencies; Docker, CI, opt-in AWS SAM; complete honest setup/security/deployment documentation.

Deployment and real provider verification require later environment values. They are not acceptance claims for this code-only delivery. No fabricated inference or quality metrics.

The claude-mem work_state tool is unavailable in this session's tool inventory; no substitute remote memory service is invoked.

## Delivery checkpoint — 28 October 2026

Code, local fixture execution, dashboard, persistence/recovery, authorization, tests, packaging, and documentation are implemented. Final verification is recorded in `docs/verification.md`. Live-provider execution, AWS deployment, remote CI execution, and a hosted public demo await environment/account configuration. The optional CrewAI dependency audit has known unresolved advisories documented in SECURITY.md; default runtime audits pass.
