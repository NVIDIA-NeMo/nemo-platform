# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK factory functions for creating NeMo Platform SDK instances.

Plugin-safe canonical home. Service-side ``nmp.common.sdk_factory`` is a
re-export shim — both import paths point at the same functions.

The plugin variant uses ``NemoPlatformConfig`` (the base config exposed by
nemo-platform-plugin) instead of the service-extended ``PlatformConfig``.
That means co-hosted-service URL routing falls back to the configured base
URL, which is correct for plugin code running outside the platform process
(jobs, tasks, controllers, deployed agents).
"""

import logging
from typing import Callable, Optional

import httpx
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.auth import (
    Principal,
    get_principal_auth_headers,
    principal_from_env,
)
from nemo_platform_plugin.config import Configuration, NemoPlatformConfig
from nemo_platform_plugin.http_clients import (
    shared_async_http_client,
    shared_sync_http_client,
)
from nemo_platform_plugin.otel_headers import (
    MARK_INTERNAL_REQUEST_HEADERS,
    get_otel_headers,
)

logger = logging.getLogger(__name__)

# Test-only: HTTP client to use for SDK requests in test context.
# Set by test fixtures to route requests through the test transport.
_test_http_client: Optional[httpx.AsyncClient] = None


def _platform_config() -> NemoPlatformConfig:
    return Configuration.get_service_config(NemoPlatformConfig)


def _base_url_from_config() -> str:
    return _platform_config().base_url


def _create_url_router(
    original: Callable[[str], httpx.URL],
) -> Callable[[str], httpx.URL]:
    """Create a URL routing function that routes requests based on API name."""
    platform_config = _platform_config()
    service_pattern = platform_config.create_service_pattern()

    def route_url(url: str) -> httpx.URL:
        if service_pattern:
            match = service_pattern.search(url)
            if match:
                api_name = match.group(1)
                svc_url = httpx.URL(platform_config.get_service_url(api_name))
                request_url = httpx.URL(url)
                logger.debug(
                    "Routing URL to matched service URL",
                    extra={"service": api_name, "url": url, "host": svc_url.host, "port": svc_url.port},
                )
                return request_url.copy_with(
                    scheme=svc_url.scheme,
                    host=svc_url.host,
                    port=svc_url.port,
                )
        request_url = original(url)
        logger.debug(
            "Routing URL to original URL",
            extra={"service": "unknown", "url": url, "host": request_url.host, "port": request_url.port},
        )
        return request_url

    return route_url


def _get_default_headers(
    as_service: str | None = None, internal: bool = False, on_behalf_of: str | Principal | None = None
) -> dict[str, str]:
    """Get default headers for SDK requests."""
    headers: dict[str, str] = {}

    if internal:
        headers.update(MARK_INTERNAL_REQUEST_HEADERS)

    if as_service is not None:
        headers["X-NMP-Principal-Id"] = f"service:{as_service}"

        if on_behalf_of is not None:
            if isinstance(on_behalf_of, Principal):
                effective_principal = on_behalf_of.effective_principal
                headers["X-NMP-Principal-On-Behalf-Of"] = effective_principal.id
                if effective_principal.groups:
                    headers["X-NMP-Principal-On-Behalf-Of-Groups"] = ",".join(effective_principal.groups)
                if effective_principal.email:
                    headers["X-NMP-Principal-On-Behalf-Of-Email"] = effective_principal.email
            else:
                headers["X-NMP-Principal-On-Behalf-Of"] = on_behalf_of
    else:
        auth_headers = get_principal_auth_headers()
        if auth_headers:
            headers.update(auth_headers)
        elif (principal := principal_from_env()) is not None:
            headers.update(principal.get_headers())

        if on_behalf_of is not None:
            headers.pop("X-NMP-Principal-On-Behalf-Of-Groups", None)
            headers.pop("X-NMP-Principal-On-Behalf-Of-Email", None)
            if isinstance(on_behalf_of, Principal):
                effective_principal = on_behalf_of.effective_principal
                headers["X-NMP-Principal-On-Behalf-Of"] = effective_principal.id
                if effective_principal.groups:
                    headers["X-NMP-Principal-On-Behalf-Of-Groups"] = ",".join(effective_principal.groups)
                if effective_principal.email:
                    headers["X-NMP-Principal-On-Behalf-Of-Email"] = effective_principal.email
            else:
                headers["X-NMP-Principal-On-Behalf-Of"] = on_behalf_of

    return headers


def get_platform_sdk(
    as_service: str | None = None,
    internal: bool = False,
    on_behalf_of: str | Principal | None = None,
) -> NeMoPlatform:
    """Returns a sync NeMoPlatform SDK configured with the platform's base URL."""
    headers = _get_default_headers(as_service, internal, on_behalf_of)
    sdk = NeMoPlatform(
        base_url=_base_url_from_config(),
        http_client=shared_sync_http_client(),
        default_headers=headers if headers else None,
    )
    # SDK exposes `_prepare_url` as a bound method we wrap with the service router.
    sdk._prepare_url = _create_url_router(sdk._prepare_url)  # type: ignore[method-assign,assignment]
    return sdk


