# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse repository for per-session rows of an Experiment.

Returns one row per ingested session (test case execution), joining
``experiment_sessions`` with the session's root span (status + input text)
and per-session aggregates from all spans (tokens + cost), plus per-evaluator
session-mean scores from ``evaluator_results``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import SpanStatus
from nmp.intake.spans.span_attribute_catalog import COST_SCALE, SpanAttributeField, spec_for_field
from nmp.intake.spans.storage import normalize_span_status, result_rows
from nmp.intake.spans.trace_repository import current_spans_sql


@dataclass(frozen=True)
class ExperimentSessionRow:
    """One ingested session of an Experiment."""

    workspace: str
    experiment_name: str
    session_id: str
    test_case_id: str | None
    trace_id: str
    root_span_id: str
    started_at: datetime
    ended_at: datetime | None
    latency_ms: float | None
    status: SpanStatus
    input: str | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    cost_total_usd: float | None
    evaluator_scores: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ExperimentSessionPage:
    rows: list[ExperimentSessionRow]
    total: int


class ExperimentSessionRepository:
    def __init__(self, client: ClickHouseSpanClient) -> None:
        self._client = client

    async def list_sessions(
        self,
        *,
        workspace: str,
        experiment_name: str,
        status: SpanStatus | None = None,
        test_case_id: str | None = None,
        page: int,
        page_size: int,
    ) -> ExperimentSessionPage:
        sessions_table = self._client.table("experiment_sessions")
        spans_table = self._client.table("spans")

        outer_filter_sql, outer_filter_parameters = _outer_filter(status=status, test_case_id=test_case_id)

        base_parameters: dict[str, Any] = {
            "workspace": workspace,
            "experiment_name": experiment_name,
            "input_tokens_key": spec_for_field(SpanAttributeField.INPUT_TOKENS).bag_key,
            "output_tokens_key": spec_for_field(SpanAttributeField.OUTPUT_TOKENS).bag_key,
            "cached_tokens_key": spec_for_field(SpanAttributeField.CACHED_TOKENS).bag_key,
            "cost_key": spec_for_field(SpanAttributeField.COST_TOTAL_USD).bag_key,
        }

        count_sql = _count_sql(
            sessions_table=sessions_table, spans_table=spans_table, outer_filter_sql=outer_filter_sql
        )
        count_result = await self._client.query(count_sql, parameters={**base_parameters, **outer_filter_parameters})
        total = int(count_result.result_rows[0][0]) if count_result.result_rows else 0
        if total == 0:
            return ExperimentSessionPage(rows=[], total=0)

        offset = (page - 1) * page_size
        list_sql = _list_sql(
            sessions_table=sessions_table,
            spans_table=spans_table,
            outer_filter_sql=outer_filter_sql,
        )
        list_result = await self._client.query(
            list_sql,
            parameters={
                **base_parameters,
                **outer_filter_parameters,
                "limit": page_size,
                "offset": offset,
            },
        )
        rows = [_row(record) for record in result_rows(list_result)]

        session_ids = [row.session_id for row in rows]
        if session_ids:
            scores_by_session = await self._fetch_session_scores(workspace=workspace, session_ids=session_ids)
            rows = [
                ExperimentSessionRow(
                    workspace=row.workspace,
                    experiment_name=row.experiment_name,
                    session_id=row.session_id,
                    test_case_id=row.test_case_id,
                    trace_id=row.trace_id,
                    root_span_id=row.root_span_id,
                    started_at=row.started_at,
                    ended_at=row.ended_at,
                    latency_ms=row.latency_ms,
                    status=row.status,
                    input=row.input,
                    input_tokens=row.input_tokens,
                    output_tokens=row.output_tokens,
                    cached_tokens=row.cached_tokens,
                    cost_total_usd=row.cost_total_usd,
                    evaluator_scores=scores_by_session.get(row.session_id, {}),
                )
                for row in rows
            ]

        return ExperimentSessionPage(rows=rows, total=total)

    async def _fetch_session_scores(self, *, workspace: str, session_ids: Iterable[str]) -> dict[str, dict[str, float]]:
        session_ids = list(dict.fromkeys(session_ids))
        placeholders_sql, id_parameters = _session_id_parameters(session_ids)
        evaluator_results_table = self._client.table("evaluator_results")
        # The aggregate alias must not shadow ``value`` (the source column referenced in WHERE),
        # so the source rows are projected through a subquery before aggregation. Same approach
        # used by ExperimentRollupRepository for the per-session score CTE.
        result = await self._client.query(
            f"""
            SELECT
                session_id,
                evaluator_name,
                avg(score) AS mean_score
            FROM (
                SELECT
                    session_id,
                    name AS evaluator_name,
                    value AS score
                FROM {evaluator_results_table} FINAL
                WHERE workspace = %(workspace)s
                    AND session_id IN ({placeholders_sql})
                    AND data_type IN ('NUMERIC', 'BOOLEAN')
                    AND value IS NOT NULL
            )
            GROUP BY session_id, evaluator_name
            """,
            parameters={"workspace": workspace, **id_parameters},
        )
        out: dict[str, dict[str, float]] = {}
        for record in result_rows(result):
            out.setdefault(record["session_id"], {})[record["evaluator_name"]] = float(record["mean_score"])
        return out


def _outer_filter(*, status: SpanStatus | None, test_case_id: str | None) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    parameters: dict[str, Any] = {}
    if status is not None:
        clauses.append("root_span_status = %(status)s")
        parameters["status"] = status.value
    if test_case_id is not None:
        clauses.append("test_case_id = %(test_case_id)s")
        parameters["test_case_id"] = test_case_id
    return (" AND ".join(clauses) if clauses else "1 = 1"), parameters


