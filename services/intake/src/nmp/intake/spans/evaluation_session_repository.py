# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse repository for per-session rows of an Evaluation.

Returns one row per ingested session (test case execution), using ``trace_index``
for root/session membership and per-session aggregates from all spans (tokens +
cost), plus per-evaluator session-mean scores from ``evaluator_results``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import IntakeResponseMode, SpanStatus
from nmp.intake.spans.span_attribute_catalog import COST_SCALE, SpanAttributeField, spec_for_field
from nmp.intake.spans.storage import (
    float_or_none,
    int_or_none,
    normalize_span_status,
    result_rows,
    str_or_none,
    text_query_parameters,
    text_select_for_mode,
)
from nmp.intake.spans.trace_repository import current_spans_sql


@dataclass(frozen=True)
class EvaluationSessionRow:
    """One ingested session of an Evaluation."""

    workspace: str
    evaluation_name: str
    session_id: str
    test_case_id: str | None
    trace_id: str
    root_span_id: str
    started_at: datetime
    ended_at: datetime | None
    latency_ms: float | None
    status: SpanStatus
    input: str | None
    output: str | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    cost_total_usd: float | None
    evaluator_scores: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationSessionPage:
    rows: list[EvaluationSessionRow]
    total: int


class EvaluationSessionRepository:
    def __init__(self, client: ClickHouseSpanClient) -> None:
        self._client = client

    async def list_sessions(
        self,
        *,
        workspace: str,
        evaluation_name: str,
        status: SpanStatus | None = None,
        test_case_id: str | None = None,
        page: int,
        page_size: int,
        mode: IntakeResponseMode,
    ) -> EvaluationSessionPage:
        trace_index_table = self._client.table("trace_index")
        spans_table = self._client.table("spans")
        evaluator_results_table = self._client.table("evaluator_results")

        scoped_filter_sql, scoped_filter_parameters = _scoped_filter(test_case_id=test_case_id, status=status)

        base_parameters: dict[str, Any] = {
            "workspace": workspace,
            "evaluation_name": evaluation_name,
            "input_tokens_key": spec_for_field(SpanAttributeField.INPUT_TOKENS).bag_key,
            "output_tokens_key": spec_for_field(SpanAttributeField.OUTPUT_TOKENS).bag_key,
            "cached_tokens_key": spec_for_field(SpanAttributeField.CACHED_TOKENS).bag_key,
            "cost_key": spec_for_field(SpanAttributeField.COST_TOTAL_USD).bag_key,
        }

        count_sql = _count_sql(
            trace_index_table=trace_index_table,
            scoped_filter_sql=scoped_filter_sql,
        )
        count_result = await self._client.query(
            count_sql,
            parameters={**base_parameters, **scoped_filter_parameters},
        )
        total = int(count_result.result_rows[0][0]) if count_result.result_rows else 0
        if total == 0:
            return EvaluationSessionPage(rows=[], total=0)

        offset = (page - 1) * page_size
        list_sql = _list_sql(
            trace_index_table=trace_index_table,
            spans_table=spans_table,
            evaluator_results_table=evaluator_results_table,
            scoped_filter_sql=scoped_filter_sql,
            mode=mode,
        )
        list_parameters = {
            **base_parameters,
            **scoped_filter_parameters,
            **text_query_parameters(mode),
            "limit": page_size,
            "offset": offset,
        }
        list_result = await self._client.query(
            list_sql,
            parameters=list_parameters,
        )
        rows = [_row(record) for record in result_rows(list_result)]
        return EvaluationSessionPage(rows=rows, total=total)


def _scoped_filter(*, test_case_id: str | None, status: SpanStatus | None) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    parameters: dict[str, Any] = {}
    if test_case_id is not None:
        parameters["test_case_id"] = test_case_id
        clauses.append("test_case_id = %(test_case_id)s")
    if status is not None:
        parameters["status"] = status.value
        clauses.append("root_status = %(status)s")
    return "".join(f"\n            AND {clause}" for clause in clauses), parameters


def _scoped_sessions_sql(
    trace_index_table: str,
    *,
    scoped_filter_sql: str,
    mode: IntakeResponseMode,
) -> str:
    select_columns = [
        "workspace",
        "evaluation_id",
        "session_id",
        "test_case_id",
        "trace_id",
        "root_span_id",
        "root_started_at AS start_time",
        "root_ended_at AS end_time",
        "latency_ms",
        "root_status AS root_span_status",
    ]
    select_columns.extend(
        (
            text_select_for_mode("root_input", alias="input", mode=mode),
            text_select_for_mode("root_output", alias="output", mode=mode),
        )
    )
    select_sql = ",\n            ".join(select_columns)
    return f"""
        SELECT
            {select_sql}
        FROM {trace_index_table} FINAL
        WHERE workspace = %(workspace)s
            AND is_deleted = 0
            AND evaluation_id = %(evaluation_name)s
            {scoped_filter_sql}
        ORDER BY root_started_at ASC, root_span_id ASC
        LIMIT 1 BY workspace, session_id, evaluation_id
    """


def _count_sql(
    *,
    trace_index_table: str,
    scoped_filter_sql: str,
) -> str:
    scoped_sessions_sql = _scoped_sessions_sql(
        trace_index_table,
        scoped_filter_sql=scoped_filter_sql,
        mode="summary",
    )
    return f"""
        SELECT count()
        FROM (
            {scoped_sessions_sql}
        ) AS scoped_sessions
    """


