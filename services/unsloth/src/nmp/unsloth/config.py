# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for the nmp-unsloth compiler and tasks.

Modeled after :mod:`nmp.automodel.config`. Environment variables use
the ``NMP_UNSLOTH_`` prefix. None of these settings are consumed by the
plugin's local ``run`` path today — they exist so a future container
submit (4-step PlatformJobSpec) lands without restructuring config.
"""

from nmp.common.config import create_service_config_class, get_platform_config, get_service_config
from pydantic import Field


class UnslothConfig(create_service_config_class("unsloth")):  # type: ignore[misc]
    """Environment variables use the ``NMP_UNSLOTH_`` prefix."""

    image_registry: str = Field(
        default="my-registry/nemo-platform-dev",
        description=(
            "Registry host/path prefix for nmp-unsloth-tasks and nmp-unsloth-training. "
            "Override via NMP_UNSLOTH_IMAGE_REGISTRY for other environments."
        ),
    )
    training_image: str | None = Field(
        default=None,
        description="Override GPU training image (default: nmp-unsloth-training under image_registry).",
    )
    tasks_image: str | None = Field(
        default=None,
        description="Override CPU tasks image (default: nmp-unsloth-tasks under image_registry).",
    )

    default_job_resource_cpu_request: str = Field(default="1")
    default_job_resource_memory_request: str = Field(default="8Gi")
    default_job_resource_cpu_limit: str = Field(default="4")
    default_job_resource_memory_limit: str = Field(default="16Gi")

    default_training_execution_profile: str = Field(
        default="gpu",
        description="Default GPU execution profile when the job spec omits training.execution_profile.",
    )


config = get_service_config(UnslothConfig)
platform_config = get_platform_config()
