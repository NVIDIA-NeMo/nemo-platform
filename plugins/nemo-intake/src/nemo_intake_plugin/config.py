# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for the Intake service."""

from __future__ import annotations

import os
from typing import ClassVar

from nemo_platform_plugin.config import EnvironmentFirstSettings, NemoConfig
from pydantic import AliasChoices, Field
from pydantic_settings import SettingsConfigDict

_DEPRECATED_ENV_PREFIX = "NMP_INTAKE_"


def deprecated_intake_env_vars() -> list[str]:
    """Return deprecated Intake env vars present in the current environment."""

    return sorted(name for name in os.environ if name.startswith(_DEPRECATED_ENV_PREFIX))


class ClickHouseConfig(EnvironmentFirstSettings):
    """Configuration for Intake's ClickHouse-backed spans storage."""

    model_config = SettingsConfigDict(extra="allow", populate_by_name=True)

    url: str = Field(
        default="http://localhost:8123",
        validation_alias=AliasChoices(
            "NEMO_INTAKE_CLICKHOUSE_URL",
            "NMP_INTAKE_CLICKHOUSE_URL",
            "NMP_INTAKE_CLICKHOUSE_CONFIG_URL",
        ),
        description="HTTP URL for the ClickHouse server used by Intake spans storage",
    )
    user: str = Field(
        default="default",
        validation_alias=AliasChoices(
            "NEMO_INTAKE_CLICKHOUSE_USER",
            "NMP_INTAKE_CLICKHOUSE_USER",
            "NMP_INTAKE_CLICKHOUSE_CONFIG_USER",
        ),
        description="ClickHouse username for Intake spans storage",
    )
    password: str = Field(
        default="",
        validation_alias=AliasChoices(
            "NEMO_INTAKE_CLICKHOUSE_PASSWORD",
            "NMP_INTAKE_CLICKHOUSE_PASSWORD",
            "NMP_INTAKE_CLICKHOUSE_CONFIG_PASSWORD",
        ),
        description="ClickHouse password for Intake spans storage",
    )
    database: str = Field(
        default="intake",
        validation_alias=AliasChoices(
            "NEMO_INTAKE_CLICKHOUSE_DATABASE",
            "NMP_INTAKE_CLICKHOUSE_DATABASE",
            "NMP_INTAKE_CLICKHOUSE_CONFIG_DATABASE",
        ),
        description="ClickHouse database for Intake spans",
    )


class IntakeConfig(NemoConfig):
    """
    Configuration for the Intake service.

    Environment variables use the NEMO_INTAKE_ prefix. NMP_INTAKE_* aliases are
    deprecated and retained for one compatibility window.
    """

    plugin_name: ClassVar[str] = "intake"
    plugin_description: ClassVar[str] = "Configuration for the NeMo Platform Intake plugin."

    clickhouse_config: ClickHouseConfig = Field(
        default_factory=ClickHouseConfig,
        description="ClickHouse connection settings for Intake spans storage.",
    )
    otlp_max_body_bytes: int = Field(
        default=5 * 1024 * 1024,
        ge=1024,
        validation_alias=AliasChoices("NEMO_INTAKE_OTLP_MAX_BODY_BYTES", "NMP_INTAKE_OTLP_MAX_BODY_BYTES"),
        description="Maximum accepted body size for OTLP ingest requests, in bytes.",
    )
