# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for the Agents plugin."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from nemo_platform_plugin.config import NemoConfig
from nmp.common.config import nmp_user_data_dir
from pydantic import BaseModel, Field, model_validator


class ControllerConfig(BaseModel):
    """Configuration for the AgentDeploymentController reconcile loop."""

    interval_seconds: int = Field(default=2, description="Reconciliation loop interval in seconds.")
    health_check_timeout_seconds: int = Field(
        default=120, description="Maximum time to wait for agent health check to succeed."
    )
    health_check_interval_seconds: int = Field(default=2, description="Health check poll interval in seconds.")
    port_range_start: int = Field(
        default=49152,
        description="First port in the range available for spawned agent processes (default: start of IANA dynamic/private range).",
    )
    port_range_end: int = Field(
        default=65535,
        description="Last port (inclusive) in the range available for spawned agent processes (default: end of IANA dynamic/private range).",
    )

    @model_validator(mode="after")
    def _validate_port_range(self) -> "ControllerConfig":
        if self.port_range_end < self.port_range_start:
            raise ValueError(
                f"port_range_end ({self.port_range_end}) must be >= port_range_start ({self.port_range_start})"
            )
        return self

    workspace_dir: Path = Field(
        default_factory=lambda: nmp_user_data_dir() / "agents",
        description=(
            "Root directory used by the in-memory runner backend for storing runtime "
            "artifacts (rendered NAT configs and per-deployment logs) under a "
            "'system/' subdirectory. Defaults to ``nmp_user_data_dir() / 'agents'`` "
            "(typically ``~/.local/share/nemo/agents``), so artifacts survive ``/tmp`` "
            "cleanup on macOS reboots and live in a documented, user-accessible "
            "location. Override the user-data root via ``NMP_DATA_DIR`` or "
            "``XDG_DATA_HOME``."
        ),
    )


class AgentsConfig(NemoConfig):
    """Configuration for the Agents plugin."""

    plugin_name: ClassVar[str] = "agents"
    plugin_description: ClassVar[str] = "Configuration for the NeMo Platform agents plugin."

    controller: ControllerConfig = Field(
        default_factory=ControllerConfig,
        description="Deployment controller settings.",
    )
    runner_backend: str = Field(
        default="in_memory",
        description="Runner backend type. Currently only 'in_memory' is supported.",
    )
