# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin configuration for Automodel training."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AutomodelPluginConfig(BaseSettings):
    """Environment-driven Automodel plugin settings."""

    model_config = SettingsConfigDict(env_prefix="NMP_AUTOMODEL_", extra="ignore")

    default_training_execution_profile: str = "gpu"


def get_config() -> AutomodelPluginConfig:
    return AutomodelPluginConfig()


def generate_automodel_id() -> str:
    """Generate a job name when the submitter omits ``name``."""
    import uuid

    return f"automodel-{uuid.uuid4().hex[:12]}"
