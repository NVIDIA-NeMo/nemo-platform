# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the per-session experiment endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

ATIF_INGEST = "/apis/intake/v2/workspaces/default/ingest/atif"
EXPERIMENTS = "/apis/intake/v2/workspaces/default/experiments"


def test_list_experiment_sessions_returns_joined_session_rows(client: TestClient) -> None:
    experiment_name = "sessions-exp"
    created = client.post(
        EXPERIMENTS,
        json={
            "name": experiment_name,
            "agent_name": "sample-agent",
            "agent_version": "1.0.0",
            "dataset_name": "sessions-dataset",
            "dataset_version": "v1",
        },
    )
    assert created.status_code == 201, created.text

    started_at = datetime.now(timezone.utc).replace(microsecond=0)
    seeds = [
        ("case-a", 1.0, 0.05, 1000, 100, 10, 0),
        ("case-b", 0.5, 0.10, 2000, 200, 20, 5),
        ("case-c", 0.0, 0.20, 3000, 300, 30, 10),
    ]
    for index, (
        test_case_id,
        score,
        cost_usd,
        latency_ms,
        prompt_tokens,
        completion_tokens,
        offset_seconds,
    ) in enumerate(seeds):
        response = client.post(
            ATIF_INGEST,
            json=_atif_body(
                started_at=started_at,
                experiment_name=experiment_name,
                test_case_id=test_case_id,
                score=score,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                offset_seconds=offset_seconds,
                run_id=f"run-{index}",
            ),
        )
        assert response.status_code == 201, response.text

    listed = client.get(f"{EXPERIMENTS}/{experiment_name}/sessions")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["pagination"]["total_results"] == 3
    assert len(body["data"]) == 3

    rows_by_case = {row["test_case_id"]: row for row in body["data"]}
    assert set(rows_by_case) == {"case-a", "case-b", "case-c"}

    case_a = rows_by_case["case-a"]
    assert case_a["experiment_name"] == experiment_name
    assert case_a["session_id"]
    assert case_a["trace_id"]
    assert case_a["root_span_id"]
    assert case_a["latency_ms"] == pytest.approx(1000.0)
    assert case_a["input_tokens"] == 100
    assert case_a["output_tokens"] == 10
    assert case_a["cost_total_usd"] == pytest.approx(0.05)
    assert case_a["evaluator_scores"] == {"harbor.verifier": pytest.approx(1.0)}
    assert case_a["status"] in {"success", "unknown"}


def test_list_experiment_sessions_filter_by_test_case(client: TestClient) -> None:
    experiment_name = "sessions-filter-exp"
    created = client.post(
        EXPERIMENTS,
        json={
            "name": experiment_name,
            "agent_name": "sample-agent",
            "agent_version": "1.0.0",
            "dataset_name": "sessions-dataset",
            "dataset_version": "v1",
        },
    )
    assert created.status_code == 201, created.text

    started_at = datetime.now(timezone.utc).replace(microsecond=0)
    for index, test_case_id in enumerate(["alpha", "beta"]):
        response = client.post(
            ATIF_INGEST,
            json=_atif_body(
                started_at=started_at,
                experiment_name=experiment_name,
                test_case_id=test_case_id,
                score=1.0,
                cost_usd=0.01,
                latency_ms=100,
                prompt_tokens=50,
                completion_tokens=5,
                offset_seconds=index * 5,
                run_id=f"run-{index}",
            ),
        )
        assert response.status_code == 201, response.text

    filtered = client.get(
        f"{EXPERIMENTS}/{experiment_name}/sessions",
        params={"test_case_id": "alpha"},
    )
    assert filtered.status_code == 200, filtered.text
    body = filtered.json()
    assert body["pagination"]["total_results"] == 1
    assert len(body["data"]) == 1
    assert body["data"][0]["test_case_id"] == "alpha"


def test_list_experiment_sessions_returns_404_for_unknown_experiment(client: TestClient) -> None:
    response = client.get(f"{EXPERIMENTS}/does-not-exist/sessions")
    assert response.status_code == 404, response.text


def _atif_body(
    *,
    started_at: datetime,
    experiment_name: str,
    test_case_id: str,
    score: float,
    cost_usd: float,
    latency_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
    offset_seconds: int,
    run_id: str,
) -> dict[str, Any]:
    session_started_at = started_at + timedelta(seconds=offset_seconds)
    finished_at = session_started_at + timedelta(milliseconds=latency_ms)
    session_id = f"{experiment_name}-{run_id}-{test_case_id}"
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": session_id,
        "experiment_context": {
            "experiment_id": experiment_name,
            "test_case_id": test_case_id,
        },
        "extra": {
            "task_id": test_case_id,
            "task_name": test_case_id,
            "verifier": {
                "started_at": _iso(session_started_at),
                "finished_at": _iso(finished_at),
            },
            "verifier_result": {"rewards": {"reward": score}},
        },
        "agent": {
            "name": "sample-agent",
            "version": "1.0.0",
            "model_name": "provider/sample-model",
        },
        "steps": [
            {
                "step_id": 1,
                "timestamp": _iso(session_started_at),
                "source": "agent",
                "model_name": "provider/sample-model",
                "message": f"solved {test_case_id}",
                "metrics": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost_usd": cost_usd,
                },
            }
        ],
    }


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
