# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapter to create a :class:`NemoClient` from an existing :class:`NeMoPlatform`.

This bridges the legacy ``NeMoPlatform`` SDK with the new typed client,
allowing plugins registered via ``NemoPluginSDKResources`` to use the
new endpoint/client infrastructure internally.

Usage::

    from nemo_platform_plugin.client.adapter import client_from_platform

    def make_sync_resource(platform: NeMoPlatform) -> NemoClient:
        return client_from_platform(platform, NemoClient)
"""

from __future__ import annotations

from typing import TypeVar, overload

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.types import RetryPolicy

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
    # Prefer _custom_headers (set via with_options/set_default_headers),
    # fall back to the httpx client's actual headers (set at construction,
    # e.g. TestClient(headers={...})), filtering out httpx defaults.
    # _custom_headers and _client are private Stainless SDK attrs present on both
    # NeMoPlatform and AsyncNeMoPlatform but not visible to the type checker.
    headers = platform._custom_headers  # type: ignore[union-attr]
    if not headers:
        _skip = {"accept", "accept-encoding", "connection", "user-agent", "host"}
        headers = {k: v for k, v in platform._client.headers.items() if k.lower() not in _skip}  # type: ignore[union-attr]

    retry = RetryPolicy(max_retries=platform.max_retries)
    if isinstance(platform, AsyncNeMoPlatform):
        if not issubclass(client_cls, AsyncNemoClient):
            raise TypeError("AsyncNeMoPlatform requires an AsyncNemoClient class")
        return client_cls(
            base_url=str(platform.base_url).rstrip("/"),
            workspace=platform.workspace,
            default_headers=headers or None,
            retry=retry,
            http_client=platform._client,
        )
    if not issubclass(client_cls, NemoClient):
        raise TypeError("NeMoPlatform requires a NemoClient class")
    return client_cls(
        base_url=str(platform.base_url).rstrip("/"),
        workspace=platform.workspace,
        default_headers=headers or None,
        retry=retry,
        http_client=platform._client,
    )
