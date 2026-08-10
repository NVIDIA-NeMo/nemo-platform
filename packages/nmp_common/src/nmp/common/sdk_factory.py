# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK factory functions for creating NeMo Platform SDK instances."""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar, cast

import httpx
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.client.constants import is_workload_identity_token_file_set
from nmp.common.auth import Principal, get_principal_auth_headers, principal_from_env
from nmp.common.config import Configuration, PlatformConfig
from nmp.common.http_clients import shared_async_http_client, shared_sync_http_client
from nmp.common.observability import MARK_INTERNAL_REQUEST_HEADERS
from nmp.common.observability.otel import get_otel_headers
from nmp.common.platform_endpoint import PlatformEndpoint, resolve_platform_endpoint, resolve_service_endpoint

logger = logging.getLogger(__name__)
PlatformSDKT = TypeVar("PlatformSDKT", NeMoPlatform, AsyncNeMoPlatform)

# Test-only: HTTP clients to use for SDK requests in test context.
# Set by test fixtures to route requests through the in-process test transport.
#
# TODO: Remove these module-level variables once all direct get_platform_sdk() /
# get_async_platform_sdk() callers are migrated to use DependencyProvider. See
# architecture/docs/http-client-injection.md for migration path and best practices.
_test_http_client: Optional[httpx.AsyncClient] = None


def _base_url_from_config() -> str:
    return Configuration.get_platform_config().base_url


def resolve_platform_request_url(
    url: str,
    *,
    platform_config: PlatformConfig,
    default_resolver: Callable[[str], httpx.URL],
) -> httpx.URL:
    """Resolve the destination URL for an SDK request.

    The generated SDK builds requests from relative paths like
    ``/apis/entities/v2/...`` and then calls its private ``_prepare_url`` hook.
    Keep the routing policy here, not in that private hook:

    - resolve the SDK URL normally against ``platform.base_url``;
    - if the path targets ``/apis/{api_name}/...``, replace only the origin
      with ``platform.get_service_url(api_name)``;
    - preserve the original path and query string.
    """
    request_url = default_resolver(url)
    service_pattern = platform_config.create_service_pattern()
    if service_pattern is None:
        return request_url
    match = service_pattern.search(request_url.path)
    if match is None:
        logger.debug(
            "Routing URL to original URL",
            extra={"service": "unknown", "path": request_url.path, "host": request_url.host, "port": request_url.port},
        )
        return request_url

    api_name = match.group(1)
    svc_endpoint = resolve_service_endpoint(api_name, platform_config)
    if svc_endpoint.transport == "uds":
        logger.debug(
            "Routing URL to UDS service",
            extra={
                "service": api_name,
                "path": request_url.path,
                "transport": svc_endpoint.transport,
            },
        )
        return request_url.copy_with(scheme="http", host="nemo-platform.local", port=None)
    service_url = httpx.URL(svc_endpoint.connect_base_url)
    routed_url = request_url.copy_with(
        scheme=service_url.scheme,
        host=service_url.host,
        port=service_url.port,
    )
    logger.debug(
        "Routing URL to service URL",
        extra={
            "service": api_name,
            "path": request_url.path,
            "host": routed_url.host,
            "port": routed_url.port,
        },
    )
    return routed_url


@dataclass(frozen=True)
class PlatformRequestRouter:
    """Routes SDK requests to the platform gateway or a service-specific origin."""

    platform_config: PlatformConfig
    default_resolver: Callable[[str], httpx.URL]

    def resolve(self, url: str) -> httpx.URL:
        return resolve_platform_request_url(
            url,
            platform_config=self.platform_config,
            default_resolver=self.default_resolver,
        )


def attach_platform_request_router(sdk: PlatformSDKT) -> PlatformSDKT:
    """Attach the platform request router to a generated SDK instance.

    Stainless sends every request through ``_prepare_url``. Assigning the hook is
    the SDK integration point; the routing policy itself lives in
    :class:`PlatformRequestRouter`.
    """
    router = PlatformRequestRouter(
        platform_config=Configuration.get_platform_config(),
        default_resolver=sdk._prepare_url,
    )
    setattr(sdk, "_nmp_request_router", router)
    sdk._prepare_url = router.resolve
    return sdk


def with_options_preserving_request_router(base_sdk: PlatformSDKT, **kwargs: Any) -> PlatformSDKT:
    """Return ``base_sdk.with_options(...)`` while preserving platform request routing."""
    scoped_sdk = cast(PlatformSDKT, base_sdk.with_options(**kwargs))
    router = getattr(base_sdk, "_nmp_request_router", None)
    if isinstance(router, PlatformRequestRouter):
        setattr(scoped_sdk, "_nmp_request_router", router)
        scoped_sdk._prepare_url = router.resolve
    return scoped_sdk


