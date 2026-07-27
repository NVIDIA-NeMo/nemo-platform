# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from nemo_platform_plugin.entities.client import AsyncEntitiesClient
from nmp.common.auth import AuthClient, Principal
from nmp.common.config import PlatformConfig
from nmp.common.service import DependencyProvider
from nmp.common.service.dependencies import (
    get_effective_principal_id,
    get_entity_client,
    get_platform_config,
    get_sdk_client,
)


def test_get_http_client_requires_initialization() -> None:
    provider = DependencyProvider()
    with pytest.raises(RuntimeError, match="DependencyProvider is not initialized"):
        provider.get_http_client()


def test_initialize_creates_http_client_and_cached_sdk_from_endpoint() -> None:
    provider = DependencyProvider()
    platform_config = PlatformConfig(base_url="http://platform:8080")  # type: ignore[abstract]
    provider._platform_config = platform_config
    platform_endpoint = MagicMock(name="platform_endpoint")
    platform_endpoint.connect_base_url = "http://platform:8080"
    http_client = MagicMock(name="http_client")
    platform_endpoint.async_sdk_http_client.return_value = http_client
    sdk = MagicMock(name="sdk")

    with (
        patch("nmp.common.service.base.resolve_platform_endpoint", return_value=platform_endpoint) as resolve_endpoint,
        patch("nmp.common.sdk_factory.get_async_platform_sdk", return_value=sdk) as sdk_factory,
    ):
        provider.initialize()
        provider.initialize()

    assert provider.get_http_client() is http_client
    assert provider.get_sdk_client() is sdk
    resolve_endpoint.assert_called_once_with(platform_config)
    platform_endpoint.async_sdk_http_client.assert_called_once_with()
    sdk_factory.assert_called_once_with(http_client=http_client, base_url="http://platform:8080")


def test_configure_http_client_is_used_for_cached_sdk_client() -> None:
    provider = DependencyProvider()
    http_client = MagicMock(name="http_client")
    sdk = MagicMock(name="sdk")
    platform_config = PlatformConfig(base_url="http://platform:8080")  # type: ignore[abstract]
    provider._platform_config = platform_config
    platform_endpoint = MagicMock(name="platform_endpoint")
    platform_endpoint.connect_base_url = "http://platform:8080"

    provider.configure_http_client(http_client)

    with (
        patch("nmp.common.service.base.resolve_platform_endpoint", return_value=platform_endpoint),
        patch("nmp.common.sdk_factory.get_async_platform_sdk", return_value=sdk) as sdk_factory,
    ):
        provider.initialize()
        assert provider.get_sdk_client() is sdk
        assert provider.get_sdk_client() is sdk

    platform_endpoint.async_sdk_http_client.assert_not_called()
    sdk_factory.assert_called_once_with(http_client=http_client, base_url="http://platform:8080")


def test_configure_platform_endpoint_is_used_during_initialization() -> None:
    provider = DependencyProvider()
    platform_endpoint = MagicMock(name="platform_endpoint")
    platform_endpoint.connect_base_url = "http://platform:8080"
    http_client = MagicMock(name="http_client")
    platform_endpoint.async_sdk_http_client.return_value = http_client
    sdk = MagicMock(name="sdk")

    provider.configure_platform_endpoint(platform_endpoint)

    with patch("nmp.common.sdk_factory.get_async_platform_sdk", return_value=sdk):
        provider.initialize()

    assert provider.get_http_client() is http_client
    assert provider.get_sdk_client() is sdk


def test_configure_http_client_rejects_changes_after_sdk_created() -> None:
    provider = DependencyProvider()
    sdk = MagicMock(name="sdk")
    http_client = MagicMock(name="http_client")
    platform_endpoint = MagicMock(name="platform_endpoint")
    platform_endpoint.connect_base_url = "http://platform:8080"
    platform_endpoint.async_sdk_http_client.return_value = http_client

    with (
        patch("nmp.common.service.base.resolve_platform_endpoint", return_value=platform_endpoint),
        patch("nmp.common.sdk_factory.get_async_platform_sdk", return_value=sdk),
    ):
        provider.initialize()

    with pytest.raises(RuntimeError, match="Cannot configure DependencyProvider HTTP client after initialization"):
        provider.configure_http_client(MagicMock(name="late_http_client"))


