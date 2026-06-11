# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Domain model for Intake trace spans."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SpanKind(StrEnum):
    LLM = "LLM"
    CHAIN = "CHAIN"
    TOOL = "TOOL"
    RETRIEVER = "RETRIEVER"
    EMBEDDING = "EMBEDDING"
    AGENT = "AGENT"
    RERANKER = "RERANKER"
    EVALUATOR = "EVALUATOR"
    GUARDRAIL = "GUARDRAIL"
    UNKNOWN = "UNKNOWN"


class SpanStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class SpanAttributeFilter(BaseModel):
    field: str
    operator: str
    value: Any


class IntakeSpan(BaseModel):
    workspace: str
    session_id: str
    trace_id: str
    source_format: str
    external_span_id: str
    start_time: datetime
    event_ts: datetime
    id: int | None = Field(default=None, ge=0, le=(1 << 64) - 1)
    external_parent_span_id: str = ""
    parent_id: int | None = None
    kind: SpanKind = SpanKind.UNKNOWN
    name: str = ""
    status: SpanStatus = SpanStatus.UNKNOWN
    end_time: datetime | None = None
    attributes_string: dict[str, str] = Field(default_factory=dict)
    attributes_number: dict[str, float] = Field(default_factory=dict)
    attributes_bool: dict[str, bool] = Field(default_factory=dict)
    input: str = ""
    output: str = ""
    is_deleted: int = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_parent(self) -> Self:
        if not self.external_span_id:
            raise ValueError("external_span_id must not be empty")
        if self.external_parent_span_id == self.external_span_id:
            raise ValueError("external_parent_span_id must differ from external_span_id")
        return self


class SpanListFilter(BaseModel):
    workspace: str
    session_id: str | None = None
    trace_id: str | None = None
    external_parent_span_id: str | None = None
    source_format: str | None = None
    kind: SpanKind | None = None
    status: SpanStatus | None = None
    started_at_gte: datetime | None = None
    started_at_lte: datetime | None = None
    attribute_filters: list[SpanAttributeFilter] = Field(default_factory=list)


class SpanGroup(BaseModel):
    group: dict[str, str]
    span_count: int = Field(ge=0)


class TraceListFilter(BaseModel):
    workspace: str
    trace_id: str | None = None
    session_id: str | None = None
    source_format: str | None = None
    status: SpanStatus | None = None
    started_at_gte: datetime | None = None
    started_at_lte: datetime | None = None
    root_attribute_filters: list[SpanAttributeFilter] = Field(default_factory=list)
    span_attribute_filters: list[SpanAttributeFilter] = Field(default_factory=list)


TraceMode = Literal["summary", "detailed"]


class TraceEvaluationContext(BaseModel):
    # Read model for root-span evaluation context. Historical rows may have
    # partial context, so this intentionally does not reuse ingest validation.
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str | None = None
    evaluation_sha: str | None = None
    evaluation_run_id: str | None = None
    dataset_id: str | None = None
    dataset_name: str | None = None
    dataset_version: str | None = None
    test_case_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def has_scalar_values(self) -> bool:
        return any(
            value is not None
            for value in (
                self.evaluation_id,
                self.evaluation_sha,
                self.evaluation_run_id,
                self.dataset_id,
                self.dataset_name,
                self.dataset_version,
                self.test_case_id,
            )
        )


class IntakeTrace(BaseModel):
    id: str
    root_span_id: str | None = None
    workspace: str
    session_id: str
    source_format: str
    name: str | None = None
    input: str | None = None
    output: str | None = None
    project: str | None = None
    evaluation_context: TraceEvaluationContext | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: float | None = None
    ingested_at: datetime
    status: SpanStatus
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


class EvaluatorResultDataType(StrEnum):
    NUMERIC = "NUMERIC"
    CATEGORICAL = "CATEGORICAL"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"


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


class EvaluatorResultListFilter(BaseModel):
    workspace: str
    span_id: str | None = None
    session_id: str | None = None
    name: str | None = None
    data_type: EvaluatorResultDataType | None = None
    created_by: str | None = None
    value_gte: float | None = None
    value_lte: float | None = None
    created_at_gte: datetime | None = None
    created_at_lte: datetime | None = None


class AnnotationKind(StrEnum):
    FEEDBACK = "feedback"
    LABEL = "label"
    NOTE = "note"
    METADATA = "metadata"


class Annotation(BaseModel):
    """Post-hoc human-supplied signal on a span or session.

    Distinct from `EvaluatorResult` (automated eval pipeline output). Annotations
    are added after ingestion by humans or downstream processes: feedback (positive/
    negative), labels (categorical or numeric), free-text notes, or structured
    metadata.
    """

    annotation_id: str
    workspace: str
    span_id: str | None = None
    session_id: str

    kind: AnnotationKind
    name: str | None = None
    value_text: str | None = None
    value_numeric: float | None = None
    text: str | None = None
    metadata: dict[str, Any] | None = None

    created_by: str | None = None
    created_at: datetime
    ingested_at: datetime


class AnnotationListFilter(BaseModel):
    workspace: str
    span_id: str | None = None
    session_id: str | None = None
    kind: AnnotationKind | None = None
    name: str | None = None
    value_text: str | None = None
    value_numeric_gte: float | None = None
    value_numeric_lte: float | None = None
    created_by: str | None = None
    created_at_gte: datetime | None = None
    created_at_lte: datetime | None = None


class TraceBatch(BaseModel):
    spans: list[IntakeSpan] = Field(default_factory=list)
    evaluator_results: list[EvaluatorResult] = Field(default_factory=list)
