# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Value types for standalone agent evaluation runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from nemo_evaluator_sdk.values import Agent, Model, RunConfig, RunConfigOnline, RunConfigOnlineModel
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor

AgentEvalAttemptStatus = Literal["completed", "failed"]
CriterionType = str | list[str]


class AgentOutput(BaseModel):
    """Output produced by an evaluated agent or imported baseline response."""

    model_config = ConfigDict(extra="forbid")

    output_text: str | None = None
    response: Any | None = None
    evidence: CandidateEvidence | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentEvalMetricSpec(BaseModel):
    """Metric declaration attached to an agent-eval task."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "type")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("metric id and type must not be empty")
        return value


class AgentEvalTask(BaseModel):
    """Standalone agent-eval task."""

    model_config = ConfigDict(extra="forbid")

    id: str
    intent: str
    inputs: dict[str, Any]
    metrics: list[AgentEvalMetricSpec] = Field(default_factory=list)
    views: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _id_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("task id must not be empty")
        return value

    @model_validator(mode="after")
    def _metric_ids_must_be_unique(self) -> "AgentEvalTask":
        ids = [metric.id for metric in self.metrics]
        duplicates = sorted({metric_id for metric_id in ids if ids.count(metric_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate task metric ids: {duplicates}")
        return self


class AgentEvalAttempt(BaseModel):
    """Stored or generated candidate attempt for one task."""

    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    status: AgentEvalAttemptStatus = "completed"
    output: AgentOutput | None = None
    evidence: list[EvidenceDescriptor] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "task_id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("attempt id and task_id must not be empty")
        return value

    @model_validator(mode="after")
    def _completed_attempt_requires_output(self) -> "AgentEvalAttempt":
        if self.status == "completed" and self.output is None:
            raise ValueError("completed attempt requires output")
        return self


class EvidenceLocator(BaseModel):
    """Concrete link to evidence for a score deduction."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    uri: str
    line: int | None = Field(default=None, ge=1)
    json_path: str | None = None
    excerpt: str | None = None
    label: str | None = None

    @model_validator(mode="after")
    def _atif_requires_line(self) -> "EvidenceLocator":
        if self.kind.lower() == "atif" and self.line is None:
            raise ValueError("ATIF evidence locators require a line number")
        return self

    def href(self) -> str:
        """Return a browser-usable evidence link."""
        base = self.uri
        if base.startswith(("http://", "https://", "atif://")):
            href = base
        elif base.startswith("/"):
            href = Path(base).as_uri()
        else:
            href = quote(base)

        if self.line is None:
            return href

        line_fragment = f"L{self.line}"
        separator = "&" if "#" in href else "#"
        return f"{href}{separator}{line_fragment}"


class ScoreDeduction(BaseModel):
    """Lost points for one failed criterion, with traceable evidence."""

    model_config = ConfigDict(extra="forbid")

    raw_points: float = Field(gt=0)
    normalized_impact: float = Field(ge=0)
    criterion_id: str
    reason: str
    evidence: list[EvidenceLocator] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("criterion_id", "reason")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("criterion_id and reason must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_evidence(self) -> "ScoreDeduction":
        for locator in self.evidence:
            if locator.kind.lower() == "atif" and locator.line is None:
                raise ValueError("ATIF score deductions require line-resolvable evidence")
        return self


class CriterionScore(BaseModel):
    """Per-criterion scoring result."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    description: str
    criterion_type: CriterionType | None = None
    weight_name: str
    points: float
    fulfilled: bool
    evidence: list[EvidenceLocator] = Field(default_factory=list)
    judge_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentEvalTaskResult(BaseModel):
    """Score result for one task attempt."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    attempt_id: str
    model_id: str
    metric_id: str
    score: float = Field(ge=0, le=1)
    earned_points: float = Field(ge=0)
    max_points: float = Field(gt=0)
    domain: str | None = None
    criterion_scores: list[CriterionScore]
    deductions: list[ScoreDeduction] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentEvalSummary(BaseModel):
    """Aggregated agent-eval scores."""

    model_config = ConfigDict(extra="forbid")

    overall_score: float | None = None
    domain_scores: dict[str, float] = Field(default_factory=dict)
    model_scores: dict[str, float] = Field(default_factory=dict)
    model_domain_scores: dict[str, dict[str, float]] = Field(default_factory=dict)
    criterion_type_fulfilment: dict[str, float] = Field(default_factory=dict)
    task_count: int = 0
    attempt_count: int = 0
    deduction_count: int = 0


class AgentEvalRunConfig(BaseModel):
    """Configuration for a standalone agent-eval run."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    output_dir: Path | None = None
    run_id: str | None = None
    prompt_template: str | dict[str, Any] | None = None
    params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None
    parallelism: int = Field(default=4, ge=1)
    judge: Any | None = Field(default=None, exclude=True)
    model_inference_fn: Any | None = Field(default=None, exclude=True)
    agent_inference_fn: Any | None = Field(default=None, exclude=True)
    model_client: Any | None = Field(default=None, exclude=True)
    agent_client: Any | None = Field(default=None, exclude=True)
    default_headers: dict[str, str] | None = None
    write_dashboard: bool = True
    benchmark: dict[str, Any] = Field(default_factory=dict)


class AgentEvalRunResult(BaseModel):
    """Completed standalone agent-eval run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    tasks: list[AgentEvalTask]
    attempts: list[AgentEvalAttempt]
    results: list[AgentEvalTaskResult]
    summary: AgentEvalSummary
    benchmark: dict[str, Any] = Field(default_factory=dict)
    output_dir: Path | None = None
    dashboard_path: Path | None = None


AgentEvalTarget = Model | Agent
