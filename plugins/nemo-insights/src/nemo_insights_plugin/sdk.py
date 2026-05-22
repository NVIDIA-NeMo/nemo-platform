# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for the insights plugin.

Mounted as ``client.insights`` on both :class:`NeMoPlatform` and
:class:`AsyncNeMoPlatform`. Each resource exposes three sub-resources:

* ``client.insights.agent_registrations``
* ``client.insights.insights``
* ``client.insights.insight_traces``

The doubled ``insights.insights`` reads awkwardly; consumers can ``ir =
client.insights.insights`` once if it bothers them. See the plan's open question
#5 for the discussion.
"""

from __future__ import annotations

from typing import Any

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.sdk import NemoPluginSDKResources

# ---------------------------------------------------------------------------
# Sync sub-resources
# ---------------------------------------------------------------------------


class _SyncBase:
    def __init__(self, platform: NeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    def _insights_url(self, path: str) -> str:
        return str(self._platform.base_url).rstrip("/") + "/apis/insights" + path

    def _workspace_url(self, workspace: str, path: str) -> str:
        return self._insights_url(f"/v2/workspaces/{workspace}{path}")


class SyncAgentRegistrations(_SyncBase):
    def create(self, workspace: str, **body: Any) -> dict[str, Any]:
        r = self._http_client.post(self._workspace_url(workspace, "/agent_registrations"), json=body)
        r.raise_for_status()
        return r.json()

    def list(self, workspace: str, **params: Any) -> dict[str, Any]:
        r = self._http_client.get(self._workspace_url(workspace, "/agent_registrations"), params=params or None)
        r.raise_for_status()
        return r.json()

    def get(self, workspace: str, name: str) -> dict[str, Any]:
        r = self._http_client.get(self._workspace_url(workspace, f"/agent_registrations/{name}"))
        r.raise_for_status()
        return r.json()

    def update(self, workspace: str, name: str, **body: Any) -> dict[str, Any]:
        r = self._http_client.patch(self._workspace_url(workspace, f"/agent_registrations/{name}"), json=body)
        r.raise_for_status()
        return r.json()

    def delete(self, workspace: str, name: str) -> None:
        r = self._http_client.delete(self._workspace_url(workspace, f"/agent_registrations/{name}"))
        r.raise_for_status()


class SyncInsights(_SyncBase):
    def create(self, workspace: str, **body: Any) -> dict[str, Any]:
        r = self._http_client.post(self._workspace_url(workspace, "/insights"), json=body)
        r.raise_for_status()
        return r.json()

    def list(self, workspace: str, **params: Any) -> dict[str, Any]:
        r = self._http_client.get(self._workspace_url(workspace, "/insights"), params=params or None)
        r.raise_for_status()
        return r.json()

    def get(self, workspace: str, name: str) -> dict[str, Any]:
        r = self._http_client.get(self._workspace_url(workspace, f"/insights/{name}"))
        r.raise_for_status()
        return r.json()

    def update(self, workspace: str, name: str, **body: Any) -> dict[str, Any]:
        r = self._http_client.patch(self._workspace_url(workspace, f"/insights/{name}"), json=body)
        r.raise_for_status()
        return r.json()

    def delete(self, workspace: str, name: str) -> dict[str, Any]:
        """Soft delete — returns the updated entity with ``status="deleted"``."""
        r = self._http_client.delete(self._workspace_url(workspace, f"/insights/{name}"))
        r.raise_for_status()
        return r.json()


class SyncInsightTraces(_SyncBase):
    def create(self, workspace: str, **body: Any) -> dict[str, Any]:
        r = self._http_client.post(self._workspace_url(workspace, "/insight_traces"), json=body)
        r.raise_for_status()
        return r.json()

    def list(self, workspace: str, **params: Any) -> dict[str, Any]:
        r = self._http_client.get(self._workspace_url(workspace, "/insight_traces"), params=params or None)
        r.raise_for_status()
        return r.json()

    def get(self, workspace: str, name: str) -> dict[str, Any]:
        r = self._http_client.get(self._workspace_url(workspace, f"/insight_traces/{name}"))
        r.raise_for_status()
        return r.json()

    def update(self, workspace: str, name: str, **body: Any) -> dict[str, Any]:
        r = self._http_client.patch(self._workspace_url(workspace, f"/insight_traces/{name}"), json=body)
        r.raise_for_status()
        return r.json()

    def delete(self, workspace: str, name: str) -> None:
        r = self._http_client.delete(self._workspace_url(workspace, f"/insight_traces/{name}"))
        r.raise_for_status()


class InsightsResource:
    """Sync SDK namespace mounted as ``client.insights``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        self.agent_registrations = SyncAgentRegistrations(platform)
        self.insights = SyncInsights(platform)
        self.insight_traces = SyncInsightTraces(platform)


