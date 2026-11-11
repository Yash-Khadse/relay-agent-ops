# Backend review

Scope: `apps/api/relay`, `infra/aws`, API contract and implementation plan. Static review only; existing tests were not rerun. No critical issue or demonstrated tenant-isolation / approval bypass found. Reviewed durable job claiming, execution locks, approval serialization, checkpoint recovery, cancellation, artifact uniqueness and provider budget reservations.

## Deployment blocker

- **High, conditional on cross-site hosting:** `apps/api/relay/api.py:96,157,192` and `infra/aws/template.yaml:18,48,131`. Setting `FrontendOrigin` to a separately hosted site and calling the generated execute-api URL does not produce a working browser deployment. Cross-site POSTs are explicitly rejected even for allowlisted origins; SameSite=Lax also excludes session cookies from cross-site fetches. Provide a concrete same-origin API reverse proxy (or same-site custom domains) in deployment instructions/infrastructure. Do not treat CORS configuration alone as sufficient. Actual DNS/proxy hosting remains unverified external setup.

## Lower-severity correctness issue

- **Medium:** `apps/api/relay/api.py:396-397`, `apps/api/relay/db.py:224-225`. `control()` loads Execution through `owned()` before obtaining its row lock. SQLAlchemy can retain that already-loaded state when the locking SELECT returns. On PostgreSQL, a request blocked behind another transaction can therefore evaluate obsolete status: simultaneous retries of a failed run can enqueue multiple retry jobs; cancellation waiting behind rejection can replace the terminal rejected status. Lock and authorize in one query, or refresh with `populate_existing=True` when locking. SQLite BEGIN IMMEDIATE serializes this earlier and can conceal the race. This does not demonstrate duplicate artifacts because execution locks and artifact uniqueness still apply.

## Verification limits

PostgreSQL contention, actual AWS/SAM image deployment, DNS/proxy routing, provider credentials/model compatibility, CrewAI execution and cloud billing/quotas were not executed. These are unverified setup/integration concerns, not claims of observed failure. Provider reservations persist before network calls and include failed attempts; approval actions lock execution before approval and enqueue in the same transaction; finalization verifies approval against the exact draft hash.

## Scoped follow-up review

The original findings are resolved in source: `locked()` now uses `populate_existing=True`; the AWS image builds and serves the frontend on the API origin with a root gateway event. The current frontend uses local page state, so no history-route fallback is required. Dispatcher now invokes cleanup. No new high/critical defect found in the watchdog changes; no tests rerun.

One new **medium, nondefault configuration** issue: `maintenance.py:34-35` holds a distinct pooled PostgreSQL connection for every execution advisory lock, plus the metadata transaction connection. SQLAlchemy's unchanged default pool permits 15 total connections; an expired workspace containing at least 15 executions self-exhausts that pool while acquiring its 15th lock. Pool timeout aborts cleanup, and the 30-second AWS dispatcher can expire before dispatching jobs. Settings permit up to 1000 executions per workspace; defaults of 10 locally / 3 on AWS avoid this case. Acquire the workspace's advisory locks using one dedicated shared connection, or use bounded cleanup batches. This is a source-derived contention issue, not an observed PostgreSQL integration failure.

## Final resolution and verification — 28 October 2026

Cleanup now acquires every execution advisory lock on one connection. Advisory-lock connections use autocommit, preventing an idle metadata transaction from blocking first-start concurrent checkpoint index creation. Checkpoint migrations are serialized across starting workers and initialized before cleanup opens its metadata transaction. A fresh PostgreSQL 18 integration test passed initialization, concurrent approval (one success and one conflict), completed resume, stale identity-map refresh, and cleanup of a 16-execution workspace. The full backend suite passed 28 tests. Live providers, deployed AWS hosting, and cloud billing remain unverified.
