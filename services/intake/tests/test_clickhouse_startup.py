# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Intake startup when ClickHouse is unavailable."""

import asyncio
import logging

import pytest
from nmp.intake.config import ClickHouseConfig, IntakeConfig
from nmp.intake.service import IntakeService


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
    caplog.set_level(logging.WARNING, logger="nmp.intake.service")
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
    assert not any("ClickHouse readiness check failed" in record.message for record in caplog.records)
