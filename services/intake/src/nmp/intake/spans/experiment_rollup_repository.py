# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse rollups for Experiment read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nmp.intake.spans.clickhouse.dao import ClickHouseDao
from nmp.intake.spans.clickhouse.experiment_queries import (
    experiment_id_parameters,
    experiment_metric_rollups_query,
    experiment_run_counts_query,
    experiment_score_rollups_query,
)
from nmp.intake.spans.clickhouse.sql import BuiltQuery, _trusted_query, merge_parameters
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient


@dataclass(frozen=True)
class ScoreRollup:
    sum: float | None
    mean: float | None
    median: float | None
    p90: float | None
    p95: float | None
    p99: float | None
    count: int


@dataclass
class ExperimentRollup:
    experiment_id: str
    run_count: int = 0
    model_names: list[str] = field(default_factory=list)
    evaluator_scores: dict[str, ScoreRollup] = field(default_factory=dict)
    cost_usd: ScoreRollup | None = None
    latency_ms: ScoreRollup | None = None

    @property
    def evaluator_names(self) -> list[str]:
        return sorted(self.evaluator_scores)


class ExperimentRollupRepository:
    def __init__(self, client: ClickHouseSpanClient) -> None:
        self._dao = ClickHouseDao(client)

    async def get_rollups(self, *, workspace: str, experiment_ids: list[str]) -> dict[str, ExperimentRollup]:
        experiment_ids = list(dict.fromkeys(experiment_ids))
        rollups = {experiment_id: ExperimentRollup(experiment_id=experiment_id) for experiment_id in experiment_ids}
        if not experiment_ids:
            return rollups

        experiment_names_sql, experiment_parameters = experiment_id_parameters(experiment_ids)
        base_parameters = {"workspace": workspace, **experiment_parameters}
        sessions_table = self._dao.table("experiment_sessions")
        evaluator_results_table = self._dao.table("evaluator_results")
        spans_table = self._dao.table("spans")

        for row in await self._dao.fetch_rows(
            _with_workspace(
                experiment_run_counts_query(
                    sessions_table,
                    experiment_names_sql=experiment_names_sql,
                ),
                base_parameters,
            )
        ):
            rollups[row["experiment_id"]].run_count = int(row["run_count"])

        for row in await self._dao.fetch_rows(
            _with_workspace(
                experiment_score_rollups_query(
                    sessions_table=sessions_table,
                    evaluator_results_table=evaluator_results_table,
                    experiment_names_sql=experiment_names_sql,
                ),
                base_parameters,
            )
        ):
            rollups[row["experiment_id"]].evaluator_scores[row["evaluator_name"]] = ScoreRollup(
                sum=_float_or_none(row["sum"]),
                mean=_float_or_none(row["mean"]),
                median=_float_or_none(row["median"]),
                p90=_float_or_none(row["p90"]),
                p95=_float_or_none(row["p95"]),
                p99=_float_or_none(row["p99"]),
                count=int(row["count"]),
            )

        for row in await self._dao.fetch_rows(
            _with_workspace(
                experiment_metric_rollups_query(
                    sessions_table=sessions_table,
                    spans_table=spans_table,
                    experiment_names_sql=experiment_names_sql,
                ),
                base_parameters,
            )
        ):
            rollup = rollups[row["experiment_id"]]
            rollup.model_names = _string_list(row["model_names"])
            rollup.cost_usd = _score_rollup(row, "cost")
            rollup.latency_ms = _score_rollup(row, "latency")

        return rollups


def _with_workspace(query: BuiltQuery, parameters: dict[str, Any]) -> BuiltQuery:
    return _trusted_query(query.sql, merge_parameters(query.parameters, parameters))


def _score_rollup(row: dict[str, Any], prefix: str) -> ScoreRollup | None:
    count = int(row[f"{prefix}_count"])
    if count == 0:
        return None
    return ScoreRollup(
        sum=_float_or_none(row[f"{prefix}_sum"]),
        mean=_float_or_none(row[f"{prefix}_mean"]),
        median=_float_or_none(row[f"{prefix}_median"]),
        p90=_float_or_none(row[f"{prefix}_p90"]),
        p95=_float_or_none(row[f"{prefix}_p95"]),
        p99=_float_or_none(row[f"{prefix}_p99"]),
        count=count,
    )


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    return sorted(str(item) for item in value if str(item))


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
