# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run-time dependencies injected into every Experimentalist tool call.

A single :class:`ExperimentalistDeps` instance carries the resolved run
configuration through the Experimentalist loop. Keeping it in its own module
avoids an import cycle between the agent definition and the components it
coordinates.
"""

from __future__ import annotations

from pathlib import Path

from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import EvaluatorType
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DatasetRef
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import (
    ExperimentalistBackend,
)
from nemo_experimentalist_plugin.resolve import EvolutionaryOptimizerConfig
from pydantic import BaseModel, model_validator


class ExperimentalistDeps(BaseModel):
    """Per-run configuration injected into every Experimentalist tool.

    At least one of ``insight`` or ``agent`` must be set:
    - Mode 1 (``insight``): agent code defaults to the NMP insight entity's agent.
      When ``agent`` is also set, it overrides the insight's agent.
    - Mode 2 (``agent``): a local agent directory is used as the baseline.

    Attributes:
        workspace: NMP workspace the Experimentalist operates in.
        insight: Entity id of the Insight being processed (Mode 1).
        agent: Local path to the baseline agent directory (Mode 2), or an
            override for the agent referenced by ``insight``.
        dataset: Local directory path OR fileset ID for the evaluation dataset.
            A :class:`~pathlib.Path` means a local directory; a plain string
            means a fileset ID that the backend will resolve at evaluation time.
            Defaults to None and must be set before ``run()``.
        backend: Shared data-access backend used by every tool. The CLI
            owns the backend's client lifecycle — tools must not close it.
        config: Optional per-run override of the EvolutionaryOptimizerConfig.
            When None the optimizer uses its own default config.
    """

    model_config = {"arbitrary_types_allowed": True}

    workspace: str = "default"
    insight: Path | str | None = None
    agent: Path | str | None = None
    train_dataset: DatasetRef
    validation_dataset: DatasetRef
    task_template: DatasetRef | None = None
    evaluator_type: EvaluatorType = "harbor"
    agent_spec: str | None = None
    backend: ExperimentalistBackend | None = None
    config: EvolutionaryOptimizerConfig | None = None

    @model_validator(mode="after")
    def _require_insight_or_agent(self) -> ExperimentalistDeps:
        has_insight = self.insight is not None
        has_agent = self.agent is not None
        if not has_insight and not has_agent:
            raise ValueError("One of 'insight' (Mode 1) or 'agent' (Mode 2) must be set.")
        if has_insight and self.task_template is None:
            raise ValueError("'task_template' is required when 'insight' is set.")
        return self
