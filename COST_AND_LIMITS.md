# Cost and limits

Fixture mode performs deterministic transformations and makes no model calls. Its model cost metric is zero. Live-mode estimated dollar cost is `null`/unavailable because no pricing table is maintained; do not treat it as a zero-cost result. Hosting, storage, network, logging, and any external database may incur charges even without inference. No free-tier or permanently-free deployment claim is made.

## Default runtime bounds

| Setting | Default | Meaning |
| --- | --- | --- |
| `RELAY_MAX_EXECUTIONS` | 10 | Lifetime creation allowance per workspace, not concurrent runs |
| `RELAY_GLOBAL_DAILY_EXECUTIONS` | 100 | Shared fixed-window creation limit |
| `RELAY_SESSION_HOURS` | 24 | Session duration; demo workspace lifetime |
| `RELAY_APPROVAL_HOURS` | 24 | Runtime setting; execution config defaults24 and accepts1–168 |
| `RELAY_MAX_RUN_SECONDS` | 240 | Graph segment time budget; excludes human waiting |
| `RELAY_LEASE_SECONDS` | 300 | Claim lifetime; must exceed max run seconds |
| `RELAY_MAX_JOB_ATTEMPTS` | 3 | Automatic worker attempt allowance |
| `RELAY_MAX_MODEL_CALLS` | 12 | Conservative per-execution model-call reservations |
| `RELAY_MAX_INPUT_TOKENS` | 30000 | Per-execution input reservation allowance |
| `RELAY_MAX_OUTPUT_TOKENS` | 12000 | Per-execution output reservation allowance |
| `RELAY_MODEL_TIMEOUT_SECONDS` | 45 | Individual model HTTP timeout |

Each provider call reserves usage **before** network I/O. Input reservation uses UTF-8 prompt bytes plus400 as a conservative estimate, not an exact tokenizer count. Output reservation is1800 per attempt. Failed/unknown calls retain reservations. Measured usage metrics are computed separately from successful model events and may differ from conservative execution counters. Provider retries/fallback and worker retries can consume additional reservations. A fallback is not enabled implicitly.

The provider tries up to two attempts per configured provider path, subject to the shared budget. CrewAI's researcher/critic collaboration uses the same provider boundary and is separately bounded to six adapter calls with low iteration limits. Timeouts and budgets reduce exposure; they do not refund an already accepted provider request.

## Input and storage bounds

Topic3–160 characters; brief10–8,000; source title2–120; source content10–24,000; at most8 source IDs; combined selected source content at most48,000. Request bodies are capped at150,000 bytes. Revision allowance0–3 and approval window1–168 hours. Approval comments are capped at2,000 characters. List endpoints expose bounded pages; event retrieval returns at most500 events after the cursor. Source uploads are plain text only.

Demo creation is rate-limited globally and per source IP. Private-login attempts and control actions also have server limits. Exact enforcement resides in `api.py`/`auth.py`; rate windows are fixed rather than a distributed edge-defense service.

Expired anonymous workspaces become inaccessible immediately. Maintenance is designed to remove their data/checkpoints after a one-hour grace, excluding active work until safe; permanent provisioned workspaces are not automatically deleted. Sessions, access codes, and rate buckets are pruned after expiry. This is application retention, not encrypted erasure or a full privacy policy. Permanent-workspace storage requires an operator retention/backup plan.

## Cloud controls and limits

The SAM template is disabled by default. When enabled it limits concurrency/throttling and lowers execution allowances, but AWS requests, logs, queue traffic, image storage, database operation, and provider calls can still be billable. Configure account-level budgets and alerts, verify quotas/current pricing, and monitor independent database costs before deploying. A budget alert is not necessarily a hard stop. No actual monthly cost has been measured.
