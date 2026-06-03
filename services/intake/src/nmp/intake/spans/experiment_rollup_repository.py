# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse rollups for Experiment read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.span_attribute_catalog import COST_SCALE, SpanAttributeField, spec_for_field
from nmp.intake.spans.storage import result_rows
from nmp.intake.spans.trace_repository import current_spans_sql


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
        self._client = client

    async def get_rollups(self, *, workspace: str, experiment_ids: list[str]) -> dict[str, ExperimentRollup]:
        experiment_ids = list(dict.fromkeys(experiment_ids))
        rollups = {experiment_id: ExperimentRollup(experiment_id=experiment_id) for experiment_id in experiment_ids}
        if not experiment_ids:
            return rollups

        experiment_names_sql, experiment_parameters = _experiment_id_parameters(experiment_ids)
        parameters = {"workspace": workspace, **experiment_parameters}
        sessions_table = self._client.table("experiment_sessions")

        for row in result_rows(
            await self._client.query(
                _run_counts_sql(sessions_table, experiment_names_sql),
                parameters=parameters,
            )
        ):
            rollups[row["experiment_id"]].run_count = int(row["run_count"])

        for row in result_rows(
            await self._client.query(
                _score_rollups_sql(
                    sessions_table=sessions_table,
                    evaluator_results_table=self._client.table("evaluator_results"),
                    experiment_names_sql=experiment_names_sql,
                ),
                parameters=parameters,
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

        for row in result_rows(
            await self._client.query(
                _metric_rollups_sql(
                    sessions_table=sessions_table,
                    spans_table=self._client.table("spans"),
                    experiment_names_sql=experiment_names_sql,
                ),
                parameters={
                    **parameters,
                    "cost_key": spec_for_field(SpanAttributeField.COST_TOTAL_USD).bag_key,
                    "model_key": spec_for_field(SpanAttributeField.MODEL).bag_key,
                },
            )
        ):
            rollup = rollups[row["experiment_id"]]
            rollup.model_names = _string_list(row["model_names"])
            rollup.cost_usd = _score_rollup(row, "cost")
            rollup.latency_ms = _score_rollup(row, "latency")

        return rollups


def _experiment_id_parameters(experiment_ids: list[str]) -> tuple[str, dict[str, str]]:
    parameters = {f"experiment_id_{index}": experiment_id for index, experiment_id in enumerate(experiment_ids)}
    return ", ".join(f"%({name})s" for name in parameters), parameters


def _scoped_sessions_sql(sessions_table: str, experiment_names_sql: str) -> str:
    return f"""
        SELECT workspace, experiment_id, session_id, latency_ms
        FROM {sessions_table} FINAL
        WHERE workspace = %(workspace)s
            AND is_deleted = 0
            AND experiment_id IN ({experiment_names_sql})
        ORDER BY start_time ASC, root_span_id ASC
        LIMIT 1 BY workspace, session_id, experiment_id
    """


def _run_counts_sql(sessions_table: str, experiment_names_sql: str) -> str:
    return f"""
        WITH scoped_sessions AS (
            {_scoped_sessions_sql(sessions_table, experiment_names_sql)}
        )
        SELECT
            experiment_id,
            count() AS run_count
        FROM scoped_sessions
        GROUP BY experiment_id
        ORDER BY experiment_id ASC
    """


# Quantile name -> ClickHouse probability argument, shared by every distribution rollup.
_STAT_QUANTILES = {"median": "0.5", "p90": "0.9", "p95": "0.95", "p99": "0.99"}


def _stat_columns(value_expr: str, *, prefix: str = "", guarded: bool = False) -> str:
    """Build the sum/mean/median/p90/p95/p99/count column list for one value expression.

    ``guarded`` wraps each aggregate so that an empty or all-NULL set yields NULL instead of
    ``sumIf``'s 0 / ``avgIf``'s NaN; use it when ``value_expr`` can be NULL per input row.
    """

    label = f"{prefix}_" if prefix else ""
    if guarded:
        not_null = f"isNotNull({value_expr})"
        guard = f"countIf({not_null}) = 0"

        def stat(expr: str) -> str:
            return f"if({guard}, NULL, {expr})"

        columns = [
            f"{stat(f'sumIf({value_expr}, {not_null})')} AS {label}sum",
            f"{stat(f'avgIf({value_expr}, {not_null})')} AS {label}mean",
            *(
                f"{stat(f'quantileExactIf({q})({value_expr}, {not_null})')} AS {label}{name}"
                for name, q in _STAT_QUANTILES.items()
            ),
            f"countIf({not_null}) AS {label}count",
        ]
    else:
        columns = [
            f"sum({value_expr}) AS {label}sum",
            f"avg({value_expr}) AS {label}mean",
            *(f"quantileExact({q})({value_expr}) AS {label}{name}" for name, q in _STAT_QUANTILES.items()),
            f"count() AS {label}count",
        ]
    return ",\n            ".join(columns)


def _score_rollups_sql(*, sessions_table: str, evaluator_results_table: str, experiment_names_sql: str) -> str:
    # Each run (session) contributes one score per evaluator, so reduce the per-span
    # evaluator_results rows to a single per-(experiment, session, evaluator) value before
    # the distribution rollup. This keeps `count` aligned with run_count and the mean
    # run-weighted rather than weighted by spans-per-session.
    return f"""
        WITH
        scoped_sessions AS (
            {_scoped_sessions_sql(sessions_table, experiment_names_sql)}
        ),
        session_scores AS (
            SELECT
                sessions.experiment_id AS experiment_id,
                results.name AS evaluator_name,
                avg(results.value) AS value
            FROM scoped_sessions AS sessions
            INNER JOIN (
                SELECT workspace, session_id, name, value
                FROM {evaluator_results_table} FINAL
                WHERE workspace = %(workspace)s
                    AND (workspace, session_id) IN (
                        SELECT DISTINCT workspace, session_id
                        FROM scoped_sessions
                    )
                    AND data_type IN ('NUMERIC', 'BOOLEAN')
                    AND value IS NOT NULL
            ) AS results
                ON sessions.workspace = results.workspace
                AND sessions.session_id = results.session_id
            GROUP BY sessions.experiment_id, sessions.session_id, results.name
        )
        SELECT
            experiment_id,
            evaluator_name,
            {_stat_columns("value")}
        FROM session_scores
        GROUP BY experiment_id, evaluator_name
        ORDER BY experiment_id ASC, evaluator_name ASC
    """


def _metric_rollups_sql(*, sessions_table: str, spans_table: str, experiment_names_sql: str) -> str:
    return f"""
        WITH
        scoped_sessions AS (
            {_scoped_sessions_sql(sessions_table, experiment_names_sql)}
        ),
        current_session_spans AS (
            {
        current_spans_sql(
            spans_table,
            extra_where_sql=(
                "(span_versions.workspace, span_versions.session_id) IN "
                "(SELECT DISTINCT workspace, session_id FROM scoped_sessions)"
            ),
        )
    }
        ),
        session_costs AS (
            SELECT
                sessions.experiment_id AS experiment_id,
                sessions.session_id AS session_id,
                sessions.latency_ms AS latency_ms,
                if(
                    countIf(has(mapKeys(spans.attributes_number), %(cost_key)s)) = 0,
                    NULL,
                    sumIf(
                        spans.attributes_number[%(cost_key)s],
                        has(mapKeys(spans.attributes_number), %(cost_key)s)
                    ) / {COST_SCALE}
                ) AS cost_usd,
                groupUniqArrayIf(
                    spans.attributes_string[%(model_key)s],
                    has(mapKeys(spans.attributes_string), %(model_key)s)
                        AND spans.attributes_string[%(model_key)s] != ''
                ) AS model_names
            FROM scoped_sessions AS sessions
            LEFT JOIN current_session_spans AS spans
                ON sessions.workspace = spans.workspace
                AND sessions.session_id = spans.session_id
                AND spans.is_deleted = 0
            GROUP BY sessions.experiment_id, sessions.session_id, sessions.latency_ms
        )
        SELECT
            experiment_id,
            arraySort(arrayDistinct(arrayFlatten(groupArray(model_names)))) AS model_names,
            {_stat_columns("cost_usd", prefix="cost", guarded=True)},
            {_stat_columns("latency_ms", prefix="latency", guarded=True)}
        FROM session_costs
        GROUP BY experiment_id
        ORDER BY experiment_id ASC
    """


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
