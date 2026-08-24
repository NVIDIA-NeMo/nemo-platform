# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapter to create a typed client from an existing :class:`NemoClient`.

Retained for backward compatibility with call sites written during the
Stainless-to-NemoClient migration (``client_from_platform(sdk, FilesClient)``).
New code should call ``FilesClient.from_client(sdk)`` directly.

Usage::

    from nemo_platform_plugin.client.adapter import client_from_platform

    def make_sync_resource(client: NemoClient) -> FilesClient:
        return client_from_platform(client, FilesClient)
"""

from __future__ import annotations

from typing import TypeVar, overload

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient

SyncT = TypeVar("SyncT", bound=NemoClient)
AsyncT = TypeVar("AsyncT", bound=AsyncNemoClient)


@overload
def client_from_platform(platform: NemoClient, client_cls: type[SyncT]) -> SyncT: ...
@overload
def client_from_platform(platform: AsyncNemoClient, client_cls: type[AsyncT]) -> AsyncT: ...


def client_from_platform(
    platform: NemoClient | AsyncNemoClient,
    client_cls: type[NemoClient] | type[AsyncNemoClient],
) -> NemoClient | AsyncNemoClient:
    """Create a typed client from a :class:`NemoClient` / :class:`AsyncNemoClient`.

    Delegates to ``client_cls.from_client(platform)``, which shares the
    underlying HTTP transport, base URL, workspace, auth, headers, timeout,
    retry policy, and URL resolver.
    """
    return client_cls.from_client(platform)
