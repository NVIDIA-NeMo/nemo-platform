# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Session repository tests."""

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.session_repository import SESSION_COLUMNS, SessionRepository, session_detail_sql


class _QueryResult:
    def __init__(self, rows: list[tuple[object, ...]], columns: list[str] | None = None) -> None:
        self.result_rows = rows
        self.column_names = columns or []


class _Client:
    def __init__(self, query_result: _QueryResult | None = None) -> None:
        self.query_result = query_result or _QueryResult([])
        self.queries: list[str] = []
        self.parameters: list[dict[str, object]] = []

    def table(self, name: str) -> str:
        return name

    async def query(self, query: str, *, parameters: dict[str, object]) -> _QueryResult:
        self.queries.append(query)
        self.parameters.append(parameters)
        return self.query_result


def _repository(client: _Client) -> SessionRepository:
    return SessionRepository(cast(ClickHouseSpanClient, client))


def test_session_query_is_primary_key_pruned_and_payload_free() -> None:
    query, parameters = session_detail_sql("spans")

    assert "FROM spans AS session_spans FINAL" in query
    assert "PREWHERE" in query
    assert "session_spans.workspace = %(workspace)s" in query
    assert "session_spans.session_id = %(session_id)s" in query
    assert "trace_index" not in query
    assert "JOIN" not in query
    assert "session_spans.input" not in query
    assert "session_spans.output" not in query
    assert "uniqExact(session_spans.source_format, session_spans.trace_id) AS trace_count" in query
    assert "count() AS span_count" in query
    assert parameters["input_tokens_key"] == "llm.token_count.prompt"
    assert parameters["cost_usd_key"] == "cost.total"


@pytest.mark.asyncio
async def test_get_session_maps_aggregate_row() -> None:
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ended_at = started_at + timedelta(seconds=8)
    values: dict[str, object | None] = {
        "id": "session-a",
        "workspace": "workspace-a",
        "started_at": started_at,
        "ended_at": ended_at,
        "status": "error",
        "input_tokens": 420,
        "output_tokens": 310,
        "cached_tokens": 128,
        "total_tokens": 858,
        "cost_usd": 0.0061,
        "cost_input_usd": 0.0024,
        "cost_output_usd": 0.0037,
        "trace_count": 2,
        "span_count": 5,
    }
    row = tuple(values[column] for column in SESSION_COLUMNS)
    client = _Client(_QueryResult([row], SESSION_COLUMNS))

    session = await _repository(client).get_session(workspace="workspace-a", session_id="session-a")

    assert session is not None
    assert session.id == "session-a"
    assert session.workspace == "workspace-a"
    assert session.started_at == started_at
    assert session.ended_at == ended_at
    assert session.duration_ms == 8000
    assert session.status.value == "error"
    assert session.trace_count == 2
    assert session.span_count == 5
    assert session.total_tokens == 858
    assert session.cost_usd == 0.0061
    assert client.parameters[0]["workspace"] == "workspace-a"
    assert client.parameters[0]["session_id"] == "session-a"


@pytest.mark.asyncio
async def test_get_session_returns_none_when_no_current_spans_exist() -> None:
    session = await _repository(_Client()).get_session(workspace="workspace-a", session_id="missing")

    assert session is None
