# Testing

Run tests from the repository root with fixture configuration and temporary databases. Do not aim destructive/recovery tests at a production database.

```powershell
uv sync --frozen --extra crew
uv run pytest -q
uv run pytest --cov=relay --cov-report=term-missing
uv run ruff check apps/api tests scripts
uv run ruff format --check apps/api tests scripts
uv run mypy apps/api/relay
uv build
```

`./scripts/dev.ps1 test` selects the installed runtime and a unique repository-local pytest temporary directory. The delivery sandbox used `.venv-runtime`; normal development uses `uv run`/`.venv`.

## Coverage intent

Backend tests cover all three complete fixture workflows, artifact/approval consistency, rejection, revisions, approval expiry, pause/resume/cancellation, idempotency/concurrent decisions, expired lease recovery, event cursor replay, cross-workspace isolation, role enforcement, request/cookie bounds, tool scope, unsupported quotations, and injected documents remaining data. Additional tests cover one-time access codes, stale outbox dispatch, provider schema validation/retries/budget reservation, actual CrewAI orchestration around a deterministic test LLM, real process-exit recovery, repeated finalization protection, expired demo cleanup, and MCP allowlist/private-address rejection.

Provider HTTP interactions in unit tests are mocked. A test using the real CrewAI framework with deterministic LLM output is not a test of live model quality or provider connectivity. Process-recovery tests prove the exercised interruption case, not every possible distributed crash interleaving.

## Frontend

```powershell
pnpm.cmd --dir apps/web install --frozen-lockfile
pnpm.cmd --dir apps/web typecheck
pnpm.cmd --dir apps/web test
pnpm.cmd --dir apps/web build
pnpm.cmd --dir apps/web exec playwright install chromium
```

Run API and worker separately, then:

```powershell
pnpm.cmd --dir apps/web test:e2e
```

Playwright starts/reuses Vite. Its main test creates an isolated demo workspace, starts research, approves it, observes completion, and downloads the Markdown artifact. A mobile test checks landing/login constraints, navigation, horizontal overflow, and light theme. An optional access-code test runs when `RELAY_TEST_ACCESS_CODE` holds an administrator-issued unconsumed code; the code is consumed by the test. `RELAY_WEB_URL` overrides the target. Traces on failure and screenshots are written under `apps/web/test-results`.

Local frontend evidence: four unit tests, type checking, build, and two Chromium tests passed. One access-code browser test was skipped without a provisioned code. Desktop/mobile screenshots were visually inspected. On 28 October 2026 the full backend suite passed 28 tests in 42.32 seconds with 25 third-party deprecation warnings. This included a fresh PostgreSQL 18 database: checkpoint initialization/resume, concurrent approvals, refreshed row locks, and retention cleanup of 16 executions. Mypy passed 17 source files; Ruff lint/format checks passed. No coverage percentage is invented.

To include the PostgreSQL regression, set `RELAY_TEST_POSTGRES_URL` to a dedicated test database before running pytest. Never point this test at production. Without this variable the PostgreSQL test is skipped. See [docs/verification.md](docs/verification.md) for final audit/build evidence.

## API smoke and evaluation

```powershell
uv run python scripts/smoke.py http://localhost:8000
uv run python scripts/evaluate.py --runs 5
```

The smoke script deliberately approves a single isolated demo execution. Do not treat it as a human judgment test. The evaluation script uses temporary storage and defaults to fixture mechanics; see [EVALUATION.md](EVALUATION.md).

## CI definition versus execution

`.github/workflows/ci.yml` defines backend lint/format/type/tests/coverage/build/dependency-audit, frontend type/tests/build/dependency-audit, PostgreSQL regression/browser integration, and SAM lint/Compose config checks. The default runtime audit is required; the optional CrewAI audit reports known advisories without blocking CI (see SECURITY.md). Artifacts include coverage, the optional audit, frontend build, and browser diagnostics. Remote CI has not been executed during delivery. Local cfn-lint validation of SAM and `docker compose config --quiet` passed; Docker image execution and AWS deployment remain unverified.
