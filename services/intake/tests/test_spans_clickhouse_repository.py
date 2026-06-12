# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Span repository tests."""

from datetime import datetime, timezone
from typing import cast

import pytest
from nmp.intake.spans.api.spans_schemas import SpanGroupBy
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import SpanListFilter
from nmp.intake.spans.span_repository import SPAN_COLUMNS, SPAN_GROUP_COLUMN_FIELDS, SpanRepository, _order_by
from nmp.intake.spans.storage import make_pagination


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


def _repository(client: _Client) -> SpanRepository:
    return SpanRepository(cast(ClickHouseSpanClient, client))


def test_order_by_whitelists_supported_span_sort_keys():
    assert _order_by("started_at") == "start_time ASC, id ASC"
    assert _order_by("-started_at") == "start_time DESC, id ASC"


def test_order_by_rejects_unsupported_span_sort_keys():
    with pytest.raises(ValueError, match="Unsupported span sort field"):
        _order_by("started_at DESC; DROP TABLE spans")


def test_make_pagination_computes_total_pages():
    pagination = make_pagination(page=2, page_size=25, current_page_size=10, total_results=60)

    assert pagination.page == 2
    assert pagination.page_size == 25
    assert pagination.current_page_size == 10
    assert pagination.total_results == 60
    assert pagination.total_pages == 3


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"page": 0, "page_size": 10, "current_page_size": 1, "total_results": 1}, "page must be >= 1"),
        ({"page": 1, "page_size": 0, "current_page_size": 0, "total_results": 0}, "page_size must be >= 1"),
        (
            {"page": 1, "page_size": 10, "current_page_size": 11, "total_results": 11},
            "current_page_size must be between 0 and page_size",
        ),
        (
            {"page": 1, "page_size": 10, "current_page_size": 0, "total_results": -1},
            "total_results must be >= 0",
        ),
    ],
)
def test_make_pagination_rejects_invalid_inputs(kwargs: dict[str, int], match: str):
    with pytest.raises(ValueError, match=match):
        make_pagination(**kwargs)


@pytest.mark.asyncio
async def test_list_spans_counts_final_rows():
    client = _Client()
    repository = _repository(client)

    await repository.list_spans(
        filters=SpanListFilter(workspace="workspace-a"),
        page=1,
        page_size=10,
        sort="started_at",
    )

    assert client.queries[0] == "SELECT count() FROM spans FINAL WHERE workspace = %(workspace)s AND is_deleted = 0"


@pytest.mark.asyncio
async def test_list_spans_reads_final_rows():
    client = _Client()
    repository = _repository(client)

    await repository.list_spans(
        filters=SpanListFilter(workspace="workspace-a"),
        page=1,
        page_size=10,
        sort="started_at",
    )

    assert "FROM spans FINAL" in client.queries[1]


def test_span_group_by_enum_matches_repository_columns():
    assert {field.value for field in SpanGroupBy} == set(SPAN_GROUP_COLUMN_FIELDS)


@pytest.mark.asyncio
async def test_list_span_groups_groups_by_columns():
    client = _Client(
        query_results=[
            _QueryResult([(2,)]),
            _QueryResult(
                [
                    ("session-a", "trace-a", 3),
                    ("session-b", "trace-b", 1),
                ],
                ["session_id", "trace_id", "span_count"],
            ),
        ]
    )
    repository = _repository(client)

    result = await repository.list_span_groups(
        filters=SpanListFilter(workspace="workspace-a"),
        group_by=["session_id", "trace_id"],
        page=1,
        page_size=10,
        sort="-span_count",
    )

    assert result.pagination.total_results == 2
    assert result.data[0].group == {"session_id": "session-a", "trace_id": "trace-a"}
    assert result.data[0].span_count == 3
    assert "FROM spans FINAL" in client.queries[0]
    assert "GROUP BY session_id, trace_id" in client.queries[0]
    assert "ORDER BY span_count DESC, session_id ASC, trace_id ASC" in client.queries[1]


@pytest.mark.asyncio
async def test_list_span_groups_reuses_span_filters():
    client = _Client()
    repository = _repository(client)

    await repository.list_span_groups(
        filters=SpanListFilter(workspace="workspace-a", status="error"),
        group_by=["trace_id"],
        page=1,
        page_size=10,
        sort="-span_count",
    )

    assert "status = %(status)s" in client.queries[0]
    assert "GROUP BY trace_id" in client.queries[0]
    assert client.parameters[0]["status"] == "error"


@pytest.mark.asyncio
async def test_list_span_groups_rejects_unsupported_group_field():
    client = _Client()
    repository = _repository(client)

    with pytest.raises(ValueError, match="Unsupported span group-by field"):
        await repository.list_span_groups(
            filters=SpanListFilter(workspace="workspace-a"),
            group_by=["trace_id; DROP TABLE spans"],
            page=1,
            page_size=10,
            sort="-span_count",
        )


@pytest.mark.asyncio
async def test_get_span_prefers_external_span_id_over_numeric_internal_id():
    row = _span_row(internal_id=7, external_span_id="123")
    client = _Client(query_results=[_QueryResult([row], SPAN_COLUMNS)])
    repository = _repository(client)

    span = await repository.get_span(workspace="workspace-a", span_id="123")

    assert span is not None
    assert span.id == 7
    assert span.external_span_id == "123"
    assert len(client.queries) == 1
    assert "external_span_id = %(span_id)s" in client.queries[0]
    assert client.parameters[0] == {"workspace": "workspace-a", "span_id": "123"}


@pytest.mark.asyncio
async def test_get_span_does_not_fall_back_to_internal_id_after_external_miss():
    client = _Client(query_results=[_QueryResult([], SPAN_COLUMNS)])
    repository = _repository(client)

    span = await repository.get_span(workspace="workspace-a", span_id="123")

    assert span is None
    assert len(client.queries) == 1
    assert "external_span_id = %(span_id)s" in client.queries[0]
    assert client.parameters[0] == {"workspace": "workspace-a", "span_id": "123"}


def _span_row(*, internal_id: int, external_span_id: str) -> tuple[object, ...]:
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    zero_time = datetime.fromtimestamp(0, tz=timezone.utc)
    values: dict[str, object] = {
        "workspace": "workspace-a",
        "session_id": "session-a",
        "trace_id": "trace-a",
        "id": internal_id,
        "source_format": "test",
        "external_span_id": external_span_id,
        "external_parent_span_id": "",
        "kind": "LLM",
        "name": "span-a",
        "status": "success",
        "start_time": started_at,
        "end_time": zero_time,
        "attributes_string": {},
        "attributes_number": {},
        "attributes_bool": {},
        "input": "",
        "output": "",
        "event_ts": started_at,
        "is_deleted": 0,
    }
    return tuple(values[column] for column in SPAN_COLUMNS)
