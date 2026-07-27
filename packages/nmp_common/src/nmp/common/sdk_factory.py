# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK factory functions for creating NeMo Platform SDK instances."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Optional, TypeVar

import httpx
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.client.auth import TokenProviderAuth
from nemo_platform_plugin.client.constants import (
    WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR,
    is_workload_identity_token_file_set,
    require_workload_identity_without_principal_env,
    workload_identity_token_file_from_env,
)
from nmp.common.auth import Principal, get_principal_auth_headers, principal_from_env
from nmp.common.immutable_http_client import ImmutableDefaultAsyncHttpxClient, ImmutableDefaultHttpxClient
from nmp.common.observability import MARK_INTERNAL_REQUEST_HEADERS
from nmp.common.observability.otel import get_otel_headers
from nmp.common.platform_endpoint import resolve_platform_endpoint

logger = logging.getLogger(__name__)
PlatformSDKT = TypeVar("PlatformSDKT", bound=NeMoPlatform | AsyncNeMoPlatform)
_HTTPClientT = TypeVar("_HTTPClientT", httpx.Client, httpx.AsyncClient)


@dataclass(frozen=True)
class _SDKConnection(Generic[_HTTPClientT]):
    base_url: str
    http_client: _HTTPClientT


def _sync_sdk_connection(base_url: str | None, http_client: httpx.Client | None) -> _SDKConnection[httpx.Client]:
    if http_client is not None:
        return _SDKConnection(
            base_url=base_url or resolve_platform_endpoint().connect_base_url, http_client=http_client
        )
    if base_url is not None:
        return _SDKConnection(base_url=base_url, http_client=ImmutableDefaultHttpxClient())
    endpoint = resolve_platform_endpoint()
    return _SDKConnection(base_url=endpoint.connect_base_url, http_client=endpoint.sync_sdk_http_client())


def _async_sdk_connection(
    base_url: str | None,
    http_client: httpx.AsyncClient | None,
) -> _SDKConnection[httpx.AsyncClient]:
    if http_client is not None:
        return _SDKConnection(
            base_url=base_url or resolve_platform_endpoint().connect_base_url, http_client=http_client
        )
    if base_url is not None:
        return _SDKConnection(base_url=base_url, http_client=ImmutableDefaultAsyncHttpxClient())
    endpoint = resolve_platform_endpoint()
    return _SDKConnection(base_url=endpoint.connect_base_url, http_client=endpoint.async_sdk_http_client())


def with_options_reusing_http_client(base_sdk: PlatformSDKT, **kwargs: Any) -> PlatformSDKT:
    """Return ``base_sdk.with_options(...)`` while reusing its underlying HTTP client."""
    if kwargs.get("http_client") is None:
        kwargs["http_client"] = base_sdk._client
    custom_auth = base_sdk.custom_auth
    if custom_auth is not None:
        extra_kwargs = dict(kwargs.pop("_extra_kwargs", {}))
        extra_kwargs.setdefault("custom_auth", custom_auth)
        kwargs["_extra_kwargs"] = extra_kwargs
    return base_sdk.with_options(**kwargs)


class _CustomAuthNeMoPlatform(NeMoPlatform):
    def __init__(self, *, custom_auth: httpx.Auth, **kwargs: Any) -> None:
        self._custom_auth = custom_auth
        super().__init__(**kwargs)

    @property
    def custom_auth(self) -> httpx.Auth | None:
        return self._custom_auth


class _CustomAuthAsyncNeMoPlatform(AsyncNeMoPlatform):
    def __init__(self, *, custom_auth: httpx.Auth, **kwargs: Any) -> None:
        self._custom_auth = custom_auth
        super().__init__(**kwargs)

    @property
    def custom_auth(self) -> httpx.Auth | None:
        return self._custom_auth


@dataclass(frozen=True)
class _ResolvedSDKInitConfig(Generic[_HTTPClientT]):
    base_url: str
    workspace: str | None
    default_headers: Mapping[str, str] | None
    http_client: _HTTPClientT
    custom_auth: httpx.Auth | None


def _should_bootstrap_workload_identity() -> bool:
    return is_workload_identity_token_file_set()


def _workload_identity_extra_headers(*, internal: bool) -> dict[str, str]:
    return MARK_INTERNAL_REQUEST_HEADERS.copy() if internal else {}


def _non_auth_otel_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    for name, value in get_otel_headers().items():
        normalized_name = name.lower()
        if normalized_name == "x-nmp-internal" or normalized_name.startswith("x-nmp-principal-"):
            continue
        headers[name] = value
    return headers


def _workload_identity_token_file() -> Path:
    token_file = workload_identity_token_file_from_env()
    if token_file is None:
        raise RuntimeError(f"{WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR} is not set")
    return token_file


