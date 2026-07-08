# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse span client tests."""

import asyncio
from typing import Any

import pytest
from nemo_intake_plugin.spans.clickhouse_client import ClickHouseSettings, ClickHouseSpanClient


class CountingClickHouseSpanClient(ClickHouseSpanClient):
    def __init__(self) -> None:
        super().__init__(
            ClickHouseSettings(
                url="http://localhost:8123",
                user="default",
                password="",
                database="default",
            )
        )
        self.created = 0

    async def _create_raw_client(self, *, database: str) -> Any:
        self.created += 1
        await asyncio.sleep(0)
        return object()


@pytest.mark.asyncio
async def test_get_raw_client_initializes_once_under_concurrency():
    client = CountingClickHouseSpanClient()

    raw_clients = await asyncio.gather(*(client._get_raw_client() for _ in range(10)))

    assert client.created == 1
    assert len({id(raw_client) for raw_client in raw_clients}) == 1
