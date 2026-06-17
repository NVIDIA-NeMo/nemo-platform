# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for the example plugin.

Uses :class:`~nemo_platform_plugin.client.client.NemoClient` with typed
:class:`~nemo_platform_plugin.client.endpoint.Endpoint` definitions so that
every ``send()`` call has full type inference on the response.

Registered via ``NemoPluginSDKResources`` for backward compatibility with
the ``NeMoPlatform`` plugin system — the adapter bridges the old platform
instance to the new typed client.
"""

from __future__ import annotations

from nemo_example_plugin.entities import ExampleItem
from nemo_example_plugin.types.endpoints import (
    CreateItemEndpoint,
    DeleteItemEndpoint,
    GetItemEndpoint,
    HelloEndpoint,
    ListItemsEndpoint,
    UpdateItemEndpoint,
)
from nemo_example_plugin.types.payloads import (
    CreateExampleItemRequest,
    ExampleItemPage,
    UpdateExampleItemRequest,
)
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.client.adapter import async_from_platform, from_platform
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.sdk import NemoPluginSDKResources


class ExampleClient(NemoClient):
    """Sync client for the example plugin API."""

    api_prefix = "/apis/example"

    # ------------------------------------------------------------------
    # Hello
    # ------------------------------------------------------------------

    def hello(self, name: str) -> str:
        resp = self.send(HelloEndpoint.request(name=name))
        return resp.data().message

    # ------------------------------------------------------------------
    # Items CRUD
    # ------------------------------------------------------------------

    def create_item(self, workspace: str, name: str, title: str, body: str = "", tags: list[str] | None = None) -> ExampleItem:
        req = CreateExampleItemRequest(name=name, title=title, body=body, tags=tags or [])
        return self.send(CreateItemEndpoint.request(req, workspace=workspace)).data()

    def list_items(self, workspace: str) -> ExampleItemPage:
        return self.send(ListItemsEndpoint.request(workspace=workspace)).data()

    def get_item(self, workspace: str, name: str) -> ExampleItem:
        return self.send(GetItemEndpoint.request(workspace=workspace, name=name)).data()

    def update_item(
        self,
        workspace: str,
        name: str,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
    ) -> ExampleItem:
        req = UpdateExampleItemRequest(title=title, body=body, tags=tags)
        return self.send(UpdateItemEndpoint.request(req, workspace=workspace, name=name)).data()

    def delete_item(self, workspace: str, name: str) -> None:
        self.send(DeleteItemEndpoint.request(workspace=workspace, name=name))


class AsyncExampleClient(AsyncNemoClient):
    """Async client for the example plugin API."""

    api_prefix = "/apis/example"

    # ------------------------------------------------------------------
    # Hello
    # ------------------------------------------------------------------

    async def hello(self, name: str) -> str:
        resp = await self.send(HelloEndpoint.request(name=name))
        return resp.data().message

    # ------------------------------------------------------------------
    # Items CRUD
    # ------------------------------------------------------------------

    async def create_item(self, workspace: str, name: str, title: str, body: str = "", tags: list[str] | None = None) -> ExampleItem:
        req = CreateExampleItemRequest(name=name, title=title, body=body, tags=tags or [])
        return (await self.send(CreateItemEndpoint.request(req, workspace=workspace))).data()

    async def list_items(self, workspace: str) -> ExampleItemPage:
        return (await self.send(ListItemsEndpoint.request(workspace=workspace))).data()

    async def get_item(self, workspace: str, name: str) -> ExampleItem:
        return (await self.send(GetItemEndpoint.request(workspace=workspace, name=name))).data()

    async def update_item(
        self,
        workspace: str,
        name: str,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
    ) -> ExampleItem:
        req = UpdateExampleItemRequest(title=title, body=body, tags=tags)
        return (await self.send(UpdateItemEndpoint.request(req, workspace=workspace, name=name))).data()

    async def delete_item(self, workspace: str, name: str) -> None:
        await self.send(DeleteItemEndpoint.request(workspace=workspace, name=name))


# ---------------------------------------------------------------------------
# Plugin SDK registration — bridges NeMoPlatform to the new typed client
# ---------------------------------------------------------------------------


def _make_sync_resource(platform: NeMoPlatform) -> ExampleClient:
    return from_platform(platform, ExampleClient)


def _make_async_resource(platform: AsyncNeMoPlatform) -> AsyncExampleClient:
    return async_from_platform(platform, AsyncExampleClient)


example_sdk_resources = NemoPluginSDKResources(
    sync_resource=_make_sync_resource,
    async_resource=_make_async_resource,
)
