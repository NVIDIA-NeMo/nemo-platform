# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions for the Data Designer service.

The Data Designer plugin exposes:
- ``POST /preview`` — streaming NDJSON preview of a config
- ``/jobs/create`` collection — standard job CRUD (create, list, get, delete,
  status, logs) rebased from the generic ``/jobs`` collection

The service prefix is ``/apis/data-designer/v2/workspaces/{workspace}``.
"""

from __future__ import annotations

from abc import abstractmethod

from nemo_platform_plugin.client.endpoint import delete, get, post
from nemo_platform_plugin.client.types import Paginated, Stream
from nemo_platform_plugin.data_designer.types import (
    DataDesignerJobLogsQueryParams,
    DataDesignerJobRequest,
    DataDesignerJobResponse,
    ListDataDesignerJobsQueryParams,
    PreviewFrameData,
    PreviewRequest,
)
from nemo_platform_plugin.jobs.schemas import PlatformJobLogPage, PlatformJobStatusResponse

_DD = "/apis/data-designer/v2/workspaces/{workspace}"
_JOBS = f"{_DD}/jobs/create"


# ---------------------------------------------------------------------------
# Preview (streaming NDJSON)
# ---------------------------------------------------------------------------


@post(f"{_DD}/preview")
@abstractmethod
def preview(*, workspace: str | None = None, body: PreviewRequest) -> Stream[PreviewFrameData]: ...


# ---------------------------------------------------------------------------
# Job CRUD (collection: /jobs/create)
# ---------------------------------------------------------------------------


@post(_JOBS)
@abstractmethod
def create_job(*, workspace: str | None = None, body: DataDesignerJobRequest) -> DataDesignerJobResponse: ...


@get(_JOBS)
@abstractmethod
def list_jobs(
    *, workspace: str | None = None, query_params: ListDataDesignerJobsQueryParams | None = None
) -> Paginated[DataDesignerJobResponse]: ...


@get(f"{_JOBS}/{{name}}")
@abstractmethod
def get_job(*, workspace: str | None = None, name: str) -> DataDesignerJobResponse: ...


@delete(f"{_JOBS}/{{name}}")
@abstractmethod
def delete_job(*, workspace: str | None = None, name: str) -> None: ...


@get(f"{_JOBS}/{{name}}/status")
@abstractmethod
def get_job_status(*, workspace: str | None = None, name: str) -> PlatformJobStatusResponse: ...


@get(f"{_JOBS}/{{name}}/logs")
@abstractmethod
def get_job_logs(
    *, workspace: str | None = None, name: str, query_params: DataDesignerJobLogsQueryParams | None = None
) -> PlatformJobLogPage: ...
