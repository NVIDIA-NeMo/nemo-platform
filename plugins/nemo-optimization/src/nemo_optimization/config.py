# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin config + job-id helper for the Tune (optimize) lane."""

from __future__ import annotations

from nmp.customization_common.contributor.config import BaseTrainingPluginConfig, generate_job_id
from pydantic_settings import SettingsConfigDict


class OptimizationPluginConfig(BaseTrainingPluginConfig):
    """Environment-driven optimize plugin settings.

    Optimize study orchestration is CPU-only (trial agent execution happens in
    Fabric/Evaluator), so the default execution profile is ``cpu`` rather than
    the training lanes' ``gpu``.
    """

    model_config = SettingsConfigDict(env_prefix="NMP_OPTIMIZATION_", extra="ignore")

    default_training_execution_profile: str = "cpu"


def get_config() -> OptimizationPluginConfig:
    return OptimizationPluginConfig()


def generate_optimize_id() -> str:
    return generate_job_id("optimize")
