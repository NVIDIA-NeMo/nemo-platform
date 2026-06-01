# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for the Intake service."""

from typing import Any, cast

from nmp.common.config import EnvironmentFirstSettings, create_service_config_class
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class ClickHouseConfig(EnvironmentFirstSettings):
    """Configuration for Intake's ClickHouse-backed spans storage."""

    model_config = SettingsConfigDict(env_prefix="NMP_INTAKE_CLICKHOUSE_")

    url: str = Field(
        default="http://localhost:8123",
        description="HTTP URL for the ClickHouse server used by Intake spans storage",
    )
    user: str = Field(
        default="default",
        description="ClickHouse username for Intake spans storage",
    )
    password: str = Field(
        default="",
        description="ClickHouse password for Intake spans storage",
    )
    database: str = Field(
        default="intake",
        description="ClickHouse database for Intake spans",
    )


_BaseIntakeConfig = cast(Any, create_service_config_class("intake"))


class IntakeConfig(_BaseIntakeConfig):
    """
    Configuration for the Intake service.

    Environment variables use the NMP_INTAKE_ prefix.
    """

    clickhouse_config: ClickHouseConfig = Field(
        default_factory=ClickHouseConfig,
        description="ClickHouse connection settings for Intake spans storage.",
    )
    otlp_max_body_bytes: int = Field(
        default=5 * 1024 * 1024,
        ge=1024,
        description="Maximum accepted body size for OTLP ingest requests, in bytes.",
    )
