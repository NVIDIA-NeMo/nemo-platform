# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Executes query plugins against ClickHouse."""

from __future__ import annotations

from collections.abc import Sequence

from nmp.intake.query_plugins.base import QueryPlugin
from nmp.intake.query_plugins.context import QueryPluginContext
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.storage import result_rows
from pydantic import BaseModel


class QueryPluginRunner:
    """Runs a :class:`QueryPlugin` via the shared span client.

    Mirrors the rollup repository's posture — it reuses the same ``ClickHouseSpanClient`` and binds
    table names through ``client.table`` — but is a separate code path and does not touch
    ``ExperimentRollupRepository``.
    """

    def __init__(self, client: ClickHouseSpanClient) -> None:
        self._client = client

    async def run(
        self,
        plugin: QueryPlugin,
        *,
        workspace: str,
        experiment_ids: Sequence[str] = (),
    ) -> BaseModel:
        ctx = QueryPluginContext(
            workspace=workspace,
            experiment_ids=tuple(experiment_ids),
            table=self._client.table,
        )
        sql, parameters = plugin.build_query(ctx)
        result = await self._client.query(sql, parameters=parameters)
        return plugin.parse(result_rows(result))