def _sync_http_client_for_endpoint(
    endpoint: PlatformEndpoint,
    http_client: httpx.Client | None,
) -> httpx.Client:
    if http_client is not None:
        return http_client
    if endpoint.transport == "uds":
        return endpoint.sync_http_client()
    return shared_sync_http_client()


def _async_http_client_for_endpoint(
    endpoint: PlatformEndpoint,
    http_client: httpx.AsyncClient | None,
) -> httpx.AsyncClient:
    if http_client is not None:
        return http_client
    if _test_http_client is not None:
        return _test_http_client
    if endpoint.transport == "uds":
        return endpoint.async_http_client()
    return shared_async_http_client()


def _should_bootstrap_workload_identity(
    *,
    as_service: str | None,
    on_behalf_of: str | Principal | None,
    http_client: httpx.Client | httpx.AsyncClient | None,
    endpoint: PlatformEndpoint,
) -> bool:
    return (
        as_service is None
        and on_behalf_of is None
        and http_client is None
        and endpoint.transport != "uds"
        and is_workload_identity_token_file_set()
    )


def _workload_identity_extra_headers(*, internal: bool) -> dict[str, str]:
    return MARK_INTERNAL_REQUEST_HEADERS.copy() if internal else {}


def _get_default_headers(
    as_service: str | None = None, internal: bool = False, on_behalf_of: str | Principal | None = None
) -> dict[str, str]:
    """Get default headers for SDK requests.

    Args:
        as_service: If provided, use service principal headers (service:{name}).
                   If None, use the current request's auth context.
        internal: If True, include headers to mark requests as internal
                 (used for controller/background task requests).

    Returns:
        Headers dict combining auth and internal markers as needed.
    """
    headers: dict[str, str] = {}

    # Add internal request marker if requested
    if internal:
        headers.update(MARK_INTERNAL_REQUEST_HEADERS)

    # Add auth headers
    if as_service is not None:
        # Use service principal
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
        # Propagate the current user's auth context
        auth_headers = get_principal_auth_headers()
        if auth_headers:
            headers.update(auth_headers)

        elif (principal := principal_from_env()) is not None:
            # If we don't have auth_headers set yet, try loading them from env
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
    http_client: httpx.Client | None = None,
    on_behalf_of: str | Principal | None = None,
    base_url: str | None = None,
) -> NeMoPlatform:
    """
    Returns an instance of the NeMoPlatform SDK configured with the platform's base URL.

    Args:
        as_service: If provided, use service principal headers (service:{name}).
                   Use this for internal service operations without user context
                   (e.g., startup, background tasks, controllers).
                   If None and auth is enabled, propagates the current user's auth context.
        internal: If True, mark all requests from this SDK as internal requests.
                 Use this for controllers and background tasks that make internal API calls.
        http_client: Optional sync HTTP client to use for requests.
        on_behalf_of: Optional principal ID to use for on-behalf-of authorization.
        base_url: Optional platform base URL. Defaults to configured platform base URL.

    Returns:
        Configured NeMoPlatform SDK instance.
    """
    endpoint = resolve_platform_endpoint()
    if _should_bootstrap_workload_identity(
        as_service=as_service,
        on_behalf_of=on_behalf_of,
        http_client=http_client,
        endpoint=endpoint,
    ):
        headers = _workload_identity_extra_headers(internal=internal)
        sdk = NeMoPlatform(
            base_url=base_url or endpoint.connect_base_url,
            default_headers=headers if headers else None,
        )
        return attach_platform_request_router(sdk)

    headers = _get_default_headers(as_service, internal, on_behalf_of)
    sdk = NeMoPlatform(
        base_url=base_url or endpoint.connect_base_url,
        http_client=_sync_http_client_for_endpoint(endpoint, http_client),
        default_headers=headers if headers else None,
    )
    return attach_platform_request_router(sdk)


def get_task_sdk(as_service: str, http_client: httpx.Client | None = None) -> NeMoPlatform:
    """Create an SDK for use inside a task container with on-behalf-of auth.

    Reads the job creator's principal from the NMP_PRINCIPAL environment variable
    (set by the jobs backend when launching task containers) and creates an SDK
    that authenticates as the given service while acting on behalf of the job creator.

    Args:
        as_service: Service name for the service principal (e.g., "customizer").
        http_client: Optional sync HTTP client to use for requests.

    Returns:
        Configured NeMoPlatform SDK with internal + on-behalf-of headers.
    """
    if http_client is None and is_workload_identity_token_file_set():
        return get_platform_sdk(internal=True)

    if http_client is None:
        http_client = resolve_platform_endpoint().sync_sdk_http_client()

    principal = principal_from_env()
    if principal is None:
        logger.warning(
            "NMP_PRINCIPAL not set; task SDK will authenticate as service:%s without on-behalf-of delegation",
            as_service,
        )
    return get_platform_sdk(
        as_service=as_service,
        internal=True,
        http_client=http_client,
        on_behalf_of=principal.effective_principal if principal else None,
    )


