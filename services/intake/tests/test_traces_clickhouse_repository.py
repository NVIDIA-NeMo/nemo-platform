# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trace repository tests."""

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import TraceListFilter
from nmp.intake.spans.trace_repository import TRACE_COLUMNS, TraceRepository, _order_by


class _QueryResult:
    def __init__(self, rows: list[tuple[object, ...]], columns: list[str] | None = None) -> None:
        self.result_rows = rows
        self.column_names = columns or []


class _Client:
    def __init__(self, query_results: list[_QueryResult] | None = None) -> None:
        self.queries: list[str] = []
        self.parameters: list[dict[str, object]] = []
        self.query_results = query_results or []

    def table(self, name: str) -> str:
        return name

    async def query(self, query: str, *, parameters: dict[str, object]) -> _QueryResult:
        self.queries.append(query)
        self.parameters.append(parameters)
        if self.query_results:
            return self.query_results.pop(0)
        if query.lstrip().startswith("SELECT count()"):
            return _QueryResult([(0,)])
        return _QueryResult([])


def _repository(client: _Client) -> TraceRepository:
    return TraceRepository(cast(ClickHouseSpanClient, client))


def test_order_by_whitelists_supported_trace_sort_keys():
    assert _order_by("started_at") == "started_at ASC, id ASC"
    assert _order_by("-started_at") == "started_at DESC, id ASC"


def test_order_by_rejects_unsupported_trace_sort_keys():
    with pytest.raises(ValueError, match="Unsupported trace sort field"):
        _order_by("started_at DESC; DROP TABLE spans")


@pytest.mark.asyncio
async def test_summary_mode_reads_root_spans_without_metric_aggregates():
    client = _Client()
    repository = _repository(client)

    await repository.list_traces(
        filters=TraceListFilter(workspace="workspace-a"),
        page=1,
        page_size=10,
        sort="started_at",
        mode="summary",
    )

    assert client.queries[0].lstrip().startswith("SELECT count()")
    assert "FROM trace_index AS trace_roots FINAL" in client.queries[0]
    assert "trace_roots.root_status AS status" in client.queries[0]
    assert "trace_roots.root_input" not in client.queries[0]
    assert "trace_roots.root_output" not in client.queries[0]
    assert "LIMIT 1 BY trace_roots.workspace, trace_roots.source_format, trace_roots.trace_id" in client.queries[0]
    assert "span_versions" not in client.queries[0]
    assert "sumIf" not in client.queries[1]
    assert "groupUniqArrayIf" not in client.queries[1]
    assert "span_versions" not in client.queries[1]


@pytest.mark.asyncio
async def test_detailed_mode_adds_trace_aggregate_block():
    client = _Client()
    repository = _repository(client)

    await repository.list_traces(
        filters=TraceListFilter(workspace="workspace-a"),
        page=1,
        page_size=10,
        sort="started_at",
        mode="detailed",
    )

    assert "FROM trace_index AS trace_roots FINAL" in client.queries[0]
    assert "span_versions" not in client.queries[0]
    assert "page_traces AS" in client.queries[1]
    assert "AS trace_spans" in client.queries[1]
    assert "(span_versions.workspace, span_versions.source_format, span_versions.trace_id) IN" in client.queries[1]
    assert "SELECT workspace, source_format, id FROM page_traces" in client.queries[1]
    assert "argMax(span_versions.input," not in client.queries[1]
    assert "argMax(span_versions.output," not in client.queries[1]
    assert "argMax(span_versions.attributes_string," in client.queries[1]
    assert "argMax(span_versions.attributes_number," in client.queries[1]
    assert "sumIf" in client.queries[1]
    assert "groupUniqArrayIf" in client.queries[1]
    assert "count() AS span_count" in client.queries[1]


