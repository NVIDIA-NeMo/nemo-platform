#!/usr/bin/env python
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Seed a group of evaluations tailored for testing multi-field sort on the Experiments leaderboard.

Creates one ExperimentGroup with several Evaluations whose rollups are hand-picked so that:
  * some share the same cost (cost_usd.mean) but differ in latency (latency_ms.mean), and
  * some share the same score AND cost, so you can chain a third key.

Each evaluation gets one ATIF session; the session's per-step cost drives cost_usd.mean, the verifier
started/finished window drives latency_ms, and the verifier reward drives the reward score.

Sort demos (in Studio, shift-click for the secondary column, or hit the API directly):
  * cost asc, then latency asc:  echo, alpha, charlie, bravo, foxtrot, delta
      curl '.../evaluations?filter[experiment_group_id]=<id>&sort=cost_usd.mean,latency_ms.mean'
  * score desc, then cost asc:   (alpha|bravo), delta, charlie, foxtrot, echo
      curl '.../evaluations?...&sort=-evaluators.reward.mean,cost_usd.mean'
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_WORKSPACE = "default"
GROUP = "multi-sort-demo-group"
DATASET_NAME = "multi-sort-demo-dataset"
AGENT_NAME = "sample-agent"
AGENT_VERSION = "1.0.0"

# (evaluation name, score, cost_usd, latency_ms). Cost ties within the 0.10 group so latency breaks it.
EVALUATIONS: list[tuple[str, float, float, int]] = [
    ("eval-alpha", 0.90, 0.10, 500),
    ("eval-bravo", 0.90, 0.10, 1500),
    ("eval-charlie", 0.80, 0.10, 900),
    ("eval-delta", 0.90, 0.25, 300),
    ("eval-echo", 0.70, 0.05, 2000),
    ("eval-foxtrot", 0.80, 0.20, 1200),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    _preflight(base_url)

    with httpx.Client(timeout=10.0) as client:
        group_id = _upsert_group(client, base_url, args.workspace)
        print(f"group '{GROUP}' -> {group_id}")
        started_at = datetime.now(timezone.utc).replace(microsecond=0)

        for index, (name, score, cost_usd, latency_ms) in enumerate(EVALUATIONS):
            _upsert_evaluation(client, base_url, args.workspace, name, group_id=group_id)
            response = client.post(
                _intake_url(base_url, args.workspace, "/ingest/atif"),
                json=_atif_body(
                    started_at=started_at,
                    evaluation_id=name,
                    test_case_id=f"{name}-case",
                    score=score,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    offset_seconds=index * 10,
                ),
            )
            response.raise_for_status()

        print("\nseeded rollups (poll until ClickHouse hydrates):")
        for name, score, cost_usd, latency_ms in EVALUATIONS:
            rollup = _wait_for_rollup(client, base_url, args.workspace, name)
            got_cost = (rollup.get("cost_usd") or {}).get("mean")
            got_latency = (rollup.get("latency_ms") or {}).get("mean")
            got_score = (rollup.get("aggregate_scores") or {}).get("reward", {}).get("mean")
            print(
                f"  {name:14s} score={got_score}  cost={got_cost}  latency_ms={got_latency}"
                f"   (wanted score={score} cost={cost_usd} latency={latency_ms})"
            )

        print(f"\nGroup id: {group_id}")
        print("Try:")
        base = _intake_url(base_url, args.workspace, "/evaluations")
        print(f"  {base}?filter[experiment_group_id]={group_id}&sort=cost_usd.mean,latency_ms.mean")
        print(f"  {base}?filter[experiment_group_id]={group_id}&sort=-evaluators.reward.mean,cost_usd.mean")


def _preflight(base_url: str) -> None:
    try:
        httpx.get(_replace_path(base_url, "/openapi.json"), timeout=2.0).raise_for_status()
    except Exception as exc:
        raise SystemExit(f"Cannot reach NeMo Platform at {base_url}: {exc}") from exc


def _upsert_group(client: httpx.Client, base_url: str, workspace: str) -> str:
    # Seed a multi-field default_sort so the group opens pre-sorted by reward desc, then cost asc.
    body = {
        "name": GROUP,
        "description": "Multi-field sort demo group.",
        "default_sort": "-evaluators.reward.mean,cost_usd.mean",
    }
    response = client.post(_intake_url(base_url, workspace, "/experiment-groups"), json=body)
    if response.status_code == 409:
        response = client.get(_intake_url(base_url, workspace, f"/experiment-groups/{GROUP}"))
    response.raise_for_status()
    return response.json()["id"]


def _upsert_evaluation(client: httpx.Client, base_url: str, workspace: str, evaluation: str, *, group_id: str) -> None:
    body = {
        "name": evaluation,
        "dataset_name": DATASET_NAME,
        "dataset_version": "v1",
        "experiment_group_id": group_id,
        "metadata": {"seeded_by": "seed_multi_sort_demo.py"},
    }
    response = client.post(_intake_url(base_url, workspace, "/evaluations"), json=body)
    if response.status_code == 409:
        response = client.put(_intake_url(base_url, workspace, f"/evaluations/{evaluation}"), json=body)
    response.raise_for_status()


def _wait_for_rollup(client: httpx.Client, base_url: str, workspace: str, evaluation: str) -> dict[str, Any]:
    url = _intake_url(base_url, workspace, f"/evaluations/{evaluation}")
    last: httpx.Response | None = None
    for _ in range(20):
        last = client.get(url)
        last.raise_for_status()
        payload = last.json()
        if payload.get("run_count") == 1 and payload.get("latency_ms"):
            return payload
        time.sleep(0.25)
    raise SystemExit(f"Rollup for {evaluation} did not hydrate: {last.text if last else '<none>'}")


def _atif_body(
    *,
    started_at: datetime,
    evaluation_id: str,
    test_case_id: str,
    score: float,
    cost_usd: float,
    latency_ms: int,
    offset_seconds: int,
) -> dict[str, Any]:
    session_started_at = started_at + timedelta(seconds=offset_seconds)
    finished_at = session_started_at + timedelta(milliseconds=latency_ms)
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": f"{evaluation_id}-session",
        "evaluation_context": {"evaluation_id": evaluation_id, "test_case_id": test_case_id},
        "extra": {
            "task_id": test_case_id,
            "task_name": test_case_id,
            # The verifier window drives the trajectory (root span) duration -> rollup latency_ms.
            "verifier": {"started_at": _iso(session_started_at), "finished_at": _iso(finished_at)},
            "verifier_result": {"rewards": {"reward": score}},
        },
        "agent": {"name": AGENT_NAME, "version": AGENT_VERSION, "model_name": "provider/sample-model"},
        "steps": [
            {
                "step_id": 1,
                "timestamp": _iso(session_started_at),
                "source": "agent",
                "model_name": "provider/sample-model",
                "message": f"solved {test_case_id}",
                "metrics": {"prompt_tokens": 100, "completion_tokens": 10, "cost_usd": cost_usd},
            }
        ],
    }


def _intake_url(base_url: str, workspace: str, suffix: str) -> str:
    return f"{base_url}/apis/intake/v2/workspaces/{workspace}{suffix}"


def _replace_path(base_url: str, path: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