def get_task_sdk(as_service: str) -> NeMoPlatform:
    """Create an SDK for use inside a task container with on-behalf-of auth."""
    principal = principal_from_env()
    if principal is None:
        logger.warning(
            "NMP_PRINCIPAL not set; task SDK will authenticate as service:%s without on-behalf-of delegation",
            as_service,
        )
    return get_platform_sdk(
        as_service=as_service,
        internal=True,
        on_behalf_of=principal.effective_principal if principal else None,
    )


def get_async_platform_sdk(
    as_service: str | None = None,
    internal: bool = False,
    http_client: Optional[httpx.AsyncClient] = None,
    on_behalf_of: Optional[str | Principal] = None,
) -> AsyncNeMoPlatform:
    """Returns an async AsyncNeMoPlatform SDK configured with the platform's base URL."""
    headers = _get_default_headers(as_service, internal, on_behalf_of)
    effective_client = http_client or _test_http_client or shared_async_http_client()

    sdk = AsyncNeMoPlatform(
        base_url=_base_url_from_config(),
        http_client=effective_client,
        default_headers=headers if headers else None,
    )
    # SDK exposes `_prepare_url` as a bound method we wrap with the service router.
    sdk._prepare_url = _create_url_router(sdk._prepare_url)  # type: ignore[method-assign,assignment]
    return sdk


def get_request_scoped_sdk(
    base_sdk: AsyncNeMoPlatform,
) -> AsyncNeMoPlatform:
    """Create a request-scoped SDK with current auth + observability headers."""
    headers = get_otel_headers().copy()
    headers.update(get_principal_auth_headers())
    if headers:
        return base_sdk.with_options(set_default_headers=headers)
    return base_sdk


def get_sdk_on_behalf_of(
    base_sdk: NeMoPlatform | AsyncNeMoPlatform,
    on_behalf_of: str | Principal,
) -> NeMoPlatform | AsyncNeMoPlatform:
    """Create an SDK with on-behalf-of headers for delegated access."""
    base_headers: dict[str, str] = dict(base_sdk.default_headers or {})  # type: ignore[arg-type]
    if isinstance(on_behalf_of, Principal):
        merged_headers: dict[str, str] = {
            **base_headers,
            "X-NMP-Principal-On-Behalf-Of": on_behalf_of.effective_principal.id,
        }
        if on_behalf_of.effective_principal.email:
            merged_headers["X-NMP-Principal-On-Behalf-Of-Email"] = on_behalf_of.effective_principal.email
        if on_behalf_of.effective_principal.groups:
            merged_headers["X-NMP-Principal-On-Behalf-Of-Groups"] = ",".join(on_behalf_of.effective_principal.groups)
    else:
        merged_headers = {**base_headers, "X-NMP-Principal-On-Behalf-Of": on_behalf_of}
        merged_headers.pop("X-NMP-Principal-On-Behalf-Of-Groups", None)
        merged_headers.pop("X-NMP-Principal-On-Behalf-Of-Email", None)
    return base_sdk.with_options(set_default_headers=merged_headers)


def get_entity_parts(name: str, default_workspace: str | None = None) -> tuple[str, str]:
    """Get the workspace and name parts of an entity reference."""
    if "/" in name:
        parts = name.split("/", 1)
        return parts[0], parts[1]
    if default_workspace is None:
        raise ValueError(
            f"Entity reference '{name}' is not qualified with a workspace, and no workspace to default to was provided. "
            "Must be in the format $workspace/$entity_name or a default workspace must be provided to fall back to."
        )
    return default_workspace, name
