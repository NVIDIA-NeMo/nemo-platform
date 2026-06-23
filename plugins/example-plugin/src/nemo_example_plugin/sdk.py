# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for the example plugin.

Endpoints are defined in ``types.endpoints.ExampleEndpoints``.  The client
classes expose them as direct methods via ``method()`` wrappers.
"""

from __future__ import annotations

from nemo_example_plugin.types.endpoints import ExampleEndpoints
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.method import method
from nemo_platform_plugin.sdk import NemoPluginSDKResources


_endpoints = ExampleEndpoints()


class _ExampleMethods:
    hello = method(_endpoints.hello)
    create_item = method(_endpoints.create_item)
    list_items = method(_endpoints.list_items)
    get_item = method(_endpoints.get_item)
    update_item = method(_endpoints.update_item)
    delete_item = method(_endpoints.delete_item)
    count = method(_endpoints.count)
    upload_blob = method(_endpoints.upload_blob)
    download_blob = method(_endpoints.download_blob)


class ExampleClient(_ExampleMethods, NemoClient):
    """Sync client for the example plugin API."""


class AsyncExampleClient(_ExampleMethods, AsyncNemoClient):
    """Async client for the example plugin API."""


def _make_sync_resource(platform: NeMoPlatform) -> ExampleClient:
    return client_from_platform(platform, ExampleClient)


def _make_async_resource(platform: AsyncNeMoPlatform) -> AsyncExampleClient:
    return client_from_platform(platform, AsyncExampleClient)


example_sdk_resources = NemoPluginSDKResources(
    sync_resource=_make_sync_resource,
    async_resource=_make_async_resource,
)
