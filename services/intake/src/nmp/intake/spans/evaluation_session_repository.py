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

# Sort fields that require a pre-pagination spans join to compute. These values live in the
# `spans` table (not `trace_index`), so they don't exist until after the session_metrics join.
# Sorting by them globally requires computing them for ALL sessions before LIMIT/OFFSET runs —
# see `_pre_page_metrics_cte_sql` and the conditional in `_list_sql`.
_PRE_METRICS_SORT_FIELDS = frozenset({"cost_total_usd", "tokens"})

# Maps each API sort field to its SQL expression used in _metric_sort_page_ids_sql (the
# pre-metrics sort query). Simple fields come from scoped_sessions (aliased as `s`);
# pre-metrics fields reference the pre_page_metrics CTE (aliased as `pm`). This map is
# NOT used by _list_sql — that path only handles trace_index columns and uses plain names.
_SORT_EXPR_PAGE: dict[str, str] = {
    "started_at": "start_time",
    "ended_at": "end_time",
    "latency_ms": "latency_ms",
    "status": "root_span_status",
    "test_case_id": "test_case_id",
    "cost_total_usd": "pm.cost_total_usd",
    "tokens": "pm.total_tokens",
}

# Same mapping for the final SELECT's ORDER BY. At that point scoped_sessions columns
# are behind the `sessions` alias, and cost/tokens come from the `metrics` CTE
# (session_metrics, computed for just the page).
_SORT_EXPR_FINAL: dict[str, str] = {
    "started_at": "sessions.start_time",
    "ended_at": "sessions.end_time",
    "latency_ms": "sessions.latency_ms",
    "status": "sessions.root_span_status",
    "test_case_id": "sessions.test_case_id",
    "cost_total_usd": "metrics.cost_total_usd",
    # Preserve NULL only when both input and output are absent (no span data at all).
    # If only one side is NULL (e.g. a failed call with no output tokens but real input tokens),
    # coalesce to 0 so the session sorts by its actual partial usage rather than disappearing
    # to the bottom via NULLS LAST.
    "tokens": (
        "if(metrics.input_tokens IS NULL AND metrics.output_tokens IS NULL, NULL, "
        "coalesce(metrics.input_tokens, 0) + coalesce(metrics.output_tokens, 0))"
    ),
}


# Sessions above this threshold will not be sorted by cost or tokens. Pre-metrics sort joins
# spans for EVERY scoped session before paginating — an unbounded aggregation on the request
# path. Mirror the evaluations list cap (_MAX_GROUP_EVALUATIONS) to prevent runaway queries.
# Raise this if legitimate evaluations routinely exceed it; the right long-term fix is to
# denormalise cost/tokens into trace_index so no pre-pagination join is needed.
_MAX_METRIC_SORT_SESSIONS = 10_000


