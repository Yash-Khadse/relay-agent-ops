# Frontend contract

All endpoints under `/api`. Cookie authentication (`credentials: include`). JSON errors `{detail: string}`. Lists return arrays, optional `limit=50&offset=0`. IDs strings, timestamps ISO UTC. API defaults http://localhost:8000; Vite proxies `/api`.

- POST `/auth/demo` -> user `{id,workspace_id,name,role,expires_at}` sets HttpOnly session cookie. POST `/auth/logout`. GET `/auth/me`.
- GET `/settings` -> `{provider,model,configured,crew_enabled,demo_mode,max_executions,version}`. No secrets.
- GET `/workflow-templates` -> `[{id,name,description,version,sample:{topic,brief},nodes:[{id,label,agent,type}],edges:[{source,target,label?}]}]`. IDs `research`, `support`, `content`.
- POST `/executions`, body `{template_id,topic,brief,source_ids?:string[],config?:{max_revisions?:number,approval_hours?:number,crew_enabled?:boolean}}`, header `Idempotency-Key` UUID -> execution.
- GET `/executions?search=&status=` -> execution[]. GET `/executions/{id}` -> execution plus `approvals`, `artifacts`, `ticket`.
- Execution `{id,workspace_id,template_id,version,topic,brief,status,current_node,created_at,updated_at,completed_at,error,revision,mode}`. Status lowercase `queued,running,waiting_approval,paused,completed,failed,cancelled,rejected,timed_out`. `mode`: `fixture` or provider name.
- POST `/executions/{id}/{cancel,retry,pause,resume}` -> execution.
- GET `/executions/{id}/events?after=0` -> `[{id,execution_id,kind,node,agent,message,data,created_at}]`. `id` monotonically increasing; fetch later cursor, deduplicate.
- GET `/approvals` -> `[{id,execution_id,topic,status,revision,draft,risk,created_at,expires_at,decision,comment}]`. Pending `status=pending`. POST `/approvals/{id}/decide` body `{decision:'approve'|'reject'|'revise',comment:string}`; idempotency header required -> approval.
- GET `/artifacts` -> `[{id,execution_id,title,content_type,content_hash,created_at,approved,producer,version}]`. GET `/artifacts/{id}/download` -> attachment Markdown (authenticated fetch/blob).
- GET `/agents` -> `[{id,name,role,description,tools:string[],max_iterations,output_schema}]`.
- GET `/metrics` -> `{total,completed,failed,pending_approvals,average_duration_seconds,llm_calls,input_tokens,output_tokens,estimated_cost_usd:number|null,by_template:[{template_id,total,completed}],daily:[{date,total,completed,failed}],node_latency:[{node,average_ms}],retries}`.
- GET `/sources` -> `[{id,title,content,kind}]`. POST `/sources` `{title,content}` bounded plain text. Defaults bundled fictional sample sources clearly labeled.
- GET `/health` public.

No fabricated populated data in UI. Fixture mode is labeled deterministic integration demo, not live AI. Crew unavailable without explicit configuration. Topology reflects actual backend graph; template editing is controlled configuration only.
