# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared request/response types for the Data Designer service.

Single source of truth for the HTTP contract. The Data Designer plugin
exposes a streaming preview function and a job-submission collection
(``/jobs/create``) rather than standard entity CRUD.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NotRequired, TypedDict

from nemo_platform_plugin.jobs.schemas import PlatformJobLogPage, PlatformJobStatus, PlatformJobStatusResponse
from nemo_platform_plugin.schema import Page
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Preview types
# ---------------------------------------------------------------------------


class PreviewRequest(BaseModel):
    """Request body for the Data Designer preview endpoint.

    Mirrors ``PreviewSpec`` from the plugin's function layer.  The ``config``
    field is an opaque dict because ``DataDesignerConfig`` is defined in the
    ``data_designer`` package, not in ``nemo_platform_plugin``.  Callers that
    have a ``DataDesignerConfigBuilder`` should call ``.build()`` and
    ``.to_dict()`` (or ``model_dump(mode="json")``) to produce this dict.
    """

    config: dict[str, Any]
    num_records: int | None = None


class PreviewFrameData(BaseModel):
    """A single NDJSON frame from the streaming preview response.

    The ``kind`` field discriminates the frame type.  Callers that need
    typed frame parsing should use the plugin's ``PreviewFrame`` union
    (``nemo_data_designer_plugin.functions._types``) to validate each line.
    """

    model_config = {"extra": "allow"}

    kind: str


# ---------------------------------------------------------------------------
# Job types
# ---------------------------------------------------------------------------


class DataDesignerJobRequest(BaseModel):
    """Request body for creating a Data Designer generation job.

    Mirrors ``BaseJobRequest`` with ``spec`` set to the Data Designer job
    config dict.  The ``spec`` is an opaque dict because
    ``DataDesignerJobConfig`` is defined in the plugin package.
    """

    name: str | None = None
    description: str | None = None
    project: str | None = None
    spec: dict[str, Any] = Field(default_factory=dict)
    ownership: dict[str, Any] | None = None
    custom_fields: dict[str, Any] | None = None
    output_location: str | None = None


class DataDesignerJobResponse(BaseModel):
    """Response model for a Data Designer job.

    Mirrors ``BaseJob`` with ``spec`` as an opaque dict.  The platform job
    status and timestamps come from the jobs service.
    """

    id: str | None = None
    name: str
    description: str | None = None
    project: str | None = None
    workspace: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    spec: dict[str, Any] = Field(default_factory=dict)
    status: PlatformJobStatus | None = None
    status_details: dict[str, Any] | None = None
    error_details: dict[str, Any] | None = None
    ownership: dict[str, Any] | None = None
    custom_fields: dict[str, Any] | None = None


DataDesignerJobPage = Page[DataDesignerJobResponse]


# ---------------------------------------------------------------------------
# Query parameter types
# ---------------------------------------------------------------------------


class ListDataDesignerJobsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]


class DataDesignerJobLogsQueryParams(TypedDict, total=False):
    limit: NotRequired[int]
    page_cursor: NotRequired[str]
