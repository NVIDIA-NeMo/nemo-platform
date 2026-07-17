# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evaluation rollup integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

ATIF_INGEST = "/apis/intake/v2/workspaces/default/ingest/atif"
EVALUATIONS = "/apis/intake/v2/workspaces/default/evaluations"
GROUPS = "/apis/intake/v2/workspaces/default/experiment-groups"


def _ensure_group(client: TestClient, name: str = "rollup-test-group") -> str:
    """Create or fetch an ExperimentGroup; returns its id."""
    response = client.post(GROUPS, json={"name": name})
    if response.status_code == 409:
        response = client.get(f"{GROUPS}/{name}")
    response.raise_for_status()
    return response.json()["id"]


def test_evaluation_response_hydrates_clickhouse_rollups(client: TestClient) -> None:
    evaluation_id = "rollup-exp"
    group_id = _ensure_group(client)
    created = client.post(
        EVALUATIONS,
        json={
            "name": evaluation_id,
            "experiment_group_id": group_id,
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
                evaluation_id=evaluation_id,
                run_id=run_id,
                test_case_id=test_case_id,
                score=score,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                offset_seconds=index * 10,
            ),
        )
        assert response.status_code == 201, response.text

    fetched = client.get(f"{EVALUATIONS}/{evaluation_id}")
    assert fetched.status_code == 200, fetched.text
    evaluation = fetched.json()

    assert evaluation["run_count"] == 4
    assert evaluation["test_case_count"] == 4  # 4 distinct test_case_ids, each run once
    assert evaluation["evaluator_names"] == ["reward"]
    assert evaluation["model_names"] == ["provider/sample-model"]

    score = evaluation["aggregate_scores"]["reward"]
    assert score["sum"] == pytest.approx(3.0)
    assert score["mean"] == pytest.approx(0.75)
    assert score["median"] == pytest.approx(0.8)
    assert score["p90"] == pytest.approx(1.0)
    assert score["p95"] == pytest.approx(1.0)
    assert score["p99"] == pytest.approx(1.0)
    assert score["count"] == 4

    cost = evaluation["cost_usd"]
    assert cost["sum"] == pytest.approx(0.65)
    assert cost["mean"] == pytest.approx(0.1625)
    assert cost["median"] == pytest.approx(0.2)
    assert cost["p90"] == pytest.approx(0.3)
    assert cost["p95"] == pytest.approx(0.3)
    assert cost["p99"] == pytest.approx(0.3)
    assert cost["count"] == 4

    latency = evaluation["latency_ms"]
    assert latency["sum"] == pytest.approx(7000.0)
    assert latency["mean"] == pytest.approx(1750.0)
    assert latency["median"] == pytest.approx(2000.0)
    assert latency["p90"] == pytest.approx(3000.0)
    assert latency["p95"] == pytest.approx(3000.0)
    assert latency["p99"] == pytest.approx(3000.0)
    assert latency["count"] == 4

    listed = client.get(EVALUATIONS)
    assert listed.status_code == 200, listed.text
    listed_evaluation = next(item for item in listed.json()["data"] if item["name"] == evaluation_id)
    assert listed_evaluation["aggregate_scores"]["reward"]["mean"] == pytest.approx(0.75)


def test_evaluation_rollups_aggregate_per_test_case_before_pooling(client: TestClient) -> None:
    # Unbalanced k: test case A has 1 attempt, test case B has 3. Test-case-weighting counts each test case once, so the
    # heavily-retried test case can't dominate. Pooling all 4 attempts would give score mean 0.75; the
    # correct two-level rollup (average per test case, then across test cases) is 0.5.
    evaluation_id = "rollup-k-exp"
    group_id = _ensure_group(client)
    created = client.post(
        EVALUATIONS,
        json={
            "name": evaluation_id,
            "experiment_group_id": group_id,
            "dataset_name": "rollup-dataset",
            "dataset_version": "v1",
        },
    )
    assert created.status_code == 201, created.text

    rows = [
        # (run_id, test_case_id, score, cost_usd, latency_ms)
        ("run-1", "case-a", 0.0, 0.10, 1000),  # test case A: 1 attempt
        ("run-1", "case-b", 1.0, 0.10, 1000),  # test case B: 3 attempts, differing cost/latency
        ("run-2", "case-b", 1.0, 0.20, 2000),
        ("run-3", "case-b", 1.0, 0.30, 3000),
    ]
    started_at = datetime.now(timezone.utc).replace(microsecond=0)
    for index, (run_id, test_case_id, score, cost_usd, latency_ms) in enumerate(rows):
        response = client.post(
            ATIF_INGEST,
            json=_atif_body(
                started_at=started_at,
                evaluation_id=evaluation_id,
                run_id=run_id,
                test_case_id=test_case_id,
                score=score,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                offset_seconds=index * 10,
            ),
        )
        assert response.status_code == 201, response.text

    evaluation = client.get(f"{EVALUATIONS}/{evaluation_id}").json()

    # run_count stays the number of attempts (4); the distributions are over the 2 test cases.
    assert evaluation["run_count"] == 4
    assert evaluation["test_case_count"] == 2  # 2 distinct test cases (case-a, case-b)

    score = evaluation["aggregate_scores"]["reward"]
    assert score["mean"] == pytest.approx(0.5)  # per test case: A=0.0, B=1.0 -> not the pooled 0.75
    assert score["sum"] == pytest.approx(1.0)
    assert score["count"] == 2

    cost = evaluation["cost_usd"]
    # per-test-case cost is avg per attempt: A=0.10, B=avg(0.10, 0.20, 0.30)=0.20 -> mean 0.15 (not sum 0.60)
    assert cost["mean"] == pytest.approx(0.15)
    assert cost["count"] == 2

    latency = evaluation["latency_ms"]
    # per-test-case latency avg per attempt: A=1000, B=avg(1000, 2000, 3000)=2000 -> mean 1500
    assert latency["mean"] == pytest.approx(1500.0)
    assert latency["count"] == 2