def _scoped_sessions_sql(sessions_table: str) -> str:
    return f"""
        SELECT
            workspace,
            experiment_id,
            session_id,
            test_case_id,
            trace_id,
            root_span_id,
            start_time,
            end_time,
            latency_ms
        FROM {sessions_table} FINAL
        WHERE workspace = %(workspace)s
            AND is_deleted = 0
            AND experiment_id = %(experiment_name)s
        ORDER BY start_time ASC, root_span_id ASC
        LIMIT 1 BY workspace, session_id, experiment_id
    """


def _hydrated_sessions_cte(sessions_table: str, spans_table: str) -> str:
    # Joins each scoped session with its root span (for status / input text) and a per-session
    # aggregate of all spans (for tokens / cost). The status column drives the outer status filter
    # and is materialized as ``root_span_status`` so it survives projection.
    return f"""
        WITH
        scoped_sessions AS (
            {_scoped_sessions_sql(sessions_table)}
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
        session_aggregates AS (
            SELECT
                sessions.workspace AS workspace,
                sessions.session_id AS session_id,
                {_token_sum_sql("input_tokens_key")} AS input_tokens,
                {_token_sum_sql("output_tokens_key")} AS output_tokens,
                {_token_sum_sql("cached_tokens_key")} AS cached_tokens,
                {_cost_sum_sql("cost_key")} AS cost_total_usd
            FROM scoped_sessions AS sessions
            LEFT JOIN current_session_spans AS spans
                ON sessions.workspace = spans.workspace
                AND sessions.session_id = spans.session_id
                AND spans.is_deleted = 0
            GROUP BY sessions.workspace, sessions.session_id
        ),
        root_spans AS (
            SELECT
                sessions.workspace AS workspace,
                sessions.session_id AS session_id,
                spans.status AS status,
                spans.input AS input
            FROM scoped_sessions AS sessions
            LEFT JOIN current_session_spans AS spans
                ON sessions.workspace = spans.workspace
                AND sessions.session_id = spans.session_id
                AND sessions.root_span_id = spans.external_span_id
                AND spans.is_deleted = 0
        ),
        hydrated AS (
            SELECT
                s.workspace AS workspace,
                s.experiment_id AS experiment_id,
                s.session_id AS session_id,
                s.test_case_id AS test_case_id,
                s.trace_id AS trace_id,
                s.root_span_id AS root_span_id,
                s.start_time AS start_time,
                s.end_time AS end_time,
                s.latency_ms AS latency_ms,
                coalesce(r.status, 'unknown') AS root_span_status,
                r.input AS input,
                a.input_tokens AS input_tokens,
                a.output_tokens AS output_tokens,
                a.cached_tokens AS cached_tokens,
                a.cost_total_usd AS cost_total_usd
            FROM scoped_sessions AS s
            LEFT JOIN root_spans AS r
                ON s.workspace = r.workspace AND s.session_id = r.session_id
            LEFT JOIN session_aggregates AS a
                ON s.workspace = a.workspace AND s.session_id = a.session_id
        )
    """


def _token_sum_sql(parameter_name: str) -> str:
    key = f"%({parameter_name})s"
    return f"""
        if(
            countIf(has(mapKeys(spans.attributes_number), {key})) = 0,
            NULL,
            sumIf(spans.attributes_number[{key}], has(mapKeys(spans.attributes_number), {key}))
        )
    """


def _cost_sum_sql(parameter_name: str) -> str:
    key = f"%({parameter_name})s"
    return f"""
        if(
            countIf(has(mapKeys(spans.attributes_number), {key})) = 0,
            NULL,
            sumIf(spans.attributes_number[{key}], has(mapKeys(spans.attributes_number), {key})) / {COST_SCALE}
        )
    """


def _count_sql(*, sessions_table: str, spans_table: str, outer_filter_sql: str) -> str:
    return f"""
        {_hydrated_sessions_cte(sessions_table, spans_table)}
        SELECT count()
        FROM hydrated
        WHERE {outer_filter_sql}
    """


def _list_sql(*, sessions_table: str, spans_table: str, outer_filter_sql: str) -> str:
    return f"""
        {_hydrated_sessions_cte(sessions_table, spans_table)}
        SELECT
            workspace,
            experiment_id,
            session_id,
            test_case_id,
            trace_id,
            root_span_id,
            start_time,
            end_time,
            latency_ms,
            root_span_status,
            input,
            input_tokens,
            output_tokens,
            cached_tokens,
            cost_total_usd
        FROM hydrated
        WHERE {outer_filter_sql}
        ORDER BY start_time ASC, root_span_id ASC
        LIMIT %(limit)s OFFSET %(offset)s
    """


def _session_id_parameters(session_ids: list[str]) -> tuple[str, dict[str, str]]:
    parameters = {f"session_id_{index}": session_id for index, session_id in enumerate(session_ids)}
    placeholders = ", ".join(f"%({name})s" for name in parameters)
    return placeholders, parameters


def _row(record: dict[str, Any]) -> ExperimentSessionRow:
    return ExperimentSessionRow(
        workspace=record["workspace"],
        experiment_name=record["experiment_id"],
        session_id=record["session_id"],
        test_case_id=_str_or_none(record["test_case_id"]),
        trace_id=record["trace_id"],
        root_span_id=record["root_span_id"],
        started_at=record["start_time"],
        ended_at=record["end_time"],
        latency_ms=_float_or_none(record["latency_ms"]),
        status=normalize_span_status(record["root_span_status"]),
        input=_str_or_none(record["input"]),
        input_tokens=_int_or_none(record["input_tokens"]),
        output_tokens=_int_or_none(record["output_tokens"]),
        cached_tokens=_int_or_none(record["cached_tokens"]),
        cost_total_usd=_float_or_none(record["cost_total_usd"]),
    )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _str_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)
