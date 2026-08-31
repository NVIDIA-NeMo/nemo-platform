# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Client overrides for config bootstrap and dynamic plugin SDK mounting."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Self

import httpx
from httpx import Timeout
from nemo_platform import (
    DEFAULT_MAX_RETRIES,
    AsyncStream,
    DefaultAsyncHttpxClient,
    DefaultHttpxClient,
    NotGiven,
    __version__,
    not_given,
)
from nemo_platform._base_client import AsyncAPIClient, SyncAPIClient
from nemo_platform_plugin.client.auth import AsyncTokenProvider, TokenProvider, TokenProviderAuth
from nemo_platform_plugin.client.constants import WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR
from nemo_platform_plugin.client.platform_options import AsyncPlatformClientOptions, SyncPlatformClientOptions
from nemo_platform_plugin.client.tls import httpx_tls_config_from_env
from nemo_platform_plugin.client.types import RetryPolicy


def _should_bootstrap_config(
    *,
    http_client: object | None,
    base_url: str | httpx.URL | None,
    config_path: Path | None,
    context_name: str | None,
    access_token: str | None,
) -> bool:
    """Return whether constructor arguments require config/auth bootstrap."""
    if http_client is not None:
        return False

    # Backward compatibility: an explicit base_url means direct mode (no config
    # bootstrap), unless config-specific overrides or workload identity are set.
    return (
        base_url is None
        or config_path is not None
        or context_name is not None
        or access_token is not None
        or bool(os.environ.get(WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR))
    )


def _copy_requires_bootstrap(
    *,
    config_path: Path | None,
    context_name: str | None,
    access_token: str | None,
) -> bool:
    return config_path is not None or context_name is not None or access_token is not None


def _typed_client_default_headers(
    custom_headers: Mapping[str, object],
    transport_headers: Mapping[str, str],
) -> Mapping[str, str] | None:
    headers = {str(key): value for key, value in custom_headers.items() if isinstance(value, str)}
    if headers:
        return headers

    default_transport_headers = {"accept", "accept-encoding", "connection", "user-agent", "host"}
    headers = {
        str(key): value
        for key, value in transport_headers.items()
        if str(key).lower() not in default_transport_headers and isinstance(value, str)
    }
    return headers or None


def _typed_client_retry(max_retries: int) -> RetryPolicy:
    return RetryPolicy(
        max_retries=max_retries,
        retryable_status_codes=(408, 409, 429),
        retry_all_server_errors=True,
        respect_retry_decision_headers=True,
        respect_retry_after_headers=True,
    )


def _typed_client_timeout(timeout: float | Timeout | None) -> float | Timeout | None:
    if timeout is None:
        return httpx.Timeout(None)
    return timeout


