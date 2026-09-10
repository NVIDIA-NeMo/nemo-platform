# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Factory for creating NeMoPlatform SDK clients from nmp config.

Layers the generated ``NeMoPlatform`` constructors on top of the shared,
SDK-independent bootstrap in :mod:`nemo_platform_ext.client.bootstrap`, which
resolves the nmp config file, discovers OIDC settings, and builds the token
provider that keeps every request authenticated.
"""

from pathlib import Path
from typing import Mapping

import httpx
from nemo_platform import (
    DefaultAsyncHttpxClient,
    DefaultHttpxClient,
    NeMoPlatform,
    NotGiven,
    not_given,
)

from nemo_platform_ext.client.bootstrap import (
    _TOKEN_PROVIDER_CACHE,
    _TOKEN_PROVIDER_CACHE_LOCK,
    AccessTokenProvider,
    ClientInitConfig,
    ResolvedBootstrap,
    _headers_with_seeded_auth,
    _make_async_auth_event_hook,
    _make_auth_event_hook,
    resolve_bootstrap,
)

__all__ = [
    "_TOKEN_PROVIDER_CACHE",
    "_TOKEN_PROVIDER_CACHE_LOCK",
    "AccessTokenProvider",
    "ClientInitConfig",
    "ResolvedBootstrap",
    "build_async_client_init_kwargs",
    "build_client_init_kwargs",
    "create_client",
]


# ---------------------------------------------------------------------------
# Public API: build kwargs / create client
# ---------------------------------------------------------------------------


def build_client_init_kwargs(
    *,
    config_path: Path | None = None,
    base_url: str | httpx.URL | None = None,
    context_name: str | None = None,
    access_token: str | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> ClientInitConfig:
    """Build constructor kwargs for a **sync** NeMoPlatform client.

    For OAuth users, returns a ``ClientInitConfig`` whose ``http_client``
    has a request event hook that transparently injects and refreshes the
    Bearer token before every request.
    """
    bootstrap = resolve_bootstrap(
        config_path=config_path,
        base_url=base_url,
        context_name=context_name,
        access_token=access_token,
        extra_headers=extra_headers,
    )
    if bootstrap.token_provider is None:
        # Non-OAuth: static headers, no custom http_client needed.
        return ClientInitConfig(
            base_url=bootstrap.base_url,
            workspace=bootstrap.workspace,
            default_headers=bootstrap.default_headers or None,
            client_verify=bootstrap.client_verify,
        )

    # Seed the default headers with a current token so that SDK internals
    # that inspect headers (e.g. auth_headers property) see a value. Workload
    # identity only seeds when the request-time provider already has a token.
    # The event hook will overwrite it with a fresh token on each request.
    headers = _headers_with_seeded_auth(bootstrap.default_headers, bootstrap.token_provider)
    hook = _make_auth_event_hook(bootstrap.token_provider)
    http_client = DefaultHttpxClient(
        event_hooks={"request": [hook], "response": []},
        follow_redirects=True,
        verify=bootstrap.client_verify,
    )
    return ClientInitConfig(
        base_url=bootstrap.base_url,
        workspace=bootstrap.workspace,
        default_headers=headers or None,
        http_client=http_client,
        client_verify=bootstrap.client_verify,
    )


def build_async_client_init_kwargs(
    *,
    config_path: Path | None = None,
    base_url: str | httpx.URL | None = None,
    context_name: str | None = None,
    access_token: str | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> ClientInitConfig:
    """Build constructor kwargs for an **async** AsyncNeMoPlatform client.

    Same as ``build_client_init_kwargs`` but returns an async httpx client
    whose event hook calls ``provider.get_access_token_async()`` (runs
    the refresh in a worker thread so it doesn't block the event loop).
    """
    bootstrap = resolve_bootstrap(
        config_path=config_path,
        base_url=base_url,
        context_name=context_name,
        access_token=access_token,
        extra_headers=extra_headers,
    )
    if bootstrap.token_provider is None:
        return ClientInitConfig(
            base_url=bootstrap.base_url,
            workspace=bootstrap.workspace,
            default_headers=bootstrap.default_headers or None,
            client_verify=bootstrap.client_verify,
        )

    headers = _headers_with_seeded_auth(bootstrap.default_headers, bootstrap.token_provider)
    hook = _make_async_auth_event_hook(bootstrap.token_provider)
    http_client = DefaultAsyncHttpxClient(
        event_hooks={"request": [hook], "response": []},
        follow_redirects=True,
        verify=bootstrap.client_verify,
    )
    return ClientInitConfig(
        base_url=bootstrap.base_url,
        workspace=bootstrap.workspace,
        default_headers=headers or None,
        http_client=http_client,
        client_verify=bootstrap.client_verify,
    )


def create_client(
    *,
    config_path: Path | None = None,
    base_url: str | httpx.URL | None = None,
    context_name: str | None = None,
    access_token: str | None = None,
    timeout: float | httpx.Timeout | None | NotGiven = not_given,
    max_retries: int = 2,
    extra_headers: Mapping[str, str] | None = None,
) -> NeMoPlatform:
    """Create a NeMoPlatform client from the nmp config.

    This is a convenience wrapper that calls ``build_client_init_kwargs``
    and passes the result to the SDK constructor.
    """
    client_init_kwargs = build_client_init_kwargs(
        config_path=config_path,
        base_url=base_url,
        context_name=context_name,
        access_token=access_token,
        extra_headers=extra_headers,
    )
    http_client = client_init_kwargs.http_client
    if http_client is not None and not isinstance(http_client, httpx.Client):
        raise TypeError("build_client_init_kwargs returned a non-sync HTTP client")
    if http_client is None and client_init_kwargs.client_verify is not True:
        http_client = DefaultHttpxClient(verify=client_init_kwargs.client_verify)

    return NeMoPlatform(
        config_path=config_path,
        context_name=context_name,
        access_token=access_token,
        base_url=client_init_kwargs.base_url,
        workspace=client_init_kwargs.workspace,
        default_headers=client_init_kwargs.default_headers,
        http_client=http_client,
        max_retries=max_retries,
        timeout=timeout,
    )
