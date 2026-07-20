# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rich NemoClient factory backed by platform internals.

This is the :class:`~nemo_platform_plugin.client.client.NemoClient` sibling of
:mod:`nmp.common.sdk_factory`.  It builds typed clients that reuse the same
platform machinery the SDK factory uses:

- base URL from :class:`~nmp.common.config.Configuration`;
- per-service URL routing via :class:`~nmp.common.sdk_factory.PlatformRequestRouter`;
- the shared sync/async HTTP clients (connection-pool + SSL-context reuse);
- principal / auth + internal-request headers via ``_get_default_headers``;
- OTEL trace-propagation headers captured on the current request.

:class:`PlatformNemoClientProvider` is registered under the ``nemo.client_provider``
entry-point group so :func:`nemo_platform_plugin.client_provider.get_nemo_client`
discovers it automatically whenever ``nmp-common`` is installed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nmp.common.auth import Principal
from nmp.common.config import get_platform_config
from nmp.common.http_clients import shared_async_http_client, shared_sync_http_client
from nmp.common.observability.otel import get_otel_headers
from nmp.common.sdk_factory import PlatformRequestRouter, _get_default_headers

logger = logging.getLogger(__name__)

# Test-only: async HTTP client to use for NemoClient requests in test context.
# Set by test fixtures to route requests through the in-process test transport,
# mirroring ``nmp.common.sdk_factory._test_http_client``.
_test_http_client: httpx.AsyncClient | None = None


def _base_url() -> str:
    return get_platform_config().base_url


def _absolute_url(url: str) -> httpx.URL:
    """Default resolver for the request router.

    :class:`NemoClient` hands its ``url_resolver`` the fully-qualified request
    URL (``base_url`` + path), so — unlike the generated SDK's ``_prepare_url``,
    which resolves a relative path — the router just needs to parse it.
    """
    return httpx.URL(url)


def _platform_url_resolver() -> Callable[[str], httpx.URL]:
    """Build a per-service URL router bound to the current platform config."""
    router = PlatformRequestRouter(
        platform_config=get_platform_config(),
        default_resolver=_absolute_url,
    )
    return router.resolve


def _platform_headers(
    as_service: str | None,
    internal: bool,
    on_behalf_of: str | Principal | None,
) -> dict[str, str]:
    """Auth / internal headers plus OTEL trace-propagation headers.

    ``_get_default_headers`` supplies the principal + internal-request markers
    (wire-identical to the SDK factory); ``get_otel_headers`` layers on the
    trace-propagation context captured on the current request (empty outside a
    request scope).
    """
    headers = _get_default_headers(as_service, internal, on_behalf_of)
    headers.update(get_otel_headers())
    return headers


def get_nemo_client(
    *,
    as_service: str | None = None,
    internal: bool = False,
    on_behalf_of: str | Principal | None = None,
    workspace: str | None = None,
    http_client: httpx.Client | None = None,
) -> NemoClient:
    """Build a sync :class:`NemoClient` configured with platform internals.

    Args:
        as_service: If provided, authenticate as ``service:{as_service}``.
            If ``None``, propagate the current request's / env principal.
        internal: Mark requests as internal (service-to-service).
        on_behalf_of: Principal (or id) to act on behalf of.  Passing a
            :class:`~nmp.common.auth.Principal` (rather than a bare id string)
            is only reachable through this direct entry point; the plugin-facing
            :class:`~nemo_platform_plugin.client_provider.NemoClientProvider`
            protocol narrows ``on_behalf_of`` to ``str | None``.
        workspace: Default workspace used to fill ``{workspace}`` path params.
        http_client: Optional sync HTTP client; defaults to the shared client.

    Note:
        OTEL trace-propagation headers are captured once, at construction, from
        the current request context.  Build a fresh client per request scope
        rather than caching one across requests, or its ``traceparent`` will be
        stale (mirrors ``get_platform_sdk``).
    """
    return NemoClient(
        base_url=_base_url(),
        workspace=workspace,
        default_headers=_platform_headers(as_service, internal, on_behalf_of) or None,
        http_client=http_client or shared_sync_http_client(),
        url_resolver=_platform_url_resolver(),
    )


def get_async_nemo_client(
    *,
    as_service: str | None = None,
    internal: bool = False,
    on_behalf_of: str | Principal | None = None,
    workspace: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> AsyncNemoClient:
    """Async counterpart of :func:`get_nemo_client`.

    Uses the explicitly provided ``http_client`` (e.g. from a test fixture), then
    the module-level ``_test_http_client`` fallback, then the shared async
    client — mirroring ``nmp.common.sdk_factory.get_async_platform_sdk``.
    """
    effective_client = http_client or _test_http_client or shared_async_http_client()
    return AsyncNemoClient(
        base_url=_base_url(),
        workspace=workspace,
        default_headers=_platform_headers(as_service, internal, on_behalf_of) or None,
        http_client=effective_client,
        url_resolver=_platform_url_resolver(),
    )


# ---------------------------------------------------------------------------
# Entry-point provider for nemo_platform_plugin.client_provider
# ---------------------------------------------------------------------------


class PlatformNemoClientProvider:
    """Rich :class:`~nemo_platform_plugin.client_provider.NemoClientProvider`
    that uses platform internals (shared HTTP clients, URL routing, OTEL
    headers, auth context).

    Registered as a ``nemo.client_provider`` entry-point so it is discovered
    automatically when ``nmp-common`` is installed.
    """

    def get_nemo_client(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | Principal | None = None,
        workspace: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> NemoClient:
        return get_nemo_client(
            as_service=as_service,
            internal=internal,
            on_behalf_of=on_behalf_of,
            workspace=workspace,
            http_client=http_client,
        )

    def get_async_nemo_client(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | Principal | None = None,
        workspace: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> AsyncNemoClient:
        return get_async_nemo_client(
            as_service=as_service,
            internal=internal,
            on_behalf_of=on_behalf_of,
            workspace=workspace,
            http_client=http_client,
        )
