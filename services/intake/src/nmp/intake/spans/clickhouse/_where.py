# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Package-private WHERE clause builder for ClickHouse queries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self

from nmp.intake.spans.clickhouse.identifiers import column
from nmp.intake.spans.clickhouse.sql import BuiltQuery, merge_parameters
from nmp.intake.spans.span_attribute_catalog import where_clause as attribute_where_clause


@dataclass(frozen=True)
class WhereClause:
    """Opaque parameterized WHERE clause. Construct only via clickhouse.filters."""

    _builder: _WhereBuilder

    def build(self, *, default: str = "1 = 1") -> tuple[str, dict[str, Any]]:
        return self._builder.build(default=default)


class _WhereBuilder:
    """Accumulates parameterized WHERE predicates."""

    def __init__(self) -> None:
        self._clauses: list[str] = []
        self._parameters: dict[str, Any] = {}

    def eq(self, column_expr: str, param_name: str, value: Any) -> Self:
        return self._append(f"{column_expr} = %({param_name})s", {param_name: value})

    def gte(self, column_expr: str, param_name: str, value: Any) -> Self:
        return self._append(f"{column_expr} >= %({param_name})s", {param_name: value})

    def lte(self, column_expr: str, param_name: str, value: Any) -> Self:
        return self._append(f"{column_expr} <= %({param_name})s", {param_name: value})

    def attribute_predicate(
        self,
        field: str,
        operator: str,
        value: Any,
        *,
        param_prefix: str,
    ) -> Self:
        clause, parameters = attribute_where_clause(field, operator, value, param_prefix=param_prefix)
        return self._append(f"({clause})", parameters)

    def is_empty_parent_span(self, *, qualifier: str | None = None) -> Self:
        return self._append(f"{column('external_parent_span_id', qualifier=qualifier)} = ''")

    def in_subquery(self, columns_expr: str, subquery: BuiltQuery) -> Self:
        if not isinstance(subquery, BuiltQuery):
            raise TypeError("in_subquery requires a built query")
        return self._append(f"({columns_expr}) IN ({subquery.sql})", subquery.parameters)

    def _append(self, clause: str, parameters: Mapping[str, Any] | None = None) -> Self:
        self._clauses.append(clause)
        if parameters:
            self._parameters = merge_parameters(self._parameters, parameters)
        return self

    def build(self, *, default: str = "1 = 1") -> tuple[str, dict[str, Any]]:
        if not self._clauses:
            return default, dict(self._parameters)
        return " AND ".join(self._clauses), dict(self._parameters)


def _new_where() -> _WhereBuilder:
    return _WhereBuilder()


def _as_clause(builder: _WhereBuilder) -> WhereClause:
    return WhereClause(builder)
