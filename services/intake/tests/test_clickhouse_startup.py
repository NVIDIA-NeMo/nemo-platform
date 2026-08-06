# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Intake startup when ClickHouse is unavailable."""

import asyncio
import logging
from unittest.mock import AsyncMock

import pytest
from nmp.intake.config import ClickHouseConfig, IntakeConfig
from nmp.intake.local_clickhouse import DockerUnavailableError, LocalClickHouseProvisioningError
from nmp.intake.service import IntakeService


def test_intake_ready_with_explicit_external_clickhouse_without_startup_warning(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_URL", "http://127.0.0.1:1")
    intake_config = IntakeConfig(
        clickhouse_config=ClickHouseConfig(
            url="http://127.0.0.1:1",
            user="default",
            password="",
            database="intake_unavailable",
        )
    )
    caplog.set_level(logging.WARNING, logger="nmp.intake.service")
    stop = AsyncMock(return_value=True)
    monkeypatch.setattr("nmp.intake.service.stop_local_clickhouse", stop)
    service = IntakeService().with_config(intake_config)

    async def check_readiness() -> bool:
        await service.on_startup()
        assert service.clickhouse_client is not None
        try:
            return await service.is_ready()
        finally:
            await service.on_shutdown()

    assert asyncio.run(check_readiness()) is True
    stop.assert_not_awaited()
    assert not [record for record in caplog.records if record.name == "nmp.intake.service"]


def test_intake_uses_reconciled_clickhouse_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NMP_INTAKE_CLICKHOUSE_URL", raising=False)
    reconcile = AsyncMock(return_value="http://127.0.0.1:55123")
    stop = AsyncMock(return_value=True)
    monkeypatch.setattr("nmp.intake.service.reconcile_local_clickhouse", reconcile)
    monkeypatch.setattr("nmp.intake.service.stop_local_clickhouse", stop)
    intake_config = IntakeConfig(clickhouse_config=ClickHouseConfig())
    service = IntakeService().with_config(intake_config)

    async def start_and_stop() -> None:
        await service.on_startup()
        try:
            assert service.clickhouse_client is not None
            assert service.clickhouse_client.settings.url == "http://127.0.0.1:55123"
        finally:
            await service.on_shutdown()

    asyncio.run(start_and_stop())
    reconcile.assert_awaited_once()
    assert reconcile.await_args is not None
    assert reconcile.await_args.kwargs == {
        "image": intake_config.clickhouse_config.image,
        "data_dir": intake_config.clickhouse_config.data_dir,
    }
    stop.assert_awaited_once_with(data_dir=intake_config.clickhouse_config.data_dir)


def test_intake_stays_ready_and_logs_docker_recovery_guidance(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NMP_INTAKE_CLICKHOUSE_URL", raising=False)
    message = (
        "Docker daemon is unavailable. Start Docker Desktop on macOS/Windows or the Docker service on Linux, "
        "then rerun `nemo setup` or restart `nemo services run`."
    )
    reconcile = AsyncMock(side_effect=DockerUnavailableError(message))
    monkeypatch.setattr("nmp.intake.service.reconcile_local_clickhouse", reconcile)
    caplog.set_level(logging.WARNING, logger="nmp.intake.service")
    service = IntakeService().with_config(IntakeConfig(clickhouse_config=ClickHouseConfig()))

    async def check_readiness() -> bool:
        await service.on_startup()
        try:
            return await service.is_ready()
        finally:
            await service.on_shutdown()

    assert asyncio.run(check_readiness()) is True
    assert any(message in record.message for record in caplog.records)


def test_intake_stays_ready_for_non_docker_reconciliation_errors(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NMP_INTAKE_CLICKHOUSE_URL", raising=False)
    reconcile = AsyncMock(side_effect=LocalClickHouseProvisioningError("container name collision"))
    monkeypatch.setattr("nmp.intake.service.reconcile_local_clickhouse", reconcile)
    caplog.set_level(logging.ERROR, logger="nmp.intake.service")
    service = IntakeService().with_config(IntakeConfig(clickhouse_config=ClickHouseConfig()))

    async def check_readiness() -> bool:
        await service.on_startup()
        try:
            assert service.clickhouse_client is not None
            return await service.is_ready()
        finally:
            await service.on_shutdown()

    assert asyncio.run(check_readiness()) is True
    assert any(
        "container name collision" in record.message and "endpoints will return 503" in record.message
        for record in caplog.records
    )