def get_async_task_sdk(as_service: str, http_client: Optional[httpx.AsyncClient] = None) -> AsyncNeMoPlatform:
    """Async counterpart of :func:`get_task_sdk` for use inside a task container.

    Reads the job creator's principal from ``NMP_PRINCIPAL`` and creates an async SDK that
    authenticates as the given service while acting on behalf of the job creator with the full
    delegated identity (on-behalf-of id, email, and groups). Wire-identical to :func:`get_task_sdk`.

    Args:
        as_service: Service name for the service principal (e.g., "evaluator").
        http_client: Optional async HTTP client to use for requests.

    Returns:
        Configured AsyncNeMoPlatform SDK with internal + on-behalf-of headers.
    """
    if http_client is None and is_workload_identity_token_file_set():
        return get_async_platform_sdk(internal=True)

    if http_client is None:
        http_client = resolve_platform_endpoint().async_sdk_http_client()

    principal = principal_from_env()
    if principal is None:
        logger.warning(
            "NMP_PRINCIPAL not set; async task SDK will authenticate as service:%s without on-behalf-of delegation",
            as_service,
        )
    return get_async_platform_sdk(
        as_service=as_service,
        internal=True,
        http_client=http_client,
        on_behalf_of=principal.effective_principal if principal else None,
    )


def get_async_platform_sdk(
    as_service: str | None = None,
    internal: bool = False,
    http_client: Optional[httpx.AsyncClient] = None,
    on_behalf_of: Optional[str | Principal] = None,
    base_url: str | None = None,
) -> AsyncNeMoPlatform:
    """
    Returns an instance of the AsyncNeMoPlatform SDK configured with the platform's base URL.

    Args:
        as_service: If provided, use service principal headers (service:{name}).
                   Use this for internal service operations without user context
                   (e.g., startup, background tasks, controllers).
                   If None and auth is enabled, propagates the current user's auth context.
        internal: If True, mark all requests from this SDK as internal requests.
                 Use this for controllers and background tasks that make internal API calls.
        http_client: Optional HTTP client to use for requests. Used for test injection
                    via DependencyProvider. See architecture/docs/http-client-injection.md.
        on_behalf_of: Optional principal ID to use for on-behalf-of authorization.
        base_url: Optional platform base URL. Defaults to configured platform base URL.
    Returns:
        Configured AsyncNeMoPlatform SDK instance.
    """
    endpoint = resolve_platform_endpoint()
    if _should_bootstrap_workload_identity(
        as_service=as_service,
        on_behalf_of=on_behalf_of,
        http_client=http_client,
        endpoint=endpoint,
    ):
        headers = _workload_identity_extra_headers(internal=internal)
        if _test_http_client is None:
            sdk = AsyncNeMoPlatform(
                base_url=base_url or endpoint.connect_base_url,
                default_headers=headers if headers else None,
            )
        else:
            sdk = AsyncNeMoPlatform(
                base_url=base_url or endpoint.connect_base_url,
                http_client=_async_http_client_for_endpoint(endpoint, http_client),
                default_headers=headers if headers else None,
            )
        return attach_platform_request_router(sdk)

    headers = _get_default_headers(as_service, internal, on_behalf_of)

    # Use explicitly provided http_client (from DependencyProvider) or fall back to
    # module-level _test_http_client for backward compatibility with direct callers.
    effective_client = _async_http_client_for_endpoint(endpoint, http_client)

    sdk = AsyncNeMoPlatform(
        base_url=base_url or endpoint.connect_base_url,
        http_client=effective_client,
        default_headers=headers if headers else None,
    )
    return attach_platform_request_router(sdk)


def get_request_scoped_sdk(
    base_sdk: AsyncNeMoPlatform,
) -> AsyncNeMoPlatform:
    """Create a request-scoped SDK with current auth and observability headers.

    Takes a base SDK (with shared HTTP client) and returns a new SDK instance
    with the current request's auth headers applied via .with_options().

    This is lightweight - the underlying HTTP client is reused.

    Args:
        base_sdk: The base SDK instance (typically cached by DependencyProvider)

    Returns:
        SDK instance with auth + OTEL headers, or base_sdk if no headers to add.

    Usage:
        This is called by DependencyProvider to create per-request SDK instances
        for FastAPI dependency injection.
    """

    # Combine OTEL headers (tracing) + auth headers (user identity)
    headers = get_otel_headers().copy()
    headers.update(get_principal_auth_headers())

    # If we have headers to add, create a new SDK with them
    # This reuses the underlying HTTP client (lightweight operation)
    if headers:
        return with_options_preserving_request_router(base_sdk, set_default_headers=headers)

    return base_sdk


