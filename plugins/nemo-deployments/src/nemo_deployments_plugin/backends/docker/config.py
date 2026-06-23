# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Executor-level Docker backend configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DockerExecutorConfig(BaseModel):
    """Knobs for a named docker executor instance (not entity backend_config)."""

    docker_host: str | None = Field(default=None, description="Override DOCKER_HOST for this executor.")
    docker_timeout: int = Field(default=60, ge=1)
    pull_images: bool = Field(default=True, description="Pull container images before run when missing locally.")
