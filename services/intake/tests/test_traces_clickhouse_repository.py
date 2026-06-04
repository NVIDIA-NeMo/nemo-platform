# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trace repository tests."""

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import SpanAttributeFilter, TraceListFilter
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
    assert "FINAL" not in client.queries[0]
    assert (
        "argMax(span_versions.status, (span_versions.event_ts, span_versions.is_deleted)) AS status"
        in client.queries[0]
    )
    assert "AS root_spans" in client.queries[0]
    assert "root_spans.external_parent_span_id = ''" in client.queries[0]
    assert "LIMIT 1 BY root_spans.workspace, root_spans.source_format, root_spans.trace_id" in client.queries[0]
    assert "sumIf" not in client.queries[0]
    assert "groupUniqArrayIf" not in client.queries[0]


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

    assert "FINAL" not in client.queries[0]
    assert "AS root_spans" in client.queries[0]
    assert "AS trace_spans" in client.queries[0]
    assert "sumIf" in client.queries[0]
    assert "groupUniqArrayIf" in client.queries[0]
    assert "count() AS span_count" in client.queries[0]


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
    assert trace.input == "root input"
    assert trace.output == "root output"
    assert trace.duration_ms == 2500
    assert trace.project == "project-a"
    assert trace.evaluation_context is not None
    assert trace.evaluation_context.evaluation_run_id == "run-a"
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
async def test_trace_started_at_filter_is_applied_to_root_spans():
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

    assert "root_spans.start_time >= %(started_at_gte)s" in client.queries[0]
    assert client.parameters[0]["started_at_gte"] == started_at


@pytest.mark.asyncio
async def test_root_and_any_span_filters_select_candidate_trace_ids():
    client = _Client()
    repository = _repository(client)

    await repository.list_traces(
        filters=TraceListFilter(
            workspace="workspace-a",
            root_attribute_filters=[
                SpanAttributeFilter(field="evaluation_run_id", operator="$eq", value="run-a"),
            ],
            span_attribute_filters=[
                SpanAttributeFilter(field="model", operator="$eq", value="model-a"),
            ],
        ),
        page=1,
        page_size=10,
        sort="started_at",
        mode="detailed",
    )

    assert "(root_spans.workspace, root_spans.source_format, root_spans.trace_id) IN" in client.queries[0]
    assert "(trace_spans.workspace, trace_spans.source_format, trace_spans.trace_id) IN" in client.queries[0]
    assert "FINAL" not in client.queries[0]
    assert "external_parent_span_id = ''" in client.queries[0]
    assert client.parameters[0]["root_candidate_0_key"] == "experiment.run_id"
    assert client.parameters[0]["root_candidate_0_value"] == "run-a"
    assert client.parameters[0]["span_candidate_0_key"] == "gen_ai.request.model"
    assert client.parameters[0]["span_candidate_0_value"] == "model-a"


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
        "input": "root input",
        "output": "root output",
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
        "root_attributes_string": {
            "project.name": "project-a",
            "experiment.run_id": "run-a",
        },
        "ingested_at": ingested_at,
    }
    return tuple(values[column] for column in TRACE_COLUMNS)
