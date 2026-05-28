# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Data-access helpers for Intake ClickHouse repositories."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from nmp.intake.spans.clickhouse.query import (
    SelectQuery,
    TableRef,
    WhereBuilder,
    count_query,
    order_by_clause,
    select_from_table,
    validate_clickhouse_identifier,
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

    async def execute(self, query: SelectQuery | tuple[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        if isinstance(query, SelectQuery):
            sql, parameters = query.build()
        else:
            sql, parameters = query
        result = await self._client.query(sql, parameters=dict(parameters))
        return result_rows(result)

    async def execute_scalar(self, query: SelectQuery | tuple[str, Mapping[str, Any]]) -> Any:
        if isinstance(query, SelectQuery):
            sql, parameters = query.build()
        else:
            sql, parameters = query
        result = await self._client.query(sql, parameters=dict(parameters))
        if not result.result_rows:
            return None
        return result.result_rows[0][0]

    async def count(self, table: TableRef, where: WhereBuilder, *, final: bool = False) -> int:
        value = await self.execute_scalar(count_query(table, where, final=final))
        return int(value or 0)

    async def fetch_one(
        self,
        table: TableRef,
        where: WhereBuilder,
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
        rows = await self.execute(query)
        return rows[0] if rows else None

    async def fetch_all(
        self,
        table: TableRef,
        where: WhereBuilder,
        *,
        columns: Sequence[str] | str = "*",
        order_by: str,
        final: bool = False,
    ) -> list[dict[str, Any]]:
        query = select_from_table(table, columns=columns, final=final).where(where).order_by_clause(order_by)
        return await self.execute(query)

    async def paginate(
        self,
        *,
        table: TableRef,
        where: WhereBuilder,
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
        rows = await self.execute(query)
        return rows, total_results
