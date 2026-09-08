# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed client for Insights analysis jobs."""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime

from nemo_insights_plugin.jobs.analyze import AnalyzeJob, AnalyzeSpec
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.endpoint import get, post
from nemo_platform_plugin.client.method import method
from nemo_platform_plugin.client.types import Paginated
from nemo_platform_plugin.jobs.schemas import PlatformJobStatus
from pydantic import BaseModel
from typing_extensions import NotRequired, TypedDict


class CreateAnalysisJobRequest(BaseModel):
    """Body accepted by the Insights analysis job route."""

    name: str | None = None
    description: str | None = None
    project: str | None = None
    spec: AnalyzeSpec
    ownership: dict[str, object] | None = None
    custom_fields: dict[str, object] | None = None
    output_location: str | None = None


class AnalysisJob(BaseModel):
    """Insights analysis job response from the plugin-owned job route."""

    id: str | None = None
    name: str
    description: str | None = None
    project: str | None = None
    workspace: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    spec: AnalyzeSpec
    status: PlatformJobStatus | None = None
    status_details: dict[str, object] | None = None
    error_details: dict[str, object] | None = None
    ownership: dict[str, object] | None = None
    custom_fields: dict[str, object] | None = None


_COLLECTION = f"/jobs/{AnalyzeJob.name}"


class ListAnalysisJobsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]


@post(f"/apis/insights/v2/workspaces/{{workspace}}{_COLLECTION}")
@abstractmethod
def create_analysis_job(*, workspace: str | None = None, body: CreateAnalysisJobRequest) -> AnalysisJob: ...


@get(f"/apis/insights/v2/workspaces/{{workspace}}{_COLLECTION}")
@abstractmethod
def list_analysis_jobs(
    *, workspace: str | None = None, query_params: ListAnalysisJobsQueryParams | None = None
) -> Paginated[AnalysisJob]: ...


@get(f"/apis/insights/v2/workspaces/{{workspace}}{_COLLECTION}/{{name}}")
@abstractmethod
def get_analysis_job(*, workspace: str | None = None, name: str) -> AnalysisJob: ...


class _AnalysisJobsMethods:
    create_analysis_job = method(create_analysis_job)
    list_analysis_jobs = method(list_analysis_jobs)
    get_analysis_job = method(get_analysis_job)


class AnalysisJobsClient(_AnalysisJobsMethods, NemoClient):
    """Sync client for the Insights analysis job API."""


class AsyncAnalysisJobsClient(_AnalysisJobsMethods, AsyncNemoClient):
    """Async client for the Insights analysis job API."""


__all__ = [
    "AnalysisJob",
    "AnalysisJobsClient",
    "AsyncAnalysisJobsClient",
    "CreateAnalysisJobRequest",
    "ListAnalysisJobsQueryParams",
]
