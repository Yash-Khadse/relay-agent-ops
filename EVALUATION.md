# Evaluation

Relay distinguishes workflow-mechanics verification from model-quality evaluation. Deterministic fixture outputs are useful for testing state transitions and approval safety; they are not evidence that a model reasons correctly or that multiple agents outperform a single model.

## Reproducible runner

```powershell
uv run python scripts/evaluate.py --runs 5
```

The default runner creates temporary metadata/checkpoint databases, uses fixture mode, runs a research workflow, records/approves the interrupt, and measures completion/approval-resume timing. It writes `docs/evaluation-results.json`. `--runs` accepts1–20; `--output` selects a different result file. Results are measurements for that machine/run, not a production performance commitment.

To compare a single research provider operation with the bounded CrewAI researcher/critic operation:

```powershell
uv run python scripts/evaluate.py --runs 5 --compare-crew
```

Without `--live` this still uses deterministic output. With `--live`, the runner explicitly permits the configured provider and can incur cost. It requires valid model/credentials and optional CrewAI dependencies for a crew comparison. The comparison checks supported quotes/limitations and reports usage/timing; it is not a blinded quality benchmark. `--compare-crew` exercises research operations rather than full approval workflows, so do not compare its timings as equivalent end-to-end work.

Output includes per-run strategy/mode/success, elapsed seconds, reported model usage, approval-resume timing for full workflows, and supported-quote counts for research comparisons; aggregate success rate/p50/p95 are computed from the current sample. For small samples these percentiles are descriptive only. Dollar savings and quality improvements are not established.

## Capability evidence

The retained `docs/evaluation-results.json` contains an actual local five-run fixture mechanics measurement: five successful research workflows, success rate1.0, median0.5452 seconds, sample p95 (maximum of five)0.6913 seconds. Approval-resume measurements range0.1645–0.2459 seconds. Reported model calls/input/output tokens are all0. These values describe deterministic in-process fixture execution with automated approvals on the delivery machine; they exclude real human review and hosted model latency and establish no AI quality improvement.

| Area | Implemented | Evidence/limit |
| --- | --- | --- |
| Fixture workflow/approval/artifact | Yes | Backend tests and local browser flow |
| Private access-code/RBAC | Yes | Backend tests; optional browser case skipped without a code |
| Checkpoint/recovery/idempotency | Yes | Focused lease/process/replay tests; expanded suite finalization tracked in TESTING |
| Source grounding | Exact quote/source-ID checks | Does not prove all prose claims correct |
| Live providers | Configurable transport/schema boundary | Mocked HTTP tests; live network inference unverified |
| CrewAI | Bounded research collaboration | Real framework + deterministic test LLM; quality uplift unverified |
| MCP | Separate opt-in adapter | Allowlist tests; not connected to graph/UI |
| Docker/PostgreSQL | Compose/images supplied | Docker runtime unavailable during delivery |
| AWS | Conditional SAM/adapters supplied | No credentials/deployment/load test |
| Remote CI | Workflow defined | No observed remote run |

## Quality study still required

Use representative, consented documents and predefine tasks, a single-provider baseline, crew variant, reviewer rubric, failure categories, and spend/time budget. Blind reviewers to strategy and score citation support, unsupported claims, completeness, usefulness, and required edits. Repeat multiple trials with the same model/settings, retain failures, and report uncertainty alongside latency and actual provider usage. Approval duration and model latency should be reported separately. Do not use the fictional bundled samples as evidence of business impact.
