# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deployments plugin configuration."""

from __future__ import annotations

from typing import Any, ClassVar

from nemo_platform_plugin.config import NemoConfig
from pydantic import BaseModel, Field


class ExecutorConfigEntry(BaseModel):
    name: str = Field(description="Unique executor name used by Deployment.executor.")
    backend: str = Field(description="Backend type key registered in BACKEND_CLASSES.")
    config: dict[str, Any] = Field(default_factory=dict)


class DeploymentsConfig(NemoConfig):
    plugin_name: ClassVar[str] = "deployments"
    plugin_description: ClassVar[str] = "Configuration for the NeMo Platform deployments plugin."

    executors: list[ExecutorConfigEntry] = Field(
        default_factory=list,
        description="Named executor instances. May be empty at scaffold time.",
    )
    default_executor: str | None = Field(
        default=None,
        description="Fallback executor when Deployment.executor is unset.",
    )
