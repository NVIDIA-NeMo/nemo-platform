# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job resource handles for customization contributor SDK status polling."""

from typing import Any

from nemo_customizer.shared.sdk.http import CustomizationHttpHelpers
from nemo_platform_plugin.jobs.schemas import PlatformJobStatusResponse
from pydantic import BaseModel


class CustomizationJobRecord(BaseModel):
    """Minimal job record returned by a customization backend jobs API."""

    name: str
    workspace: str
    status: str | None = None
    spec: dict[str, Any] | None = None


class CustomizationJobResource:
    """Sync handle for one submitted customization job."""

    def __init__(
        self,
        job: CustomizationJobRecord,
        http_client: Any,
        http: CustomizationHttpHelpers,
        base_url: str,
        workspace: str,
        headers: dict[str, str],
    ) -> None:
        self.job = job
        self._http_client = http_client
        self._http = http
        self._base_url = base_url
        self._workspace = workspace
        self._headers = headers

    def get_status(self) -> PlatformJobStatusResponse:
        """Fetch current job status."""
        response = self._http_client.get(
            self._http.job_status_path(self._base_url, self._workspace, self.job.name),
            headers=self._headers,
        )
        response.raise_for_status()
        return PlatformJobStatusResponse.model_validate(response.json())


class AsyncCustomizationJobResource:
    """Async handle for one submitted customization job."""

    def __init__(
        self,
        job: CustomizationJobRecord,
        http_client: Any,
        http: CustomizationHttpHelpers,
        base_url: str,
        workspace: str,
        headers: dict[str, str],
    ) -> None:
        self.job = job
        self._http_client = http_client
        self._http = http
        self._base_url = base_url
        self._workspace = workspace
        self._headers = headers

    async def get_status(self) -> PlatformJobStatusResponse:
        """Fetch current job status."""
        response = await self._http_client.get(
            self._http.job_status_path(self._base_url, self._workspace, self.job.name),
            headers=self._headers,
        )
        response.raise_for_status()
        return PlatformJobStatusResponse.model_validate(response.json())