class NeMoPlatform(SyncAPIClient):
    def __init__(
        self,
        *,
        workspace: str | None = None,
        base_url: str | httpx.URL | None = None,
        inference_base_url: str | httpx.URL | None = None,
        config_path: Path | None = None,
        context_name: str | None = None,
        access_token: str | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Mapping[str, str] | None = None,
        default_query: Mapping[str, object] | None = None,
        token_provider: TokenProvider | None = None,
        # Configure a custom httpx client.
        # We provide a `DefaultHttpxClient` class that you can pass to retain the default values we use for `limits`, `timeout` & `follow_redirects`.
        # See the [httpx documentation](https://www.python-httpx.org/api/#client) for more details.
        http_client: httpx.Client | None = None,
        # Enable or disable schema validation for data returned by the API.
        # When enabled an error APIResponseValidationError is raised
        # if the API responds with invalid data for the expected schema.
        #
        # This parameter may be removed or changed in the future.
        # If you rely on this feature, please open a GitHub issue
        # outlining your use-case to help us decide if it should be
        # part of our public interface in the future.
        _strict_response_validation: bool = False,
    ) -> None:
        """Construct a new synchronous NeMoPlatform client instance.

        Calling with no arguments reads configuration from the active context in
        ``~/.config/nmp/config.yaml`` and wires up transparent OIDC token refresh.

        Passing only ``base_url`` activates *direct mode* — no config file is read
        and no auth headers are injected. To combine a custom ``base_url`` with
        config-based auth, also pass ``context_name`` or ``access_token``.

        Example — zero-config (reads from ``nemo auth login`` credentials):

        .. code-block:: python

            from nemo_platform import NeMoPlatform
            client = NeMoPlatform()

        Example — explicit token for automation:

        .. code-block:: python

            import os
            from nemo_platform import NeMoPlatform
            client = NeMoPlatform(
                base_url=os.environ["NMP_BASE_URL"],
                access_token=os.environ["NMP_ACCESS_TOKEN"],
                workspace="default",
            )

        Args:
            workspace: Workspace name used as a path parameter in all resource
                routes (``/workspaces/{workspace}/...``). Can also be supplied
                per-method. Raises ``ValueError`` at call time if absent from both.
            base_url: Base URL of the NeMo Platform API. If omitted, read from
                the active context in the nmp config file. Passing this parameter
                without ``context_name`` or ``access_token`` activates direct mode
                (no config file is read, no auth headers are injected).
            config_path: Path to the nmp config file. Defaults to
                ``~/.config/nmp/config.yaml``. Override in containers or CI where
                the default path is not available or writable.
            context_name: Name of the context to activate from the config file.
                Use this to switch between clusters. Also forces the auth bootstrap
                when ``base_url`` is explicitly set.
            access_token: Explicit Bearer token. Bypasses config-file auth and is
                suitable for CI/CD pipelines that obtain tokens externally.
                Automatic token refresh is not performed when this parameter is used.
            timeout: HTTP request timeout applied to all API calls. Accepts a float
                (seconds), an ``httpx.Timeout`` object, or ``None`` (no timeout).
                Individual methods can override this with their own ``timeout``
                argument.
            max_retries: Maximum number of automatic retries on transient failures.
                Defaults to ``2``. Set to ``0`` to disable retries.
            default_headers: Additional HTTP headers sent with every request.
            default_query: Additional query parameters appended to every request URL.
            http_client: Custom ``httpx.Client`` instance. When provided, the auth
                bootstrap is skipped entirely regardless of other parameters.
        """
        env_base_url = os.environ.get("NEMO_PLATFORM_BASE_URL")
        bootstrap_base_url = base_url if base_url is not None else env_base_url

        should_bootstrap = _should_bootstrap_config(
            http_client=http_client,
            base_url=base_url,
            config_path=config_path,
            context_name=context_name,
            access_token=access_token,
        )
        if should_bootstrap:
            try:
                from nemo_platform_ext.client.factory import build_client_init_kwargs

                client_init_kwargs = build_client_init_kwargs(
                    config_path=config_path,
                    base_url=bootstrap_base_url,
                    context_name=context_name,
                    access_token=access_token,
                    extra_headers=default_headers,
                )
                base_url = client_init_kwargs.base_url
                if workspace is None:
                    workspace = client_init_kwargs.workspace
                default_headers = client_init_kwargs.default_headers
                token_provider = client_init_kwargs.token_provider
                if client_init_kwargs.http_client is not None and not isinstance(
                    client_init_kwargs.http_client, httpx.Client
                ):
                    raise TypeError("Expected httpx.Client from sync client factory")
                http_client = client_init_kwargs.http_client
            except Exception as e:
                raise RuntimeError(f"NeMoPlatform client initialization failed: {e}") from e

        if base_url is None:
            base_url = bootstrap_base_url

        if base_url is None:
            raise RuntimeError("NeMoPlatform client initialization failed: base_url is required")

        tls_config = httpx_tls_config_from_env()
        if http_client is None and tls_config:
            http_client = DefaultHttpxClient(**tls_config)

        self.workspace = workspace
        self._token_provider = token_provider
        self._token_provider_auth = TokenProviderAuth(token_provider) if token_provider is not None else None

        super().__init__(
            version=__version__,
            base_url=base_url,
            max_retries=max_retries,
            timeout=timeout,
            http_client=http_client,
            custom_headers=default_headers,
            custom_query=default_query,
            _strict_response_validation=_strict_response_validation,
        )

        # TODO: needs to be removed
        self.inference_base_url = self._enforce_trailing_slash(httpx.URL(inference_base_url or base_url))

    @property
    def custom_auth(self) -> TokenProviderAuth | None:
        return self._token_provider_auth

    @property
    def http_client(self) -> httpx.Client:
        return self._client

    @property
    def token_provider(self) -> TokenProvider | None:
        return self._token_provider

    def typed_client_options(self) -> SyncPlatformClientOptions:
        return SyncPlatformClientOptions(
            base_url=str(self.base_url).rstrip("/"),
            workspace=self.workspace,
            default_headers=_typed_client_default_headers(self._custom_headers, self._client.headers),
            timeout=_typed_client_timeout(self.timeout),
            retry=_typed_client_retry(self.max_retries),
            http_client=self._client,
            url_resolver=self._prepare_url,
            auth=self._token_provider,
        )

    def __getattr__(self, name: str) -> Any:
        from nemo_platform_plugin.discovery import discover_sdk

        plugins = discover_sdk()
        if name not in plugins:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute {name!r}")

        resource_cls = getattr(plugins[name], "sync_resource", None)
        if resource_cls is None:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute {name!r}")

        instance = resource_cls(self)
        self.__dict__[name] = instance
        return instance

    def copy(
        self,
        *,
        workspace: str | None = None,
        base_url: str | httpx.URL | None = None,
        inference_base_url: str | httpx.URL | None = None,
        config_path: Path | None = None,
        context_name: str | None = None,
        access_token: str | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
        http_client: httpx.Client | None = None,
        max_retries: int | NotGiven = not_given,
        default_headers: Mapping[str, str] | None = None,
        set_default_headers: Mapping[str, str] | None = None,
        default_query: Mapping[str, object] | None = None,
        set_default_query: Mapping[str, object] | None = None,
        _extra_kwargs: Mapping[str, Any] = {},
    ) -> Self:
        """
        Create a new client instance re-using the same options given to the current client with optional overriding.
        """
        if default_headers is not None and set_default_headers is not None:
            raise ValueError("The `default_headers` and `set_default_headers` arguments are mutually exclusive")

        if default_query is not None and set_default_query is not None:
            raise ValueError("The `default_query` and `set_default_query` arguments are mutually exclusive")

        headers = self._custom_headers
        if default_headers is not None:
            headers = {**headers, **default_headers}
        elif set_default_headers is not None:
            headers = set_default_headers

        params = self._custom_query
        if default_query is not None:
            params = {**params, **default_query}
        elif set_default_query is not None:
            params = set_default_query

        requires_bootstrap = _copy_requires_bootstrap(
            config_path=config_path,
            context_name=context_name,
            access_token=access_token,
        )
        if http_client is None and not requires_bootstrap:
            http_client = self._client
        extra_kwargs = dict(_extra_kwargs)
        if not requires_bootstrap:
            extra_kwargs.setdefault("token_provider", self._token_provider)
        return self.__class__(
            workspace=workspace or self.workspace,
            base_url=base_url or self.base_url,
            inference_base_url=inference_base_url or self.inference_base_url,
            config_path=config_path,
            context_name=context_name,
            access_token=access_token,
            timeout=self.timeout if isinstance(timeout, NotGiven) else timeout,
            http_client=http_client,
            max_retries=self.max_retries if isinstance(max_retries, NotGiven) else max_retries,
            default_headers=headers,
            default_query=params,
            **extra_kwargs,
        )


