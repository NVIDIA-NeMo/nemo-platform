# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pydantic schemas for ClickHouse-backed Intake trace summaries."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from nmp.common.entities.values import DatetimeFilter
from nmp.intake.spans.api.spans_schemas import SpanEvaluationContext
from nmp.intake.spans.domain import IntakeTrace, SpanStatus
from pydantic import BaseModel, ConfigDict, Field


class TraceSortField(StrEnum):
    STARTED_AT_ASC = "started_at"
    STARTED_AT_DESC = "-started_at"


TraceMode = Literal["summary", "detailed"]


class TraceFilter(BaseModel):
    id: str | None = Field(default=None, description="Filter by canonical Intake trace id.")
    session_id: str | None = Field(default=None, description="Filter by session id.")
    status: SpanStatus | None = Field(default=None, description="Filter by rolled-up trace status.")
    started_at: DatetimeFilter | None = Field(default=None, description="Filter by root span start timestamp.")
    evaluation_id: str | None = Field(default=None, description="Filter by root-span evaluation id.")
    evaluation_sha: str | None = Field(default=None, description="Filter by root-span evaluation sha.")
    evaluation_run_id: str | None = Field(default=None, description="Filter by root-span evaluation run id.")
    dataset_id: str | None = Field(default=None, description="Filter by root-span dataset id.")
    dataset_name: str | None = Field(default=None, description="Filter by root-span dataset name.")
    dataset_version: str | None = Field(default=None, description="Filter by root-span dataset version.")
    test_case_id: str | None = Field(default=None, description="Filter by root-span dataset test case id.")


class Trace(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    root_span_id: str | None = None
    session_id: str
    workspace: str
    name: str | None = None
    evaluation_context: SpanEvaluationContext | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: float | None = None
    status: SpanStatus
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = None
    cost_input_usd: float | None = None
    cost_output_usd: float | None = None
    span_count: int | None = Field(default=None, ge=0)
    error_count: int | None = Field(default=None, ge=0)

    @classmethod
    def from_domain(cls, trace: IntakeTrace) -> Self:
        return cls(
            id=trace.id,
            root_span_id=trace.root_span_id,
            session_id=trace.session_id,
            workspace=trace.workspace,
            name=trace.name,
            evaluation_context=SpanEvaluationContext.model_validate(trace.evaluation_context.model_dump())
            if trace.evaluation_context is not None
            else None,
            started_at=trace.started_at,
            ended_at=trace.ended_at,
            duration_ms=trace.duration_ms,
            status=trace.status,
            input_tokens=trace.input_tokens,
            output_tokens=trace.output_tokens,
            cached_tokens=trace.cached_tokens,
            total_tokens=trace.total_tokens,
            cost_usd=trace.cost_usd,
            cost_input_usd=trace.cost_input_usd,
            cost_output_usd=trace.cost_output_usd,
            span_count=trace.span_count,
            error_count=trace.error_count,
        )
