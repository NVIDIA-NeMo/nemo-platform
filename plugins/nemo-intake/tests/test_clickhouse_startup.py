# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Intake startup when ClickHouse is unavailable."""

import asyncio
import logging
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends
from nemo_intake_plugin.config import ClickHouseConfig, IntakeConfig
from nemo_intake_plugin.service import IntakeService
from nemo_intake_plugin.spans.clickhouse_client import (
    ClickHouseSpanClient,
    get_clickhouse_client,
    get_intake_runtime,
)
from nemo_platform_plugin.service import RouterSpec
from nmp.platform_runner.plugin_adapter import NemoServiceAdapter
from nmp.platform_runner.server import create_app
from starlette.testclient import TestClient


def test_intake_ready_when_clickhouse_is_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    intake_config = IntakeConfig(
        clickhouse_config=ClickHouseConfig(
            url="http://127.0.0.1:1",
            user="default",
            password="",
            database="intake_unavailable",
        )
    )
    caplog.set_level(logging.WARNING, logger="nemo_intake_plugin.service")
    service = IntakeService().with_config(intake_config)

    async def check_readiness() -> bool:
        await service.on_startup()
        assert service.clickhouse_client is not None
        try:
            return await service.is_ready()
        finally:
            await service.on_shutdown()

    assert asyncio.run(check_readiness()) is True
    assert any(
        "ClickHouse schema setup was not run during Intake startup" in record.message for record in caplog.records
    )
    assert any(
        "plugins/nemo-intake/scripts/spans/run_clickhouse.sh" in record.message
        and "plugins/nemo-intake/README.md#local-development" in record.message
        for record in caplog.records
    )
    assert not any("ClickHouse readiness check failed" in record.message for record in caplog.records)


def test_platform_mounted_request_resolves_plugin_owned_clickhouse_client() -> None:
    class FakeClickHouseClient(ClickHouseSpanClient):
        def __init__(self) -> None:
            self.bootstrapped = False

        async def bootstrap_schema(self) -> None:
            self.bootstrapped = True

    class ProbeIntakeService(IntakeService):
        def get_routers(self) -> list[RouterSpec]:
            router = APIRouter()

            @router.get("/probe")
            async def probe(client: Annotated[Any, Depends(get_clickhouse_client)]) -> dict[str, bool]:
                return {"bootstrapped": client.bootstrapped}

            return [RouterSpec(router)]

    fake_client = FakeClickHouseClient()
    service = ProbeIntakeService()
    service.clickhouse_client = fake_client
    get_intake_runtime().configure(fake_client, IntakeConfig())
    app = create_app([NemoServiceAdapter(service)])

    try:
        client = TestClient(app)
        response = client.get("/apis/intake/probe")

        assert response.status_code == 200
        assert response.json() == {"bootstrapped": True}
        assert fake_client.bootstrapped is True
    finally:
        get_intake_runtime().clear(fake_client)