class AsyncNeMoPlatform(AsyncAPIClient):
    # client options
    workspace: str | None

    def __init__(
        self,
        *,
        workspace: str | None = None,
        base_url: str | httpx.URL | None = None,
        inference_base_url: str | httpx.URL | None = None,
        config_path: Path | None = None,
        context_name: str | None = None,
        access_token: str | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Mapping[str, str] | None = None,
        default_query: Mapping[str, object] | None = None,
        token_provider: TokenProvider | AsyncTokenProvider | None = None,
        # Configure a custom httpx client.
        # We provide a `DefaultAsyncHttpxClient` class that you can pass to retain the default values we use for `limits`, `timeout` & `follow_redirects`.
        # See the [httpx documentation](https://www.python-httpx.org/api/#asyncclient) for more details.
        http_client: httpx.AsyncClient | None = None,
        # Enable or disable schema validation for data returned by the API.
        # When enabled an error APIResponseValidationError is raised
        # if the API responds with invalid data for the expected schema.
        #
        # This parameter may be removed or changed in the future.
        # If you rely on this feature, please open a GitHub issue
        # outlining your use-case to help us decide if it should be
        # part of our public interface in the future.
        _strict_response_validation: bool = False,
    ) -> None:
        """Construct a new asynchronous AsyncNeMoPlatform client instance.

        Calling with no arguments reads configuration from the active context in
        ``~/.config/nmp/config.yaml`` and wires up transparent OIDC token refresh.

        Passing only ``base_url`` activates *direct mode* — no config file is read
        and no auth headers are injected. To combine a custom ``base_url`` with
        config-based auth, also pass ``context_name`` or ``access_token``.

        Example — zero-config (reads from ``nemo auth login`` credentials):

        .. code-block:: python

            import asyncio
            from nemo_platform import AsyncNeMoPlatform
            from nemo_platform_plugin.client.adapter import client_from_platform
            from nemo_platform_plugin.workspaces.client import AsyncWorkspacesClient

            async def main() -> None:
                client = AsyncNeMoPlatform()
                workspaces = await client_from_platform(client, AsyncWorkspacesClient).list_workspaces()
                async for ws in workspaces.items():
                    print(ws.name)

            asyncio.run(main())

        Example — explicit token (CI/CD):

        .. code-block:: python

            import asyncio, os
            from nemo_platform import AsyncNeMoPlatform
            from nemo_platform_plugin.client.adapter import client_from_platform
            from nemo_platform_plugin.workspaces.client import AsyncWorkspacesClient

            async def main() -> None:
                client = AsyncNeMoPlatform(
                    base_url=os.environ["NMP_BASE_URL"],
                    access_token=os.environ["NMP_ACCESS_TOKEN"],
                    workspace="default",
                )
                workspaces = await client_from_platform(client, AsyncWorkspacesClient).list_workspaces()
                async for ws in workspaces.items():
                    print(ws.name)

            asyncio.run(main())

        Args:
            workspace: Workspace name used as a path parameter in all resource
                routes (``/workspaces/{workspace}/...``). Can also be supplied
                per-method. Raises ``ValueError`` at call time if absent from both.
            base_url: Base URL of the NeMo Platform API. If omitted, read from
                the active context in the nmp config file. Passing this parameter
                without ``context_name`` or ``access_token`` activates direct mode
                (no config file is read, no auth headers are injected).
            config_path: Path to the nmp config file. Defaults to
                ``~/.config/nmp/config.yaml``. Override in containers or CI where
                the default path is not available or writable.
            context_name: Name of the context to activate from the config file.
                Use this to switch between clusters. Also forces the auth bootstrap
                when ``base_url`` is explicitly set.
            access_token: Explicit Bearer token. Bypasses config-file auth and is
                suitable for CI/CD pipelines that obtain tokens externally.
                Automatic token refresh is not performed when this parameter is used.
            timeout: HTTP request timeout applied to all API calls. Accepts a float
                (seconds), an ``httpx.Timeout`` object, or ``None`` (no timeout).
                Individual methods can override this with their own ``timeout``
                argument.
            max_retries: Maximum number of automatic retries on transient failures.
                Defaults to ``2``. Set to ``0`` to disable retries.
            default_headers: Additional HTTP headers sent with every request.
            default_query: Additional query parameters appended to every request URL.
            http_client: Custom ``httpx.AsyncClient`` instance. When provided, the
                auth bootstrap is skipped entirely regardless of other parameters.
        """
        env_base_url = os.environ.get("NEMO_PLATFORM_BASE_URL")
        bootstrap_base_url = base_url if base_url is not None else env_base_url

        should_bootstrap = _should_bootstrap_config(
            http_client=http_client,
            base_url=base_url,
            config_path=config_path,
            context_name=context_name,
            access_token=access_token,
        )
        if should_bootstrap:
            try:
                from nemo_platform_ext.client.factory import build_async_client_init_kwargs

                client_init_kwargs = build_async_client_init_kwargs(
                    config_path=config_path,
                    base_url=bootstrap_base_url,
                    context_name=context_name,
                    access_token=access_token,
                    extra_headers=default_headers,
                )
                base_url = client_init_kwargs.base_url
                if workspace is None:
                    workspace = client_init_kwargs.workspace
                default_headers = client_init_kwargs.default_headers
                token_provider = client_init_kwargs.token_provider
                if client_init_kwargs.http_client is not None and not isinstance(
                    client_init_kwargs.http_client, httpx.AsyncClient
                ):
                    raise TypeError("Expected httpx.AsyncClient from async client factory")
                http_client = client_init_kwargs.http_client
            except Exception as e:
                raise RuntimeError(f"NeMoPlatform client initialization failed: {e}") from e

        if base_url is None:
            base_url = bootstrap_base_url

        if base_url is None:
            raise RuntimeError("NeMoPlatform client initialization failed: base_url is required")

        tls_config = httpx_tls_config_from_env()
        if http_client is None and tls_config:
            http_client = DefaultAsyncHttpxClient(**tls_config)

        self.workspace = workspace
        self._token_provider = token_provider
        self._token_provider_auth = TokenProviderAuth(token_provider) if token_provider is not None else None

        super().__init__(
            version=__version__,
            base_url=base_url,
            max_retries=max_retries,
            timeout=timeout,
            http_client=http_client,
            custom_headers=default_headers,
            custom_query=default_query,
            _strict_response_validation=_strict_response_validation,
        )

        self._default_stream_cls = AsyncStream

        # If no inference_base_url is provided, use base_url
        # TODO: needs to be removed
        self.inference_base_url = self._enforce_trailing_slash(httpx.URL(inference_base_url or base_url))

    @property
    def custom_auth(self) -> TokenProviderAuth | None:
        return self._token_provider_auth

    @property
    def http_client(self) -> httpx.AsyncClient:
        return self._client

    @property
    def token_provider(self) -> TokenProvider | AsyncTokenProvider | None:
        return self._token_provider

    def typed_client_options(self) -> AsyncPlatformClientOptions:
        return AsyncPlatformClientOptions(
            base_url=str(self.base_url).rstrip("/"),
            workspace=self.workspace,
            default_headers=_typed_client_default_headers(self._custom_headers, self._client.headers),
            timeout=_typed_client_timeout(self.timeout),
            retry=_typed_client_retry(self.max_retries),
            http_client=self._client,
            url_resolver=self._prepare_url,
            auth=self._token_provider,
        )

    def __getattr__(self, name: str) -> Any:
        from nemo_platform_plugin.discovery import discover_sdk

        plugins = discover_sdk()
        if name not in plugins:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute {name!r}")

        resource_cls = getattr(plugins[name], "async_resource", None)
        if resource_cls is None:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute {name!r}")

        instance = resource_cls(self)
        self.__dict__[name] = instance
        return instance

    def copy(
        self,
        *,
        workspace: str | None = None,
        base_url: str | httpx.URL | None = None,
        inference_base_url: str | httpx.URL | None = None,
        config_path: Path | None = None,
        context_name: str | None = None,
        access_token: str | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
        http_client: httpx.AsyncClient | None = None,
        max_retries: int | NotGiven = not_given,
        default_headers: Mapping[str, str] | None = None,
        set_default_headers: Mapping[str, str] | None = None,
        default_query: Mapping[str, object] | None = None,
        set_default_query: Mapping[str, object] | None = None,
        _extra_kwargs: Mapping[str, Any] = {},
    ) -> Self:
        """
        Create a new client instance re-using the same options given to the current client with optional overriding.
        """
        if default_headers is not None and set_default_headers is not None:
            raise ValueError("The `default_headers` and `set_default_headers` arguments are mutually exclusive")

        if default_query is not None and set_default_query is not None:
            raise ValueError("The `default_query` and `set_default_query` arguments are mutually exclusive")

        headers = self._custom_headers
        if default_headers is not None:
            headers = {**headers, **default_headers}
        elif set_default_headers is not None:
            headers = set_default_headers

        params = self._custom_query
        if default_query is not None:
            params = {**params, **default_query}
        elif set_default_query is not None:
            params = set_default_query

        requires_bootstrap = _copy_requires_bootstrap(
            config_path=config_path,
            context_name=context_name,
            access_token=access_token,
        )
        if http_client is None and not requires_bootstrap:
            http_client = self._client
        extra_kwargs = dict(_extra_kwargs)
        if not requires_bootstrap:
            extra_kwargs.setdefault("token_provider", self._token_provider)
        return self.__class__(
            workspace=workspace or self.workspace,
            base_url=base_url or self.base_url,
            inference_base_url=inference_base_url or self.inference_base_url,
            config_path=config_path,
            context_name=context_name,
            access_token=access_token,
            timeout=self.timeout if isinstance(timeout, NotGiven) else timeout,
            http_client=http_client,
            max_retries=self.max_retries if isinstance(max_retries, NotGiven) else max_retries,
            default_headers=headers,
            default_query=params,
            **extra_kwargs,
        )