@pytest.mark.asyncio
async def test_list_traces_maps_detailed_row():
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ended_at = started_at + timedelta(milliseconds=2500)
    ingested_at = started_at + timedelta(seconds=3)
    row = _trace_row(started_at=started_at, ended_at=ended_at, ingested_at=ingested_at)
    client = _Client(query_results=[_QueryResult([(1,)]), _QueryResult([row], TRACE_COLUMNS)])
    repository = _repository(client)

    result = await repository.list_traces(
        filters=TraceListFilter(workspace="workspace-a"),
        page=1,
        page_size=10,
        sort="-started_at",
        mode="detailed",
    )

    trace = result.data[0]
    assert trace.id == "trace-a"
    assert trace.session_id == "session-a"
    assert trace.root_span_id == "span-root"
    assert trace.name == "root"
    assert trace.input is None
    assert trace.output is None
    assert trace.duration_ms == 2500
    assert trace.project == "project-a"
    assert trace.experiment_id == "experiment-a"
    assert trace.test_case_id == "case-a"
    assert trace.input_tokens == 420
    assert trace.output_tokens == 310
    assert trace.cached_tokens == 128
    assert trace.total_tokens == 858
    assert trace.cost_usd == 0.0061
    assert trace.cost_input_usd == 0.0024
    assert trace.cost_output_usd == 0.0037
    assert trace.models == ["model-a", "model-b"]
    assert trace.providers == ["openai"]
    assert trace.span_count == 3
    assert trace.error_count == 1


@pytest.mark.asyncio
async def test_summary_mode_maps_no_aggregate_fields():
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row = _trace_row(started_at=started_at, ended_at=None, ingested_at=started_at, detailed=False)
    client = _Client(query_results=[_QueryResult([(1,)]), _QueryResult([row], TRACE_COLUMNS)])
    repository = _repository(client)

    result = await repository.list_traces(
        filters=TraceListFilter(workspace="workspace-a"),
        page=1,
        page_size=10,
        sort="-started_at",
        mode="summary",
    )

    trace = result.data[0]
    assert trace.status.value == "error"
    assert trace.input_tokens is None
    assert trace.total_tokens is None
    assert trace.cost_usd is None
    assert trace.models is None
    assert trace.providers is None
    assert trace.span_count is None
    assert trace.error_count is None


@pytest.mark.asyncio
async def test_trace_started_at_filter_is_applied_to_trace_index():
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    client = _Client()
    repository = _repository(client)

    await repository.list_traces(
        filters=TraceListFilter(workspace="workspace-a", started_at_gte=started_at),
        page=1,
        page_size=10,
        sort="started_at",
        mode="summary",
    )

    assert "trace_roots.root_started_at >= %(started_at_gte)s" in client.queries[0]
    assert client.parameters[0]["started_at_gte"] == started_at


@pytest.mark.asyncio
async def test_root_filters_use_trace_index_columns():
    client = _Client()
    repository = _repository(client)

    await repository.list_traces(
        filters=TraceListFilter(
            workspace="workspace-a",
            experiment_id="experiment-a",
        ),
        page=1,
        page_size=10,
        sort="started_at",
        mode="detailed",
    )

    assert "trace_roots.experiment_id = %(filter_experiment_id)s" in client.queries[0]
    assert "candidate_spans" not in client.queries[0]
    assert client.parameters[0]["filter_experiment_id"] == "experiment-a"


def _trace_row(
    *,
    started_at: datetime,
    ended_at: datetime | None,
    ingested_at: datetime,
    detailed: bool = True,
) -> tuple[object, ...]:
    values: dict[str, object | None] = {
        "id": "trace-a",
        "workspace": "workspace-a",
        "session_id": "session-a",
        "source_format": "otel",
        "root_span_id": "span-root",
        "name": "root",
        "project": "project-a",
        "experiment_id": "experiment-a",
        "test_case_id": "case-a",
        "started_at": started_at,
        "ended_at": ended_at,
        "status": "error",
        "input_tokens": 420 if detailed else None,
        "output_tokens": 310 if detailed else None,
        "cached_tokens": 128 if detailed else None,
        "total_tokens": 858 if detailed else None,
        "cost_usd": 0.0061 if detailed else None,
        "cost_input_usd": 0.0024 if detailed else None,
        "cost_output_usd": 0.0037 if detailed else None,
        "models": ["model-a", "model-b"] if detailed else None,
        "providers": ["openai"] if detailed else None,
        "span_count": 3 if detailed else None,
        "error_count": 1 if detailed else None,
        "ingested_at": ingested_at,
    }
    return tuple(values[column] for column in TRACE_COLUMNS)
