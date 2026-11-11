# Local setup

## Supported development path

Use PowerShell from the repository root. Install Python 3.13, uv, Node 24, and pnpm 10.24.0 using your normal workstation package tooling. Python metadata accepts versions >=3.12,<3.14. A GPU and cloud account are unnecessary for fixture mode.

```powershell
Copy-Item .env.example .env
uv sync --frozen
pnpm.cmd --dir apps/web install --frozen-lockfile
```

Use `uv sync --frozen --extra crew` to install optional CrewAI for its integration/tests after reviewing the dependency findings in [SECURITY.md](SECURITY.md). Normal uv synchronization creates `.venv`. The delivery sandbox used `.venv-runtime`; `scripts/dev.ps1` detects it first, then `.venv`. This alternate folder is an environment workaround, not a required installation convention.

Run in three terminals:

```powershell
./scripts/dev.ps1 api
```

```powershell
./scripts/dev.ps1 worker
```

```powershell
./scripts/dev.ps1 web
```

The API initializes its metadata tables at startup. The worker opens/setup its LangGraph checkpoint store. Relative SQLite URLs resolve from the repository root; always start services there. The defaults create `data/relay.db` and `data/checkpoints.db`. Both are needed for recovery. Do not commit either database or `.env`.

## First run

At http://localhost:5173 choose **Try demo workspace**. Choose a workflow and review the fictional bundled sources. Provide a topic/brief, run, then approve or request a revision. A completed execution exposes a Markdown download. The fixture revision records the feedback; it does not perform a semantic rewrite.

Without an explicit source selection, the API uses its bundled sources. Source uploads accept text; this is not a PDF parser, website crawler, or vector-search pipeline. The workflow snapshots selected source content at creation.

## Private workspaces and access codes

Provisioning is a local administrative command requiring database access:

```powershell
uv run python -m relay.admin create-user --name "Workspace owner" --role owner
```

Record the returned user/workspace IDs securely and deliver the access code privately. The code is single-use and expires after one hour. Open **Sign in to your workspace** on the landing page and paste it. The client submits only the code; identity, role, and workspace are assigned on the server.

To add a user to an existing permanent workspace, pass `--workspace` with the ID returned by provisioning. To issue a replacement code or revoke sessions, pass the provisioned user ID to:

```powershell
uv run python -m relay.admin issue-code --user $RelayUserId
uv run python -m relay.admin revoke --user $RelayUserId
```

Here `$RelayUserId` is the real ID you retained from provisioning. Revocation deletes outstanding codes and login sessions. It does not delete the user or workspace. Available roles: owner/admin (read, run, approve, manage), operator (read/run), approver (read/approve), viewer (read). There is no public registration or identity-provider integration.

## Optional live inference

Set `RELAY_PROVIDER` to `ollama`, `groq`, or `gemini`, select an actual model available to that provider using `RELAY_MODEL`, and set `RELAY_API_KEY` for hosted providers. Ollama uses `RELAY_OLLAMA_URL` (default `http://localhost:11434/v1`) and requires the selected model to be available locally. Verify provider account/model access outside Relay before running. Live calls have not been verified in this delivery.

Private provisioned workspaces can use configured live inference. Expiring demo workspaces cannot do so unless the administrator explicitly sets `RELAY_PUBLIC_LIVE_ENABLED=true`. Keep that switch false for an unaudited public demo. Fallback is enabled only when both fallback provider and model are configured; it also requires suitable credentials.

CrewAI additionally needs `uv sync --extra crew`, `RELAY_CREW_ENABLED=true`, `RELAY_CREW_MODEL`, and per-execution `config.crew_enabled=true`. The bounded adapter uses the configured main provider endpoint/key and overrides its model with `crew_model`. CrewAI does not own workflow routing. The current UI does not expose a Crew opt-in checkbox; use the API for that advanced configuration.

## PostgreSQL

Use both metadata and checkpoint databases consistently. Metadata uses a SQLAlchemy psycopg URL; checkpoint persistence uses a psycopg connection URL. `.env.example` contains commented URL forms. Containers provide a PostgreSQL development option; see [DEPLOYMENT.md](DEPLOYMENT.md). No schema migration tool is included: `create_all` creates missing tables but does not upgrade existing table definitions.
