# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapter to create a typed client from an existing platform client.

Accepts either a legacy ``NeMoPlatform`` SDK instance or a :class:`NemoClient`
/ :class:`AsyncNemoClient`, so plugins registered via ``NemoPluginSDKResources``
can use the typed endpoint/client infrastructure regardless of which platform
client the caller holds.

Usage::

    from nemo_platform_plugin.client.adapter import client_from_platform

    def make_sync_resource(platform: object) -> NemoClient:
        return client_from_platform(platform, NemoClient)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, TypeVar, cast, overload, runtime_checkable

import httpx
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.types import RetryPolicy

SyncT = TypeVar("SyncT", bound=NemoClient)
AsyncT = TypeVar("AsyncT", bound=AsyncNemoClient)


@runtime_checkable
class PlatformClient(Protocol):
    """Structural shape shared by every platform handle :func:`client_from_platform` accepts.

    Satisfied by :class:`NemoClient` / :class:`AsyncNemoClient` and by the
    generated ``NeMoPlatform`` / ``AsyncNeMoPlatform`` SDK classes. Use it to
    annotate ``sdk`` / ``async_sdk`` parameters that are only forwarded to
    :func:`client_from_platform`, so the annotating module does not need to
    import the generated SDK.
    """

    @property
    def base_url(self) -> str | httpx.URL: ...

    @property
    def workspace(self) -> str | None: ...


class _PlatformClient(Protocol):
    base_url: str | httpx.URL
    workspace: str | None
    max_retries: int
    timeout: float | httpx.Timeout | None
    _custom_headers: Mapping[str, str]
    _client: httpx.Client | httpx.AsyncClient

    def _prepare_url(self, url: str) -> httpx.URL: ...


def platform_default_headers(platform: object) -> dict[str, str]:
    """Return a copy of the default headers *platform* sends on every request.

    Reads ``default_headers`` off a :class:`NemoClient` / :class:`AsyncNemoClient`
    and ``_custom_headers`` off a generated ``NeMoPlatform`` SDK instance, so
    callers forwarding identity headers through a non-SDK HTTP client do not
    need to know which platform handle they were given.
    """
    if isinstance(platform, (NemoClient, AsyncNemoClient)):
        return dict(platform.default_headers)
    return dict(cast(_PlatformClient, platform)._custom_headers)


@overload
def client_from_platform(platform: object, client_cls: type[SyncT]) -> SyncT: ...
@overload
def client_from_platform(platform: object, client_cls: type[AsyncT]) -> AsyncT: ...


def client_from_platform(
    platform: object,
    client_cls: type[NemoClient] | type[AsyncNemoClient],
) -> NemoClient | AsyncNemoClient:
    """Create a typed client sharing a platform client's transport.

    When *platform* is already a :class:`NemoClient` or :class:`AsyncNemoClient`
    the typed client is derived with ``client_cls.from_client`` and shares its
    auth, headers, retry policy, and transport. Otherwise *platform* is treated
    as a generated ``NeMoPlatform`` SDK instance.

    The overloads preserve the sync/async pairing between platform and client.
    """
    if isinstance(platform, AsyncNemoClient):
        if not issubclass(client_cls, AsyncNemoClient):
            raise TypeError("AsyncNemoClient requires an AsyncNemoClient class")
        if isinstance(platform, client_cls):
            return platform
        return client_cls.from_client(platform)
    if isinstance(platform, NemoClient):
        if not issubclass(client_cls, NemoClient):
            raise TypeError("NemoClient requires a NemoClient class")
        if isinstance(platform, client_cls):
            return platform
        return client_cls.from_client(platform)

    platform_client = cast(_PlatformClient, platform)

    # Prefer _custom_headers (set via with_options/set_default_headers),
    # fall back to the httpx client's actual headers (set at construction,
    # e.g. TestClient(headers={...})), filtering out httpx defaults.
    headers = platform_client._custom_headers
    if not headers:
        _skip = {"accept", "accept-encoding", "connection", "user-agent", "host"}
        headers = {k: v for k, v in platform_client._client.headers.items() if k.lower() not in _skip}

    retry = RetryPolicy(
        max_retries=platform_client.max_retries,
        retryable_status_codes=(408, 409, 429),
        retry_all_server_errors=True,
        respect_retry_decision_headers=True,
        respect_retry_after_headers=True,
    )
    url_resolver = platform_client._prepare_url

    # Carry the platform's timeout across as a per-request override. The shared
    # httpx client keeps whatever timeout it was built with, so a caller's
    # ``platform.with_options(timeout=...)`` would otherwise be silently dropped
    # on the way to the typed client — the httpx client it hands over is the
    # *same* transport instance, with the *original* timeout still on it.
    timeout = platform_client.timeout
    if timeout is None:
        # ``None`` on the platform means "no timeout at all", but the typed
        # client reads None as "defer to the transport". Say the same thing in
        # the form httpx itself uses, so the override survives.
        timeout = httpx.Timeout(None)

    if isinstance(platform_client._client, httpx.AsyncClient):
        if not issubclass(client_cls, AsyncNemoClient):
            raise TypeError("AsyncNeMoPlatform requires an AsyncNemoClient class")
        return client_cls(
            base_url=str(platform_client.base_url).rstrip("/"),
            workspace=platform_client.workspace,
            default_headers=headers or None,
            timeout=timeout,
            retry=retry,
            http_client=platform_client._client,
            url_resolver=url_resolver,
        )

    if not issubclass(client_cls, NemoClient):
        raise TypeError("NeMoPlatform requires a NemoClient class")
    return client_cls(
        base_url=str(platform_client.base_url).rstrip("/"),
        workspace=platform_client.workspace,
        default_headers=headers or None,
        timeout=timeout,
        retry=retry,
        http_client=platform_client._client,
        url_resolver=url_resolver,
    )
