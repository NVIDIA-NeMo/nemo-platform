# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for the example plugin.

Endpoints are defined once in a mixin, then sync/async client classes
inherit the mixin + the appropriate client base.
The descriptor protocol on each endpoint returns the right bound callable.
"""

from __future__ import annotations

from nemo_example_plugin.types.endpoints import (
    CountEndpoint,
    CreateItemEndpoint,
    DeleteItemEndpoint,
    DownloadBlobEndpoint,
    GetItemEndpoint,
    HelloEndpoint,
    ListItemsEndpoint,
    UpdateItemEndpoint,
    UploadBlobEndpoint,
)
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.sdk import NemoPluginSDKResources

# -- Endpoint assignments (defined once) -----------------------------------


class _ExampleEndpoints:
    hello = HelloEndpoint
    create_item = CreateItemEndpoint
    list_items = ListItemsEndpoint
    get_item = GetItemEndpoint
    update_item = UpdateItemEndpoint
    delete_item = DeleteItemEndpoint
    count = CountEndpoint
    upload_blob = UploadBlobEndpoint
    download_blob = DownloadBlobEndpoint


# -- Client classes: mixin + client base -----------------------------------


class ExampleClient(_ExampleEndpoints, NemoClient):
    """Sync client for the example plugin API."""


class AsyncExampleClient(_ExampleEndpoints, AsyncNemoClient):
    """Async client for the example plugin API."""


# ---------------------------------------------------------------------------
# Plugin SDK registration — bridges NeMoPlatform to the new typed client
# ---------------------------------------------------------------------------


def _make_sync_resource(platform: NeMoPlatform) -> ExampleClient:
    return client_from_platform(platform, ExampleClient)


def _make_async_resource(platform: AsyncNeMoPlatform) -> AsyncExampleClient:
    return client_from_platform(platform, AsyncExampleClient)


example_sdk_resources = NemoPluginSDKResources(
    sync_resource=_make_sync_resource,
    async_resource=_make_async_resource,
)
