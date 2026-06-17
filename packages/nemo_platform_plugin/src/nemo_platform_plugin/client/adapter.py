# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapter to create a :class:`NemoClient` from an existing :class:`NeMoPlatform`.

This bridges the legacy ``NeMoPlatform`` SDK with the new typed client,
allowing plugins registered via ``NemoPluginSDKResources`` to use the
new endpoint/client infrastructure internally.

Usage::

    from nemo_platform_plugin.client.adapter import client_from_platform

    class ExampleClient(_ExampleEndpoints, NemoClient):
        pass

    def make_example_client(platform: NeMoPlatform) -> ExampleClient:
        return client_from_platform(platform, ExampleClient)
"""

from __future__ import annotations

from typing import TypeVar, overload

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient

SyncT = TypeVar("SyncT", bound=NemoClient)
AsyncT = TypeVar("AsyncT", bound=AsyncNemoClient)


@overload
def client_from_platform(platform: NeMoPlatform, client_cls: type[SyncT]) -> SyncT: ...
@overload
def client_from_platform(platform: AsyncNeMoPlatform, client_cls: type[AsyncT]) -> AsyncT: ...


def client_from_platform(
    platform: NeMoPlatform | AsyncNeMoPlatform,
    client_cls: type[NemoClient] | type[AsyncNemoClient],
) -> NemoClient | AsyncNemoClient:
    """Create a :class:`NemoClient` or :class:`AsyncNemoClient` from a :class:`NeMoPlatform` instance.

    The overloads ensure callers get the correct concrete return type.
    """
    return client_cls(
        base_url=str(platform.base_url).rstrip("/"),
        workspace=platform.workspace,
        http_client=platform._client,  # type: ignore[arg-type]
    )
