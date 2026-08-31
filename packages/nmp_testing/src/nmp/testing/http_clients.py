# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP client helpers for tests that need platform endpoint routing."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TypeAlias

import httpx
from nmp.common.platform_endpoint import PlatformEndpoint, resolve_platform_endpoint

SyncMockHandler: TypeAlias = Callable[[httpx.Request], httpx.Response]
AsyncMockHandler: TypeAlias = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]
MockHandler: TypeAlias = SyncMockHandler | AsyncMockHandler


def _set_request_url(request: httpx.Request, url: httpx.URL) -> None:
    if request.url == url:
        return
    request.url = url
    if url.host:
        request.headers["Host"] = url.netloc.decode("ascii")


class RoutedMockTransport(httpx.AsyncBaseTransport, httpx.BaseTransport):
    """Mock transport that applies platform endpoint routing before handling requests."""

    def __init__(self, handler: MockHandler, *, endpoint: PlatformEndpoint | None = None) -> None:
        self._endpoint = endpoint or resolve_platform_endpoint()
        self._mock_transport = httpx.MockTransport(handler)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        routed = self._endpoint.route_request_url(request.url)
        _set_request_url(request, routed.url)
        return self._mock_transport.handle_request(request)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        routed = self._endpoint.route_request_url(request.url)
        _set_request_url(request, routed.url)
        return await self._mock_transport.handle_async_request(request)


def routed_mock_transport(
    handler: MockHandler,
    *,
    endpoint: PlatformEndpoint | None = None,
) -> RoutedMockTransport:
    return RoutedMockTransport(handler, endpoint=endpoint)


def routed_mock_client(
    handler: MockHandler,
    *,
    endpoint: PlatformEndpoint | None = None,
) -> httpx.Client:
    return httpx.Client(transport=routed_mock_transport(handler, endpoint=endpoint))


def routed_async_mock_client(
    handler: MockHandler,
    *,
    endpoint: PlatformEndpoint | None = None,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=routed_mock_transport(handler, endpoint=endpoint))
