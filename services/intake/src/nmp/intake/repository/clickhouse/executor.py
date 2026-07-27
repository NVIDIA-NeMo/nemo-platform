# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed runtime query boundary for Intake ClickHouse repositories."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from clickhouse_connect.driver.exceptions import ClickHouseError
from nmp.intake.repository.clickhouse.tables import ClickHouseTable, qualified_table
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClickHouseQuery:
    """One named, parameterized ClickHouse read statement."""

    name: str
    statement: str
    parameters: Mapping[str, object] = field(default_factory=dict)

    def bind(self, **parameters: object) -> ClickHouseQuery:
        """Return a copy with additional bound parameters."""

        return ClickHouseQuery(
            name=self.name,
            statement=self.statement,
            parameters={**self.parameters, **parameters},
        )


class ClickHouseQueryError(RuntimeError):
    """Raised when a named repository query fails."""

    def __init__(self, query_name: str) -> None:
        self.query_name = query_name
        super().__init__(f"ClickHouse query failed: {query_name}")


class ClickHouseExecutor:
    """Execute named repository queries without exposing the raw driver result."""

    def __init__(self, client: ClickHouseSpanClient) -> None:
        self._client = client

    def table(self, table: ClickHouseTable) -> str:
        return qualified_table(self._client.database, table)

    async def fetch_all(self, query: ClickHouseQuery) -> list[dict[str, Any]]:
        started_at = perf_counter()
        try:
            result = await self._client.query(
                query.statement,
                parameters=dict(query.parameters),
            )
        except ClickHouseError as exc:
            logger.exception("ClickHouse repository query failed", extra={"query_name": query.name})
            raise ClickHouseQueryError(query.name) from exc
        finally:
            logger.debug(
                "ClickHouse repository query finished",
                extra={
                    "query_name": query.name,
                    "duration_ms": (perf_counter() - started_at) * 1000,
                },
            )

        columns: Sequence[str] = result.column_names
        rows: Sequence[Sequence[Any]] = result.result_rows
        return [dict(zip(columns, row, strict=True)) for row in rows]
