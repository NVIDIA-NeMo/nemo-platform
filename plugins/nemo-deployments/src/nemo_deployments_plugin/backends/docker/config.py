# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Executor-level Docker backend configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class DockerExecutorConfig(BaseModel):
    """Knobs for a named docker executor instance (not entity backend_config)."""

    docker_host: str | None = Field(default=None, description="Override DOCKER_HOST for this executor.")
    docker_timeout: int = Field(
        default=600,
        ge=1,
        description="Docker client timeout in seconds for pull/create/status operations (default: 10 minutes).",
    )
    pull_images: bool = Field(default=True, description="Pull container images before run when missing locally.")
    port_range_start: int = Field(
        default=9000,
        ge=1,
        le=65535,
        description="First host port to consider when publishing container ports for this executor.",
    )
    port_range_end: int = Field(
        default=9100,
        ge=1,
        le=65535,
        description="Last host port (inclusive) to consider when publishing container ports for this executor.",
    )

    @model_validator(mode="after")
    def _validate_port_range(self) -> DockerExecutorConfig:
        if self.port_range_start > self.port_range_end:
            raise ValueError("port_range_start must not exceed port_range_end")
        return self
