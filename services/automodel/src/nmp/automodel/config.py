# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for the nmp-automodel compiler and tasks."""

from nmp.common.config import create_service_config_class, get_platform_config, get_service_config
from pydantic import Field


class AutomodelConfig(create_service_config_class("automodel")):  # type: ignore
    """Environment variables use the NMP_AUTOMODEL_ prefix."""

    image_registry: str = Field(
        default="nvcr.io/0921617854601259/nemo-platform-dev",
        description=(
            "Registry host/path prefix for nmp-automodel-tasks and nmp-automodel-training. "
            "Override via NMP_AUTOMODEL_IMAGE_REGISTRY for other environments."
        ),
    )
    training_image: str | None = Field(
        default=None,
        description="Override GPU training image (default: nmp-automodel-training under image_registry).",
    )
    tasks_image: str | None = Field(
        default=None,
        description="Override CPU tasks image (default: nmp-automodel-tasks under image_registry).",
    )

    default_job_resource_cpu_request: str = Field(default="1")
    default_job_resource_memory_request: str = Field(default="8Gi")
    default_job_resource_cpu_limit: str = Field(default="4")
    default_job_resource_memory_limit: str = Field(default="16Gi")

    training_staleness_timeout_seconds: int = Field(
        default=3600,
        description="Terminate training if no task progress within this many seconds (0 disables).",
    )

    default_training_execution_profile: str = Field(
        default="gpu",
        description="Default GPU execution profile when the job spec omits training.execution_profile.",
    )


config = get_service_config(AutomodelConfig)
platform_config = get_platform_config()

# Legacy compiler attribute names
config.training_automodel_image = config.training_image
