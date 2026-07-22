# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse implementation of Intake session detail reads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import IntakeSession
from nmp.intake.spans.span_rollups import METRIC_ATTRIBUTE_FIELDS, metric_aggregate_columns
from nmp.intake.spans.storage import float_or_none, int_or_none, normalize_span_status, result_rows

SESSION_COLUMNS = [
    "id",
    "workspace",
    "started_at",
    "ended_at",
    "status",
    *METRIC_ATTRIBUTE_FIELDS.keys(),
    "trace_count",
    "span_count",
]


class SessionRepository:
    def __init__(self, client: ClickHouseSpanClient) -> None:
        self._client = client

    async def get_session(self, *, workspace: str, session_id: str) -> IntakeSession | None:
        query, parameters = session_detail_sql(self._client.table("spans"))
        result = await self._client.query(
            query,
            parameters={**parameters, "workspace": workspace, "session_id": session_id},
        )
        rows = result_rows(result)
        return _row_to_session(rows[0]) if rows else None


def session_detail_sql(table: str) -> tuple[str, dict[str, Any]]:
    """Return a primary-key-pruned aggregate over the current rows of one session."""

    source_alias = "session_spans"
    metric_columns, parameters = metric_aggregate_columns(source_alias)
    query = f"""
        SELECT
            %(session_id)s AS id,
            any({source_alias}.workspace) AS workspace,
            min({source_alias}.start_time) AS started_at,
            if(
                countIf({source_alias}.end_time = toDateTime64(0, 6)) > 0,
                NULL,
                max({source_alias}.end_time)
            ) AS ended_at,
            multiIf(
                countIf({source_alias}.status = 'error') > 0, 'error',
                countIf({source_alias}.status = 'cancelled') > 0, 'cancelled',
                countIf({source_alias}.status = 'unknown') > 0, 'unknown',
                'success'
            ) AS status,
            {metric_columns},
            uniqExact({source_alias}.source_format, {source_alias}.trace_id) AS trace_count,
            count() AS span_count
        FROM {table} AS {source_alias} FINAL
        PREWHERE
            {source_alias}.workspace = %(workspace)s
            AND {source_alias}.session_id = %(session_id)s
        WHERE {source_alias}.is_deleted = 0
        HAVING span_count > 0
    """
    return query, parameters


def _row_to_session(row: dict[str, Any]) -> IntakeSession:
    ended_at = row.get("ended_at")
    return IntakeSession(
        id=row["id"],
        workspace=row["workspace"],
        started_at=row["started_at"],
        ended_at=ended_at,
        duration_ms=_duration_ms(row["started_at"], ended_at),
        status=normalize_span_status(row.get("status")),
        input_tokens=int_or_none(row.get("input_tokens")),
        output_tokens=int_or_none(row.get("output_tokens")),
        cached_tokens=int_or_none(row.get("cached_tokens")),
        total_tokens=int_or_none(row.get("total_tokens")),
        cost_usd=float_or_none(row.get("cost_usd")),
        cost_input_usd=float_or_none(row.get("cost_input_usd")),
        cost_output_usd=float_or_none(row.get("cost_output_usd")),
        trace_count=int(row["trace_count"]),
        span_count=int(row["span_count"]),
    )


def _duration_ms(started_at: datetime, ended_at: datetime | None) -> float | None:
    if ended_at is None:
        return None
    return (ended_at - started_at).total_seconds() * 1000
