# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experiment rollup repository tests."""

from typing import cast

import pytest
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.experiment_rollup_repository import ExperimentRollupRepository


class _QueryResult:
    def __init__(self, rows: list[tuple[object, ...]], columns: list[str]) -> None:
        self.result_rows = rows
        self.column_names = columns


class _Client:
    def __init__(self, query_results: list[_QueryResult]) -> None:
        self.queries: list[str] = []
        self.parameters: list[dict[str, object]] = []
        self.query_results = query_results

    def table(self, name: str) -> str:
        return name

    async def query(self, query: str, *, parameters: dict[str, object]) -> _QueryResult:
        self.queries.append(query)
        self.parameters.append(parameters)
        return self.query_results.pop(0)


def _repository(client: _Client) -> ExperimentRollupRepository:
    return ExperimentRollupRepository(cast(ClickHouseSpanClient, client))


@pytest.mark.asyncio
async def test_experiment_rollups_anchor_on_root_session_membership():
    client = _Client(
        [
            _QueryResult(
                [("exp-a", 3)],
                ["experiment_id", "run_count"],
            ),
            _QueryResult(
                [("exp-a", "harbor.verifier", 3.0, 0.75, 0.8, 1.0, 1.0, 1.0, 4)],
                ["experiment_id", "evaluator_name", "sum", "mean", "median", "p90", "p95", "p99", "count"],
            ),
            _QueryResult(
                [
                    (
                        "exp-a",
                        ["model-b", "model-a"],
                        0.65,
                        0.1625,
                        0.2,
                        0.3,
                        0.3,
                        0.3,
                        4,
                        7000.0,
                        1750.0,
                        2000.0,
                        3000.0,
                        3000.0,
                        3000.0,
                        4,
                    )
                ],
                [
                    "experiment_id",
                    "model_names",
                    "cost_sum",
                    "cost_mean",
                    "cost_median",
                    "cost_p90",
                    "cost_p95",
                    "cost_p99",
                    "cost_count",
                    "latency_sum",
                    "latency_mean",
                    "latency_median",
                    "latency_p90",
                    "latency_p95",
                    "latency_p99",
                    "latency_count",
                ],
            ),
        ]
    )
    repository = _repository(client)

    rollups = await repository.get_rollups(workspace="default", experiment_ids=["exp-a"])

    rollup = rollups["exp-a"]
    assert rollup.run_count == 3
    assert rollup.evaluator_names == ["harbor.verifier"]
    assert rollup.model_names == ["model-a", "model-b"]
    assert rollup.evaluator_scores["harbor.verifier"].sum == 3.0
    assert rollup.evaluator_scores["harbor.verifier"].mean == 0.75
    assert rollup.evaluator_scores["harbor.verifier"].median == 0.8
    assert rollup.evaluator_scores["harbor.verifier"].p90 == 1.0
    assert rollup.evaluator_scores["harbor.verifier"].p95 == 1.0
    assert rollup.evaluator_scores["harbor.verifier"].p99 == 1.0
    assert rollup.evaluator_scores["harbor.verifier"].count == 4
    assert rollup.cost_usd is not None
    assert rollup.cost_usd.sum == 0.65
    assert rollup.cost_usd.mean == 0.1625
    assert rollup.cost_usd.median == 0.2
    assert rollup.cost_usd.p90 == 0.3
    assert rollup.cost_usd.p95 == 0.3
    assert rollup.cost_usd.p99 == 0.3
    assert rollup.cost_usd.count == 4
    assert rollup.latency_ms is not None
    assert rollup.latency_ms.sum == 7000
    assert rollup.latency_ms.mean == 1750
    assert rollup.latency_ms.median == 2000
    assert rollup.latency_ms.p90 == 3000
    assert rollup.latency_ms.p95 == 3000
    assert rollup.latency_ms.p99 == 3000
    assert rollup.latency_ms.count == 4

    assert len(client.queries) == 3
    assert "FROM experiment_sessions FINAL" in client.queries[0]
    assert "count() AS run_count" in client.queries[0]
    assert "experiment_id IN (%(experiment_id_0)s)" in client.queries[0]
    assert "FROM evaluator_results FINAL" in client.queries[1]
    assert "quantileExact(0.5)(value) AS median" in client.queries[1]
    assert "quantileExact(0.99)(value) AS p99" in client.queries[1]
    assert "AND (workspace, session_id) IN (" in client.queries[1]
    assert "sessions.session_id = results.session_id" in client.queries[1]
    # Scores are reduced to one value per (experiment, session, evaluator) before the
    # distribution rollup so count tracks runs and the mean is not span-weighted.
    assert "GROUP BY sessions.experiment_id, sessions.session_id, results.name" in client.queries[1]
    assert "current_session_spans AS" in client.queries[2]
    assert "(span_versions.workspace, span_versions.session_id) IN" in client.queries[2]
    assert "LEFT JOIN current_session_spans AS spans" in client.queries[2]
    assert "sessions.session_id = spans.session_id" in client.queries[2]
    assert "arraySort(arrayDistinct(arrayFlatten(groupArray(model_names)))) AS model_names" in client.queries[2]
    assert "quantileExactIf(0.5)" in client.queries[2]
    assert "cost_median" in client.queries[2]
    assert "quantileExactIf(0.99)" in client.queries[2]
    assert "latency_p99" in client.queries[2]
    assert "sessions.trace_id = spans.trace_id" not in client.queries[2]
    assert client.parameters[0]["experiment_id_0"] == "exp-a"
    assert client.parameters[2]["model_key"] == "gen_ai.request.model"
