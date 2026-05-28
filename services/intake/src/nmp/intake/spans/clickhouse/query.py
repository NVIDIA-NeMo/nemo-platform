# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Safe, parameterized ClickHouse query construction for Intake spans."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_clickhouse_identifier(identifier: str) -> str:
    """Return identifier after validating it is safe for SQL interpolation."""

    if not _IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Invalid ClickHouse identifier: {identifier!r}")
    return identifier


def column(name: str, *, qualifier: str | None = None) -> str:
    """Build a validated column reference, optionally qualified by table alias."""

    validate_clickhouse_identifier(name)
    if qualifier is None:
        return name
    validate_clickhouse_identifier(qualifier)
    return f"{qualifier}.{name}"


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


@dataclass
class WhereBuilder:
    """Accumulates parameterized WHERE predicates."""

    _clauses: list[str] = field(default_factory=list)
    _parameters: dict[str, Any] = field(default_factory=dict)

    def add(self, clause: str, parameters: Mapping[str, Any] | None = None) -> WhereBuilder:
        """Append a pre-validated SQL predicate and optional bound parameters."""

        self._clauses.append(clause)
        if parameters:
            self._parameters.update(parameters)
        return self

    def eq(self, column_expr: str, param_name: str, value: Any) -> WhereBuilder:
        """Append `column = %(param)s`."""

        return self.add(f"{column_expr} = %({param_name})s", {param_name: value})

    def gte(self, column_expr: str, param_name: str, value: Any) -> WhereBuilder:
        """Append `column >= %(param)s`."""

        return self.add(f"{column_expr} >= %({param_name})s", {param_name: value})

    def lte(self, column_expr: str, param_name: str, value: Any) -> WhereBuilder:
        """Append `column <= %(param)s`."""

        return self.add(f"{column_expr} <= %({param_name})s", {param_name: value})

    def extend(self, other: WhereBuilder) -> WhereBuilder:
        """Merge another builder's clauses and parameters."""

        self._clauses.extend(other._clauses)
        self._parameters.update(other._parameters)
        return self

    def build(self, *, default: str = "1 = 1") -> tuple[str, dict[str, Any]]:
        """Return `(where_sql, parameters)` for use in a query."""

        if not self._clauses:
            return default, dict(self._parameters)
        return " AND ".join(self._clauses), dict(self._parameters)


@dataclass(frozen=True)
class TableRef:
    """Qualified ClickHouse table reference."""

    qualified_name: str
    logical_name: str


@dataclass
class SelectQuery:
    """Composable SELECT statement with bound parameters."""

    select_expr: str
    from_expr: str
    where_builder: WhereBuilder | None = None
    order_by: str | None = None
    limit_param: str | None = None
    offset_param: str | None = None
    extra_parameters: dict[str, Any] = field(default_factory=dict)

    def where(self, builder: WhereBuilder) -> SelectQuery:
        self.where_builder = builder
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

        clauses = [f"SELECT {self.select_expr}", f"FROM {self.from_expr}"]
        parameters = dict(self.extra_parameters)
        if self.where_builder is not None:
            where_sql, where_parameters = self.where_builder.build()
            clauses.append(f"WHERE {where_sql}")
            parameters.update(where_parameters)
        if self.order_by is not None:
            clauses.append(f"ORDER BY {self.order_by}")
        if self.limit_param is not None:
            clauses.append(f"LIMIT %({self.limit_param})s")
        if self.offset_param is not None:
            clauses.append(f"OFFSET %({self.offset_param})s")
        return "\n".join(clauses), parameters


def select_from_table(
    table: TableRef,
    *,
    columns: Sequence[str] | str = "*",
    final: bool = False,
) -> SelectQuery:
    """Start a SELECT against a table, optionally with ClickHouse FINAL."""

    if isinstance(columns, str):
        select_expr = columns
    else:
        select_expr = format_columns(columns)
    from_expr = f"{table.qualified_name} FINAL" if final else table.qualified_name
    return SelectQuery(select_expr=select_expr, from_expr=from_expr)


def count_query(table: TableRef, where_builder: WhereBuilder, *, final: bool = False) -> SelectQuery:
    """Build `SELECT count()` with optional FINAL."""

    from_expr = f"{table.qualified_name} FINAL" if final else table.qualified_name
    return SelectQuery(select_expr="count()", from_expr=from_expr, where_builder=where_builder)