def _list_sql(
    *,
    trace_index_table: str,
    spans_table: str,
    evaluator_results_table: str,
    scoped_filter_sql: str,
    mode: IntakeResponseMode,
) -> str:
    scoped_sessions_sql = _scoped_sessions_sql(
        trace_index_table,
        scoped_filter_sql=scoped_filter_sql,
        mode=mode,
    )
    return f"""
        WITH
        scoped_sessions AS (
            {scoped_sessions_sql}
        ),
        page_sessions AS (
            SELECT
                workspace,
                evaluation_id,
                session_id,
                test_case_id,
                trace_id,
                root_span_id,
                start_time,
                end_time,
                latency_ms,
                root_span_status,
                input,
                output
            FROM scoped_sessions
            ORDER BY start_time ASC, root_span_id ASC
            LIMIT %(limit)s OFFSET %(offset)s
        ),
        current_page_spans AS (
            {
        current_spans_sql(
            spans_table,
            extra_where_sql=(
                "(span_versions.workspace, span_versions.session_id) IN "
                "(SELECT workspace, session_id FROM page_sessions)"
            ),
        )
    }
        ),
        session_metrics AS (
            SELECT
                sessions.workspace AS workspace,
                sessions.session_id AS session_id,
                {_guarded_sum_sql("input_tokens_key")} AS input_tokens,
                {_guarded_sum_sql("output_tokens_key")} AS output_tokens,
                {_guarded_sum_sql("cached_tokens_key")} AS cached_tokens,
                {_guarded_sum_sql("cost_key", scale=COST_SCALE)} AS cost_total_usd
            FROM page_sessions AS sessions
            LEFT JOIN current_page_spans AS spans
                ON sessions.workspace = spans.workspace
                AND sessions.session_id = spans.session_id
                AND spans.is_deleted = 0
            GROUP BY sessions.workspace, sessions.session_id
        ),
        session_scores AS (
            SELECT
                workspace,
                session_id,
                mapFromArrays(groupArray(evaluator_name), groupArray(mean_score)) AS evaluator_scores
            FROM (
                SELECT
                    results.workspace AS workspace,
                    results.session_id AS session_id,
                    results.name AS evaluator_name,
                    avg(results.value) AS mean_score
                FROM (
                    SELECT workspace, session_id, name, value
                    FROM {evaluator_results_table} FINAL
                    WHERE workspace = %(workspace)s
                        AND (workspace, session_id) IN (
                            SELECT workspace, session_id
                            FROM page_sessions
                        )
                        AND data_type IN ('NUMERIC', 'BOOLEAN')
                        AND value IS NOT NULL
                ) AS results
                GROUP BY results.workspace, results.session_id, results.name
            )
            GROUP BY workspace, session_id
        )
        SELECT
            sessions.workspace AS workspace,
            sessions.evaluation_id AS evaluation_id,
            sessions.session_id AS session_id,
            sessions.test_case_id AS test_case_id,
            sessions.trace_id AS trace_id,
            sessions.root_span_id AS root_span_id,
            sessions.start_time AS start_time,
            sessions.end_time AS end_time,
            sessions.latency_ms AS latency_ms,
            sessions.root_span_status AS root_span_status,
            sessions.input AS input,
            sessions.output AS output,
            metrics.input_tokens AS input_tokens,
            metrics.output_tokens AS output_tokens,
            metrics.cached_tokens AS cached_tokens,
            metrics.cost_total_usd AS cost_total_usd,
            scores.evaluator_scores AS evaluator_scores
        FROM page_sessions AS sessions
        LEFT JOIN session_metrics AS metrics
            ON sessions.workspace = metrics.workspace
            AND sessions.session_id = metrics.session_id
        LEFT JOIN session_scores AS scores
            ON sessions.workspace = scores.workspace
            AND sessions.session_id = scores.session_id
        ORDER BY sessions.start_time ASC, sessions.root_span_id ASC
    """


def _guarded_sum_sql(parameter_name: str, *, scale: int = 1) -> str:
    key = f"%({parameter_name})s"
    sum_expr = f"sumIf(spans.attributes_number[{key}], has(mapKeys(spans.attributes_number), {key}))"
    if scale != 1:
        sum_expr = f"{sum_expr} / {scale}"
    return f"""
        if(
            countIf(has(mapKeys(spans.attributes_number), {key})) = 0,
            NULL,
            {sum_expr}
        )
    """


def _row(record: dict[str, Any]) -> EvaluationSessionRow:
    return EvaluationSessionRow(
        workspace=record["workspace"],
        evaluation_name=record["evaluation_id"],
        session_id=record["session_id"],
        test_case_id=str_or_none(record["test_case_id"]),
        trace_id=record["trace_id"],
        root_span_id=record["root_span_id"],
        started_at=record["start_time"],
        ended_at=record["end_time"],
        latency_ms=float_or_none(record["latency_ms"]),
        status=normalize_span_status(record["root_span_status"]),
        input=str_or_none(record["input"]),
        output=str_or_none(record["output"]),
        input_tokens=int_or_none(record["input_tokens"]),
        output_tokens=int_or_none(record["output_tokens"]),
        cached_tokens=int_or_none(record["cached_tokens"]),
        cost_total_usd=float_or_none(record["cost_total_usd"]),
        evaluator_scores=_score_map(record.get("evaluator_scores")),
    )


def _score_map(value: Any) -> dict[str, float]:
    if value is None:
        return {}
    return {str(key): float(score) for key, score in dict(value).items()}
