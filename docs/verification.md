# Delivery verification — 28 October 2026

The repository is runnable locally without provider credentials in explicitly labeled deterministic fixture mode. Environment values, live inference, cloud deployment, and public-demo validation are deferred to configuration.

| Check | Observed result |
| --- | --- |
| Python tests, including dedicated PostgreSQL 18 | 28 passed in 42.32 seconds; 25 dependency deprecation warnings |
| PostgreSQL regression | Fresh checkpoint schema, approval race, resume, row refresh, cleanup of 16 runs passed |
| Ruff lint and format | Passed, 26 Python files formatted |
| Mypy | Passed, 17 source files |
| Frontend unit tests | 4 passed |
| Chromium browser integration | 2 passed; optional access-code test skipped without a code |
| Frontend production build | Passed; JS 489.96 kB, gzip 152.84 kB |
| Python wheel and source build | Passed |
| SAM cfn-lint | Passed after moving PackageType to individual function properties |
| Docker Compose configuration | Passed; container builds/runs not performed |
| Default Python runtime audit | No known vulnerabilities found |
| Frontend production audit | No known vulnerabilities found |
| Optional CrewAI dependency audit | Four known ChromaDB advisories; see SECURITY.md |
| Fixture benchmark | 5/5 completed, median 0.5452 s, p95 0.6913 s; no model-quality claim |

Tests exercise real LangGraph persistence and real CrewAI orchestration with deterministic model output. Provider HTTP unit tests use mocks. No live provider connectivity, model quality, cloud throughput, remote CI, public demo, or AWS cost eligibility result is claimed.

Artifacts: `docs/evaluation-results.json`, browser screenshots under `apps/web/test-results`, local audit JSON under ignored `data`, and packages under ignored `dist`. CI uploads its own coverage/build/browser/audit results when run.

Experimental scope: the administrator-only MCP adapter is not wired into workflow execution. External customer messaging, arbitrary web crawling, SSO, and live external tool actions are not implemented. Approved support responses create local ticket records. See EVALUATION.md for the capability matrix.
