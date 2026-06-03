# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse experiment rollup SQL for Intake."""

from __future__ import annotations

from nmp.intake.spans.clickhouse.query import TableRef
from nmp.intake.spans.clickhouse.sql import BuiltQuery, _trusted_query, _trusted_sql, merge_parameters
from nmp.intake.spans.clickhouse.trace_queries import current_spans_sql
from nmp.intake.spans.span_attribute_catalog import COST_SCALE, SpanAttributeField, spec_for_field

# Quantile name -> ClickHouse probability argument, shared by every distribution rollup.
_STAT_QUANTILES = {"median": "0.5", "p90": "0.9", "p95": "0.95", "p99": "0.99"}


def experiment_id_parameters(experiment_ids: list[str]) -> tuple[str, dict[str, str]]:
    parameters = {f"experiment_id_{index}": experiment_id for index, experiment_id in enumerate(experiment_ids)}
    return ", ".join(f"%({name})s" for name in parameters), parameters


def experiment_run_counts_query(
    sessions_table: TableRef,
    *,
    experiment_names_sql: str,
) -> BuiltQuery:
    return _trusted_query(
        f"""
        WITH scoped_sessions AS (
            {_scoped_sessions_sql(sessions_table.qualified_name, experiment_names_sql)}
        )
        SELECT
            experiment_id,
            count() AS run_count
        FROM scoped_sessions
        GROUP BY experiment_id
        ORDER BY experiment_id ASC
        """,
    )


def experiment_score_rollups_query(
    *,
    sessions_table: TableRef,
    evaluator_results_table: TableRef,
    experiment_names_sql: str,
) -> BuiltQuery:
    return _trusted_query(
        f"""
        WITH
        scoped_sessions AS (
            {_scoped_sessions_sql(sessions_table.qualified_name, experiment_names_sql)}
        ),
        session_scores AS (
            SELECT
                sessions.experiment_id AS experiment_id,
                results.name AS evaluator_name,
                avg(results.value) AS value
            FROM scoped_sessions AS sessions
            INNER JOIN (
                SELECT workspace, session_id, name, value
                FROM {evaluator_results_table.qualified_name} FINAL
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
        """,
    )


def experiment_metric_rollups_query(
    *,
    sessions_table: TableRef,
    spans_table: TableRef,
    experiment_names_sql: str,
) -> BuiltQuery:
    session_span_filter = _trusted_sql(
        "(span_versions.workspace, span_versions.session_id) IN "
        "(SELECT DISTINCT workspace, session_id FROM scoped_sessions)"
    )
    current_session_spans = current_spans_sql(spans_table, extra_where=session_span_filter)
    return _trusted_query(
        f"""
        WITH
        scoped_sessions AS (
            {_scoped_sessions_sql(sessions_table.qualified_name, experiment_names_sql)}
        ),
        current_session_spans AS (
            {current_session_spans.sql}
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
        """,
        merge_parameters(
            current_session_spans.parameters,
            {
                "cost_key": spec_for_field(SpanAttributeField.COST_TOTAL_USD).bag_key,
                "model_key": spec_for_field(SpanAttributeField.MODEL).bag_key,
            },
        ),
    )


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


def _stat_columns(value_expr: str, *, prefix: str = "", guarded: bool = False) -> str:
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
