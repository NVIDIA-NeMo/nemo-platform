# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Intake ClickHouse query builder."""

import pytest
from nmp.intake.spans.clickhouse.query import (
    SelectQuery,
    TableRef,
    WhereBuilder,
    column,
    count_query,
    format_columns,
    order_by_clause,
    select_from_table,
    validate_clickhouse_identifier,
)


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
    where = WhereBuilder().eq("workspace", "workspace", "workspace-a").gte("start_time", "started_at_gte", "2026-01-01")

    sql, parameters = where.build()

    assert sql == "workspace = %(workspace)s AND start_time >= %(started_at_gte)s"
    assert parameters == {"workspace": "workspace-a", "started_at_gte": "2026-01-01"}


def test_where_builder_default_clause():
    sql, parameters = WhereBuilder().build()

    assert sql == "1 = 1"
    assert parameters == {}


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
        WhereBuilder().eq("workspace", "workspace", "workspace-a")
    )

    sql, parameters = query.build()

    assert "SELECT workspace, trace_id" in sql
    assert "FROM intake.spans FINAL" in sql
    assert "WHERE workspace = %(workspace)s" in sql
    assert parameters == {"workspace": "workspace-a"}


def test_count_query_builds_parameterized_count():
    table = TableRef(qualified_name="intake.annotations", logical_name="annotations")
    where = WhereBuilder().eq("workspace", "workspace", "workspace-a")

    sql, parameters = count_query(table, where, final=True).build()

    assert sql.startswith("SELECT count()")
    assert "FROM intake.annotations FINAL" in sql
    assert "WHERE workspace = %(workspace)s" in sql
    assert parameters == {"workspace": "workspace-a"}


def test_select_query_supports_pagination_parameters():
    query = (
        SelectQuery(select_expr="*", from_expr="spans FINAL")
        .limit(limit_param="limit", offset_param="offset")
        .with_parameters({"limit": 10, "offset": 20})
    )

    sql, parameters = query.build()

    assert "LIMIT %(limit)s" in sql
    assert "OFFSET %(offset)s" in sql
    assert parameters == {"limit": 10, "offset": 20}
