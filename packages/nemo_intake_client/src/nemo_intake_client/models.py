# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Wire models for the supported Intake Python client operations."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, model_validator
from typing_extensions import TypeAliasType


class ExperimentContext(BaseModel):
    experiment_id: str
    test_case_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class AtifImageSource(BaseModel):
    media_type: Literal["image/jpeg", "image/png", "image/gif", "image/webp"]
    path: str

    model_config = ConfigDict(extra="forbid")


class AtifContentPartText(BaseModel):
    type: Literal["text"]
    text: str

    model_config = ConfigDict(extra="forbid")


class AtifContentPartImage(BaseModel):
    type: Literal["image"]
    source: AtifImageSource

    model_config = ConfigDict(extra="forbid")


AtifContentPart = TypeAliasType(
    "AtifContentPart",
    Annotated[AtifContentPartText | AtifContentPartImage, Field(discriminator="type")],
)


class AtifAgent(BaseModel):
    name: str
    version: str
    model_name: str | None = None
    tool_definitions: list[dict[str, Any]] | None = None
    extra: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class AtifToolCall(BaseModel):
    tool_call_id: str
    function_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class AtifMetrics(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    cost_usd: float | None = None
    prompt_token_ids: list[int] | None = None
    completion_token_ids: list[int] | None = None
    logprobs: list[float] | None = None
    extra: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class AtifFinalMetrics(BaseModel):
    total_prompt_tokens: int | None = None
    total_completion_tokens: int | None = None
    total_cached_tokens: int | None = None
    total_cost_usd: float | None = None
    total_steps: int | None = Field(default=None, ge=0)
    extra: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class AtifStepBase(BaseModel):
    step_id: int = Field(ge=1)
    timestamp: str | None = None
    message: str | list[AtifContentPart] = ""
    is_copied_context: bool | None = None
    extra: dict[str, Any] | None = None
    llm_call_count: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")


class AtifStepSystem(AtifStepBase):
    source: Literal["system"]


class AtifStepUser(AtifStepBase):
    source: Literal["user"]


class AtifStepAgent(AtifStepBase):
    source: Literal["agent"]
    model_name: str | None = None
    reasoning_effort: str | float | None = None
    reasoning_content: str | None = None
    tool_calls: list[AtifToolCall] | None = None
    metrics: AtifMetrics | None = None


AtifStep = TypeAliasType(
    "AtifStep",
    Annotated[AtifStepSystem | AtifStepUser | AtifStepAgent, Field(discriminator="source")],
)


class AtifIngestRequest(BaseModel):
    schema_version: Literal[
        "ATIF-v1.0", "ATIF-v1.1", "ATIF-v1.2", "ATIF-v1.3", "ATIF-v1.4", "ATIF-v1.5", "ATIF-v1.6", "ATIF-v1.7"
    ]
    session_id: str | None = None
    agent: AtifAgent
    final_metrics: AtifFinalMetrics | None = None
    continued_trajectory_ref: str | None = None
    notes: str | None = None
    extra: dict[str, Any] | None = None
    steps: list[AtifStep] = Field(default_factory=list)
    experiment_context: ExperimentContext | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_step_ids(self) -> Self:
        for index, step in enumerate(self.steps):
            if step.step_id != index + 1:
                raise ValueError(f"steps[{index}].step_id must be sequential from 1")
        return self


class EvaluatorResultDataType(StrEnum):
    NUMERIC = "NUMERIC"
    CATEGORICAL = "CATEGORICAL"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"


class EvaluatorResultInput(BaseModel):
    span_id: str
    session_id: str
    name: str
    data_type: EvaluatorResultDataType
    value: float | None = None
    string_value: str | None = None
    comment: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_value(self) -> Self:
        if self.data_type in (EvaluatorResultDataType.NUMERIC, EvaluatorResultDataType.BOOLEAN):
            if self.value is None:
                raise ValueError(f"value is required for {self.data_type.value}")
        elif self.string_value is None:
            raise ValueError(f"string_value is required for {self.data_type.value}")
        if self.data_type == EvaluatorResultDataType.BOOLEAN and self.value not in (0, 1, 0.0, 1.0):
            raise ValueError("value must be 0 or 1 for BOOLEAN")
        return self


class EvaluatorResult(BaseModel):
    evaluator_result_id: str
    span_id: str
    session_id: str
    workspace: str
    name: str
    value: float | None = None
    string_value: str | None = None
    data_type: EvaluatorResultDataType
    comment: str | None = None
    created_by: str | None = None
    created_at: datetime
    ingested_at: datetime


class SpanStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class TraceSortField(StrEnum):
    STARTED_AT_ASC = "started_at"
    STARTED_AT_DESC = "-started_at"


TraceMode = Literal["summary", "detailed"]


class TraceFilter(BaseModel):
    id: str | None = None
    session_id: str | None = None
    status: SpanStatus | None = None
    experiment_id: str | None = None
    test_case_id: str | None = None


class Trace(BaseModel):
    id: str
    root_span_id: str | None = None
    session_id: str
    workspace: str
    name: str | None = None
    experiment_context: ExperimentContext | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: float | None = None
    status: SpanStatus
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    cost_input_usd: float | None = None
    cost_output_usd: float | None = None
    span_count: int | None = None
    error_count: int | None = None


class ExperimentGroupRequest(BaseModel):
    name: str
    description: str | None = None
    insight_id: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] | None = None
    default_sort: str = "-created_at"

    model_config = ConfigDict(extra="forbid")


class ExperimentGroupResponse(BaseModel):
    id: str
    name: str
    workspace: str
    description: str | None = None
    insight_id: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] | None = None
    default_sort: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    experiment_count: int = 0


class ExperimentRequest(BaseModel):
    name: str
    experiment_group_id: str
    dataset_name: str
    dataset_version: str | None = None
    source_link: AnyUrl | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    parent_experiment_id: str | None = None
    status: str | None = None
    root_cause: str | None = None

    model_config = ConfigDict(extra="forbid")


class EvaluatorAggregate(BaseModel):
    sum: float | None = None
    mean: float | None = None
    median: float | None = None
    p90: float | None = None
    p95: float | None = None
    p99: float | None = None
    count: int = 0


class ExperimentResponse(BaseModel):
    id: str
    name: str
    workspace: str
    experiment_group_id: str
    dataset_name: str
    dataset_version: str | None = None
    source_link: AnyUrl | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    parent_experiment_id: str | None = None
    status: str | None = None
    root_cause: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pinned_at: datetime | None = None
    evaluator_names: list[str] = Field(default_factory=list)
    model_names: list[str] = Field(default_factory=list)
    agent_names: list[str] = Field(default_factory=list)
    agent_versions: list[str] = Field(default_factory=list)
    aggregate_scores: dict[str, EvaluatorAggregate] | None = None
    run_count: int = 0
    cost_usd: EvaluatorAggregate | None = None
    latency_ms: EvaluatorAggregate | None = None
