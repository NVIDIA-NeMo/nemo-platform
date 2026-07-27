# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rich NemoClient factory backed by platform internals.

This is the :class:`~nemo_platform_plugin.client.client.NemoClient` sibling of
:mod:`nmp.common.sdk_factory`.  It builds typed clients that reuse the same
platform machinery the SDK factory uses:

- base URL from :class:`~nmp.common.config.Configuration`;
- per-service URL routing via :class:`~nmp.common.platform_endpoint.PlatformEndpoint`;
- endpoint-aware HTTP clients for TCP, Unix domain sockets, and service routes;
- principal / auth + internal-request headers via ``_get_default_headers``;
- OTEL trace-propagation headers captured on the current request.

:class:`PlatformNemoClientProvider` is registered under the ``nemo.client_provider``
entry-point group so :func:`nemo_platform_plugin.client_provider.get_nemo_client`
discovers it automatically whenever ``nmp-common`` is installed.
"""

from __future__ import annotations

import logging

import httpx
from nemo_platform_plugin.client.auth import TokenProvider
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.constants import (
    WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR,
    is_workload_identity_token_file_set,
    require_workload_identity_without_principal_env,
    workload_identity_token_file_from_env,
)
from nmp.common.auth import Principal, principal_from_env
from nmp.common.observability import MARK_INTERNAL_REQUEST_HEADERS
from nmp.common.observability.otel import get_otel_headers
from nmp.common.platform_endpoint import PlatformEndpoint, resolve_platform_endpoint
from nmp.common.sdk_factory import _get_default_headers

logger = logging.getLogger(__name__)


def _sync_http_client_for_endpoint(
    endpoint: PlatformEndpoint,
    http_client: httpx.Client | None,
) -> httpx.Client:
    """Return the sync HTTP client this NemoClient should use.

    Explicit clients are caller-owned and keep their transport. Otherwise the
    endpoint builds the concrete default client for TCP, UDS, and service-route
    transports in one place.
    """
    if http_client is not None:
        return http_client
    return endpoint.sync_sdk_http_client()


def _async_http_client_for_endpoint(
    endpoint: PlatformEndpoint,
    http_client: httpx.AsyncClient | None,
) -> httpx.AsyncClient:
    """Async counterpart of :func:`_sync_http_client_for_endpoint`."""
    if http_client is not None:
        return http_client
    return endpoint.async_sdk_http_client()


def _workload_identity_auth(base_url: str) -> TokenProvider:
    """Build a workload-identity token-exchange auth provider.

    Only call when :func:`is_workload_identity_token_file_set` is true.
    """
    from nemo_platform_plugin.client.oidc_factory import resolve_workload_exchange_provider

    token_file = workload_identity_token_file_from_env()
    if token_file is None:
        raise RuntimeError(f"{WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR} is not set")
    return resolve_workload_exchange_provider(base_url=base_url, subject_token_file=token_file)


def _workload_identity_headers(internal: bool) -> dict[str, str]:
    return MARK_INTERNAL_REQUEST_HEADERS.copy() if internal else {}


def _should_bootstrap_workload_identity(
    *,
    as_service: str | None,
    on_behalf_of: str | Principal | None,
    endpoint: PlatformEndpoint,
) -> bool:
    if not is_workload_identity_token_file_set():
        return False
    require_workload_identity_without_principal_env()
    if as_service is not None or on_behalf_of is not None:
        raise ValueError(f"{WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR} cannot be combined with trusted principal headers")
    return endpoint.transport != "uds"


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
    for name, value in get_otel_headers().items():
        normalized_name = name.lower()
        if normalized_name == "x-nmp-internal" or normalized_name.startswith("x-nmp-principal-"):
            continue
        headers[name] = value
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
        http_client: Optional sync HTTP client. If omitted, this factory builds
            the endpoint-aware default client.

    Note:
        OTEL trace-propagation headers are captured once, at construction, from
        the current request context.  Build a fresh client per request scope
        rather than caching one across requests, or its ``traceparent`` will be
        stale (mirrors ``get_platform_sdk``).
    """
    endpoint = resolve_platform_endpoint()
    client_http = _sync_http_client_for_endpoint(endpoint, http_client)
    if _should_bootstrap_workload_identity(
        as_service=as_service,
        on_behalf_of=on_behalf_of,
        endpoint=endpoint,
    ):
        return NemoClient(
            base_url=endpoint.connect_base_url,
            workspace=workspace,
            auth=_workload_identity_auth(endpoint.connect_base_url),
            default_headers=_workload_identity_headers(internal) or None,
            http_client=client_http,
        )
    return NemoClient(
        base_url=endpoint.connect_base_url,
        workspace=workspace,
        default_headers=_platform_headers(as_service, internal, on_behalf_of) or None,
        http_client=client_http,
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

    Uses the explicitly provided ``http_client`` (e.g. from a test fixture), or
    the endpoint-aware default async client.
    """
    endpoint = resolve_platform_endpoint()
    client_http = _async_http_client_for_endpoint(endpoint, http_client)
    if _should_bootstrap_workload_identity(
        as_service=as_service,
        on_behalf_of=on_behalf_of,
        endpoint=endpoint,
    ):
        return AsyncNemoClient(
            base_url=endpoint.connect_base_url,
            workspace=workspace,
            auth=_workload_identity_auth(endpoint.connect_base_url),
            default_headers=_workload_identity_headers(internal) or None,
            http_client=client_http,
        )
    return AsyncNemoClient(
        base_url=endpoint.connect_base_url,
        workspace=workspace,
        default_headers=_platform_headers(as_service, internal, on_behalf_of) or None,
        http_client=client_http,
    )


def get_task_nemo_client(
    service_name: str,
    *,
    workspace: str | None = None,
    http_client: httpx.Client | None = None,
) -> NemoClient:
    """Build a sync :class:`NemoClient` for use inside a task container.

    NemoClient counterpart of :func:`nmp.common.sdk_factory.get_task_sdk`:
    reads the job creator's principal from ``NMP_PRINCIPAL`` and authenticates
    as ``service:{service_name}`` while acting on behalf of that creator, or --
    when ``NMP_WORKLOAD_IDENTITY_TOKEN_FILE`` is set -- bootstraps
    workload-identity bearer-token exchange (via :func:`get_nemo_client` with
    ``internal=True``) instead of trusted ``X-NMP-*`` principal headers.
    """
    if is_workload_identity_token_file_set():
        require_workload_identity_without_principal_env()
        return get_nemo_client(internal=True, workspace=workspace, http_client=http_client)
    principal = principal_from_env()
    if principal is None:
        logger.warning(
            "NMP_PRINCIPAL not set; task NemoClient will authenticate as service:%s without on-behalf-of delegation",
            service_name,
        )
    return get_nemo_client(
        as_service=service_name,
        internal=True,
        on_behalf_of=principal.effective_principal if principal else None,
        workspace=workspace,
        http_client=http_client,
    )


def get_async_task_nemo_client(
    service_name: str,
    *,
    workspace: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> AsyncNemoClient:
    """Async counterpart of :func:`get_task_nemo_client`. Wire-identical."""
    if is_workload_identity_token_file_set():
        require_workload_identity_without_principal_env()
        return get_async_nemo_client(internal=True, workspace=workspace, http_client=http_client)
    principal = principal_from_env()
    if principal is None:
        logger.warning(
            "NMP_PRINCIPAL not set; async task NemoClient will authenticate as service:%s without on-behalf-of delegation",
            service_name,
        )
    return get_async_nemo_client(
        as_service=service_name,
        internal=True,
        on_behalf_of=principal.effective_principal if principal else None,
        workspace=workspace,
        http_client=http_client,
    )


# ---------------------------------------------------------------------------
# Entry-point provider for nemo_platform_plugin.client_provider
# ---------------------------------------------------------------------------


class PlatformNemoClientProvider:
    """Rich :class:`~nemo_platform_plugin.client_provider.NemoClientProvider`
    that uses platform internals (endpoint-aware HTTP clients, URL routing, OTEL
    headers, auth context).

    Registered as a ``nemo.client_provider`` entry-point so it is discovered
    automatically when ``nmp-common`` is installed.
    """

    def get_nemo_client(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
        workspace: str | None = None,
    ) -> NemoClient:
        return get_nemo_client(
            as_service=as_service,
            internal=internal,
            on_behalf_of=on_behalf_of,
            workspace=workspace,
        )

    def get_async_nemo_client(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
        workspace: str | None = None,
    ) -> AsyncNemoClient:
        return get_async_nemo_client(
            as_service=as_service,
            internal=internal,
            on_behalf_of=on_behalf_of,
            workspace=workspace,
        )

    def get_task_nemo_client(
        self,
        service_name: str,
        *,
        workspace: str | None = None,
    ) -> NemoClient:
        return get_task_nemo_client(service_name, workspace=workspace)

    def get_async_task_nemo_client(
        self,
        service_name: str,
        *,
        workspace: str | None = None,
    ) -> AsyncNemoClient:
        return get_async_task_nemo_client(service_name, workspace=workspace)
