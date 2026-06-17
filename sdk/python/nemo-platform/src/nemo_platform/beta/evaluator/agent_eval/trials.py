# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trial artifacts and the runtime interface that produces them."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_platform.beta.evaluator.values import Agent, Model
from nemo_platform.beta.evaluator.values.evidence import CandidateEvidence
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentEvalTrialStatus(str, Enum):
    """Lifecycle status for a trial: completed, failed, or partial."""

    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AgentOutput(BaseModel):
    """Captured final output from the evaluated agent, model, or imported baseline for a trial."""

    model_config = ConfigDict(extra="forbid")

    output_text: str | None = Field(
        default=None,
        description="User-visible final text produced by the agent, if any.",
    )
    response: Any | None = Field(
        default=None,
        description="Structured final response payload produced by the agent, if any.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form metadata associated with the agent output.",
    )


class AgentEvalTrial(BaseModel):
    """Durable trial artifact for one task: output, evidence, status, and metadata."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable identifier for this trial.")
    task_id: str = Field(description="Identifier of the AgentEvalTask this trial was produced for.")
    status: AgentEvalTrialStatus = Field(description="Lifecycle status of the trial.")
    output: AgentOutput | None = Field(
        default=None,
        description="Final agent output captured for the trial; required when status is completed.",
    )
    evidence: CandidateEvidence | None = Field(
        default=None,
        description="Named evidence descriptors (final state, traces, logs, ...) captured for the trial.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form metadata associated with the trial.",
    )

    @field_validator("id", "task_id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("trial id and task_id must not be empty")
        return value

    @model_validator(mode="after")
    def _completed_trial_requires_output(self) -> AgentEvalTrial:
        if self.status == AgentEvalTrialStatus.COMPLETED and self.output is None:
            raise ValueError("completed trial requires output")
        return self


@runtime_checkable
class AgentTaskRunner(Protocol):
    """Online execution interface that runs tasks and produces trials."""

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> Sequence[AgentEvalTrial]: ...


AgentEvalTarget = Model | Agent | AgentTaskRunner
