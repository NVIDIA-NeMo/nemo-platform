# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Automodel contributor SDK resources (composed by ``nemo-customizer-plugin``)."""

from __future__ import annotations

from typing import Any

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform

from nemo_automodel_plugin.schema import AutomodelJobInput
from nemo_automodel_plugin.sdk import http_utils
from nemo_automodel_plugin.sdk.job_resources import (
    AsyncAutomodelJobResource,
    AutomodelJobRecord,
    AutomodelJobResource,
)


class AutomodelJobsResource:
    """Sync SDK namespace at ``client.customization.automodel.jobs``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    def plugin_status(self) -> dict[str, object]:
        """Return Automodel contributor health from the customization service."""
        response = self._http_client.get(
            http_utils.url(
                self._platform,
                "v2/workspaces/{workspace}/automodel/healthz",
                self._platform.workspace,
            ),
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Automodel health response must be a JSON object.")
        return {str(key): value for key, value in payload.items()}

    def create(
        self,
        spec: AutomodelJobInput,
        workspace: str | None = None,
        name: str | None = None,
    ) -> AutomodelJobResource:
        """Submit an Automodel training job."""
        body: dict[str, Any] = http_utils.create_job_payload(spec)
        if name is not None:
            body["name"] = name
        response = self._http_client.post(
            http_utils.jobs_collection_url(self._platform, workspace),
            json=body,
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        record = AutomodelJobRecord.model_validate(response.json())
        resolved_ws = http_utils.resolve_workspace(self._platform, workspace)
        return AutomodelJobResource(
            job=record,
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=http_utils.platform_default_headers(self._platform),
        )

    def get_job_resource(self, job_name: str, workspace: str | None = None) -> AutomodelJobResource:
        """Get a resource handle for an existing Automodel job."""
        resolved_ws = http_utils.resolve_workspace(self._platform, workspace)
        response = self._http_client.get(
            http_utils.job_url(self._platform, job_name, resolved_ws),
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return AutomodelJobResource(
            job=AutomodelJobRecord.model_validate(response.json()),
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=http_utils.platform_default_headers(self._platform),
        )


class AsyncAutomodelJobsResource:
    """Async SDK namespace at ``client.customization.automodel.jobs``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    async def plugin_status(self) -> dict[str, object]:
        """Return Automodel contributor health from the customization service."""
        response = await self._http_client.get(
            http_utils.url(
                self._platform,
                "v2/workspaces/{workspace}/automodel/healthz",
                self._platform.workspace,
            ),
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Automodel health response must be a JSON object.")
        return {str(key): value for key, value in payload.items()}

    async def create(
        self,
        spec: AutomodelJobInput,
        workspace: str | None = None,
        name: str | None = None,
    ) -> AsyncAutomodelJobResource:
        """Submit an Automodel training job."""
        body: dict[str, Any] = http_utils.create_job_payload(spec)
        if name is not None:
            body["name"] = name
        response = await self._http_client.post(
            http_utils.jobs_collection_url(self._platform, workspace),
            json=body,
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        record = AutomodelJobRecord.model_validate(response.json())
        resolved_ws = http_utils.resolve_workspace(self._platform, workspace)
        return AsyncAutomodelJobResource(
            job=record,
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=http_utils.platform_default_headers(self._platform),
        )

    async def get_job_resource(self, job_name: str, workspace: str | None = None) -> AsyncAutomodelJobResource:
        """Get a resource handle for an existing Automodel job."""
        resolved_ws = http_utils.resolve_workspace(self._platform, workspace)
        response = await self._http_client.get(
            http_utils.job_url(self._platform, job_name, resolved_ws),
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return AsyncAutomodelJobResource(
            job=AutomodelJobRecord.model_validate(response.json()),
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=http_utils.platform_default_headers(self._platform),
        )


class AutomodelCustomization:
    """Sync SDK namespace at ``client.customization.automodel``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        self.jobs = AutomodelJobsResource(platform)


class AsyncAutomodelCustomization:
    """Async SDK namespace at ``client.customization.automodel``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self.jobs = AsyncAutomodelJobsResource(platform)