def _workload_identity_auth(base_url: str) -> httpx.Auth:
    from nemo_platform_plugin.client.oidc_factory import resolve_workload_exchange_provider

    provider = resolve_workload_exchange_provider(
        base_url=base_url,
        subject_token_file=_workload_identity_token_file(),
    )
    return TokenProviderAuth(provider)


def _ensure_no_trusted_headers_for_workload_identity(
    *,
    as_service: str | None,
    on_behalf_of: str | Principal | None,
) -> None:
    if as_service is not None or on_behalf_of is not None:
        raise ValueError(f"{WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR} cannot be combined with trusted principal headers")


def _resolve_sdk_init_config(
    *,
    connection: _SDKConnection[_HTTPClientT],
    as_service: str | None,
    internal: bool,
    on_behalf_of: str | Principal | None,
) -> _ResolvedSDKInitConfig[_HTTPClientT]:
    if not _should_bootstrap_workload_identity():
        headers = _get_default_headers(as_service, internal, on_behalf_of)
        return _ResolvedSDKInitConfig(
            base_url=connection.base_url,
            workspace=None,
            default_headers=headers if headers else None,
            http_client=connection.http_client,
            custom_auth=None,
        )

    require_workload_identity_without_principal_env()
    _ensure_no_trusted_headers_for_workload_identity(as_service=as_service, on_behalf_of=on_behalf_of)
    extra_headers = _workload_identity_extra_headers(internal=internal)
    return _ResolvedSDKInitConfig(
        base_url=connection.base_url,
        workspace=None,
        default_headers=extra_headers or None,
        http_client=connection.http_client,
        custom_auth=_workload_identity_auth(connection.base_url),
    )


def _sync_sdk_from_init_config(sdk_config: _ResolvedSDKInitConfig[httpx.Client]) -> NeMoPlatform:
    if sdk_config.custom_auth is None:
        return NeMoPlatform(
            base_url=sdk_config.base_url,
            workspace=sdk_config.workspace,
            default_headers=sdk_config.default_headers,
            http_client=sdk_config.http_client,
        )
    return _CustomAuthNeMoPlatform(
        custom_auth=sdk_config.custom_auth,
        base_url=sdk_config.base_url,
        workspace=sdk_config.workspace,
        default_headers=sdk_config.default_headers,
        http_client=sdk_config.http_client,
    )


def _async_sdk_from_init_config(sdk_config: _ResolvedSDKInitConfig[httpx.AsyncClient]) -> AsyncNeMoPlatform:
    if sdk_config.custom_auth is None:
        return AsyncNeMoPlatform(
            base_url=sdk_config.base_url,
            workspace=sdk_config.workspace,
            default_headers=sdk_config.default_headers,
            http_client=sdk_config.http_client,
        )
    return _CustomAuthAsyncNeMoPlatform(
        custom_auth=sdk_config.custom_auth,
        base_url=sdk_config.base_url,
        workspace=sdk_config.workspace,
        default_headers=sdk_config.default_headers,
        http_client=sdk_config.http_client,
    )


def _task_on_behalf_of_principal() -> Principal | None:
    principal = principal_from_env()
    return principal.effective_principal if principal is not None else None


