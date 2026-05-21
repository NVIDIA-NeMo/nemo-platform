# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pydantic schemas for ClickHouse-backed Intake spans."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, Self

from nmp.common.entities.values import DatetimeFilter
from nmp.intake.spans.domain import IntakeSpan, SpanKind, SpanStatus
from nmp.intake.spans.span_attribute_bags import SpanAttributeBags
from nmp.intake.spans.span_semantic_attributes import SpanSemanticAttributes
from pydantic import BaseModel, ConfigDict, Field


class SpanSortField(StrEnum):
    STARTED_AT_ASC = "started_at"
    STARTED_AT_DESC = "-started_at"


SpanMode = Literal["summary", "detailed"]


class SpanFilter(BaseModel):
    session_id: str | None = Field(default=None, description="Filter by span session id.")
    project: str | None = Field(default=None, description="Filter by project name.")
    evaluation_id: str | None = Field(default=None, description="Filter by evaluation id.")
    evaluation_sha: str | None = Field(default=None, description="Filter by evaluation sha.")
    evaluation_run_id: str | None = Field(
        default=None,
        description=(
            "Filter by evaluation run id. ATIF evaluation context is stored on root trajectory spans; "
            "use session_id from a matched root to fetch the full trace tree."
        ),
    )
    dataset_id: str | None = Field(default=None, description="Filter by dataset id.")
    dataset_name: str | None = Field(default=None, description="Filter by dataset name.")
    dataset_version: str | None = Field(default=None, description="Filter by dataset version.")
    test_case_id: str | None = Field(default=None, description="Filter by dataset test case id.")
    source: str | None = Field(
        default=None, description="Filter by ingest source (e.g. 'otel', 'atif', 'chat_completions')."
    )
    kind: SpanKind | None = Field(default=None, description="Filter by normalized span kind.")
    status: SpanStatus | None = Field(default=None, description="Filter by normalized span status.")
    model: str | None = Field(default=None, description="Filter by model name.")
    tool_name: str | None = Field(default=None, description="Filter by tool name.")
    provider: str | None = Field(default=None, description="Filter by provider (e.g. 'openai', 'nim', 'anthropic').")
    agent_id: str | None = Field(default=None, description="Filter by agent identifier.")
    agent_name: str | None = Field(
        default=None, description="Filter by agent application name (e.g. 'claude-code', 'codex')."
    )
    prompt_name: str | None = Field(default=None, description="Filter by prompt template name.")
    prompt_version: str | None = Field(default=None, description="Filter by prompt template version.")
    parent_span_id: str | None = Field(
        default=None, description="Filter by parent span id. Use to fetch direct children of a span."
    )
    started_at: DatetimeFilter | None = Field(default=None, description="Filter by span start timestamp.")


class SpanEvaluationContext(BaseModel):
    # Keep fields aligned with the ingest EvaluationContext. This read model does not
    # enforce ingest-side cross-field validation so historical rows can be read.
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str | None = None
    evaluation_sha: str | None = None
    evaluation_run_id: str | None = None
    dataset_id: str | None = None
    dataset_name: str | None = None
    dataset_version: str | None = None
    test_case_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_semantic_attributes(
        cls,
        attributes: SpanSemanticAttributes,
        *,
        metadata: dict[str, Any] | None,
    ) -> Self | None:
        context = cls(
            evaluation_id=attributes.evaluation_id,
            evaluation_sha=attributes.evaluation_sha,
            evaluation_run_id=attributes.evaluation_run_id,
            dataset_id=attributes.dataset_id,
            dataset_name=attributes.dataset_name,
            dataset_version=attributes.dataset_version,
            test_case_id=attributes.test_case_id,
            metadata=metadata or {},
        )
        if metadata is None and not context.has_scalar_values():
            return None
        return context

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