def test_get_sdk_client_caches_request_sdk_and_creates_fresh_service_sdk() -> None:
    provider = DependencyProvider()
    request_sdk = MagicMock(name="request_sdk")
    service_sdk = MagicMock(name="service_sdk")
    request_sdk.custom_auth = None
    request_sdk.with_options.return_value = service_sdk
    http_client = MagicMock(name="http_client")
    request_sdk._client = http_client
    platform_endpoint = MagicMock(name="platform_endpoint")
    platform_endpoint.connect_base_url = "http://platform:8080"
    platform_endpoint.async_sdk_http_client.return_value = http_client

    with (
        patch("nmp.common.service.base.resolve_platform_endpoint", return_value=platform_endpoint),
        patch("nmp.common.sdk_factory.get_async_platform_sdk", side_effect=[request_sdk, service_sdk]) as sdk_factory,
    ):
        provider.initialize()
        assert provider.get_sdk_client() is request_sdk
        assert provider.get_sdk_client() is request_sdk
        assert provider.get_sdk_client(as_service="jobs") is service_sdk

    sdk_factory.assert_called_once_with(http_client=http_client, base_url="http://platform:8080")
    request_sdk.with_options.assert_called_once_with(
        set_default_headers={
            "X-NMP-Internal": "true",
            "X-NMP-Principal-Id": "service:jobs",
        },
        http_client=http_client,
    )


def test_setup_dependencies_registers_fastapi_overrides() -> None:
    provider = DependencyProvider()
    app = FastAPI()
    service = MagicMock()
    service._service_config = None

    provider.setup_dependencies(app, service)

    assert app.dependency_overrides[get_sdk_client] == provider.get_request_scoped_sdk
    assert app.dependency_overrides[get_entity_client] == provider.get_entity_client
    assert app.dependency_overrides[get_effective_principal_id] == provider.get_effective_principal_id
    assert app.dependency_overrides[get_platform_config] == provider.get_platform_config


def test_get_effective_principal_id_uses_delegated_identity() -> None:
    provider = DependencyProvider()
    request = MagicMock()
    auth_client = MagicMock(spec=AuthClient)
    auth_client.principal = Principal(
        id="service:agents",
        email=None,
        on_behalf_of="session-owner",
        on_behalf_of_email=None,
    )

    with patch("nmp.common.auth.get_auth_client", return_value=auth_client):
        assert provider.get_effective_principal_id(request) == "session-owner"


@pytest.mark.asyncio
async def test_close_closes_managed_clients_and_clears_references() -> None:
    provider = DependencyProvider()
    http_client = AsyncMock(spec=httpx.AsyncClient)
    sdk = MagicMock()
    sdk.close = AsyncMock()
    provider._service_http_client = http_client
    provider._owns_service_http_client = True
    provider._sdk_client = sdk

    await provider.close()

    http_client.aclose.assert_awaited_once_with()
    sdk.close.assert_not_awaited()
    assert provider._service_http_client is None
    assert provider._configured_http_client is None
    assert provider._sdk_client is None


@pytest.mark.asyncio
async def test_close_does_not_close_configured_http_client() -> None:
    provider = DependencyProvider()
    http_client = AsyncMock(spec=httpx.AsyncClient)
    sdk = MagicMock()
    sdk.close = AsyncMock()
    provider._service_http_client = http_client
    provider._configured_http_client = http_client
    provider._sdk_client = sdk

    await provider.close()

    http_client.aclose.assert_not_awaited()
    sdk.close.assert_not_awaited()
    assert provider._service_http_client is None
    assert provider._configured_http_client is None
    assert provider._sdk_client is None


@pytest.mark.asyncio
async def test_close_closes_cached_sdk_when_no_factory_exists() -> None:
    provider = DependencyProvider()
    sdk = MagicMock()
    sdk.close = AsyncMock()
    provider._sdk_client = sdk

    await provider.close()

    sdk.close.assert_awaited_once_with()
    assert provider._sdk_client is None


def test_get_entity_client_as_service_uses_fresh_service_sdk() -> None:
    provider = DependencyProvider()
    sdk = MagicMock(name="service_sdk")
    entities_client = MagicMock(name="entities_client")
    entity_client = MagicMock(name="entity_client")

    with (
        patch.object(provider, "get_sdk_client", return_value=sdk) as get_sdk,
        patch(
            "nemo_platform_plugin.client.adapter.client_from_platform",
            return_value=entities_client,
        ) as adapter,
        patch("nmp.common.entities.client.EntityClient", return_value=entity_client) as client_factory,
    ):
        result = provider.get_entity_client(as_service="models")

    assert result is entity_client
    get_sdk.assert_called_once_with(as_service="models")
    adapter.assert_called_once_with(sdk, AsyncEntitiesClient)
    client_factory.assert_called_once_with(entities_client)
