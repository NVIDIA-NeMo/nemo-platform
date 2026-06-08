# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parser for evaluator-specific agentic-use task metadata."""

import tomllib
from pathlib import Path
from typing import Any

from evaluator_agent_eval.schemas import SurfaceName
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvaluatorSurfaceConfig(BaseModel):
    """Surface policy declared by ``task.toml`` for scoring."""

    model_config = ConfigDict(extra="forbid")

    constraint: SurfaceName
    allowed: list[SurfaceName]
    forbidden: list[SurfaceName] = Field(default_factory=list)

    @field_validator("allowed")
    @classmethod
    def _allowed_not_empty(cls, value: list[SurfaceName]) -> list[SurfaceName]:
        if not value:
            raise ValueError("evaluator.surface.allowed must not be empty")
        return value


class EvaluatorExpectedConfig(BaseModel):
    """Task-specific deterministic answer expectations."""

    model_config = ConfigDict(extra="forbid")

    required_terms: list[str] = Field(default_factory=list)


class EvaluatorTaskConfig(BaseModel):
    """Evaluator benchmark extension for an agentic-use ``task.toml`` file."""

    model_config = ConfigDict(extra="forbid")

    surface: EvaluatorSurfaceConfig
    expected: EvaluatorExpectedConfig = Field(default_factory=EvaluatorExpectedConfig)
    forbidden_patterns: list[str] = Field(default_factory=list)


class AgenticUseTaskConfig(BaseModel):
    """Subset of the local agentic-use task contract used by this benchmark."""

    model_config = ConfigDict(extra="allow")

    version: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    evaluator: EvaluatorTaskConfig

    @property
    def suite_id(self) -> str:
        value = self.metadata.get("suite_id")
        return value if isinstance(value, str) and value else "evaluator_agent_benchmark"

    @property
    def suite_version(self) -> str:
        value = self.metadata.get("suite_version")
        return value if isinstance(value, str) and value else "v0"


def load_agentic_use_task_config(task_dir: str | Path) -> AgenticUseTaskConfig:
    """Load and validate the evaluator benchmark metadata from ``task.toml``."""
    task_path = Path(task_dir) / "task.toml"
    try:
        with task_path.open("rb") as fh:
            data = tomllib.load(fh)
        return AgenticUseTaskConfig.model_validate(data)
    except ValueError as exc:
        raise ValueError(f"Invalid evaluator benchmark task config at {task_path}: {exc}") from exc
