# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The reasoning component that selects a diverse survivor set."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nemo_experimentalist_plugin.config import MetricTarget
from nemo_experimentalist_plugin.entities import Candidate
from nemo_experimentalist_plugin.experimentalist.components.model_config import get_smart_model
from nemo_experimentalist_plugin.experimentalist.components.tools import WorkspaceTool
from nooa import Agent, CodeActStrategy, strategy
from nooa.config import CodeActConfig


class SurvivorSelector(Agent):
    """Select survivors from a Pareto-ranked population."""

    def __init__(self, workspace: Path, **kwargs: Any) -> None:
        super().__init__(llm=kwargs.pop("llm", None) or get_smart_model(), **kwargs)
        self.workspace = WorkspaceTool(workspace=workspace)

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=100, cell_timeout=3600.0)))
    async def select(
        self,
        ranked: list[Candidate],
        k: int,
        objective_metrics: list[MetricTarget],
        regression_metrics: list[MetricTarget],
    ) -> list[Candidate]:  # pyright: ignore[reportReturnType]
        """Choose up to k survivors from Pareto-ranked candidates.

        ``ranked`` is already Pareto-sorted using outcome and trajectory scores:
        front 0 (non-dominated) first, then front 1, etc. Inside a front,
        candidates are incomparable, so prefer agents with distinct architecture
        changes, complementary task coverage, and different trajectory strengths.

        To avoid getting stuck on the same agents round after round:
        1. Always include at least 1 candidate that was newly created this round. Look up
           `self.workspace.get_metadata(c.name)["round"]` for each candidate; new candidates
           are the ones whose round equals the max round across `ranked`.
        2. Prefer candidates with different optimization_type values or that address different root causes.
        3. If all new candidates sit on a worse Pareto front, still include the best new candidate.

        ## MANDATORY: Prefer agents with complementary strengths

        Read each candidate's per-dimension validation rewards from metadata and
        prefer a set whose strong dimensions cover each other (one agent leads on
        dimensions where another trails):

        ```python
        rewards = {c.id: self.workspace.get_metadata(c.name).reward("validation").metrics or {} for c in ranked}
        ```

        Between 1 to 3 survivors per round.
        Return the selected subset, preserving the input's Pareto-front order.

        ``objective_metrics`` are the evaluator metric dimensions to improve.
        ``regression_metrics`` are evaluator metric dimensions that must not
        worsen. Use their reported values as evidence; do not invent formulas,
        weights, thresholds, or another mechanical selection rule.
        """
        ...
