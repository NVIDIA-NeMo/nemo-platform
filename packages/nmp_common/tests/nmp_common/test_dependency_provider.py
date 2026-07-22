# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from nmp.common.service import DependencyProvider
from nmp.common.service.dependencies import get_entity_client, get_platform_config, get_sdk_client


def test_get_http_client_caches_default_client() -> None:
    provider = DependencyProvider()
    client = MagicMock()

    with patch("nmp.common.service.base.DefaultAsyncHttpxClient", return_value=client) as factory:
        first = provider.get_http_client()
        second = provider.get_http_client()

    assert first is client
    assert second is client
    factory.assert_called_once_with()


def test_get_sdk_client_caches_request_sdk_and_creates_fresh_service_sdk() -> None:
    provider = DependencyProvider()
    request_sdk = MagicMock(name="request_sdk")
    service_sdk = MagicMock(name="service_sdk")

    with patch("nmp.common.sdk_factory.get_async_platform_sdk", side_effect=[request_sdk, service_sdk]) as factory:
        assert provider.get_sdk_client() is request_sdk
        assert provider.get_sdk_client() is request_sdk
        assert provider.get_sdk_client(as_service="jobs") is service_sdk

    assert factory.call_args_list[0].kwargs == {"http_client": None}
    assert factory.call_args_list[1].kwargs == {
        "as_service": "jobs",
        "internal": True,
        "http_client": None,
    }


def test_setup_dependencies_registers_fastapi_overrides() -> None:
    provider = DependencyProvider()
    app = FastAPI()
    service = MagicMock()
    service._service_config = None

    provider.setup_dependencies(app, service)

    assert app.dependency_overrides[get_sdk_client] == provider.get_request_scoped_sdk
    assert app.dependency_overrides[get_entity_client] == provider.get_entity_client
    assert app.dependency_overrides[get_platform_config] == provider.get_platform_config


@pytest.mark.asyncio
async def test_close_closes_managed_clients_and_clears_references() -> None:
    provider = DependencyProvider()
    http_client = MagicMock()
    http_client.aclose = AsyncMock()
    sdk = MagicMock()
    sdk.close = AsyncMock()
    provider._http_client = http_client
    provider._sdk_client = sdk

    await provider.close()

    http_client.aclose.assert_awaited_once_with()
    sdk.close.assert_awaited_once_with()
    assert provider._http_client is None
    assert provider._sdk_client is None


def test_get_entity_client_as_service_uses_fresh_service_sdk() -> None:
    provider = DependencyProvider()
    sdk = MagicMock(name="service_sdk")
    entities_api = MagicMock(name="entities_api")
    entity_client = MagicMock(name="entity_client")

    with (
        patch.object(provider, "get_sdk_client", return_value=sdk) as get_sdk,
        patch("nemo_platform.resources.entities.AsyncEntitiesResource", return_value=entities_api) as resource,
        patch("nmp.common.entities.client.EntityClient", return_value=entity_client) as client_factory,
    ):
        result = provider.get_entity_client(as_service="models")

    assert result is entity_client
    get_sdk.assert_called_once_with(as_service="models")
    resource.assert_called_once_with(sdk)
    client_factory.assert_called_once_with(entities_api)
