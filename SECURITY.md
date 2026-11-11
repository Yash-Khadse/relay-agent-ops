# Security model

## Dependency audit — 28 October 2026

The locked default Python runtime and production frontend audit returned no known vulnerabilities. Filelock was upgraded to 4.2.4 to address the reported advisories. This is a point-in-time audit, not a guarantee against undiscovered vulnerabilities.

The optional CrewAI extra installs ChromaDB 1.5.9, for which the audit reports PYSEC-2026-311, PYSEC-2026-3814, PYSEC-2026-3815, and PYSEC-2026-3813 with no patched version listed. Relay disables CrewAI memory and never starts a ChromaDB server, but the affected dependency remains installed when this extra is selected. Keep the extra out of public deployments until these advisories have been reviewed or resolved. Default Docker/AWS images do not install it.

CI requires a clean default-runtime audit. The full optional-extra audit is visibly nonblocking and uploads its JSON findings; a passing CI run does not mean the optional dependency set is vulnerability-free. No advisory is silently ignored.

Relay treats source documents, model outputs, and reviewer feedback as untrusted data. Its goal is to confine their effect to validated workflow state and a human-reviewed local artifact. This is a bounded application design, not a claim that prompt injection or all application threats are solved.

## Identity and authorization

- Sessions use random bearer tokens stored as SHA-256 hashes in the database. Browser cookies are HttpOnly, SameSite=Lax, path `/`, and Secure when configured for HTTPS.
- Demo sign-in creates an isolated expiring workspace with a server-assigned owner role. It does not grant access to another workspace.
- Private users are provisioned by an administrator with database access. Single-use, one-hour access codes are hashed at rest and exchanged for a session. Identity, workspace, and role are not accepted from the browser.
- Owner/admin: read/run/approve/manage; operator: read/run; approver: read/approve; viewer: read. Provisioning remains a local CLI; there is no public user-management API or SSO integration.
- Reads/downloads and writes enforce workspace ownership. Foreign resources return404. Mutation permissions are enforced server-side even if a button appears in the frontend.

Access codes are secrets. Do not put them in screenshots, logs, issue bodies, or version control. Revoking a user through the admin CLI removes their sessions/outstanding codes. No password recovery or email identity proofing is implemented.

## Request and approval boundaries

Mutation middleware checks Origin against same-origin/explicit trusted origins and rejects `Sec-Fetch-Site: cross-site`. This complements SameSite cookies; it is not a general bearer-token API design. Public hosting must preserve the intended HTTPS same-origin path. Request-size and strict Pydantic field limits reduce resource abuse. JSON output schemas reject extra fields.

Execution creation and approval decisions require idempotency keys. Reusing a creation key with changed input conflicts. An approval is tied to execution, revision, and exact Markdown hash. Resume must match the recorded approval ID/decision. Finalization rechecks approved status/hash under the execution lock. Rejection, expiry, or cancellation does not authorize finalization. Approval and a resume job commit together; the worker cannot substitute a client-provided draft.

## Model/tool trust

Prompts explicitly mark context as untrusted. Research output must cite selected sources and exact quotations; drafts cannot cite unknown source IDs. Schema/citation checks are useful guards but do not prove factual completeness or semantic correctness. Humans remain responsible for reviewing outputs.

Agents do not receive shell execution or arbitrary filesystem access. Registered tools have role scopes; final export requires approval. Support response approval updates a local ticket record, never sends a customer message. The experimental MCP adapter requires explicit server/tool/workspace allowlists, allowed roles, HTTPS, public-address checks, bounded input/output, server-side credentials, and no redirects. It is not wired into workflows/UI and should not be described as a production connector. DNS/address validation alone does not replace a controlled egress layer.

## Data and operations

Source snapshots, drafts, comments, events, artifacts, tickets, and checkpoints can contain sensitive user content. Local SQLite is not application-encrypted. Protect workstation access, use encrypted disks/backups, configure PostgreSQL SSL and least-privilege credentials, and avoid real confidential data in anonymous demos. Artifacts download as attachments with a restrictive response CSP; the UI renders draft text rather than executing Markdown HTML.

Worker errors deliberately persist type-level diagnostics rather than raw SDK exception strings that can contain prompts/secrets. JSON logging/event fields and OpenTelemetry instrumentation still require operator review before adding exporters. No external trace exporter is enabled by default. Secrets are not returned by `/api/settings`.

The web container includes a CSP and security headers. TLS termination, dependency patching, secret rotation, external rate limiting, audit-log retention, backup restoration, database migrations, and production incident response remain deployment responsibilities. Test cookie/origin behavior at the final host. Do not interpret `NoEcho` SAM parameters as a substitute for a managed secret store.

For a suspected exposure: disable live inference/public demo creation, revoke affected sessions/codes, rotate provider/database credentials as appropriate, preserve relevant diagnostics, inspect scoped records, and restore only from trusted backups. No public security contact has been configured in this repository; report privately through the repository owner's established contact channel.
