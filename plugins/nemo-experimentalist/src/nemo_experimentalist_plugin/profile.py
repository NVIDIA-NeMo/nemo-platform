# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experimentalist-owned models for the shared ``optimizer.yaml`` profile.

The profile is the shared per-agent contract: the Platform-owned
``nemo insights analyze`` producer writes
``<profile-dir>/.nemo-optimizer/insights.yaml``, and
``nemo experimentalist run`` reads it by default. NeMo Experimentalist validates
the full experiment schema; NeMo Insights consumes only its analysis subset.
"""

from pathlib import Path

from nemo_insights_plugin.contracts.profile import load_profile_model
from pydantic import BaseModel, ConfigDict


class DatasetsSpec(BaseModel):
    """Train/validation dataset references: local paths or harbor registry refs."""

    model_config = ConfigDict(extra="forbid")

    train: str
    validation: str
    registry_url: str | None = None


class AgentProfile(BaseModel):
    """Parsed ``optimizer.yaml``; ``profile_dir`` anchors its relative paths."""

    model_config = ConfigDict(extra="forbid")

    agent: str
    task_template: str
    datasets: DatasetsSpec
    agent_source: str = "."
    agent_spec: str | None = None
    experiment_config: dict | str | None = None
    framework_skills: list[str] = []
    workspace: str = "default"
    profile_dir: Path


def load_profile(path: Path) -> AgentProfile:
    """Load and validate *path* as the Experimentalist's strict profile model."""
    return load_profile_model(path, AgentProfile)
