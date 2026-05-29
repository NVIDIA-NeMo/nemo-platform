# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Data-access helpers for Intake ClickHouse repositories."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from nmp.intake.spans.clickhouse._where import WhereClause
from nmp.intake.spans.clickhouse.identifiers import validate_clickhouse_identifier
from nmp.intake.spans.clickhouse.query import (
    SelectQuery,
    TableRef,
    count_query,
    order_by_clause,
    select_from_table,
)
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.storage import result_rows


class ClickHouseDao:
    """Base DAO enforcing parameterized ClickHouse access patterns."""

    def __init__(self, client: ClickHouseSpanClient) -> None:
        self._client = client

    def table(self, name: str) -> TableRef:
        validate_clickhouse_identifier(name)
        return TableRef(qualified_name=self._client.table(name), logical_name=name)

    async def insert_rows(
        self,
        table_name: str,
        rows: Sequence[Sequence[Any]],
        *,
        column_names: Sequence[str],
    ) -> None:
        if not rows:
            return
        for column_name in column_names:
            validate_clickhouse_identifier(column_name)
        await self._client.insert(table_name, rows, column_names=column_names)

    async def _execute_raw(self, query: SelectQuery | tuple[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        if isinstance(query, SelectQuery):
            sql, parameters = query.build()
        else:
            sql, parameters = query
        result = await self._client.query(sql, parameters=dict(parameters))
        return result_rows(result)

    async def _execute_scalar_raw(self, query: SelectQuery | tuple[str, Mapping[str, Any]]) -> Any:
        if isinstance(query, SelectQuery):
            sql, parameters = query.build()
        else:
            sql, parameters = query
        result = await self._client.query(sql, parameters=dict(parameters))
        if not result.result_rows:
            return None
        return result.result_rows[0][0]

    async def count(self, table: TableRef, where: WhereClause, *, final: bool = False) -> int:
        value = await self._execute_scalar_raw(count_query(table, where, final=final))
        return int(value or 0)

    async def fetch_one(
        self,
        table: TableRef,
        where: WhereClause,
        *,
        columns: Sequence[str] | str = "*",
        final: bool = False,
    ) -> dict[str, Any] | None:
        query = (
            select_from_table(table, columns=columns, final=final)
            .where(where)
            .limit(limit_param="limit")
            .with_parameters({"limit": 1})
        )
        rows = await self._execute_raw(query)
        return rows[0] if rows else None

    async def fetch_all(
        self,
        table: TableRef,
        where: WhereClause,
        *,
        columns: Sequence[str] | str = "*",
        order_by: str,
        final: bool = False,
    ) -> list[dict[str, Any]]:
        query = select_from_table(table, columns=columns, final=final).where(where).order_by_clause(order_by)
        return await self._execute_raw(query)

    async def paginate(
        self,
        *,
        table: TableRef,
        where: WhereClause,
        columns: Sequence[str] | str = "*",
        sort: str,
        sort_columns: Mapping[str, str],
        tiebreaker: str,
        sort_label: str,
        page: int,
        page_size: int,
        final: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        total_results = await self.count(table, where, final=final)
        offset = (page - 1) * page_size
        query = (
            select_from_table(table, columns=columns, final=final)
            .where(where)
            .order_by_clause(
                order_by_clause(
                    sort,
                    sort_columns=sort_columns,
                    tiebreaker=tiebreaker,
                    label=sort_label,
                )
            )
            .limit(limit_param="limit", offset_param="offset")
            .with_parameters({"limit": page_size, "offset": offset})
        )
        rows = await self._execute_raw(query)
        return rows, total_results

    async def paginate_subquery(
        self,
        *,
        subquery_sql: str,
        subquery_parameters: Mapping[str, Any],
        outer_where: WhereClause,
        sort: str,
        sort_columns: Mapping[str, str],
        tiebreaker: str,
        sort_label: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        outer_where_sql, outer_where_parameters = outer_where.build()
        query_parameters = {**subquery_parameters, **outer_where_parameters}

        total_results = int(
            await self._execute_scalar_raw(
                (
                    f"""
                    SELECT count()
                    FROM ({subquery_sql}) AS traces
                    WHERE {outer_where_sql}
                    """,
                    query_parameters,
                )
            )
            or 0
        )

        offset = (page - 1) * page_size
        rows = await self._execute_raw(
            SelectQuery(
                select_expr="*",
                from_expr=f"({subquery_sql}) AS traces",
                where_clause=outer_where,
                order_by=order_by_clause(
                    sort,
                    sort_columns=sort_columns,
                    tiebreaker=tiebreaker,
                    label=sort_label,
                ),
                limit_param="limit",
                offset_param="offset",
            ).with_parameters({**query_parameters, "limit": page_size, "offset": offset})
        )
        return rows, total_results
