# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resource namespaces for customization backends (composed by the hub)."""

from dataclasses import dataclass
from typing import Any

from nemo_customizer.shared.sdk.http import CustomizationHttpHelpers
from nemo_customizer.shared.sdk.job_resources import (
    AsyncCustomizationJobResource,
    CustomizationJobRecord,
    CustomizationJobResource,
)
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from pydantic import BaseModel


@dataclass(frozen=True)
class CustomizationSdkConfig:
    """Parameters for building a backend SDK namespace."""

    backend: str
    display_name: str
    input_schema: type[BaseModel]
    create_doc: str | None = None


def _parse_health_payload(payload: object, display_name: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise TypeError(f"{display_name} health response must be a JSON object.")
    return {str(key): value for key, value in payload.items()}


class CustomizationJobsResource:
    """Sync SDK namespace at ``client.customization.<backend>.jobs``."""

    def __init__(self, platform: NeMoPlatform, config: CustomizationSdkConfig) -> None:
        self._platform = platform
        self._http_client = platform._client
        self._config = config
        self._http = CustomizationHttpHelpers(config.backend)

    def plugin_status(self) -> dict[str, object]:
        """Return contributor health from the customization service."""
        response = self._http_client.get(
            self._http.url(self._platform, self._http.healthz_path(), self._platform.workspace),
            headers=self._http.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return _parse_health_payload(response.json(), self._config.display_name)

    def create(
        self,
        spec: BaseModel,
        workspace: str | None = None,
        name: str | None = None,
    ) -> CustomizationJobResource:
        """Submit a training job record."""
        body: dict[str, Any] = self._http.create_job_payload(spec)
        if name is not None:
            body["name"] = name
        response = self._http_client.post(
            self._http.jobs_collection_url(self._platform, workspace),
            json=body,
            headers=self._http.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        record = CustomizationJobRecord.model_validate(response.json())
        resolved_ws = self._http.resolve_workspace(self._platform, workspace)
        return CustomizationJobResource(
            job=record,
            http_client=self._http_client,
            http=self._http,
            base_url=self._http.base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=self._http.platform_default_headers(self._platform),
        )

    def get_job_resource(self, job_name: str, workspace: str | None = None) -> CustomizationJobResource:
        """Get a resource handle for an existing job."""
        resolved_ws = self._http.resolve_workspace(self._platform, workspace)
        response = self._http_client.get(
            self._http.job_url(self._platform, job_name, resolved_ws),
            headers=self._http.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return CustomizationJobResource(
            job=CustomizationJobRecord.model_validate(response.json()),
            http_client=self._http_client,
            http=self._http,
            base_url=self._http.base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=self._http.platform_default_headers(self._platform),
        )


class AsyncCustomizationJobsResource:
    """Async SDK namespace at ``client.customization.<backend>.jobs``."""

    def __init__(self, platform: AsyncNeMoPlatform, config: CustomizationSdkConfig) -> None:
        self._platform = platform
        self._http_client = platform._client
        self._config = config
        self._http = CustomizationHttpHelpers(config.backend)

    async def plugin_status(self) -> dict[str, object]:
        response = await self._http_client.get(
            self._http.url(self._platform, self._http.healthz_path(), self._platform.workspace),
            headers=self._http.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return _parse_health_payload(response.json(), self._config.display_name)

    async def create(
        self,
        spec: BaseModel,
        workspace: str | None = None,
        name: str | None = None,
    ) -> AsyncCustomizationJobResource:
        body: dict[str, Any] = self._http.create_job_payload(spec)
        if name is not None:
            body["name"] = name
        response = await self._http_client.post(
            self._http.jobs_collection_url(self._platform, workspace),
            json=body,
            headers=self._http.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        record = CustomizationJobRecord.model_validate(response.json())
        resolved_ws = self._http.resolve_workspace(self._platform, workspace)
        return AsyncCustomizationJobResource(
            job=record,
            http_client=self._http_client,
            http=self._http,
            base_url=self._http.base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=self._http.platform_default_headers(self._platform),
        )

    async def get_job_resource(
        self,
        job_name: str,
        workspace: str | None = None,
    ) -> AsyncCustomizationJobResource:
        resolved_ws = self._http.resolve_workspace(self._platform, workspace)
        response = await self._http_client.get(
            self._http.job_url(self._platform, job_name, resolved_ws),
            headers=self._http.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return AsyncCustomizationJobResource(
            job=CustomizationJobRecord.model_validate(response.json()),
            http_client=self._http_client,
            http=self._http,
            base_url=self._http.base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=self._http.platform_default_headers(self._platform),
        )


class CustomizationBackendSdk:
    """Sync SDK namespace at ``client.customization.<backend>``."""

    def __init__(self, platform: NeMoPlatform, config: CustomizationSdkConfig) -> None:
        self.jobs = CustomizationJobsResource(platform, config)


class AsyncCustomizationBackendSdk:
    """Async SDK namespace at ``client.customization.<backend>``."""

    def __init__(self, platform: AsyncNeMoPlatform, config: CustomizationSdkConfig) -> None:
        self.jobs = AsyncCustomizationJobsResource(platform, config)


def make_customization_sdk_classes(
    config: CustomizationSdkConfig,
) -> tuple[type, type, type, type]:
    """Build sync/async SDK root classes with backend-specific type names.

    Returns:
        (SyncCustomization, AsyncCustomization, SyncJobsResource, AsyncJobsResource)
        where the jobs resource types alias the shared implementations for typing.
    """

    class SyncJobsResource(CustomizationJobsResource):
        pass

    class AsyncJobsResource(AsyncCustomizationJobsResource):
        pass

    class SyncCustomization:
        """Sync SDK namespace."""

        def __init__(self, platform: NeMoPlatform) -> None:
            self.jobs = SyncJobsResource(platform, config)

    class AsyncCustomization:
        """Async SDK namespace."""

        def __init__(self, platform: AsyncNeMoPlatform) -> None:
            self.jobs = AsyncJobsResource(platform, config)

    SyncCustomization.__doc__ = f"Sync SDK namespace at ``client.customization.{config.backend}``."
    AsyncCustomization.__doc__ = f"Async SDK namespace at ``client.customization.{config.backend}``."
    SyncJobsResource.__doc__ = f"Sync SDK namespace at ``client.customization.{config.backend}.jobs``."
    AsyncJobsResource.__doc__ = f"Async SDK namespace at ``client.customization.{config.backend}.jobs``."

    return SyncCustomization, AsyncCustomization, SyncJobsResource, AsyncJobsResource
