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
from nemo_platform_plugin.client.platform_options import AsyncPlatformClientOptions, SyncPlatformClientOptions

SyncT = TypeVar("SyncT", bound=NemoClient)
AsyncT = TypeVar("AsyncT", bound=AsyncNemoClient)


def _sync_client_from_options(client_cls: type[SyncT], options: SyncPlatformClientOptions) -> SyncT:
    return client_cls(
        base_url=options.base_url,
        workspace=options.workspace,
        default_headers=options.default_headers,
        timeout=options.timeout,
        retry=options.retry,
        http_client=options.http_client,
        url_resolver=options.url_resolver,
        auth=options.auth,
    )


def _async_client_from_options(client_cls: type[AsyncT], options: AsyncPlatformClientOptions) -> AsyncT:
    return client_cls(
        base_url=options.base_url,
        workspace=options.workspace,
        default_headers=options.default_headers,
        timeout=options.timeout,
        retry=options.retry,
        http_client=options.http_client,
        url_resolver=options.url_resolver,
        auth=options.auth,
    )


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
    if isinstance(platform, AsyncNeMoPlatform):
        if not issubclass(client_cls, AsyncNemoClient):
            raise TypeError("AsyncNeMoPlatform requires an AsyncNemoClient class")
        return _async_client_from_options(client_cls, platform.typed_client_options())

    if not issubclass(client_cls, NemoClient):
        raise TypeError("NeMoPlatform requires a NemoClient class")
    return _sync_client_from_options(client_cls, platform.typed_client_options())