def test_evaluation_rollups_exclude_sessions_without_test_case_id(client: TestClient) -> None:
    # Sessions with no test_case_id aren't attributable to a test case, so they're dropped from the
    # test-case-weighted rollup: no scores/cost/latency and test_case_count 0, though run_count still
    # reflects that the runs were ingested.
    evaluation_id = "rollup-no-test-case-exp"
    group_id = _ensure_group(client)
    created = client.post(
        EVALUATIONS,
        json={
            "name": evaluation_id,
            "experiment_group_id": group_id,
            "dataset_name": "rollup-dataset",
            "dataset_version": "v1",
        },
    )
    assert created.status_code == 201, created.text

    rows = [
        ("run-1", "", 0.0, 0.10, 1000),
        ("run-2", "", 1.0, 0.30, 3000),
    ]
    started_at = datetime.now(timezone.utc).replace(microsecond=0)
    for index, (run_id, test_case_id, score, cost_usd, latency_ms) in enumerate(rows):
        response = client.post(
            ATIF_INGEST,
            json=_atif_body(
                started_at=started_at,
                evaluation_id=evaluation_id,
                run_id=run_id,
                test_case_id=test_case_id,
                score=score,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                offset_seconds=index * 10,
            ),
        )
        assert response.status_code == 201, response.text

    evaluation = client.get(f"{EVALUATIONS}/{evaluation_id}").json()
    assert evaluation["run_count"] == 2  # the runs were ingested
    assert evaluation["test_case_count"] == 0  # but none are attributable to a test case
    assert not evaluation.get("aggregate_scores")  # excluded from the test-case-weighted score rollup
    assert evaluation.get("cost_usd") is None
    assert evaluation.get("latency_ms") is None


def test_atif_ingest_rejects_deleted_evaluation(client: TestClient) -> None:
    evaluation_id = "soft-deleted-exp"
    group_id = _ensure_group(client)
    created = client.post(
        EVALUATIONS,
        json={
            "name": evaluation_id,
            "experiment_group_id": group_id,
            "dataset_name": "rollup-dataset",
            "dataset_version": "v1",
        },
    )
    assert created.status_code == 201, created.text
    deleted = client.delete(f"{EVALUATIONS}/{evaluation_id}")
    assert deleted.status_code == 204, deleted.text

    response = client.post(
        ATIF_INGEST,
        json=_atif_body(
            started_at=datetime.now(timezone.utc).replace(microsecond=0),
            evaluation_id=evaluation_id,
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


def test_atif_ingest_rejects_unknown_evaluation_context(client: TestClient) -> None:
    response = client.post(
        ATIF_INGEST,
        json=_atif_body(
            started_at=datetime.now(timezone.utc).replace(microsecond=0),
            evaluation_id="missing-exp",
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


def test_deprecated_evaluation_context_hydrates_evaluation_rollups(client: TestClient) -> None:
    evaluation_id = "legacy-eval-context-exp"
    group_id = _ensure_group(client)
    created = client.post(
        EVALUATIONS,
        json={
            "name": evaluation_id,
            "experiment_group_id": group_id,
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
                evaluation_id=evaluation_id,
                run_id="run-1",
                test_case_id="case-1",
                score=1.0,
                cost_usd=0.01,
                latency_ms=100,
                offset_seconds=0,
            ),
            "evaluation_context": {"evaluation_id": evaluation_id, "test_case_id": "case-1"},
        },
    )

    assert response.status_code == 201, response.text

    fetched = client.get(f"{EVALUATIONS}/{evaluation_id}")
    assert fetched.status_code == 200, fetched.text
    evaluation = fetched.json()
    assert evaluation["run_count"] == 1
    assert evaluation["aggregate_scores"]["reward"]["mean"] == pytest.approx(1.0)


def _atif_body(
    *,
    started_at: datetime,
    evaluation_id: str,
    run_id: str,
    test_case_id: str,
    score: float,
    cost_usd: float,
    latency_ms: int,
    offset_seconds: int,
) -> dict[str, Any]:
    session_started_at = started_at + timedelta(seconds=offset_seconds)
    finished_at = session_started_at + timedelta(milliseconds=latency_ms)
    session_id = f"{evaluation_id}-{run_id}-{test_case_id}"
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": session_id,
        "evaluation_context": {
            "evaluation_id": evaluation_id,
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
