"""Measure real workflow mechanics or compare provider research against a bounded crew.

No quality improvements are claimed: results contain timing, usage and citation checks only.
"""

import argparse
import json
import math
import statistics
import tempfile
import time
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from relay.api import create_app
from relay.config import Settings
from relay.contracts import ResearchResult
from relay.crew import research_crew
from relay.db import Database
from relay.providers import Provider, measured_usage
from relay.templates import BUNDLED_SOURCES
from relay.tools import validate_evidence
from relay.worker import Worker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--live", action="store_true", help="Explicitly permit configured provider calls"
    )
    parser.add_argument("--compare-crew", action="store_true")
    parser.add_argument("--output", default="docs/evaluation-results.json")
    args = parser.parse_args()
    if not 1 <= args.runs <= 20:
        parser.error("runs must be 1..20")
    Path("data").mkdir(exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(dir="data") as directory:
        root = Path(directory).resolve()
        overrides = {
            "database_url": f"sqlite:///{root / 'metadata.db'}",
            "checkpoint_url": f"sqlite:///{root / 'checkpoint.db'}",
            "data_dir": root,
            "max_executions": 50,
            "public_live_enabled": True,
        }
        if not args.live:
            overrides["provider"] = "fixture"
        settings = Settings(**overrides)
        db = Database(settings.database_url)
        with TestClient(create_app(settings, db)) as client:
            client.post("/api/auth/demo").raise_for_status()
            worker = Worker(settings, db)
            for _ in range(args.runs):
                for strategy in ["single", "crew"] if args.compare_crew else ["workflow"]:
                    response = client.post(
                        "/api/executions",
                        headers={"Idempotency-Key": str(uuid.uuid4())},
                        json={
                            "template_id": "research",
                            "topic": "Compare sample support platforms",
                            "brief": "Compare the supplied fictional platforms and document missing evidence.",
                        },
                    )
                    response.raise_for_status()
                    id = response.json()["id"]
                    started = time.perf_counter()
                    row = {"strategy": strategy, "mode": settings.provider, "success": False}
                    try:
                        if strategy == "workflow":
                            worker.tick()
                            run = client.get(f"/api/executions/{id}").json()
                            if run["status"] != "waiting_approval":
                                raise RuntimeError("Did not reach approval")
                            approval = run["approvals"][-1]
                            resumed = time.perf_counter()
                            client.post(
                                f"/api/approvals/{approval['id']}/decide",
                                headers={"Idempotency-Key": str(uuid.uuid4())},
                                json={"decision": "approve"},
                            ).raise_for_status()
                            worker.tick()
                            run = client.get(f"/api/executions/{id}").json()
                            row.update(
                                success=run["status"] == "completed",
                                approval_resume_seconds=time.perf_counter() - resumed,
                            )
                        else:
                            configured = settings.model_copy(
                                update={
                                    "crew_enabled": True,
                                    "crew_model": settings.crew_model
                                    or settings.model
                                    or "fixture",
                                }
                            )
                            provider = Provider(configured, db, id)
                            context = {
                                "topic": "Compare platforms",
                                "brief": "Compare grounded evidence",
                                "sources": BUNDLED_SOURCES,
                            }
                            result = (
                                research_crew(provider, context)
                                if strategy == "crew"
                                else provider.generate(ResearchResult, context, "research")
                            )
                            validate_evidence(result, BUNDLED_SOURCES)
                            row.update(
                                success=True,
                                supported_quotes=len(result.evidence),
                                limitations=len(result.limitations),
                            )
                        calls, tokens_in, tokens_out = measured_usage(db, [id])
                        row.update(
                            reported_model_calls=calls,
                            input_tokens=tokens_in,
                            output_tokens=tokens_out,
                        )
                    except Exception as exc:
                        row["error_type"] = type(exc).__name__
                    row["seconds"] = time.perf_counter() - started
                    rows.append(row)
        db.engine.dispose()
    durations = sorted(r["seconds"] for r in rows)
    output = {
        "label": "Live provider evaluation"
        if args.live
        else "Deterministic mechanics benchmark; not a model quality benchmark",
        "runs": rows,
        "success_rate": sum(r["success"] for r in rows) / len(rows),
        "p50_seconds": statistics.median(durations),
        "p95_seconds": durations[math.ceil(len(durations) * 0.95) - 1],
        "quality_improvement": "Not established; requires blinded human evaluation on representative real documents",
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved {len(rows)} measured runs to {args.output}")


if __name__ == "__main__":
    main()
