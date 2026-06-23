# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for the example plugin.

Endpoints are defined in ``types.endpoints``.  The plugin SDK registration
bridges ``NeMoPlatform`` to a plain ``NemoClient`` / ``AsyncNemoClient``
via the adapter.
"""

from __future__ import annotations

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.sdk import NemoPluginSDKResources


def _make_sync_resource(platform: NeMoPlatform) -> NemoClient:
    return client_from_platform(platform, NemoClient)


def _make_async_resource(platform: AsyncNeMoPlatform) -> AsyncNemoClient:
    return client_from_platform(platform, AsyncNemoClient)


example_sdk_resources = NemoPluginSDKResources(
    sync_resource=_make_sync_resource,
    async_resource=_make_async_resource,
)
