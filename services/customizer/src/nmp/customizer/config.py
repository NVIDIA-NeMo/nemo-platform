# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for the Customizer service (v2)."""

from nmp.common.config import create_service_config_class, get_platform_config, get_service_config
from pydantic import Field


class CustomizerConfig(create_service_config_class("customizer")):  # type: ignore
    """
    Configuration for the Customizer service.

    Environment variables use the NMP_CUSTOMIZER_ prefix.
    """

    port: int = Field(
        default=8000,
        description="Port to run the service on",
    )

    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )

    # Container image overrides for training tasks.
    training_rl_image: str | None = Field(
        default=None,
        description="Override container image for DPO training. If not set, uses platform defaults.",
    )

    # Job resource defaults
    default_job_resource_cpu_request: str = Field(default="1")
    default_job_resource_memory_request: str = Field(default="8Gi")
    default_job_resource_cpu_limit: str = Field(default="4")
    default_job_resource_memory_limit: str = Field(default="16Gi")

    training_staleness_timeout_seconds: int = Field(
        default=3600,
        description="Terminate a training step if no task reports progress within this many seconds. 0 disables the check.",
    )

    default_training_execution_profile: str = Field(
        default="default",
        description="Default execution profile for GPU training steps. "
        "Used for all training jobs unless the user specifies one explicitly.",
    )


# Module-level singletons
config = get_service_config(CustomizerConfig)
platform_config = get_platform_config()
