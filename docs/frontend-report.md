# Relay frontend implementation

## Delivered

`apps/web` is a Vite / React 19 / strict TypeScript client with TanStack Query, XYFlow, and Lucide icons. A responsive token-based stylesheet provides dark and light themes, persistent appearance preferences, accessible native controls, reduced-motion support, narrow-screen navigation, and loading, error, and empty states.

The landing page supports an isolated demo session and administrator-issued workspace access-code login (`POST /api/auth/login`, `{code}`; 32–128 characters). No client-selected user identity or role is submitted. Cookies are sent on every authenticated request, 401 responses return the app to sign-in, and logout clears cached workspace data.

Implemented views: overview; workflow templates and backend-defined topology; controlled run configuration; execution search/status filters; execution details and deduplicated incremental event polling; pause/resume/cancel/retry; approval draft/risk review with approve/reject/revise and comments; artifact downloads using authenticated fetch/blob; agent registry and output schemas; analytics using API metrics; and runtime settings.

Every populated list and metric comes from the API. Fixture mode is explicitly labeled “Deterministic integration demo” with a no-live-AI explanation. Source material can be selected or uploaded as bounded plain text; bundled sources are labeled fictional. Form bounds match the backend: topic 3–160, brief 10–8,000, source title 2–120, source content 10–24,000, at most eight selected sources, revisions 0–3, approval window 1–168 hours. Mutations disable while pending and carry idempotency keys.

## Verification

- `pnpm typecheck`: passed after access-code login changes.
- `pnpm test`: passed four meaningful tests covering credentialed/idempotent requests, preserved authentication errors, empty responses, and overlapping event deduplication.
- Final production build after login changes passed (490 KB JavaScript / 152.84 KB gzip; 35 KB CSS).
- Playwright Chromium installed. Integration spec covers demo → run → approval → completed artifact download; mobile spec checks navigation, horizontal overflow, login constraints, and persistent light theme. Screenshots are emitted into `apps/web/test-results`.
- First real-browser integration attempt launched the UI successfully but could not sign in because API port 8000 was not listening (`ECONNREFUSED`). This is an environment dependency, not a passing end-to-end result. After backend startup, the full workflow browser test passed, including authenticated artifact download. The mobile navigation / horizontal-overflow / light-theme test also passed. Result: 2 passed, 1 optional access-code test skipped (no provisioned test code supplied). Desktop overview and mobile light-mode screenshots were visually inspected; layout, contrast, spacing, and responsive navigation are coherent.

## Running

From `apps/web`: `pnpm install`, `pnpm dev` (port 5173), `pnpm build`, `pnpm test`, and `pnpm test:e2e`. The Vite development proxy forwards `/api` to `127.0.0.1:8000`; end-to-end execution also needs the API and workflow worker. `RELAY_WEB_URL` can override the browser test target. Set `RELAY_TEST_ACCESS_CODE` to an administrator-provisioned code to additionally exercise actual access-code authentication.

## Limits

Server configuration is displayed read-only because the contract exposes no settings mutation. Workflow editing is controlled configuration rather than arbitrary topology mutation. The current client uses in-workspace navigation state rather than deep-link routing. Google Fonts are progressive enhancement with local sans-serif fallbacks.
