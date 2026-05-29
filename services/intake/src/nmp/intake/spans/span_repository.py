# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse implementation of Intake span storage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from nmp.common.api.common import PaginatedResult
from nmp.intake.spans.clickhouse.dao import ClickHouseDao
from nmp.intake.spans.clickhouse.filters import span_list_where, span_lookup_where
from nmp.intake.spans.clickhouse.query import order_by_clause
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import IntakeSpan, SpanListFilter
from nmp.intake.spans.storage import (
    dict_to_row,
    make_pagination,
    normalize_span_kind,
    normalize_span_status,
)

SPAN_COLUMNS = [
    "workspace",
    "session_id",
    "trace_id",
    "id",
    "source_format",
    "external_span_id",
    "external_parent_span_id",
    "kind",
    "name",
    "status",
    "start_time",
    "end_time",
    "attributes_string",
    "attributes_number",
    "attributes_bool",
    "input",
    "output",
    "event_ts",
    "is_deleted",
]
SPAN_INSERT_COLUMNS = [column_name for column_name in SPAN_COLUMNS if column_name != "id"]

SPAN_SORT_COLUMNS = {
    "started_at": "start_time",
}

_ZERO_DATETIME = datetime.fromtimestamp(0, tz=timezone.utc)


class SpanRepository:
    def __init__(self, client: ClickHouseSpanClient) -> None:
        self._dao = ClickHouseDao(client)

    async def save_spans(self, spans: list[IntakeSpan]) -> None:
        rows = [dict_to_row(_span_to_row(span), SPAN_INSERT_COLUMNS) for span in spans]
        await self._dao.insert_rows("spans", rows, column_names=SPAN_INSERT_COLUMNS)

    async def list_spans(
        self,
        *,
        filters: SpanListFilter,
        page: int,
        page_size: int,
        sort: str,
    ) -> PaginatedResult[IntakeSpan]:
        rows, total_results = await self._dao.paginate(
            table=self._dao.table("spans"),
            where=span_list_where(filters),
            columns=SPAN_COLUMNS,
            sort=sort,
            sort_columns=SPAN_SORT_COLUMNS,
            tiebreaker="id",
            sort_label="span",
            page=page,
            page_size=page_size,
            final=True,
        )
        spans = _rows_to_spans(rows)
        return PaginatedResult(
            data=spans,
            pagination=make_pagination(
                page=page, page_size=page_size, current_page_size=len(spans), total_results=total_results
            ),
        )

    async def get_span(self, *, workspace: str, span_id: str) -> IntakeSpan | None:
        row = await self._dao.fetch_one(
            self._dao.table("spans"),
            span_lookup_where(workspace=workspace, span_id=span_id),
            columns=SPAN_COLUMNS,
            final=True,
        )
        if row is None:
            return None
        return _row_to_span(row)


def _order_by(sort: str) -> str:
    return order_by_clause(
        sort,
        sort_columns=SPAN_SORT_COLUMNS,
        tiebreaker="id",
        label="span",
    )


def _span_to_row(span: IntakeSpan) -> dict[str, Any]:
    return {
        "workspace": span.workspace,
        "session_id": span.session_id,
        "trace_id": span.trace_id,
        "source_format": span.source_format,
        "external_span_id": span.external_span_id,
        "external_parent_span_id": span.external_parent_span_id,
        "kind": span.kind.value,
        "name": span.name,
        "status": span.status.value,
        "start_time": span.start_time,
        "end_time": span.end_time or _ZERO_DATETIME,
        "attributes_string": span.attributes_string,
        "attributes_number": {key: float(value) for key, value in span.attributes_number.items()},
        "attributes_bool": span.attributes_bool,
        "input": span.input,
        "output": span.output,
        "event_ts": span.event_ts,
        "is_deleted": span.is_deleted,
    }


def _rows_to_spans(rows: list[dict[str, Any]]) -> list[IntakeSpan]:
    # Parent linkage is reconstructed only within the returned result set. Partial
    # views still expose external_parent_span_id for clients that need full trace assembly.
    id_by_external = {
        (row["workspace"], row["source_format"], row["trace_id"], row["external_span_id"]): int(row["id"])
        for row in rows
    }
    return [_row_to_span(row, id_by_external=id_by_external) for row in rows]


def _row_to_span(
    row: dict[str, Any],
    *,
    id_by_external: dict[tuple[str, str, str, str], int] | None = None,
) -> IntakeSpan:
    parent_id = None
    external_parent_span_id = row.get("external_parent_span_id") or ""
    if external_parent_span_id and id_by_external is not None:
        parent_id = id_by_external.get(
            (row["workspace"], row["source_format"], row["trace_id"], external_parent_span_id)
        )
    return IntakeSpan(
        workspace=row["workspace"],
        session_id=row["session_id"],
        trace_id=row["trace_id"],
        id=int(row["id"]),
        source_format=row["source_format"],
        external_span_id=row["external_span_id"],
        external_parent_span_id=external_parent_span_id,
        parent_id=parent_id,
        kind=normalize_span_kind(row.get("kind")),
        name=row.get("name") or "",
        status=normalize_span_status(row.get("status")),
        start_time=row["start_time"],
        end_time=_none_if_zero_datetime(row.get("end_time")),
        attributes_string=dict(row.get("attributes_string") or {}),
        attributes_number={key: float(value) for key, value in dict(row.get("attributes_number") or {}).items()},
        attributes_bool={key: bool(value) for key, value in dict(row.get("attributes_bool") or {}).items()},
        input=row.get("input") or "",
        output=row.get("output") or "",
        event_ts=row["event_ts"],
        is_deleted=int(row.get("is_deleted") or 0),
    )


def _none_if_zero_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if value.timestamp() == 0:
        return None
    return value
