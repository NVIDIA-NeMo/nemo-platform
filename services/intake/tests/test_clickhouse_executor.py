# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the typed ClickHouse repository executor."""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from clickhouse_connect.driver.exceptions import ClickHouseError
from nmp.intake.repository.clickhouse.executor import ClickHouseExecutor, ClickHouseQuery, ClickHouseQueryError
from nmp.intake.repository.clickhouse.tables import ClickHouseTable, qualified_table
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient


class _Client:
    database = "intake"

    def __init__(self, *, error: ClickHouseError | None = None) -> None:
        self.error = error
        self.statements: list[str] = []
        self.parameters: list[dict[str, Any]] = []

    async def query(self, statement: str, *, parameters: dict[str, Any]) -> SimpleNamespace:
        self.statements.append(statement)
        self.parameters.append(parameters)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            column_names=["session_id", "span_count"],
            result_rows=[("session-a", 3)],
        )


def _executor(client: _Client) -> ClickHouseExecutor:
    return ClickHouseExecutor(cast(ClickHouseSpanClient, client))


def test_query_bind_preserves_base_parameters() -> None:
    query = ClickHouseQuery(
        name="sessions.get",
        statement="SELECT %(session_id)s",
        parameters={"metric_key": "cost.total"},
    )

    bound = query.bind(session_id="session-a")

    assert query.parameters == {"metric_key": "cost.total"}
    assert bound.parameters == {
        "metric_key": "cost.total",
        "session_id": "session-a",
    }


@pytest.mark.asyncio
async def test_executor_returns_mapped_rows_and_bound_parameters() -> None:
    client = _Client()
    query = ClickHouseQuery(
        name="sessions.get",
        statement="SELECT %(session_id)s",
        parameters={"session_id": "session-a"},
    )

    rows = await _executor(client).fetch_all(query)

    assert rows == [{"session_id": "session-a", "span_count": 3}]
    assert client.statements == [query.statement]
    assert client.parameters == [{"session_id": "session-a"}]


@pytest.mark.asyncio
async def test_executor_returns_first_scalar() -> None:
    scalar = await _executor(_Client()).fetch_scalar(
        ClickHouseQuery(
            name="sessions.first_id",
            statement="SELECT session_id",
        )
    )

    assert scalar == "session-a"


@pytest.mark.asyncio
async def test_executor_translates_clickhouse_errors_without_sql_details() -> None:
    query = ClickHouseQuery(
        name="sessions.get",
        statement="SELECT secret FROM hidden",
    )

    with pytest.raises(ClickHouseQueryError) as exc_info:
        await _executor(_Client(error=ClickHouseError("driver details"))).fetch_all(query)

    assert exc_info.value.query_name == "sessions.get"
    assert str(exc_info.value) == "ClickHouse query failed: sessions.get"
    assert query.statement not in str(exc_info.value)


def test_table_registry_quotes_known_tables() -> None:
    assert qualified_table("intake", ClickHouseTable.SPANS) == "`intake`.`spans`"


def test_table_registry_rejects_unregistered_names() -> None:
    with pytest.raises(TypeError, match="Expected ClickHouseTable"):
        qualified_table("intake", cast(ClickHouseTable, "system.tables"))
