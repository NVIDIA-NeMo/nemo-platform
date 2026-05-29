# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse implementation of Intake trace reads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from nmp.common.api.common import PaginatedResult
from nmp.intake.spans.clickhouse.dao import ClickHouseDao
from nmp.intake.spans.clickhouse.filters import trace_outer_where
from nmp.intake.spans.clickhouse.query import order_by_clause
from nmp.intake.spans.clickhouse.trace_queries import METRIC_ATTRIBUTE_FIELDS, trace_rows_sql
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import IntakeTrace, TraceEvaluationContext, TraceListFilter, TraceMode
from nmp.intake.spans.span_attribute_bags import SpanAttributeBags
from nmp.intake.spans.span_semantic_attributes import SpanSemanticAttributes
from nmp.intake.spans.storage import make_pagination, normalize_span_status

TRACE_SORT_COLUMNS = {
    "started_at": "started_at",
}

TRACE_COLUMNS = [
    "id",
    "workspace",
    "session_id",
    "source_format",
    "root_span_id",
    "name",
    "input",
    "output",
    "started_at",
    "ended_at",
    "status",
    *METRIC_ATTRIBUTE_FIELDS.keys(),
    "models",
    "providers",
    "span_count",
    "error_count",
    "root_attributes_string",
    "ingested_at",
]

_ZERO_DATETIME = datetime.fromtimestamp(0, tz=timezone.utc)


class TraceRepository:
    def __init__(self, client: ClickHouseSpanClient) -> None:
        self._dao = ClickHouseDao(client)
        self._spans_table = self._dao.table("spans")

    async def list_traces(
        self,
        *,
        filters: TraceListFilter,
        page: int,
        page_size: int,
        sort: str,
        mode: TraceMode,
    ) -> PaginatedResult[IntakeTrace]:
        trace_query = trace_rows_sql(self._spans_table, filters, mode=mode)
        rows, total_results = await self._dao.paginate_subquery(
            subquery=trace_query,
            outer_where=trace_outer_where(filters),
            sort=sort,
            sort_columns=TRACE_SORT_COLUMNS,
            tiebreaker="id",
            sort_label="trace",
            page=page,
            page_size=page_size,
        )
        traces = [_row_to_trace(row) for row in rows]
        return PaginatedResult(
            data=traces,
            pagination=make_pagination(
                page=page,
                page_size=page_size,
                current_page_size=len(traces),
                total_results=total_results,
            ),
        )

    async def get_trace(self, *, workspace: str, trace_id: str, mode: TraceMode) -> IntakeTrace | None:
        result = await self.list_traces(
            filters=TraceListFilter(workspace=workspace, trace_id=trace_id),
            page=1,
            page_size=1,
            sort="-started_at",
            mode=mode,
        )
        return result.data[0] if result.data else None


def _order_by(sort: str) -> str:
    return order_by_clause(
        sort,
        sort_columns=TRACE_SORT_COLUMNS,
        tiebreaker="id",
        label="trace",
    )


def _row_to_trace(row: dict[str, Any]) -> IntakeTrace:
    root_attributes = dict(row.get("root_attributes_string") or {})
    attribute_bags = SpanAttributeBags.from_domain_maps(
        attributes_string=root_attributes,
        attributes_number={},
        attributes_bool={},
    )
    semantic_attributes = SpanSemanticAttributes.from_bags(attribute_bags)
    ended_at = _none_if_zero_datetime(row.get("ended_at"))
    return IntakeTrace(
        id=row["id"],
        root_span_id=row.get("root_span_id") or None,
        workspace=row["workspace"],
        session_id=row["session_id"],
        source_format=row["source_format"],
        name=row.get("name") or None,
        input=row.get("input") or None,
        output=row.get("output") or None,
        project=semantic_attributes.project,
        evaluation_context=_evaluation_context(semantic_attributes, attribute_bags),
        started_at=row["started_at"],
        ended_at=ended_at,
        duration_ms=_duration_ms(row["started_at"], ended_at),
        ingested_at=row["ingested_at"],
        status=normalize_span_status(row.get("status")),
        input_tokens=_int_or_none(row.get("input_tokens")),
        output_tokens=_int_or_none(row.get("output_tokens")),
        cached_tokens=_int_or_none(row.get("cached_tokens")),
        total_tokens=_int_or_none(row.get("total_tokens")),
        cost_usd=_float_or_none(row.get("cost_usd")),
        cost_input_usd=_float_or_none(row.get("cost_input_usd")),
        cost_output_usd=_float_or_none(row.get("cost_output_usd")),
        models=_string_list_or_none(row.get("models")),
        providers=_string_list_or_none(row.get("providers")),
        span_count=_int_or_none(row.get("span_count")),
        error_count=_int_or_none(row.get("error_count")),
    )


def _evaluation_context(
    attributes: SpanSemanticAttributes,
    attribute_bags: SpanAttributeBags,
) -> TraceEvaluationContext | None:
    metadata = attribute_bags.evaluation_metadata()
    context = TraceEvaluationContext(
        evaluation_id=attributes.evaluation_id,
        evaluation_sha=attributes.evaluation_sha,
        evaluation_run_id=attributes.evaluation_run_id,
        dataset_id=attributes.dataset_id,
        dataset_name=attributes.dataset_name,
        dataset_version=attributes.dataset_version,
        test_case_id=attributes.test_case_id,
        metadata=metadata or {},
    )
    if metadata is None and not context.has_scalar_values():
        return None
    return context


def _duration_ms(started_at: datetime, ended_at: datetime | None) -> float | None:
    if ended_at is None:
        return None
    return (ended_at - started_at).total_seconds() * 1000


def _none_if_zero_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if value == _ZERO_DATETIME or value.timestamp() == 0:
        return None
    return value


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _string_list_or_none(value: Any) -> list[str] | None:
    if value is None:
        return None
    values = [str(item) for item in value if str(item)]
    return values
