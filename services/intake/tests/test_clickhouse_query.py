# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Intake ClickHouse query builder."""

from typing import Any, cast

import pytest
from nmp.intake.spans.clickhouse._where import _as_clause, _new_where
from nmp.intake.spans.clickhouse.dao import ClickHouseDao
from nmp.intake.spans.clickhouse.filters import span_list_where, span_lookup_where
from nmp.intake.spans.clickhouse.identifiers import column, validate_clickhouse_identifier
from nmp.intake.spans.clickhouse.query import (
    SelectQuery,
    TableRef,
    count_query,
    format_columns,
    order_by_clause,
    select_from_table,
    subquery_from,
)
from nmp.intake.spans.clickhouse.trace_queries import trace_rows_sql
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import SpanListFilter, TraceListFilter


class _QueryResult:
    result_rows: list[tuple[object, ...]] = []
    column_names: list[str] = []


class _Client:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.parameters: list[dict[str, object]] = []

    def table(self, name: str) -> str:
        return name

    async def query(self, query: str, *, parameters: dict[str, object]) -> _QueryResult:
        self.queries.append(query)
        self.parameters.append(parameters)
        return _QueryResult()


def test_validate_clickhouse_identifier_accepts_safe_names():
    assert validate_clickhouse_identifier("spans") == "spans"
    assert validate_clickhouse_identifier("root_spans") == "root_spans"


def test_validate_clickhouse_identifier_rejects_unsafe_names():
    with pytest.raises(ValueError, match="Invalid ClickHouse identifier"):
        validate_clickhouse_identifier("spans; DROP TABLE spans")


def test_column_builds_qualified_reference():
    assert column("workspace", qualifier="root_spans") == "root_spans.workspace"


def test_format_columns_joins_validated_names():
    assert format_columns(["workspace", "trace_id"]) == "workspace, trace_id"


def test_where_builder_parameterizes_predicates():
    where = _new_where().eq("workspace", "workspace", "workspace-a").gte("start_time", "started_at_gte", "2026-01-01")

    sql, parameters = where.build()

    assert sql == "workspace = %(workspace)s AND start_time >= %(started_at_gte)s"
    assert parameters == {"workspace": "workspace-a", "started_at_gte": "2026-01-01"}


def test_span_list_where_parameterizes_workspace_filter():
    sql, parameters = span_list_where(SpanListFilter(workspace="workspace-a")).build()

    assert "workspace = %(workspace)s" in sql
    assert "is_deleted = %(is_deleted)s" in sql
    assert parameters == {"workspace": "workspace-a", "is_deleted": 0}


def test_span_lookup_where_parameterizes_external_span_id():
    sql, parameters = span_lookup_where(workspace="workspace-a", span_id="123").build()

    assert "external_span_id = %(span_id)s" in sql
    assert parameters["workspace"] == "workspace-a"
    assert parameters["span_id"] == "123"
    assert parameters["is_deleted"] == 0


def test_order_by_clause_whitelists_sort_keys():
    assert (
        order_by_clause(
            "-started_at",
            sort_columns={"started_at": "start_time"},
            tiebreaker="id",
            label="span",
        )
        == "start_time DESC, id ASC"
    )


def test_order_by_clause_rejects_unsupported_sort_keys():
    with pytest.raises(ValueError, match="Unsupported span sort field"):
        order_by_clause(
            "started_at DESC; DROP TABLE spans",
            sort_columns={"started_at": "start_time"},
            tiebreaker="id",
            label="span",
        )


def test_select_from_table_supports_final_modifier():
    table = TableRef(qualified_name="intake.spans", logical_name="spans")
    query = select_from_table(table, columns=["workspace", "trace_id"], final=True).where(
        span_list_where(SpanListFilter(workspace="workspace-a"))
    )

    sql, parameters = query.build()

    assert "SELECT workspace, trace_id" in sql
    assert "FROM intake.spans FINAL" in sql
    assert "WHERE workspace = %(workspace)s" in sql
    assert parameters == {"workspace": "workspace-a", "is_deleted": 0}


def test_count_query_builds_parameterized_count():
    table = TableRef(qualified_name="intake.annotations", logical_name="annotations")
    where = span_list_where(SpanListFilter(workspace="workspace-a"))

    sql, parameters = count_query(table, where, final=True).build()

    assert sql.startswith("SELECT count()")
    assert "FROM intake.annotations FINAL" in sql
    assert "WHERE workspace = %(workspace)s" in sql
    assert parameters == {"workspace": "workspace-a", "is_deleted": 0}


def test_select_query_supports_pagination_parameters():
    table = TableRef(qualified_name="spans", logical_name="spans")
    query = (
        select_from_table(table)
        .limit(limit_param="limit", offset_param="offset")
        .with_parameters({"limit": 10, "offset": 20})
    )

    sql, parameters = query.build()

    assert "LIMIT %(limit)s" in sql
    assert "OFFSET %(offset)s" in sql
    assert parameters == {"limit": 10, "offset": 20}


def test_select_query_rejects_raw_from_expressions():
    with pytest.raises(TypeError, match="trusted FROM expression"):
        SelectQuery(select_expr="*", from_expr=cast(Any, "spans FINAL"))


def test_subquery_from_wraps_built_query_with_validated_alias():
    table = TableRef(qualified_name="spans", logical_name="spans")
    subquery = select_from_table(table).render()

    from_expr = subquery_from(subquery, alias="safe_alias")

    assert from_expr.sql == "(SELECT *\nFROM spans) AS safe_alias"
    with pytest.raises(ValueError, match="Invalid ClickHouse identifier"):
        subquery_from(subquery, alias="safe_alias; DROP TABLE spans")


@pytest.mark.asyncio
async def test_fetch_all_uses_validated_sort_key():
    client = _Client()
    dao = ClickHouseDao(cast(ClickHouseSpanClient, client))
    where = _as_clause(_new_where().eq("workspace", "workspace", "workspace-a"))

    await dao.fetch_all(
        dao.table("evaluator_results"),
        where,
        sort="created_at",
        sort_columns={"created_at": "created_at"},
        tiebreaker="evaluator_result_id",
        sort_label="evaluator_result",
    )

    assert "ORDER BY created_at ASC, evaluator_result_id ASC" in client.queries[0]
    with pytest.raises(ValueError, match="Unsupported evaluator_result sort field"):
        await dao.fetch_all(
            dao.table("evaluator_results"),
            where,
            sort="created_at DESC; DROP TABLE evaluator_results",
            sort_columns={"created_at": "created_at"},
            tiebreaker="evaluator_result_id",
            sort_label="evaluator_result",
        )


def test_trace_rows_sql_requires_table_ref_and_returns_built_query():
    table = TableRef(qualified_name="spans", logical_name="spans")

    query = trace_rows_sql(table, TraceListFilter(workspace="workspace-a"), mode="summary")

    assert "FROM spans AS span_versions" in query.sql
    assert query.parameters["workspace"] == "workspace-a"
    with pytest.raises(TypeError, match="TableRef"):
        trace_rows_sql(cast(Any, "spans"), TraceListFilter(workspace="workspace-a"), mode="summary")
