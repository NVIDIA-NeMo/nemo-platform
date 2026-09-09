# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed wire shapes for the Intake APIs used by evaluator."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, NotRequired, Required, TypedDict

from nemo_platform_plugin.schema import Page
from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

EvaluatorResultDataType = Literal["NUMERIC", "BOOLEAN", "CATEGORICAL", "TEXT"]
TraceMode = Literal["summary", "preview", "detailed"]
TraceStatus = Literal["OK", "ERROR", "UNSET"] | str


class EvaluationContextParam(TypedDict, total=False):
    evaluation_name: str
    test_case_name: str


class AtifAgentParam(TypedDict, total=False):
    name: Required[str]
    version: Required[str]
    model_name: NotRequired[str]
    tool_definitions: NotRequired[list[dict[str, Any]]]
    extra: NotRequired[dict[str, Any]]


class AtifFinalMetricsParam(TypedDict, total=False):
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cached_tokens: int
    total_cost_usd: float
    total_steps: int
    extra: dict[str, Any]


class AtifStepAgentParam(TypedDict, total=False):
    source: Required[Literal["agent"]]
    step_id: Required[int]
    timestamp: str | datetime
    message: str | list[dict[str, Any]]
    model_name: str
    reasoning_effort: str | float
    reasoning_content: str
    tool_calls: list[dict[str, Any]]
    metrics: dict[str, Any]
    observation: dict[str, Any]
    llm_call_count: int
    is_copied_context: bool
    extra: dict[str, Any]


AtifStepParam = dict[str, Any]


class AtifCreateParams(TypedDict, total=False):
    workspace: str
    evaluation_context: EvaluationContextParam
    schema_version: Required[str]
    session_id: str
    trajectory_id: str
    agent: Required[AtifAgentParam]
    final_metrics: AtifFinalMetricsParam
    continued_trajectory_ref: str
    notes: str
    extra: dict[str, Any]
    steps: list[AtifStepParam]
    subagent_trajectories: list[dict[str, Any]]


class AtifCreateRequest(RootModel[AtifCreateParams]):
    """Request body for POST /ingest/atif."""


class IngestResponse(BaseModel):
    """Response body for OTLP trace ingest."""

    errors: list[str] = Field(default_factory=list)


class EvaluatorResultCreateParams(TypedDict, total=False):
    workspace: str
    span_id: Required[str]
    session_id: Required[str]
    name: Required[str]
    value: float
    string_value: str
    data_type: Required[EvaluatorResultDataType]
    comment: str


class EvaluatorResultCreateRequest(BaseModel):
    """Request body for POST /evaluator-results."""

    model_config = ConfigDict(extra="forbid")

    span_id: str = Field(description="Target span id.")
    session_id: str = Field(description="Session id the target span belongs to.")
    name: str = Field(description="Evaluator / metric identity.")
    value: float | None = None
    string_value: str | None = None
    data_type: EvaluatorResultDataType
    comment: str | None = None

    @model_validator(mode="after")
    def _enforce_value_coherence(self) -> EvaluatorResultCreateRequest:
        if self.data_type in ("NUMERIC", "BOOLEAN") and self.value is None:
            raise ValueError(f"`value` is required when data_type is {self.data_type}.")
        if self.data_type in ("CATEGORICAL", "TEXT") and self.string_value is None:
            raise ValueError(f"`string_value` is required when data_type is {self.data_type}.")
        if self.data_type == "BOOLEAN" and self.value not in (0, 1, 0.0, 1.0):
            raise ValueError("`value` must be 0 or 1 when data_type is BOOLEAN.")
        return self


class EvaluatorResult(BaseModel):
    """Response model for evaluator-result reads."""

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


class EvaluatorAggregate(BaseModel):
    """Aggregate stats hydrated onto evaluation responses."""

    mean: float | None = None
    min: float | None = None
    max: float | None = None
    median: float | None = None
    p90: float | None = None
    p95: float | None = None
    p99: float | None = None
    count: int = 0


class EvaluationPatchRequest(BaseModel):
    """Partial-update body for an Evaluation."""

    model_config = ConfigDict(extra="forbid")

    experiment_ids: list[str] | None = None
    source_link: str | None = None
    metadata: dict[str, str] | None = None
    description: str | None = None
    parent_evaluation_id: str | None = None
    status: str | None = None
    root_cause: str | None = None


class EvaluationResponse(BaseModel):
    """Evaluation as served by the Intake API."""

    id: str
    name: str
    workspace: str
    experiment_ids: list[str]
    dataset_name: str
    dataset_version: str | None = None
    source_link: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    description: str | None = None
    parent_evaluation_id: str | None = None
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
    test_case_count: int = 0
    cost_usd: EvaluatorAggregate | None = None
    latency_ms: EvaluatorAggregate | None = None
    tokens: EvaluatorAggregate | None = None


class Trace(BaseModel):
    """Trace summary returned by Intake trace listing."""

    id: str
    root_span_id: str | None = None
    session_id: str
    workspace: str
    name: str | None = None
    input: str | None = None
    output: str | None = None
    evaluation_context: EvaluationContextParam | None = None
    agent_name: str | None = None
    agent_version: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: float | None = None
    status: TraceStatus
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = None
    cost_input_usd: float | None = None
    cost_output_usd: float | None = None
    models: list[str] | None = None
    providers: list[str] | None = None
    span_count: int | None = Field(default=None, ge=0)
    error_count: int | None = Field(default=None, ge=0)


class TraceFilterParam(TypedDict, total=False):
    id: str
    session_id: str
    status: str
    started_at: dict[str, str]
    evaluation_name: str
    test_case_name: str
    evaluation_id: str
    test_case_id: str
    agent_name: str


class ListTracesQueryParams(TypedDict, total=False):
    page: int
    page_size: int
    sort: str
    mode: TraceMode
    filter: TraceFilterParam


class ListEvaluatorResultsQueryParams(TypedDict, total=False):
    page: int
    page_size: int
    sort: str
    filter: dict[str, Any]


TracePage = Page[Trace]
EvaluatorResultPage = Page[EvaluatorResult]