class Span(BaseModel):
    span_id: str
    session_id: str
    workspace: str
    project: str | None = None
    evaluation_context: SpanEvaluationContext | None = None
    parent_span_id: str | None = None
    kind: SpanKind
    name: str | None = None
    source: str
    trace_id: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    status: SpanStatus
    error_type: str | None = None
    error_message: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_id: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    tool_name: str | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    usage_details: dict[str, int] = Field(default_factory=dict)
    cost_total_usd: float | None = None
    cost_input_usd: float | None = None
    cost_output_usd: float | None = None
    cost_details: dict[str, float] = Field(default_factory=dict)
    input: str | None = None
    output: str | None = None
    raw_attributes: str | None = None
    ingested_at: datetime

    @classmethod
    def from_domain(cls, span: IntakeSpan, *, mode: SpanMode = "detailed") -> Self:
        summary = mode == "summary"
        attribute_bags = SpanAttributeBags.from_domain_maps(
            attributes_string=span.attributes_string,
            attributes_number=span.attributes_number,
            attributes_bool=span.attributes_bool,
        )
        semantic_attributes = SpanSemanticAttributes.from_bags(attribute_bags)
        cost_total = _float_or_none(semantic_attributes.cost_total_usd)
        return cls(
            span_id=span.external_span_id,
            session_id=span.session_id,
            workspace=span.workspace,
            project=semantic_attributes.project,
            evaluation_context=_evaluation_context(semantic_attributes, attribute_bags),
            parent_span_id=span.external_parent_span_id or None,
            kind=span.kind,
            name=span.name or None,
            source=span.source_format,
            trace_id=span.trace_id,
            started_at=span.start_time,
            ended_at=span.end_time,
            status=span.status,
            error_type=semantic_attributes.error_type,
            error_message=None if summary else semantic_attributes.error_message,
            provider=semantic_attributes.provider,
            model=semantic_attributes.model,
            prompt_id=semantic_attributes.prompt_id,
            prompt_name=semantic_attributes.prompt_name,
            prompt_version=semantic_attributes.prompt_version,
            agent_id=semantic_attributes.agent_id,
            agent_name=semantic_attributes.agent_name,
            tool_name=semantic_attributes.tool_name,
            input_tokens=semantic_attributes.input_tokens,
            output_tokens=semantic_attributes.output_tokens,
            cached_tokens=semantic_attributes.cached_tokens,
            total_tokens=semantic_attributes.total_tokens,
            usage_details=_usage_details(semantic_attributes),
            cost_total_usd=cost_total,
            cost_input_usd=_float_or_none(semantic_attributes.cost_input_usd),
            cost_output_usd=_float_or_none(semantic_attributes.cost_output_usd),
            cost_details=attribute_bags.cost_details(),
            input=None if summary else span.input or None,
            output=None if summary else span.output or None,
            raw_attributes=None if summary else attribute_bags.raw_attributes_json(),
            ingested_at=span.event_ts,
        )


def _evaluation_context(
    attributes: SpanSemanticAttributes,
    attribute_bags: SpanAttributeBags,
) -> SpanEvaluationContext | None:
    return SpanEvaluationContext.from_semantic_attributes(
        attributes,
        metadata=attribute_bags.evaluation_metadata(),
    )


def _usage_details(attributes: SpanSemanticAttributes) -> dict[str, int]:
    details: dict[str, int] = {}
    if attributes.prompt_cache_write_tokens is not None:
        details["prompt_details.cache_write"] = attributes.prompt_cache_write_tokens
    if attributes.prompt_audio_tokens is not None:
        details["prompt_details.audio"] = attributes.prompt_audio_tokens
    if attributes.completion_reasoning_tokens is not None:
        details["completion_details.reasoning"] = attributes.completion_reasoning_tokens
    if attributes.completion_audio_tokens is not None:
        details["completion_details.audio"] = attributes.completion_audio_tokens
    return details


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str | int | float | Decimal):
        return float(value)
    raise TypeError(f"Expected float-compatible span value, got {type(value).__name__}")
