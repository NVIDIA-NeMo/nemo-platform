# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapter to create a :class:`NemoClient` from an existing :class:`NeMoPlatform`.

This bridges the legacy ``NeMoPlatform`` SDK with the new typed client,
allowing plugins registered via ``NemoPluginSDKResources`` to use the
new endpoint/client infrastructure internally.

Usage::

    from nemo_platform_plugin.client.adapter import from_platform, async_from_platform

    class ExampleClient(NemoClient):
        api_prefix = "/apis/example"

    def make_example_client(platform: NeMoPlatform) -> ExampleClient:
        return from_platform(platform, ExampleClient)
"""

from __future__ import annotations

from typing import TypeVar

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient

SyncT = TypeVar("SyncT", bound=NemoClient)
AsyncT = TypeVar("AsyncT", bound=AsyncNemoClient)


def from_platform(platform: NeMoPlatform, client_cls: type[SyncT]) -> SyncT:
    """Create a :class:`NemoClient` (or subclass) from a :class:`NeMoPlatform` instance."""
    return client_cls(
        base_url=str(platform.base_url).rstrip("/"),
        workspace=platform.workspace,
        http_client=platform._client,    )


def async_from_platform(platform: AsyncNeMoPlatform, client_cls: type[AsyncT]) -> AsyncT:
    """Create an :class:`AsyncNemoClient` (or subclass) from an :class:`AsyncNeMoPlatform` instance."""
    return client_cls(
        base_url=str(platform.base_url).rstrip("/"),
        workspace=platform.workspace,
        http_client=platform._client,    )