class MetricSortTooLargeError(Exception):
    """Raised when a cost/tokens sort is requested on more sessions than the pre-metrics cap allows.

    This is a domain exception (not HTTPException) so the repository stays HTTP-agnostic.
    The endpoint catches it and converts it to 413.
    """

    def __init__(self, total: int, limit: int) -> None:
        self.total = total
        self.limit = limit
        super().__init__(f"Metric sort requested on {total} sessions, limit is {limit}")


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
        sort_keys: list[tuple[str, bool]] | None = None,
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

        needs_pre_metrics = sort_keys is not None and any(f in _PRE_METRICS_SORT_FIELDS for f, _ in sort_keys)
        if needs_pre_metrics and total > _MAX_METRIC_SORT_SESSIONS:
            raise MetricSortTooLargeError(total, _MAX_METRIC_SORT_SESSIONS)

        offset = (page - 1) * page_size

        if needs_pre_metrics:
            # Two-query path for cost/tokens sorts.
            #
            # ClickHouse 24.3 inlines CTEs (does not materialise them), so a single query that
            # references `page_sessions` from multiple downstream CTEs (current_page_spans,
            # session_metrics, session_scores, final SELECT) would re-execute the expensive
            # all-session span aggregation once per reference. Splitting into two queries
            # ensures the aggregation runs exactly once.
            #
            # Query 2: compute the sorted page — aggregate cost/tokens once across all sessions,
            # apply ORDER BY + LIMIT/OFFSET, return ordered (workspace, session_id) pairs only.
            page_ids_sql = _metric_sort_page_ids_sql(
                trace_index_table=trace_index_table,
                spans_table=spans_table,
                scoped_filter_sql=scoped_filter_sql,
                sort_keys=sort_keys,  # type: ignore[arg-type]  # guaranteed non-None here
            )
            page_ids_result = await self._client.query(
                page_ids_sql,
                parameters={
                    **base_parameters,
                    **scoped_filter_parameters,
                    "limit": page_size,
                    "offset": offset,
                },
            )
            ordered_ids = [record["session_id"] for record in result_rows(page_ids_result)]

            if not ordered_ids:
                return EvaluationSessionPage(rows=[], total=total)

            # Query 3: hydrate those session IDs — fetch session fields, page-only span metrics,
            # and evaluator scores. Returns rows in unspecified order; we restore Query 2's
            # ordering in Python after the fetch.
            hydrate_sql = _hydrate_by_ids_sql(
                trace_index_table=trace_index_table,
                spans_table=spans_table,
                evaluator_results_table=evaluator_results_table,
                mode=mode,
            )
            hydrate_result = await self._client.query(
                hydrate_sql,
                parameters={
                    **base_parameters,
                    **text_query_parameters(mode),
                    "session_ids": ordered_ids,
                },
            )
            rows_by_id = {record["session_id"]: _row(record) for record in result_rows(hydrate_result)}
            # Restore the order from Query 2. `rows_by_id` may be missing a session_id if a
            # race caused the trace_index to disagree between queries, so guard with `if sid in`.
            rows = [rows_by_id[sid] for sid in ordered_ids if sid in rows_by_id]
        else:
            # Single-query path for trace_index column sorts (started_at, latency_ms, etc.).
            # No pre-metrics join needed; ClickHouse CTE inlining is harmless here because
            # page_sessions doesn't depend on an expensive aggregation.
            list_sql = _list_sql(
                trace_index_table=trace_index_table,
                spans_table=spans_table,
                evaluator_results_table=evaluator_results_table,
                scoped_filter_sql=scoped_filter_sql,
                mode=mode,
                sort_keys=sort_keys or [],
            )
            list_parameters = {
                **base_parameters,
                **scoped_filter_parameters,
                **text_query_parameters(mode),
                "limit": page_size,
                "offset": offset,
            }
            list_result = await self._client.query(list_sql, parameters=list_parameters)
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


def _build_order_by(sort_keys: list[tuple[str, bool]], expr_map: dict[str, str], tiebreaker: str) -> str:
    """Build a comma-separated ORDER BY clause from an ordered list of (field, descending) pairs.

    Each field is looked up in expr_map to get its SQL expression in the current query scope
    (column names differ between page_sessions and the final SELECT — callers pass the right map).
    NULLS LAST on every user key so missing values sort at the end rather than the front.
    Always appends tiebreaker as the final stable sort key so pages are deterministic when the
    user's keys produce ties.
    """
    parts = [f"{expr_map[field]} {'DESC' if desc else 'ASC'} NULLS LAST" for field, desc in sort_keys]
    parts.append(tiebreaker)
    return ", ".join(parts)


def _metric_sort_page_ids_sql(
    *,
    trace_index_table: str,
    spans_table: str,
    scoped_filter_sql: str,
    sort_keys: list[tuple[str, bool]],
) -> str:
    """Query 2 of the two-query pre-metrics sort path.

    Aggregates cost/tokens across ALL scoped sessions exactly once, then applies
    ORDER BY + LIMIT/OFFSET to return the ordered (workspace, session_id) pairs for
    the requested page. Only IDs are returned — row hydration is a separate query.

    Why separate: ClickHouse 24.3 inlines CTEs rather than materialising them, so a
    single query that references `page_sessions` from multiple CTEs would re-execute
    the expensive all-session span aggregation once per reference. Returning IDs here
    and hydrating in _hydrate_by_ids_sql ensures the aggregation runs exactly once.
    """
    # summary mode: text payloads are not needed for sorting
    scoped_sessions_sql = _scoped_sessions_sql(
        trace_index_table,
        scoped_filter_sql=scoped_filter_sql,
        mode="summary",
    )
    all_scoped_spans = current_spans_sql(
        spans_table,
        extra_where_sql=(
            "(span_versions.workspace, span_versions.session_id) IN (SELECT workspace, session_id FROM scoped_sessions)"
        ),
    )
    order_by = _build_order_by(sort_keys, _SORT_EXPR_PAGE, "s.root_span_id ASC")
    return f"""
        WITH
        scoped_sessions AS (
            {scoped_sessions_sql}
        ),
        pre_page_metrics AS (
            SELECT
                s.workspace AS workspace,
                s.session_id AS session_id,
                {_guarded_sum_sql("cost_key", scale=COST_SCALE)} AS cost_total_usd,
                if(
                    {_guarded_sum_sql("input_tokens_key")} IS NULL AND {_guarded_sum_sql("output_tokens_key")} IS NULL,
                    NULL,
                    coalesce({_guarded_sum_sql("input_tokens_key")}, 0) + coalesce({_guarded_sum_sql("output_tokens_key")}, 0)
                ) AS total_tokens
            FROM scoped_sessions AS s
            LEFT JOIN {all_scoped_spans} AS spans
                ON s.workspace = spans.workspace
                AND s.session_id = spans.session_id
                AND spans.is_deleted = 0
            GROUP BY s.workspace, s.session_id
        )
        SELECT s.workspace, s.session_id
        FROM scoped_sessions AS s
        LEFT JOIN pre_page_metrics AS pm
            ON s.workspace = pm.workspace AND s.session_id = pm.session_id
        ORDER BY {order_by}
        LIMIT %(limit)s OFFSET %(offset)s
    """


