# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared request/response types for the Evaluator service.

Single source of truth for the HTTP contract. Replaces the Stainless-generated
evaluator types and the hand-written ``nemo_evaluator.sdk`` resource layer's
direct ``NeMoPlatform._client`` usage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NotRequired, TypeAlias, TypedDict

from nemo_platform_plugin.schema import Page
from pydantic import BaseModel, ConfigDict, Field, RootModel

FlatQueryParams: TypeAlias = dict[str, str | int | bool | None]

# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------


class EvaluatorHealth(BaseModel):
    """Evaluator plugin health response."""

    model_config = ConfigDict(extra="allow")

    plugin: str | None = None
    status: str | None = None
    service: str | None = None
    jobs: list[str] = Field(default_factory=list)


class EvaluateJob(BaseModel):
    """Response from an evaluate job route."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    status: str | None = None
    spec: dict[str, Any] | None = None
    id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentEvalJob(BaseModel):
    """Response from an agent-evaluate job route."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    status: str | None = None
    spec: dict[str, Any] | None = None
    id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


EvaluatorJobResponse: TypeAlias = EvaluateJob


class _WorkspaceResource(BaseModel):
    """Permissive base for evaluator workspace resources."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    workspace: str | None = None
    id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentEvalResult(_WorkspaceResource):
    """Agent evaluation result record."""


AgentEvalResultPage = Page[AgentEvalResult]


class EvalResult(_WorkspaceResource):
    """Row evaluation result record."""


EvalResultPage = Page[EvalResult]


class Metric(_WorkspaceResource):
    """Stored metric bundle entity."""


MetricBundle: TypeAlias = Metric
MetricBundlePage = Page[Metric]


class Task(_WorkspaceResource):
    """Stored evaluator task entity."""


TaskPage = Page[Task]


class Taskset(_WorkspaceResource):
    """Stored evaluator taskset entity."""


TasksetPage = Page[Taskset]


class Revision(BaseModel):
    """Published task or taskset revision."""

    model_config = ConfigDict(extra="allow")

    content_hash: str | None = None
    revision: int | str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


RevisionPage = Page[Revision]


# ---------------------------------------------------------------------------
# Request types
# ---------------------------------------------------------------------------


class SubmitEvaluateJobRequest(BaseModel):
    """Request body for POST /evaluate/jobs."""

    model_config = ConfigDict(extra="forbid")

    spec: dict[str, Any]


class SubmitAgentEvalJobRequest(BaseModel):
    """Request body for POST /agent-evaluate/jobs."""

    model_config = ConfigDict(extra="forbid")

    spec: dict[str, Any]


class CreateMetricRequest(RootModel[dict[str, Any]]):
    """Request body for POST /metrics/{name}."""


class CreateTaskRequest(RootModel[dict[str, Any]]):
    """Request body for POST /tasks/{name}."""


class ReplaceTaskRequest(RootModel[dict[str, Any]]):
    """Request body for PUT /tasks/{name}."""


class CreateTasksetRequest(RootModel[dict[str, Any]]):
    """Request body for POST /tasksets/{name}."""


class ReplaceTasksetRequest(RootModel[dict[str, Any]]):
    """Request body for PUT /tasksets/{name}."""


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
    include_derived: NotRequired[bool]


class ListTasksQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]


class ListTasksetsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]


class ListRevisionsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]


class ProjectQueryParams(TypedDict, total=False):
    project: NotRequired[str]


class RevisionQueryParams(TypedDict, total=False):
    revision: NotRequired[str]
