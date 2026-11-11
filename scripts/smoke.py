"""Explicitly run against a chosen demo deployment; creates one isolated test workspace."""

import argparse
import time
import uuid

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="API origin, e.g. http://localhost:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=20) as client:
        client.get("/api/health").raise_for_status()
        client.post("/api/auth/demo").raise_for_status()
        template = client.get("/api/workflow-templates").json()[0]
        response = client.post(
            "/api/executions",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={"template_id": template["id"], **template["sample"]},
        )
        response.raise_for_status()
        id = response.json()["id"]
        deadline = time.monotonic() + 240
        decided = False
        while time.monotonic() < deadline:
            run = client.get(f"/api/executions/{id}").json()
            if run["status"] == "waiting_approval" and not decided:
                approval = run["approvals"][-1]
                result = client.post(
                    f"/api/approvals/{approval['id']}/decide",
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                    json={
                        "decision": "approve",
                        "comment": "Automated smoke test in isolated demo workspace",
                    },
                )
                result.raise_for_status()
                decided = True
            if run["status"] == "completed":
                client.get(
                    f"/api/artifacts/{run['artifacts'][0]['id']}/download"
                ).raise_for_status()
                print(f"PASS: {id} completed; artifact downloadable")
                return
            if run["status"] in {"failed", "cancelled", "timed_out", "rejected"}:
                raise RuntimeError(f"Smoke execution ended {run['status']}")
            time.sleep(2)
        raise TimeoutError("Smoke execution did not finish before deadline")


if __name__ == "__main__":
    main()
