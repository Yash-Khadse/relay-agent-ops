# Troubleshooting

| Symptom | Check and action |
| --- | --- |
| `pnpm` resolves incorrectly in PowerShell | Use `pnpm.cmd`; install the documented version and restart the shell if PATH changed. |
| Missing Python packages | Run `uv sync --frozen --extra crew` from root. `scripts/dev.ps1` detects `.venv-runtime` then `.venv`; normal uv uses `.venv`. |
| Vite reports `ECONNREFUSED 127.0.0.1:8000` | Start the API and check `/api/health`. Vite's `/api` proxy targets that address. |
| Runs remain queued | Start the worker with the same database/checkpoint configuration and working directory as the API. Health alone does not prove worker liveness. |
| Login works then returns401 | Check session/workspace expiry and use an unconsumed code/new demo. For HTTPS require Secure cookies; avoid cross-site frontend/API hosts. |
| Access code rejected | Codes are single-use and expire after one hour. Ask the database administrator to issue a replacement with `relay.admin issue-code`. |
|403 on mutation | Check role, Origin/CORS, fetch-site policy, and whether anonymous live inference is disabled. Do not weaken workspace authorization. |
|409 on decision/control | Refresh run/approval state. Another decision may have committed, a deadline passed, or the operation is invalid for that status. Retry is only for failed runs. |
|422 source/request | Check documented lengths, exact field names, selected source ownership, combined48,000-character context limit, and revision allowance. |
|429 after repeated demos/runs | Respect IP/global/workspace limits. Demo workspaces have a lifetime creation allowance; waiting does not reset their workspace counter. |
| Provider/configuration failure | Verify explicit provider/model/key/endpoint and budget. Fixture is never an implicit fallback. A different provider model may reject JSON response format. |
| Crew opt-in rejected | Install extra, enable server flag, select crew_model and live provider, and pass per-run opt-in. The current UI has no Crew toggle. |
| Resume fails with missing checkpoint | Preserve both persistence stores. Do not restart from scratch under an old approval or bypass the hash check; investigate restoration/version mismatch. |
| SQLite locked/slow | Keep services on one machine with consistent files/lock directory; avoid network-file shares. Use PostgreSQL for shared deployment. |
| Stale running job after worker crash | Retain DB/checkpoints and restart worker. Expired leases are reclaimable; execution locks protect overlapping work. Inspect events/dead-job retry allowance. |
| Pause seems delayed | Pause is cooperative at a node boundary; an in-flight model request is not recalled. |
| No model costs/metrics in fixture | Expected: fixture performs no live calls. Live dollar estimates are unavailable, not zero. |
| Fonts differ inside Docker | nginx CSP blocks remote Google Fonts; system fallbacks are intentional. |
| PostgreSQL/Docker startup failure | Start Docker, inspect `docker compose config` and database health/logs; container execution was not verified during delivery. |
| SAM deploy creates nothing | Default `EnableResources=false` is deliberate. Review external DB, secrets, cost controls and parameters before enabling. |

For failures, collect execution ID, correlation header, status, event cursor, provider mode, sanitized worker JSON logs, and reproduction steps. Do not paste access codes, cookies, API keys, database URLs, raw confidential prompts, or user source content into public reports. Browser test traces may include user content; handle them as private diagnostics.

Relative database paths resolve from the current directory. Starting one process from a different directory can create a second empty database and make the system appear disconnected. `scripts/dev.ps1` changes to root to avoid this.

Back up metadata and checkpoints before repair. Recreating a table is not a schema migration. Do not delete local data as a first troubleshooting step; it destroys execution evidence and pending approvals. Permanent workspaces require deliberate operator retention; anonymous cleanup applies only after expiry and grace.
