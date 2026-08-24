# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Runtime metrics that surface a runner's own reward.

These live here rather than beside their runners because a built-in metric subclasses
``MetricBase``, which drags the dataset-schema stack (jinja2, jsonschema) with it. The Harbor
runtime is on the optimizer's light import path — see
``test_agent_eval_import_does_not_pull_the_execution_stack`` — so defining them there would make
every consumer of that module pay for machinery these metrics do not use. The runner modules
re-export them lazily, so ``from ...harbor_runtime import HarborRewardMetric`` still works.
"""

from typing import Literal

from nemo_evaluator_sdk.enums import MetricType
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values.metrics import MetricBase
from pydantic import Field

__all__ = ["GymRewardMetric", "HarborRewardMetric"]


class GymRewardMetric(MetricBase):
    """Score the Gym verifier reward stamped onto trial metadata.

    The Gym analogue of :class:`HarborRewardMetric`: reads the per-trial ``reward`` off the
    candidate metadata (populated by ``GymAgentTaskRunner``); a trial with no reward is left
    **unscored** (``None`` → ``nan``), excluded from the mean and surfaced as ``nan_count`` rather
    than counted as a spurious ``0.0``. Gym owns the scoring — this metric only surfaces it.
    """

    type: Literal[MetricType.GYM_REWARD] = MetricType.GYM_REWARD
    output_name: str = Field(
        default="reward", description="Name of the emitted score, read from the trial's `reward` metadata."
    )

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score(self.output_name)]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        reward = input.candidate.metadata.get("reward")
        value = float(reward) if reward is not None else None
        return MetricResult(outputs=[MetricOutput(name=self.output_name, value=value)])


class HarborRewardMetric(MetricBase):
    """Score the verifier reward Harbor stamped onto trial metadata.

    Reads ``reward`` from the candidate metadata (populated by ``build_trials_from_job_dir``); a
    trial with no verifier reward scores ``0.0``.
    """

    type: Literal[MetricType.HARBOR_REWARD] = MetricType.HARBOR_REWARD
    output_name: str = Field(
        default="reward", description="Name of the emitted score, read from the trial's `reward` metadata."
    )

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score(self.output_name)]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        reward = input.candidate.metadata.get("reward")
        value = float(reward) if reward is not None else 0.0
        return MetricResult(outputs=[MetricOutput(name=self.output_name, value=value)])
