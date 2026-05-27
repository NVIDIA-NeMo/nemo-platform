# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Automodel job resources for status polling via the customization plugin API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from nemo_platform_plugin.jobs.schemas import PlatformJobStatusResponse
from pydantic import BaseModel

from nemo_automodel_plugin.sdk import http_utils


class AutomodelJobRecord(BaseModel):
    """Minimal job record returned by the customization Automodel jobs API."""

    name: str
    workspace: str
    status: str | None = None
    spec: dict[str, Any] | None = None


class AutomodelJobResource:
    """Sync handle for one submitted Automodel job."""

    def __init__(
        self,
        job: AutomodelJobRecord,
        http_client: Any,
        base_url: str,
        workspace: str,
        headers: dict[str, str],
    ) -> None:
        self.job = job
        self._http_client = http_client
        self._base_url = base_url
        self._workspace = workspace
        self._headers = headers

    def get_status(self) -> PlatformJobStatusResponse:
        """Fetch current job status."""
        response = self._http_client.get(
            _job_status_path(self._base_url, self._workspace, self.job.name),
            headers=self._headers,
        )
        response.raise_for_status()
        return PlatformJobStatusResponse.model_validate(response.json())


class AsyncAutomodelJobResource:
    """Async handle for one submitted Automodel job."""

    def __init__(
        self,
        job: AutomodelJobRecord,
        http_client: Any,
        base_url: str,
        workspace: str,
        headers: dict[str, str],
    ) -> None:
        self.job = job
        self._http_client = http_client
        self._base_url = base_url
        self._workspace = workspace
        self._headers = headers

    async def get_status(self) -> PlatformJobStatusResponse:
        """Fetch current job status."""
        response = await self._http_client.get(
            _job_status_path(self._base_url, self._workspace, self.job.name),
            headers=self._headers,
        )
        response.raise_for_status()
        return PlatformJobStatusResponse.model_validate(response.json())


def _job_status_path(base_url: str, workspace: str, job_name: str) -> str:
    encoded_workspace = quote(workspace, safe="")
    encoded_job = quote(job_name, safe="")
    return (
        f"{http_utils.base_url(base_url)}/apis/customization/v2/workspaces/"
        f"{encoded_workspace}/automodel/jobs/{encoded_job}"
    )
