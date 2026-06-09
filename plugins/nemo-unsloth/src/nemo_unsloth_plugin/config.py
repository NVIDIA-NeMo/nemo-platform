# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin configuration for Unsloth container-submit training."""

from __future__ import annotations

import uuid

from pydantic_settings import BaseSettings, SettingsConfigDict


class UnslothPluginConfig(BaseSettings):
    """Environment-driven Unsloth plugin settings.

    All fields are optional. The only knob the contributor actually
    consumes today is ``default_training_execution_profile`` — forwarded
    into ``add_job_routes`` so the platform's job collection routes have
    a sensible profile when the submitter omits one.
    """

    model_config = SettingsConfigDict(env_prefix="NMP_UNSLOTH_", extra="ignore")

    default_training_execution_profile: str = "gpu"


def get_config() -> UnslothPluginConfig:
    return UnslothPluginConfig()


def generate_unsloth_id() -> str:
    """Generate a job name when the submitter omits ``name``."""
    return f"unsloth-{uuid.uuid4().hex[:12]}"