def get_sdk_on_behalf_of(
    base_sdk: NeMoPlatform | AsyncNeMoPlatform,
    on_behalf_of: str | Principal,
) -> NeMoPlatform | AsyncNeMoPlatform:
    """Create an SDK with on-behalf-of headers for delegated access.

    Takes an existing SDK (typically created as a service principal) and returns
    a new SDK instance with X-NMP-Principal-On-Behalf-Of header added. This enables
    service principals to act on behalf of users while checking the delegated user's
    permissions.

    This is lightweight - the underlying HTTP client is reused, and all original
    headers are preserved.

    Args:
        base_sdk: The base SDK instance (typically created with as_service)
        on_behalf_of: The principal ID to act on behalf of (e.g., user email)

    Returns:
        SDK instance with on-behalf-of header added and all original headers preserved.

    Usage:
        ```python
        # Create a service SDK
        service_sdk = get_platform_sdk(as_service="my-service")

        # Create delegated SDK for accessing resources on behalf of a user
        delegated_sdk = get_sdk_on_behalf_of(service_sdk, "user@example.com")

        # Create delegated SDK for accessing resources on behalf of a principal
        delegated_sdk = get_sdk_on_behalf_of(service_sdk, Principal(id="user@example.com", groups=["group1", "group2"], email="user@example.com"))

        # Secret access will check user@example.com's permissions
        secret = delegated_sdk.secrets.access("my-secret", workspace="workspace-name")
        ```
    """
    # Merge existing headers with the new on-behalf-of header
    headers = base_sdk.default_headers or {}
    if isinstance(on_behalf_of, Principal):
        merged_headers = {
            **headers,
            "X-NMP-Principal-On-Behalf-Of": on_behalf_of.effective_principal.id,
        }
        if on_behalf_of.effective_principal.email:
            merged_headers["X-NMP-Principal-On-Behalf-Of-Email"] = on_behalf_of.effective_principal.email
        if on_behalf_of.effective_principal.groups:
            merged_headers["X-NMP-Principal-On-Behalf-Of-Groups"] = ",".join(on_behalf_of.effective_principal.groups)
    else:
        merged_headers = {**headers, "X-NMP-Principal-On-Behalf-Of": on_behalf_of}
        merged_headers.pop("X-NMP-Principal-On-Behalf-Of-Groups", None)
        merged_headers.pop("X-NMP-Principal-On-Behalf-Of-Email", None)
    return with_options_preserving_request_router(base_sdk, set_default_headers=merged_headers)


def get_entity_parts(name: str, default_workspace: str | None = None) -> tuple[str, str]:
    """Get the workspace and name parts of an entity reference."""
    if "/" in name:
        parts = name.split("/", 1)
        return parts[0], parts[1]
    if default_workspace is None:
        raise ValueError(
            f"Entity reference '{name}' is not qualified with a workspace, and no workspace to default to was provided. Must be in the format $workspace/$entity_name or a default workspace must be provided to fall back to."
        )
    return default_workspace, name


# ---------------------------------------------------------------------------
# Entry-point provider for nemo_platform_plugin.sdk_provider
# ---------------------------------------------------------------------------


class PlatformSDKProvider:
    """Rich :class:`~nemo_platform_plugin.sdk_provider.SDKProvider` that uses
    platform internals (shared HTTP clients, URL routing, OTEL headers, auth
    context vars).

    Registered as a ``nemo.sdk_provider`` entry-point so it is
    discovered automatically when ``nmp-common`` is installed.
    """

    def get_task_sdk(self, service_name: str, http_client: httpx.Client | None = None) -> NeMoPlatform:
        return get_task_sdk(service_name, http_client=http_client)

    def get_async_task_sdk(self, service_name: str, http_client: httpx.AsyncClient | None = None) -> AsyncNeMoPlatform:
        return get_async_task_sdk(service_name, http_client=http_client)

    def get_platform_sdk(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        http_client: httpx.Client | None = None,
        on_behalf_of: str | Principal | None = None,
        base_url: str | None = None,
    ) -> NeMoPlatform:
        return get_platform_sdk(
            as_service=as_service,
            internal=internal,
            http_client=http_client,
            on_behalf_of=on_behalf_of,
            base_url=base_url,
        )

    def get_async_platform_sdk(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | Principal | None = None,
        base_url: str | None = None,
    ) -> AsyncNeMoPlatform:
        return get_async_platform_sdk(
            as_service=as_service,
            internal=internal,
            on_behalf_of=on_behalf_of,
            base_url=base_url,
        )