# ---------------------------------------------------------------------------
# Async sub-resources
# ---------------------------------------------------------------------------


class _AsyncBase:
    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    def _insights_url(self, path: str) -> str:
        return str(self._platform.base_url).rstrip("/") + "/apis/insights" + path

    def _workspace_url(self, workspace: str, path: str) -> str:
        return self._insights_url(f"/v2/workspaces/{workspace}{path}")


class AsyncAgentRegistrations(_AsyncBase):
    async def create(self, workspace: str, **body: Any) -> dict[str, Any]:
        r = await self._http_client.post(self._workspace_url(workspace, "/agent_registrations"), json=body)
        r.raise_for_status()
        return r.json()

    async def list(self, workspace: str, **params: Any) -> dict[str, Any]:
        r = await self._http_client.get(self._workspace_url(workspace, "/agent_registrations"), params=params or None)
        r.raise_for_status()
        return r.json()

    async def get(self, workspace: str, name: str) -> dict[str, Any]:
        r = await self._http_client.get(self._workspace_url(workspace, f"/agent_registrations/{name}"))
        r.raise_for_status()
        return r.json()

    async def update(self, workspace: str, name: str, **body: Any) -> dict[str, Any]:
        r = await self._http_client.patch(self._workspace_url(workspace, f"/agent_registrations/{name}"), json=body)
        r.raise_for_status()
        return r.json()

    async def delete(self, workspace: str, name: str) -> None:
        r = await self._http_client.delete(self._workspace_url(workspace, f"/agent_registrations/{name}"))
        r.raise_for_status()


class AsyncInsights(_AsyncBase):
    async def create(self, workspace: str, **body: Any) -> dict[str, Any]:
        r = await self._http_client.post(self._workspace_url(workspace, "/insights"), json=body)
        r.raise_for_status()
        return r.json()

    async def list(self, workspace: str, **params: Any) -> dict[str, Any]:
        r = await self._http_client.get(self._workspace_url(workspace, "/insights"), params=params or None)
        r.raise_for_status()
        return r.json()

    async def get(self, workspace: str, name: str) -> dict[str, Any]:
        r = await self._http_client.get(self._workspace_url(workspace, f"/insights/{name}"))
        r.raise_for_status()
        return r.json()

    async def update(self, workspace: str, name: str, **body: Any) -> dict[str, Any]:
        r = await self._http_client.patch(self._workspace_url(workspace, f"/insights/{name}"), json=body)
        r.raise_for_status()
        return r.json()

    async def delete(self, workspace: str, name: str) -> dict[str, Any]:
        r = await self._http_client.delete(self._workspace_url(workspace, f"/insights/{name}"))
        r.raise_for_status()
        return r.json()


class AsyncInsightTraces(_AsyncBase):
    async def create(self, workspace: str, **body: Any) -> dict[str, Any]:
        r = await self._http_client.post(self._workspace_url(workspace, "/insight_traces"), json=body)
        r.raise_for_status()
        return r.json()

    async def list(self, workspace: str, **params: Any) -> dict[str, Any]:
        r = await self._http_client.get(self._workspace_url(workspace, "/insight_traces"), params=params or None)
        r.raise_for_status()
        return r.json()

    async def get(self, workspace: str, name: str) -> dict[str, Any]:
        r = await self._http_client.get(self._workspace_url(workspace, f"/insight_traces/{name}"))
        r.raise_for_status()
        return r.json()

    async def update(self, workspace: str, name: str, **body: Any) -> dict[str, Any]:
        r = await self._http_client.patch(self._workspace_url(workspace, f"/insight_traces/{name}"), json=body)
        r.raise_for_status()
        return r.json()

    async def delete(self, workspace: str, name: str) -> None:
        r = await self._http_client.delete(self._workspace_url(workspace, f"/insight_traces/{name}"))
        r.raise_for_status()


class AsyncInsightsResource:
    """Async SDK namespace mounted as ``client.insights``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self.agent_registrations = AsyncAgentRegistrations(platform)
        self.insights = AsyncInsights(platform)
        self.insight_traces = AsyncInsightTraces(platform)


insights_sdk_resources = NemoPluginSDKResources(
    sync_resource=InsightsResource,
    async_resource=AsyncInsightsResource,
)
