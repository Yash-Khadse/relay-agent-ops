# Deployment and operations

The delivered system runs locally. Docker Compose and AWS SAM files are provided as deployment assets; no cloud deployment, production hardening certification, or remote CI success is claimed.

## Container development

With Docker Engine/Compose running:

```powershell
docker compose config --quiet
docker compose up --build
```

Compose defines PostgreSQL 17, API, worker, and an unprivileged nginx frontend on http://localhost:8080. The API binds host loopback port 8000. PostgreSQL health gates API startup; API health gates web/worker startup. A named volume retains PostgreSQL data. The embedded database password is for local development only. Supply real secrets and appropriate network restrictions for any other environment.

The API image installs locked non-development dependencies without the Crew extra. Enabling CrewAI in that image requires deliberately changing the image dependency installation. The frontend image builds with Node 24/pnpm10.24 and serves static assets via nginx. These images were not built/run in the delivery environment because Docker was not running.

## Public browser hosting

Serve the web app and `/api/*` behind the **same HTTPS origin**. The client hardcodes relative `/api`; it has no configurable cross-origin API base. nginx's supplied location proxies `/api/` to the API and falls back to `index.html` for static-app routes. In a different platform, implement equivalent reverse-proxy routing. CORS by itself does not make a cross-site `SameSite=Lax` session cookie a supported design.

Set `RELAY_COOKIE_SECURE=true`, configure exact trusted origins, keep secrets server-side, and decide whether anonymous demo creation should remain enabled. HTTPS termination, DNS, certificates, private database connectivity, secret management, backups, and monitoring must be supplied by the deployment environment. The repository's nginx CSP blocks remote Google Fonts, so local font fallbacks apply in the container.

Use durable PostgreSQL for both metadata and checkpoints in shared/multi-instance environments. Do not put SQLite on ephemeral/serverless storage. Database table creation is automatic; there is no migration framework. Back up and test restoration of both stores before deploying schema changes. Deploy API/worker graph versions together; the worker rejects unsupported graph versions.

## Operational checks

1. Request `/api/health` and confirm metadata database connectivity.
2. Confirm worker startup and that a newly queued fixture execution progresses.
3. Run the isolated demo smoke test from [TESTING.md](TESTING.md).
4. Verify approval decisions, cookie flags, origin rejection, and artifact downloads at the actual public origin.
5. Review execution events, dead jobs, expired approvals, usage limits, database growth, and provider errors.

The health endpoint does not verify checkpoint availability, provider access, or worker liveness. Logs are JSON on the worker with execution/error identifiers; events persist operational history. OpenTelemetry spans are instrumented but no exporter/collector is configured by default.

For a rolling change, prevent new work, allow active work to reach a safe checkpoint, back up persistence, and update API and worker together. Pending approvals remain stored. Restart workers to reclaim expired job leases; preserve checkpoint state. Do not manually mark approvals approved or overwrite hashes to repair a run.

## AWS

See [AWS_ARCHITECTURE.md](AWS_ARCHITECTURE.md). The SAM template defaults to no enabled resources. Its Lambda image bundles and serves the React app at the API origin root. It does not provision PostgreSQL, a CDN/custom domain, managed secrets, an application identity provider, or a complete production monitoring/budget stack. Review and supply those before enabling resources. Cloud execution has not been verified.
