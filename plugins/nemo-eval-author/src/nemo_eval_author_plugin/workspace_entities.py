# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# TODO(shared-module): exact copy of experimentalist Candidate entity for WorkspaceTool; unify with experimentalist entities.

from typing import Any, Sequence

from nemo_eval_author_plugin.evaluator.models import TrialResult
from nemo_platform_plugin.entity import NemoEntity
from pydantic import Field


class Candidate(NemoEntity, entity_type="candidate"):
    """Candidate metadata used by WorkspaceTool when reading agent metadata.json."""

    workspace: str = Field(default="default")
    run_id: str = Field(...)
    label: str = Field(...)
    ancestor: str | None = Field(default=None)
    round: int = Field(...)
    optimization: str = Field(...)
    optimization_type: str | None = Field(default=None)
    task_ids: list[str] = Field(default_factory=list)
    train_reward: dict[str, float] | None = Field(default=None)
    train_reward_details: Sequence[TrialResult] | None = Field(default=None)
    validation_reward: dict[str, float] | None = Field(default=None)
    validation_reward_details: Sequence[TrialResult] | None = Field(default=None)
    insight_reward: dict[str, float] | None = Field(default=None)
    insight_reward_details: Sequence[TrialResult] | None = Field(default=None)
    insight_suite_identity: str | None = Field(default=None)
    insight_metric_keys: list[str] | None = Field(default=None)
    validation_trajectory_reward: dict[str, float] | None = Field(default=None)
    validation_trajectory_reward_details: dict[str, Any] | None = Field(default=None)
    killed_round: int | None = Field(default=None)
    artifacts: dict[str, Any] = Field(default_factory=dict, exclude=True)
