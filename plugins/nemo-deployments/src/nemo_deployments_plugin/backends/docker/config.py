# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Executor-level Docker backend configuration."""

from __future__ import annotations

import os

from nemo_deployments_plugin.backends.labels import DEFAULT_RESOURCE_SCOPE
from pydantic import BaseModel, Field, model_validator

DOCKER_NETWORK_ENV_VAR = "NEMO_DEPLOYMENTS_DOCKER_NETWORK"
LEGACY_MODELS_DOCKER_NETWORK_ENV_VAR = "MODELS_DOCKER_NETWORK"


def _default_network() -> str | None:
    for env_var in (DOCKER_NETWORK_ENV_VAR, LEGACY_MODELS_DOCKER_NETWORK_ENV_VAR):
        value = os.getenv(env_var)
        if value:
            return value
    return None


class DockerExecutorConfig(BaseModel):
    """Knobs for a named docker executor instance (not entity backend_config)."""

    docker_host: str | None = Field(default=None, description="Override DOCKER_HOST for this executor.")
    docker_timeout: int = Field(
        default=600,
        ge=1,
        description="Docker client timeout in seconds for pull/create/status operations (default: 10 minutes).",
    )
    oneshot_observe_timeout_seconds: int = Field(
        default=5,
        ge=1,
        description=(
            "Max seconds to wait for a Never one-shot container to exit during create. "
            "Should stay near the deployments controller reconcile interval (default 5s). "
            "Longer jobs return STARTING and finish via read_status polling."
        ),
    )
    pull_images: bool = Field(default=True, description="Pull container images before run when missing locally.")
    network: str | None = Field(
        default_factory=_default_network,
        description=(
            "Default Docker network for containers created by this executor. "
            f"Can also be set with {DOCKER_NETWORK_ENV_VAR}; "
            f"{LEGACY_MODELS_DOCKER_NETWORK_ENV_VAR} is accepted for compatibility."
        ),
    )
    resource_scope: str = Field(
        default=DEFAULT_RESOURCE_SCOPE,
        min_length=1,
        description=(
            "Owner scope label for Docker-managed resources. Orphan cleanup only lists resources with the "
            "same scope, allowing multiple platform instances to share one Docker daemon."
        ),
    )
    port_range_start: int = Field(
        default=49152,
        ge=1,
        le=65535,
        description="First host port to consider when publishing container ports for this executor.",
    )
    port_range_end: int = Field(
        default=49251,
        ge=1,
        le=65535,
        description="Last host port (inclusive) to consider when publishing container ports for this executor.",
    )

    @model_validator(mode="after")
    def _validate_port_range(self) -> DockerExecutorConfig:
        if self.port_range_start > self.port_range_end:
            raise ValueError("port_range_start must not exceed port_range_end")
        return self
