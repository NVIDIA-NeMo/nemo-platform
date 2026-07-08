# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Intake plugin configuration compatibility."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import pytest
from nemo_intake_plugin.config import IntakeConfig
from nemo_intake_plugin.service import IntakeService
from nemo_platform_plugin.config import Configuration


@pytest.fixture(autouse=True)
def clear_intake_env(monkeypatch: pytest.MonkeyPatch):
    for name in list(os.environ):
        if name.startswith(("NEMO_INTAKE_", "NMP_INTAKE_")):
            monkeypatch.delenv(name, raising=False)
    Configuration.clear_cache()
    yield
    Configuration.clear_cache()


def test_nemo_intake_env_vars_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEMO_INTAKE_CLICKHOUSE_URL", "https://clickhouse.example.com")
    monkeypatch.setenv("NEMO_INTAKE_CLICKHOUSE_USER", "nemo-user")
    monkeypatch.setenv("NEMO_INTAKE_CLICKHOUSE_PASSWORD", "nemo-password")
    monkeypatch.setenv("NEMO_INTAKE_CLICKHOUSE_DATABASE", "nemo-intake")
    monkeypatch.setenv("NEMO_INTAKE_OTLP_MAX_BODY_BYTES", "8192")

    cfg = IntakeConfig()

    assert cfg.clickhouse_config.url == "https://clickhouse.example.com"
    assert cfg.clickhouse_config.user == "nemo-user"
    assert cfg.clickhouse_config.password == "nemo-password"
    assert cfg.clickhouse_config.database == "nemo-intake"
    assert cfg.otlp_max_body_bytes == 8192


def test_nemo_intake_env_vars_win_over_deprecated_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_PASSWORD", "old-password")
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_CONFIG_PASSWORD", "old-nested-password")
    monkeypatch.setenv("NEMO_INTAKE_CLICKHOUSE_PASSWORD", "new-password")

    cfg = IntakeConfig()

    assert cfg.clickhouse_config.password == "new-password"


def test_generic_user_env_var_does_not_override_clickhouse_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USER", "local-shell-user")

    cfg = IntakeConfig()

    assert cfg.clickhouse_config.user == "default"


def test_deprecated_nmp_intake_env_vars_load_and_warn(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_URL", "http://deprecated-clickhouse:8123")
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_USER", "deprecated-user")
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_PASSWORD", "deprecated-password")
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_DATABASE", "deprecated-intake")
    monkeypatch.setenv("NMP_INTAKE_OTLP_MAX_BODY_BYTES", "16384")

    cfg = IntakeConfig()
    assert cfg.clickhouse_config.url == "http://deprecated-clickhouse:8123"
    assert cfg.clickhouse_config.user == "deprecated-user"
    assert cfg.clickhouse_config.password == "deprecated-password"
    assert cfg.clickhouse_config.database == "deprecated-intake"
    assert cfg.otlp_max_body_bytes == 16384

    caplog.set_level(logging.WARNING, logger="nemo_intake_plugin.service")
    service = IntakeService()

    async def start_and_stop() -> None:
        await service.on_startup()
        await service.on_shutdown()

    asyncio.run(start_and_stop())

    assert any("Deprecated NMP_INTAKE_* environment variables are set" in record.message for record in caplog.records)


def test_deprecated_nested_nmp_intake_clickhouse_config_env_vars_load(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_CONFIG_URL", "http://nested-clickhouse:8123")
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_CONFIG_USER", "nested-user")
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_CONFIG_PASSWORD", "nested-password")
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_CONFIG_DATABASE", "nested-intake")

    cfg = IntakeConfig()
    assert cfg.clickhouse_config.url == "http://nested-clickhouse:8123"
    assert cfg.clickhouse_config.user == "nested-user"
    assert cfg.clickhouse_config.password == "nested-password"
    assert cfg.clickhouse_config.database == "nested-intake"

    caplog.set_level(logging.WARNING, logger="nemo_intake_plugin.service")
    service = IntakeService()

    async def start_and_stop() -> None:
        await service.on_startup()
        await service.on_shutdown()

    asyncio.run(start_and_stop())

    assert any("Deprecated NMP_INTAKE_* environment variables are set" in record.message for record in caplog.records)
    assert any("NMP_INTAKE_CLICKHOUSE_CONFIG_PASSWORD" in record.message for record in caplog.records)


def test_yaml_intake_section_keeps_clickhouse_config_shape(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
intake:
  clickhouse_config:
    url: http://yaml-clickhouse:8123
    user: yaml-user
    password: yaml-password
    database: yaml-intake
  otlp_max_body_bytes: 32768
""",
        encoding="utf-8",
    )

    settings = Configuration.get_global_settings_from_file(str(config_path))
    cfg = IntakeConfig(**settings["intake"])

    assert cfg.clickhouse_config.url == "http://yaml-clickhouse:8123"
    assert cfg.clickhouse_config.user == "yaml-user"
    assert cfg.clickhouse_config.password == "yaml-password"
    assert cfg.clickhouse_config.database == "yaml-intake"
    assert cfg.otlp_max_body_bytes == 32768
