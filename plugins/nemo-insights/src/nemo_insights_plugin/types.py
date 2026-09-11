# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed request/response DTOs for the Insights plugin HTTP client."""

from __future__ import annotations

from datetime import datetime
from typing import NotRequired, TypedDict

from nemo_insights_plugin.jobs.analyze import AnalyzeSpec
from nemo_platform_plugin.jobs.schemas import PlatformJobStatus
from pydantic import BaseModel, JsonValue


class ListInsightsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    agent: NotRequired[str]
    status: NotRequired[str]


class ListAnalysisConfigsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    enabled: NotRequired[bool]


class ListAnalysisRunsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    agent: NotRequired[str]


class ListAnalysisRunStatusesQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]


class CreateAnalysisJobRequest(BaseModel):
    """Body accepted by the Insights analysis job route."""

    name: str | None = None
    description: str | None = None
    project: str | None = None
    spec: AnalyzeSpec
    ownership: dict[str, JsonValue] | None = None
    custom_fields: dict[str, JsonValue] | None = None
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
    status_details: dict[str, JsonValue] | None = None
    error_details: dict[str, JsonValue] | None = None
    ownership: dict[str, JsonValue] | None = None
    custom_fields: dict[str, JsonValue] | None = None


class ListAnalysisJobsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str | dict[str, JsonValue]]
