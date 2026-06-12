# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experiment rollup integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

ATIF_INGEST = "/apis/intake/v2/workspaces/default/ingest/atif"
EXPERIMENTS = "/apis/intake/v2/workspaces/default/experiments"
GROUPS = "/apis/intake/v2/workspaces/default/experiment-groups"


def _ensure_group(client: TestClient, name: str = "rollup-test-group") -> str:
    """Create or fetch an ExperimentGroup; returns its id."""
    response = client.post(GROUPS, json={"name": name})
    if response.status_code == 409:
        response = client.get(f"{GROUPS}/{name}")
    response.raise_for_status()
    return response.json()["id"]


def test_experiment_response_hydrates_clickhouse_rollups(client: TestClient) -> None:
    experiment_id = "rollup-exp"
    group_id = _ensure_group(client)
    created = client.post(
        EXPERIMENTS,
        json={
            "name": experiment_id,
            "experiment_group_id": group_id,
            "agent_name": "sample-agent",
            "agent_version": "1.0.0",
            "dataset_name": "rollup-dataset",
            "dataset_version": "v1",
        },
    )
    assert created.status_code == 201, created.text

    rows = [
        ("run-1", "case-1a", 0.4, 0.05, 500),
        ("run-1", "case-1b", 0.8, 0.10, 1500),
        ("run-2", "case-2", 0.8, 0.20, 2000),
        ("run-3", "case-3", 1.0, 0.30, 3000),
    ]
    started_at = datetime.now(timezone.utc).replace(microsecond=0)
    for index, (run_id, test_case_id, score, cost_usd, latency_ms) in enumerate(rows):
        response = client.post(
            ATIF_INGEST,
            json=_atif_body(
                started_at=started_at,
                experiment_id=experiment_id,
                run_id=run_id,
                test_case_id=test_case_id,
                score=score,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                offset_seconds=index * 10,
            ),
        )
        assert response.status_code == 201, response.text

    fetched = client.get(f"{EXPERIMENTS}/{experiment_id}")
    assert fetched.status_code == 200, fetched.text
    experiment = fetched.json()

    assert experiment["run_count"] == 4
    assert experiment["evaluator_names"] == ["harbor.verifier"]
    assert experiment["model_names"] == ["provider/sample-model"]

    score = experiment["aggregate_scores"]["harbor.verifier"]
    assert score["sum"] == pytest.approx(3.0)
    assert score["mean"] == pytest.approx(0.75)
    assert score["median"] == pytest.approx(0.8)
    assert score["p90"] == pytest.approx(1.0)
    assert score["p95"] == pytest.approx(1.0)
    assert score["p99"] == pytest.approx(1.0)
    assert score["count"] == 4

    cost = experiment["cost_usd"]
    assert cost["sum"] == pytest.approx(0.65)
    assert cost["mean"] == pytest.approx(0.1625)
    assert cost["median"] == pytest.approx(0.2)
    assert cost["p90"] == pytest.approx(0.3)
    assert cost["p95"] == pytest.approx(0.3)
    assert cost["p99"] == pytest.approx(0.3)
    assert cost["count"] == 4

    latency = experiment["latency_ms"]
    assert latency["sum"] == pytest.approx(7000.0)
    assert latency["mean"] == pytest.approx(1750.0)
    assert latency["median"] == pytest.approx(2000.0)
    assert latency["p90"] == pytest.approx(3000.0)
    assert latency["p95"] == pytest.approx(3000.0)
    assert latency["p99"] == pytest.approx(3000.0)
    assert latency["count"] == 4

    listed = client.get(EXPERIMENTS)
    assert listed.status_code == 200, listed.text
    listed_experiment = next(item for item in listed.json()["data"] if item["name"] == experiment_id)
    assert listed_experiment["aggregate_scores"]["harbor.verifier"]["mean"] == pytest.approx(0.75)


def test_atif_ingest_rejects_deleted_experiment(client: TestClient) -> None:
    experiment_id = "soft-deleted-exp"
    group_id = _ensure_group(client)
    created = client.post(
        EXPERIMENTS,
        json={
            "name": experiment_id,
            "experiment_group_id": group_id,
            "agent_name": "sample-agent",
            "agent_version": "1.0.0",
            "dataset_name": "rollup-dataset",
            "dataset_version": "v1",
        },
    )
    assert created.status_code == 201, created.text
    deleted = client.delete(f"{EXPERIMENTS}/{experiment_id}")
    assert deleted.status_code == 204, deleted.text

    response = client.post(
        ATIF_INGEST,
        json=_atif_body(
            started_at=datetime.now(timezone.utc).replace(microsecond=0),
            experiment_id=experiment_id,
            run_id="run-1",
            test_case_id="case-1",
            score=1.0,
            cost_usd=0.01,
            latency_ms=100,
            offset_seconds=0,
        ),
    )
    assert response.status_code == 400, response.text
    assert "deleted" in response.json()["detail"].lower()


def test_atif_ingest_rejects_unknown_experiment_context(client: TestClient) -> None:
    response = client.post(
        ATIF_INGEST,
        json=_atif_body(
            started_at=datetime.now(timezone.utc).replace(microsecond=0),
            experiment_id="missing-exp",
            run_id="run-1",
            test_case_id="case-1",
            score=1.0,
            cost_usd=0.01,
            latency_ms=100,
            offset_seconds=0,
        ),
    )

    assert response.status_code == 400, response.text
    assert "must be created before it can be logged" in response.json()["detail"]


def test_deprecated_evaluation_context_hydrates_experiment_rollups(client: TestClient) -> None:
    experiment_id = "legacy-eval-context-exp"
    group_id = _ensure_group(client)
    created = client.post(
        EXPERIMENTS,
        json={
            "name": experiment_id,
            "experiment_group_id": group_id,
            "agent_name": "sample-agent",
            "agent_version": "1.0.0",
            "dataset_name": "rollup-dataset",
            "dataset_version": "v1",
        },
    )
    assert created.status_code == 201, created.text

    response = client.post(
        ATIF_INGEST,
        json={
            **_atif_body(
                started_at=datetime.now(timezone.utc).replace(microsecond=0),
                experiment_id=experiment_id,
                run_id="run-1",
                test_case_id="case-1",
                score=1.0,
                cost_usd=0.01,
                latency_ms=100,
                offset_seconds=0,
            ),
            "experiment_context": None,
            "evaluation_context": {"evaluation_id": experiment_id, "test_case_id": "case-1"},
        },
    )

    assert response.status_code == 201, response.text

    fetched = client.get(f"{EXPERIMENTS}/{experiment_id}")
    assert fetched.status_code == 200, fetched.text
    experiment = fetched.json()
    assert experiment["run_count"] == 1
    assert experiment["aggregate_scores"]["harbor.verifier"]["mean"] == pytest.approx(1.0)


def _atif_body(
    *,
    started_at: datetime,
    experiment_id: str,
    run_id: str,
    test_case_id: str,
    score: float,
    cost_usd: float,
    latency_ms: int,
    offset_seconds: int,
) -> dict[str, Any]:
    session_started_at = started_at + timedelta(seconds=offset_seconds)
    finished_at = session_started_at + timedelta(milliseconds=latency_ms)
    session_id = f"{experiment_id}-{run_id}-{test_case_id}"
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": session_id,
        "experiment_context": {
            "experiment_id": experiment_id,
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
                    "prompt_tokens": 100,
                    "completion_tokens": 10,
                    "cost_usd": cost_usd,
                },
            }
        ],
    }


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
