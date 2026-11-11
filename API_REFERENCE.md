# API reference

FastAPI exposes `/docs` and `/openapi.json` when running. All application routes below begin `/api`. IDs are strings except monotonic event IDs; timestamps serialize to ISO UTC. Lists return arrays. The API expects a `relay_session` cookie; browser requests include credentials. No bearer-header authentication is implemented.

## Authentication

| Method/path | Input | Result |
| --- | --- | --- |
| `GET /health` | None; public | Database liveness/version |
| `POST /auth/demo` | No required body | Isolated expiring workspace/user and session cookie; can be disabled |
| `POST /auth/login` | `{ "code": "administrator-issued single-use code" }` | Assigned user/workspace/role, expires_at and session cookie |
| `GET /auth/me` | Session | Current user/workspace/role/expiry |
| `POST /auth/logout` | Session if present | Revokes current session and deletes cookie |

Login code length32–128; invalid, consumed, or expired codes fail. Provisioning uses `python -m relay.admin`, not an HTTP user-creation endpoint. Successful login does not let callers select their own role or workspace.

## Catalog/configuration

Authenticated GETs: `/workflow-templates`, `/agents`, `/sources`, `/settings`. Templates are `research`, `support`, `content`; responses include sample topic/brief, graph nodes/edges, description, version. Agents describe name/role/tools/iteration limits/output schema. Sources include bundled fictional samples and workspace-owned text. Settings expose provider/model/configured/crew_enabled/demo_mode/max_executions/version without secrets. Settings/topology are not mutable through this API.

`POST /sources` requires run permission and `{title,content}`. Title2–120 characters; content10–24,000; response201 source. Unknown fields are rejected.

## Executions

`POST /executions` requires run permission plus an `Idempotency-Key` header (8–128 characters; UUID recommended). It returns202 with the execution; job processing is asynchronous.

```json
{
  "template_id": "research",
  "topic": "Compare the supplied platforms",
  "brief": "Compare capabilities supported by the supplied fictional sources and identify missing evidence.",
  "source_ids": [],
  "config": {"max_revisions": 2, "approval_hours": 24, "crew_enabled": false}
}
```

Topic3–160, brief10–8,000, at most8 source IDs and48,000 combined source characters. Empty/omitted source IDs use bundled samples. Config accepts revisions0–3, approval hours1–168. Crew opt-in requires enabled live configuration. Source snapshots are stored with the run. Same workspace/key/input returns the prior run; changed input/key reuse returns409. Workspace/global creation allowances can return429. Live anonymous demos are403 unless explicitly allowed.

| Method/path | Behavior |
| --- | --- |
| `GET /executions?search=&status=&limit=50&offset=0` | Workspace runs; bounded paging (limit1–100) |
| `GET /executions/{id}` | Run plus approvals/artifacts/local ticket |
| `GET /executions/{id}/events?after=0` | Up to500 ordered events with ID greater than cursor |
| `POST /executions/{id}/pause` | Queued/running/paused; running pause takes effect at a node boundary |
| `POST /executions/{id}/resume` | Only paused; queues checkpoint-aware work |
| `POST /executions/{id}/retry` | Only failed; requires safe checkpoint if work previously started |
| `POST /executions/{id}/cancel` | Cancels unfinished work; already-cancelled is safe to repeat |

Control operations require run permission and reject incompatible states409. Retry/resume calls are server-rate-limited. They do not use the creation idempotency contract. Once approved finalization has committed an artifact, cancel is refused. Status values: queued, running, waiting_approval, paused, completed, failed, cancelled, rejected, timed_out. `mode` names fixture/provider. `failed` is recoverable by explicit retry; other finished outcomes are not offered retry.

Events contain `id,execution_id,kind,node,agent,message,data,created_at`. Advance cursors by the highest returned ID, not array length; deduplicate overlap on reconnect. Events are operational traces, not private model reasoning. This is HTTP polling, not SSE/WebSocket.

## Approvals

`GET /approvals?limit=50&offset=0` returns workspace approvals. Pending items contain execution/topic/revision/draft/risk/expiry. `POST /approvals/{id}/decide` requires approve permission and idempotency key:

```json
{"decision":"revise","comment":"Clarify which comparison claims lack evidence."}
```

Decision is approve/reject/revise; comment up to2,000 characters. Revise requires a nonblank comment and remaining revision allowance. A decision commits recorded authorization and a resume job atomically. Repeating the same key/decision/comment returns the prior decision; incompatible duplicate, expired, cancelled, or nonpending approvals return409. Human approval authorizes the stored exact draft hash, not a client replacement payload.

## Artifacts and metrics

`GET /artifacts?limit=50&offset=0` returns metadata, excluding content. `GET /artifacts/{id}/download` returns authenticated Markdown attachment with restrictive CSP. Artifact metadata includes content hash, producer, version, approved flag, title, creation time, and execution ID.

`GET /metrics` returns total/completed/failed/pending_approvals/average_duration_seconds, measured successful model calls/input/output tokens, estimated_cost_usd, by_template, daily, node_latency, and retries. Fixture cost is0; live estimated dollar cost is unavailable (`null`). Usage reservations are conservative enforcement counters and are not the same as provider-reported usage metrics.

## Errors and bounds

Application HTTP errors generally return `{detail: string}`. FastAPI schema-validation422 errors can instead contain a structured `detail` array; consumers should normalize it for display. Common codes:401 session required/expired;403 role/origin/live-demo restriction;404 foreign or absent resource;409 state/idempotency conflict;422 invalid input/revision/config;429 allowance/rate limit;413 request body over150,000 bytes. Do not depend on human-readable error text as an error code.