def _warn_missing_task_principal(*, as_service: str, async_sdk: bool) -> None:
    qualifier = "async task SDK" if async_sdk else "task SDK"
    logger.warning(
        "NMP_PRINCIPAL not set; %s will authenticate as service:%s without on-behalf-of delegation",
        qualifier,
        as_service,
    )


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
    Returns a NeMoPlatform SDK configured from explicit arguments or the resolved platform endpoint.

    Args:
        as_service: If provided, use service principal headers (service:{name}).
                   Use this for internal service operations without user context
                   (e.g., startup, background tasks, controllers).
                   If None and auth is enabled, propagates the current user's auth context.
        internal: If True, mark all requests from this SDK as internal requests.
                 Use this for controllers and background tasks that make internal API calls.
        http_client: Optional sync HTTP client to use for requests.
        on_behalf_of: Optional principal ID to use for on-behalf-of authorization.
        base_url: Optional platform base URL. When omitted with no explicit http_client,
            the resolved platform endpoint supplies both the base URL and HTTP client.

    Returns:
        Configured NeMoPlatform SDK instance.
    """
    connection = _sync_sdk_connection(base_url, http_client)
    sdk_config = _resolve_sdk_init_config(
        connection=connection,
        as_service=as_service,
        internal=internal,
        on_behalf_of=on_behalf_of,
    )
    return _sync_sdk_from_init_config(sdk_config)


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
    if is_workload_identity_token_file_set():
        require_workload_identity_without_principal_env()
        return get_platform_sdk(
            internal=True,
            http_client=http_client,
        )

    on_behalf_of = _task_on_behalf_of_principal()
    if on_behalf_of is None:
        _warn_missing_task_principal(as_service=as_service, async_sdk=False)
    return get_platform_sdk(
        as_service=as_service,
        internal=True,
        http_client=http_client,
        on_behalf_of=on_behalf_of,
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
    if is_workload_identity_token_file_set():
        require_workload_identity_without_principal_env()
        return get_async_platform_sdk(
            internal=True,
            http_client=http_client,
        )

    on_behalf_of = _task_on_behalf_of_principal()
    if on_behalf_of is None:
        _warn_missing_task_principal(as_service=as_service, async_sdk=True)
    return get_async_platform_sdk(
        as_service=as_service,
        internal=True,
        http_client=http_client,
        on_behalf_of=on_behalf_of,
    )


def get_async_platform_sdk(
    as_service: str | None = None,
    internal: bool = False,
    http_client: Optional[httpx.AsyncClient] = None,
    on_behalf_of: Optional[str | Principal] = None,
    base_url: str | None = None,
) -> AsyncNeMoPlatform:
    """
    Returns an AsyncNeMoPlatform SDK configured from explicit arguments or the resolved platform endpoint.

    Args:
        as_service: If provided, use service principal headers (service:{name}).
                   Use this for internal service operations without user context
                   (e.g., startup, background tasks, controllers).
                   If None and auth is enabled, propagates the current user's auth context.
        internal: If True, mark all requests from this SDK as internal requests.
                 Use this for controllers and background tasks that make internal API calls.
        http_client: Optional async HTTP client to use for requests.
        on_behalf_of: Optional principal ID to use for on-behalf-of authorization.
        base_url: Optional platform base URL. When omitted with no explicit http_client,
            the resolved platform endpoint supplies both the base URL and HTTP client.
    Returns:
        Configured AsyncNeMoPlatform SDK instance.
    """
    connection = _async_sdk_connection(base_url, http_client)
    sdk_config = _resolve_sdk_init_config(
        connection=connection,
        as_service=as_service,
        internal=internal,
        on_behalf_of=on_behalf_of,
    )
    return _async_sdk_from_init_config(sdk_config)


def get_service_scoped_sdk(
    base_sdk: PlatformSDKT,
    service_name: str,
    *,
    internal: bool = True,
    on_behalf_of: str | Principal | None = None,
) -> PlatformSDKT:
    """Derive a service-principal SDK from an existing SDK.

    The returned SDK reuses the base SDK's HTTP client and endpoint routing.
    If the base SDK is using workload identity, keep bearer-token auth and add
    only workload-safe internal headers instead of trusted principal headers.
    """
    if base_sdk.custom_auth is not None:
        if on_behalf_of is not None:
            raise ValueError(f"{WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR} cannot be combined with trusted principal headers")
        headers = _workload_identity_extra_headers(internal=internal)
    else:
        headers = _get_default_headers(
            as_service=service_name,
            internal=internal,
            on_behalf_of=on_behalf_of,
        )
    return with_options_reusing_http_client(base_sdk, set_default_headers=headers)


def get_request_scoped_sdk(
    base_sdk: AsyncNeMoPlatform,
) -> AsyncNeMoPlatform:
    """Create a request-scoped SDK with current auth and observability headers.

    Takes a base SDK and returns a new SDK instance that reuses the same HTTP client
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

    # Combine OTEL headers (tracing) + auth headers (user identity).
    headers = _non_auth_otel_headers()
    if base_sdk.custom_auth is None:
        headers.update(get_principal_auth_headers())

    # If we have headers to add, create a new SDK with them
    # This reuses the underlying HTTP client (lightweight operation)
    if headers:
        return with_options_reusing_http_client(base_sdk, set_default_headers=headers)

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
    if base_sdk.custom_auth is not None:
        raise ValueError(f"{WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR} cannot be combined with trusted principal headers")

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
    return with_options_reusing_http_client(base_sdk, set_default_headers=merged_headers)


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
    platform internals (SDK-owned HTTP clients, OTEL headers, auth context vars).

    Registered as a ``nemo.sdk_provider`` entry-point so it is
    discovered automatically when ``nmp-common`` is installed.
    """

    def get_task_sdk(self, service_name: str) -> NeMoPlatform:
        return get_task_sdk(service_name)

    def get_async_task_sdk(self, service_name: str) -> AsyncNeMoPlatform:
        return get_async_task_sdk(service_name)

    def get_platform_sdk(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
    ) -> NeMoPlatform:
        return get_platform_sdk(
            as_service=as_service,
            internal=internal,
            on_behalf_of=on_behalf_of,
        )

    def get_async_platform_sdk(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
    ) -> AsyncNeMoPlatform:
        return get_async_platform_sdk(
            as_service=as_service,
            internal=internal,
            on_behalf_of=on_behalf_of,
        )
