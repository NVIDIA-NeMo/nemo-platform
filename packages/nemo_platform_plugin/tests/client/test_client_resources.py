# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for discovered plugin resources, clone isolation, and transport auth.

Covers three behaviours that only surface through the compatibility layer:

- ``sdk.inference.*`` must hand back a resource client matching the owning
  client's sync/async flavour.
- ``with_options()`` clones must not reuse resources bound to the original.
- Raw calls through the exposed ``_client`` transport must stay authenticated.
"""

from __future__ import annotations

import httpx
import pytest
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient

BASE = "http://test:8000"


class _Resource:
    """Stand-in for a discovered plugin SDK resource."""

    def __init__(self, platform: object) -> None:
        self.platform = platform


@pytest.fixture
def discovered(monkeypatch: pytest.MonkeyPatch):
    """Register a fake ``thing`` resource on the plugin SDK discovery surface."""

    class Resources:
        sync_resource = _Resource
        async_resource = _Resource

    monkeypatch.setattr(
        "nemo_platform_plugin.discovery.discover_sdk",
        lambda: {"thing": Resources()},
    )


# ---------------------------------------------------------------------------
# sdk.inference.* sync/async dispatch
# ---------------------------------------------------------------------------


def test_inference_namespace_returns_sync_clients_for_sync_client() -> None:
    from nemo_platform_plugin.models.client import ModelsClient
    from nemo_platform_plugin.virtual_models.client import VirtualModelsClient

    client = NemoClient(base_url=BASE)

    assert isinstance(client.inference.providers, ModelsClient)
    assert isinstance(client.inference.deployments, ModelsClient)
    assert isinstance(client.inference.deployment_configs, ModelsClient)
    assert isinstance(client.inference.virtual_models, VirtualModelsClient)


def test_inference_namespace_returns_async_clients_for_async_client() -> None:
    """An async client must never wrap its AsyncClient in a sync resource."""
    from nemo_platform_plugin.models.client import AsyncModelsClient
    from nemo_platform_plugin.virtual_models.client import AsyncVirtualModelsClient

    client = AsyncNemoClient(base_url=BASE)

    assert isinstance(client.inference.providers, AsyncModelsClient)
    assert isinstance(client.inference.deployments, AsyncModelsClient)
    assert isinstance(client.inference.deployment_configs, AsyncModelsClient)
    assert isinstance(client.inference.virtual_models, AsyncVirtualModelsClient)


@pytest.mark.parametrize(
    ("client_factory", "transport_type"),
    [(NemoClient, httpx.Client), (AsyncNemoClient, httpx.AsyncClient)],
)
def test_inference_resources_transport_matches_flavour(client_factory, transport_type) -> None:
    client = client_factory(base_url=BASE)

    assert isinstance(client.inference.providers._http, transport_type)
    assert isinstance(client.inference.virtual_models._http, transport_type)


# ---------------------------------------------------------------------------
# with_options() clone isolation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("client_factory", [NemoClient, AsyncNemoClient])
def test_with_options_does_not_reuse_cached_resources(client_factory, discovered) -> None:
    client = client_factory(base_url=BASE)
    original = client.thing

    clone = client.with_headers({"X-Trace": "1"})

    assert clone.thing is not original
    assert clone.thing.platform is clone
    assert original.platform is client


@pytest.mark.parametrize("client_factory", [NemoClient, AsyncNemoClient])
def test_cloned_resource_sees_overridden_options(client_factory, discovered) -> None:
    """The whole point of the clone: overrides must reach the resource."""
    client = client_factory(base_url=BASE)
    _ = client.thing  # prime the cache before cloning

    clone = client.with_headers({"X-Trace": "1"})

    assert clone.thing.platform.default_headers == {"X-Trace": "1"}
    assert client.thing.platform.default_headers == {}


@pytest.mark.parametrize("client_factory", [NemoClient, AsyncNemoClient])
def test_resource_is_cached_within_one_client(client_factory, discovered) -> None:
    client = client_factory(base_url=BASE)

    assert client.thing is client.thing


@pytest.mark.parametrize("client_factory", [NemoClient, AsyncNemoClient])
def test_unknown_attribute_still_raises(client_factory, discovered) -> None:
    client = client_factory(base_url=BASE)

    with pytest.raises(AttributeError, match="nope"):
        _ = client.nope


# ---------------------------------------------------------------------------
# Auth on the raw _client transport
# ---------------------------------------------------------------------------


def test_raw_client_calls_are_authenticated() -> None:
    """Plugin resources using platform._client bypass send() but keep auth."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = NemoClient(base_url=BASE, auth="tok")
    client._http._transport = httpx.MockTransport(handler)

    transport = client._client
    assert isinstance(transport, httpx.Client)
    transport.get(f"{BASE}/apis/anything")

    assert seen[0].headers["Authorization"] == "Bearer tok"


@pytest.mark.asyncio
async def test_raw_async_client_calls_are_authenticated() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = AsyncNemoClient(base_url=BASE, auth="tok")
    client._http._transport = httpx.MockTransport(handler)

    transport = client._client
    assert isinstance(transport, httpx.AsyncClient)
    await transport.get(f"{BASE}/apis/anything")

    assert seen[0].headers["Authorization"] == "Bearer tok"


def test_transport_auth_does_not_override_explicit_header() -> None:
    """send() and per-call overrides stay authoritative over transport auth."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = NemoClient(base_url=BASE, auth="tok")
    client._http._transport = httpx.MockTransport(handler)

    transport = client._client
    assert isinstance(transport, httpx.Client)
    transport.get(f"{BASE}/apis/anything", headers={"Authorization": "Bearer explicit"})

    assert seen[0].headers["Authorization"] == "Bearer explicit"


def test_no_auth_configured_leaves_transport_unauthenticated() -> None:
    client = NemoClient(base_url=BASE)

    assert client._http.auth is None


def test_shared_transport_keeps_auth_across_from_client() -> None:
    """Resource clients built from a parent share its authenticated transport."""
    from nemo_platform_plugin.client.auth import TokenProviderAuth
    from nemo_platform_plugin.models.client import ModelsClient

    parent = NemoClient(base_url=BASE, auth="tok")
    child = ModelsClient.from_client(parent)

    assert child._http is parent._http
    assert isinstance(child._http.auth, TokenProviderAuth)