def _hydrate_by_ids_sql(
    *,
    trace_index_table: str,
    spans_table: str,
    evaluator_results_table: str,
    mode: IntakeResponseMode,
) -> str:
    """Query 3 of the two-query pre-metrics sort path.

    Given a list of session_ids (passed as %(session_ids)s), fetches the full row for
    each session: trace_index fields, per-page span metrics, and evaluator scores.
    Returns rows in unspecified order — the caller restores the ordering from Query 2
    in Python after the fetch.

    No ORDER BY is emitted; no pre_page_metrics join is needed (the aggregation here
    is bounded to the page, which is at most 1000 rows).
    """
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

    page_spans = current_spans_sql(
        spans_table,
        extra_where_sql=(
            "(span_versions.workspace, span_versions.session_id) IN (SELECT workspace, session_id FROM page_sessions)"
        ),
    )

    return f"""
        WITH
        page_sessions AS (
            SELECT
                {select_sql}
            FROM {trace_index_table} FINAL
            WHERE workspace = %(workspace)s
                AND is_deleted = 0
                AND evaluation_id = %(evaluation_name)s
                AND session_id IN %(session_ids)s
            LIMIT 1 BY workspace, session_id, evaluation_id
        ),
        current_page_spans AS (
            {page_spans}
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
    """


def _list_sql(
    *,
    trace_index_table: str,
    spans_table: str,
    evaluator_results_table: str,
    scoped_filter_sql: str,
    mode: IntakeResponseMode,
    sort_keys: list[tuple[str, bool]],
) -> str:
    """Single-query path for trace_index column sorts (started_at, latency_ms, etc.).

    Only called when no sort field requires the pre-metrics spans join (i.e. no cost/tokens
    sort). ClickHouse CTE inlining is harmless here because page_sessions doesn't depend on
    an expensive all-session aggregation.
    """
    scoped_sessions_sql = _scoped_sessions_sql(
        trace_index_table,
        scoped_filter_sql=scoped_filter_sql,
        mode=mode,
    )
    # Empty sort_keys means no sort param — preserve the original default order.
    page_order_by = (
        _build_order_by(sort_keys, _SORT_EXPR_PAGE, "root_span_id ASC")
        if sort_keys
        else "start_time ASC, root_span_id ASC"
    )
    # The final SELECT re-orders already-paginated rows as they emerge from the CTE joins.
    # ClickHouse does not guarantee CTE output order, so this ORDER BY must match page_order_by.
    final_order_by = (
        _build_order_by(sort_keys, _SORT_EXPR_FINAL, "sessions.root_span_id ASC")
        if sort_keys
        else "sessions.start_time ASC, sessions.root_span_id ASC"
    )
    current_page_spans = current_spans_sql(
        spans_table,
        extra_where_sql=(
            "(span_versions.workspace, span_versions.session_id) IN (SELECT workspace, session_id FROM page_sessions)"
        ),
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
            ORDER BY {page_order_by}
            LIMIT %(limit)s OFFSET %(offset)s
        ),
        current_page_spans AS (
            {current_page_spans}
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
        ORDER BY {final_order_by}
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
