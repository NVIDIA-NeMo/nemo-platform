# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for the auditor plugin.

Mounted on :class:`~nemo_platform.NeMoPlatform` as ``client.auditor`` via the
``nemo.sdk`` entry-point in :file:`pyproject.toml`. Exposes:

- ``client.auditor.plugin_status()`` — service healthz check.
- ``client.auditor.configs.{create,list,get,update,delete}`` — ``AuditConfig`` CRUD.
- ``client.auditor.targets.{create,list,get,update,delete}`` — ``AuditTarget`` CRUD.
- ``client.auditor.run(config=..., target=..., workspace=...)`` — submit an
  ``auditor.audit`` platform job through the plugin service.
"""

from __future__ import annotations

from nemo_auditor.entities import AuditConfig, AuditTarget
from nemo_auditor.jobs.audit import AuditInputSpec, AuditJob
from nemo_auditor.sdk_resources.configs import _AsyncConfigResource, _ConfigResource
from nemo_auditor.sdk_resources.targets import _AsyncTargetResource, _TargetResource
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.sdk import NemoPluginSDKResources


class AuditorPluginResource:
    """Sync SDK namespace mounted as ``client.auditor``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client
        self._configs: _ConfigResource | None = None
        self._targets: _TargetResource | None = None

    def plugin_status(self) -> dict[str, object]:
        response = self._http_client.get(self._url("/v1/healthz"))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Auditor plugin status response must be a JSON object.")
        return {str(key): value for key, value in payload.items()}

    @property
    def configs(self) -> _ConfigResource:
        if self._configs is None:
            self._configs = _ConfigResource(self)
        return self._configs

    @property
    def targets(self) -> _TargetResource:
        if self._targets is None:
            self._targets = _TargetResource(self)
        return self._targets

    def run(
        self,
        *,
        config: AuditConfig | str,
        target: AuditTarget | str,
        workspace: str | None = None,
    ) -> dict:
        """Submit an ``auditor.audit`` job through the plugin service."""
        ws = workspace or "default"
        spec = AuditInputSpec(config=config, target=target)
        response = self._http_client.post(
            self._url(f"/v2/workspaces/{ws}/jobs/{AuditJob.name}"),
            json={"spec": spec.model_dump(mode="json")},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Auditor job submission response must be a JSON object.")
        return payload

    def _url(self, path: str) -> str:
        return str(self._platform.base_url).rstrip("/") + "/apis/auditor" + path


class AsyncAuditorPluginResource:
    """Async SDK namespace mounted as ``client.auditor``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client
        self._configs: _AsyncConfigResource | None = None
        self._targets: _AsyncTargetResource | None = None

    async def plugin_status(self) -> dict[str, object]:
        response = await self._http_client.get(self._url("/v1/healthz"))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Auditor plugin status response must be a JSON object.")
        return {str(key): value for key, value in payload.items()}

    @property
    def configs(self) -> _AsyncConfigResource:
        if self._configs is None:
            self._configs = _AsyncConfigResource(self)
        return self._configs

    @property
    def targets(self) -> _AsyncTargetResource:
        if self._targets is None:
            self._targets = _AsyncTargetResource(self)
        return self._targets

    async def run(
        self,
        *,
        config: AuditConfig | str,
        target: AuditTarget | str,
        workspace: str | None = None,
    ) -> dict:
        """Submit an ``auditor.audit`` job through the plugin service."""
        ws = workspace or "default"
        spec = AuditInputSpec(config=config, target=target)
        response = await self._http_client.post(
            self._url(f"/v2/workspaces/{ws}/jobs/{AuditJob.name}"),
            json={"spec": spec.model_dump(mode="json")},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Auditor job submission response must be a JSON object.")
        return payload

    def _url(self, path: str) -> str:
        return str(self._platform.base_url).rstrip("/") + "/apis/auditor" + path


auditor_sdk_resources = NemoPluginSDKResources(
    sync_resource=AuditorPluginResource,
    async_resource=AsyncAuditorPluginResource,
)
