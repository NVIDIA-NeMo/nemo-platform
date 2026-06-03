# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unsloth contributor SDK resources (composed by ``nemo-customizer-plugin``).

A job-collection resource exposing ``plugin_status``, ``create``, and
``get_job_resource``, plus a ``UnslothCustomization`` namespace that
the hub mounts under ``client.customization.unsloth``.

Even though Unsloth runs locally, we keep the SDK because the
customization router still persists job records (the jobs collection
route is exposed). ``create`` will succeed at the HTTP layer up to the
point ``compile()`` runs; production deployments should prefer the
local CLI path.
"""

from __future__ import annotations

from typing import Any

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform

from nemo_unsloth_plugin.schema import UnslothJobInput
from nemo_unsloth_plugin.sdk import http_utils
from nemo_unsloth_plugin.sdk.job_resources import (
    AsyncUnslothJobResource,
    UnslothJobRecord,
    UnslothJobResource,
)


class UnslothJobsResource:
    """Sync SDK namespace at ``client.customization.unsloth.jobs``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    def plugin_status(self) -> dict[str, object]:
        """Return Unsloth contributor health from the customization service."""
        response = self._http_client.get(
            http_utils.url(
                self._platform,
                "v2/workspaces/{workspace}/unsloth/healthz",
                self._platform.workspace,
            ),
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Unsloth health response must be a JSON object.")
        return {str(key): value for key, value in payload.items()}

    def create(
        self,
        spec: UnslothJobInput,
        workspace: str | None = None,
        name: str | None = None,
    ) -> UnslothJobResource:
        """Submit an Unsloth training job record.

        Note:
            Unsloth jobs execute *locally* — the platform-side compile
            path raises ``NotImplementedError`` if the request lands
            against an environment that tries to run the canonical job
            container. Use ``nemo customization unsloth run`` for the
            common case.
        """
        body: dict[str, Any] = http_utils.create_job_payload(spec)
        if name is not None:
            body["name"] = name
        response = self._http_client.post(
            http_utils.jobs_collection_url(self._platform, workspace),
            json=body,
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        record = UnslothJobRecord.model_validate(response.json())
        resolved_ws = http_utils.resolve_workspace(self._platform, workspace)
        return UnslothJobResource(
            job=record,
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=http_utils.platform_default_headers(self._platform),
        )

    def get_job_resource(self, job_name: str, workspace: str | None = None) -> UnslothJobResource:
        """Get a resource handle for an existing Unsloth job."""
        resolved_ws = http_utils.resolve_workspace(self._platform, workspace)
        response = self._http_client.get(
            http_utils.job_url(self._platform, job_name, resolved_ws),
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return UnslothJobResource(
            job=UnslothJobRecord.model_validate(response.json()),
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=http_utils.platform_default_headers(self._platform),
        )


class AsyncUnslothJobsResource:
    """Async SDK namespace at ``client.customization.unsloth.jobs``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    async def plugin_status(self) -> dict[str, object]:
        response = await self._http_client.get(
            http_utils.url(
                self._platform,
                "v2/workspaces/{workspace}/unsloth/healthz",
                self._platform.workspace,
            ),
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Unsloth health response must be a JSON object.")
        return {str(key): value for key, value in payload.items()}

    async def create(
        self,
        spec: UnslothJobInput,
        workspace: str | None = None,
        name: str | None = None,
    ) -> AsyncUnslothJobResource:
        body: dict[str, Any] = http_utils.create_job_payload(spec)
        if name is not None:
            body["name"] = name
        response = await self._http_client.post(
            http_utils.jobs_collection_url(self._platform, workspace),
            json=body,
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        record = UnslothJobRecord.model_validate(response.json())
        resolved_ws = http_utils.resolve_workspace(self._platform, workspace)
        return AsyncUnslothJobResource(
            job=record,
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=http_utils.platform_default_headers(self._platform),
        )

    async def get_job_resource(self, job_name: str, workspace: str | None = None) -> AsyncUnslothJobResource:
        resolved_ws = http_utils.resolve_workspace(self._platform, workspace)
        response = await self._http_client.get(
            http_utils.job_url(self._platform, job_name, resolved_ws),
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return AsyncUnslothJobResource(
            job=UnslothJobRecord.model_validate(response.json()),
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=resolved_ws,
            headers=http_utils.platform_default_headers(self._platform),
        )


class UnslothCustomization:
    """Sync SDK namespace at ``client.customization.unsloth``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        self.jobs = UnslothJobsResource(platform)


class AsyncUnslothCustomization:
    """Async SDK namespace at ``client.customization.unsloth``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self.jobs = AsyncUnslothJobsResource(platform)
