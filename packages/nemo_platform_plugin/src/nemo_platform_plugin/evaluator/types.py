# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared request/response types for the Evaluator service.

Single source of truth for the HTTP contract. Replaces the Stainless-generated
evaluator types and the hand-written ``nemo_evaluator.sdk`` resource layer's
direct ``NeMoPlatform._client`` usage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NotRequired, TypedDict

from nemo_platform_plugin.schema import Page
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------


class EvaluatorJobResponse(BaseModel):
    """Response from a job submission (evaluate or agent-evaluate)."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    status: str = ""


class AgentEvalResult(BaseModel):
    """Agent evaluation result record."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    workspace: str = ""
    job: str = ""
    status: str = ""
    id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


AgentEvalResultPage = Page[AgentEvalResult]


class EvalResult(BaseModel):
    """Row evaluation result record."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    workspace: str = ""
    job: str = ""
    id: str | None = None
    created_at: datetime | None = None


EvalResultPage = Page[EvalResult]


class MetricBundle(BaseModel):
    """Stored metric bundle entity."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    workspace: str = ""
    id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


MetricBundlePage = Page[MetricBundle]


# ---------------------------------------------------------------------------
# Request types
# ---------------------------------------------------------------------------


class SubmitEvaluateJobRequest(BaseModel):
    """Request body for POST /evaluate/jobs."""

    model_config = ConfigDict(extra="allow")

    spec: dict[str, Any]


class SubmitAgentEvalJobRequest(BaseModel):
    """Request body for POST /agent-evaluate/jobs."""

    model_config = ConfigDict(extra="allow")

    spec: dict[str, Any]


class CreateMetricRequest(BaseModel):
    """Request body for POST /metrics."""

    model_config = ConfigDict(extra="allow")

    name: str
    spec: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Query parameter types
# ---------------------------------------------------------------------------


class ListAgentEvalResultsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]


class ListEvalResultsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]


class ListMetricsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]
