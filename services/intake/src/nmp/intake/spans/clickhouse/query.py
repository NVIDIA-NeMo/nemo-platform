# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Safe, parameterized ClickHouse query construction for Intake spans."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from nmp.intake.spans.clickhouse._where import WhereClause
from nmp.intake.spans.clickhouse.identifiers import validate_clickhouse_identifier
from nmp.intake.spans.clickhouse.sql import BuiltQuery, TrustedSql, _trusted_query, _trusted_sql


def format_columns(columns: Sequence[str]) -> str:
    """Join validated column names for SELECT lists."""

    return ", ".join(validate_clickhouse_identifier(column_name) for column_name in columns)


def order_by_clause(
    sort: str,
    *,
    sort_columns: Mapping[str, str],
    tiebreaker: str,
    label: str,
) -> str:
    """Build an ORDER BY clause from a whitelisted API sort key."""

    direction = "DESC" if sort.startswith("-") else "ASC"
    field = sort.removeprefix("-")
    mapped_column = sort_columns.get(field)
    if mapped_column is None:
        raise ValueError(f"Unsupported {label} sort field: {field}")
    validate_clickhouse_identifier(mapped_column)
    validate_clickhouse_identifier(tiebreaker)
    return f"{mapped_column} {direction}, {tiebreaker} ASC"


@dataclass(frozen=True)
class TableRef:
    """Qualified ClickHouse table reference."""

    qualified_name: str
    logical_name: str


@dataclass
class SelectQuery:
    """Composable SELECT statement with bound parameters."""

    select_expr: str
    from_expr: TrustedSql
    where_clause: WhereClause | None = None
    order_by: str | None = None
    limit_param: str | None = None
    offset_param: str | None = None
    extra_parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.from_expr, TrustedSql):
            raise TypeError("SelectQuery requires a trusted FROM expression")

    def where(self, clause: WhereClause) -> SelectQuery:
        self.where_clause = clause
        return self

    def order_by_clause(self, clause: str) -> SelectQuery:
        self.order_by = clause
        return self

    def limit(self, *, limit_param: str, offset_param: str | None = None) -> SelectQuery:
        self.limit_param = limit_param
        self.offset_param = offset_param
        return self

    def with_parameters(self, parameters: Mapping[str, Any]) -> SelectQuery:
        self.extra_parameters.update(parameters)
        return self

    def build(self) -> tuple[str, dict[str, Any]]:
        """Render SQL and merge all bound parameters."""

        built_query = self.render()
        return built_query.sql, dict(built_query.parameters)

    def render(self) -> BuiltQuery:
        """Render SQL into a reusable trusted query object."""

        clauses = [f"SELECT {self.select_expr}", f"FROM {self.from_expr.sql}"]
        parameters = dict(self.extra_parameters)
        if self.where_clause is not None:
            where_sql, where_parameters = self.where_clause.build()
            clauses.append(f"WHERE {where_sql}")
            parameters.update(where_parameters)
        if self.order_by is not None:
            clauses.append(f"ORDER BY {self.order_by}")
        if self.limit_param is not None:
            clauses.append(f"LIMIT %({self.limit_param})s")
        if self.offset_param is not None:
            clauses.append(f"OFFSET %({self.offset_param})s")
        return _trusted_query("\n".join(clauses), parameters)


def select_from_table(
    table: TableRef,
    *,
    columns: Sequence[str] | str = "*",
    final: bool = False,
) -> SelectQuery:
    """Start a SELECT against a table, optionally with ClickHouse FINAL."""

    if isinstance(columns, str):
        if columns != "*":
            validate_clickhouse_identifier(columns)
        select_expr = columns
    else:
        select_expr = format_columns(columns)
    from_expr = _trusted_sql(f"{table.qualified_name} FINAL" if final else table.qualified_name)
    return SelectQuery(select_expr=select_expr, from_expr=from_expr)


def count_query(table: TableRef, where_clause: WhereClause, *, final: bool = False) -> SelectQuery:
    """Build `SELECT count()` with optional FINAL."""

    from_expr = _trusted_sql(f"{table.qualified_name} FINAL" if final else table.qualified_name)
    return SelectQuery(select_expr="count()", from_expr=from_expr, where_clause=where_clause)


def subquery_from(query: BuiltQuery, *, alias: str) -> TrustedSql:
    """Build a trusted FROM expression from a rendered subquery and validated alias."""

    if not isinstance(query, BuiltQuery):
        raise TypeError("subquery_from requires a built query")
    alias = validate_clickhouse_identifier(alias)
    return _trusted_sql(f"({query.sql}) AS {alias}")
