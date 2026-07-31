# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from nemo_platform_plugin.entities.client import AsyncEntitiesClient
from nmp.common.service import DependencyProvider
from nmp.common.service.dependencies import get_entity_client, get_platform_config, get_sdk_client
from starlette.requests import Request


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
    service.name = "data-designer"
    service._service_config = None

    provider.setup_dependencies(app, service)

    assert provider._service_name == "data-designer"
    assert app.dependency_overrides[get_sdk_client] == provider.get_request_scoped_sdk
    assert app.dependency_overrides[get_entity_client] == provider.get_request_scoped_entity_client
    assert app.dependency_overrides[get_platform_config] == provider.get_platform_config


def test_request_scoped_sdk_uses_service_name_and_workspace_path() -> None:
    provider = DependencyProvider()
    provider._service_name = "data-designer"
    base_sdk = MagicMock(name="base_sdk")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v2/workspaces/workspace-a/preview",
            "headers": [],
            "path_params": {"workspace": "workspace-a"},
        }
    )

    with (
        patch.object(provider, "get_sdk_client", return_value=base_sdk),
        patch("nmp.common.sdk_factory.get_request_scoped_sdk", return_value=MagicMock()) as scoped,
    ):
        provider.get_request_scoped_sdk(request)

    scoped.assert_called_once_with(
        base_sdk,
        as_service="data-designer",
        origin_workspace="workspace-a",
    )


def test_request_scoped_sdk_preserves_direct_principal_without_workspace() -> None:
    provider = DependencyProvider()
    provider._service_name = "auth"
    base_sdk = MagicMock(name="base_sdk")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v2/iam/opa-bundle.tar.gz",
            "headers": [],
            "path_params": {},
        }
    )

    with (
        patch.object(provider, "get_sdk_client", return_value=base_sdk),
        patch("nmp.common.sdk_factory.get_request_scoped_sdk", return_value=MagicMock()) as scoped,
    ):
        provider.get_request_scoped_sdk(request)

    scoped.assert_called_once_with(
        base_sdk,
        as_service=None,
        origin_workspace=None,
    )


def test_request_scoped_sdk_preserves_direct_principal_for_all_workspaces() -> None:
    provider = DependencyProvider()
    base_sdk = MagicMock(name="base_sdk")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v2/workspaces/-/jobs",
            "headers": [],
            "path_params": {"workspace": "-"},
        }
    )

    with (
        patch.object(provider, "get_sdk_client", return_value=base_sdk),
        patch("nmp.common.sdk_factory.get_request_scoped_sdk", return_value=MagicMock()) as scoped,
    ):
        provider.get_request_scoped_sdk(request)

    scoped.assert_called_once_with(
        base_sdk,
        as_service=None,
        origin_workspace=None,
    )


def test_request_scoped_entity_client_delegates_with_route_workspace() -> None:
    provider = DependencyProvider()
    provider._service_name = "data-designer"
    base_sdk = MagicMock(name="base_sdk")
    sdk = MagicMock(name="scoped_sdk")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v2/workspaces/workspace-a/entities",
            "headers": [],
            "path_params": {"workspace": "workspace-a"},
        }
    )

    with (
        patch.object(provider, "get_sdk_client", return_value=base_sdk),
        patch(
            "nmp.common.service.headers.build_downstream_service_headers", return_value={"test": "header"}
        ) as headers,
        patch("nmp.common.sdk_factory.with_options_preserving_request_router", return_value=sdk) as scoped,
        patch("nemo_platform_plugin.client.adapter.client_from_platform"),
        patch("nmp.common.entities.client.EntityClient"),
    ):
        provider.get_request_scoped_entity_client(request)

    headers.assert_called_once_with("data-designer", origin_workspace="workspace-a")
    scoped.assert_called_once_with(base_sdk, set_default_headers={"test": "header"})


def test_request_service_name_uses_merged_router_context() -> None:
    provider = DependencyProvider()
    provider._service_name = "last-registered-service"
    app_ctx = MagicMock(service_name="files")

    with patch("nmp.common.observability.context.get_app_ctx", return_value=app_ctx):
        assert provider._request_service_name() == "files"


def test_request_scoped_entity_client_preserves_direct_principal_without_workspace() -> None:
    provider = DependencyProvider()
    base_sdk = MagicMock(name="base_sdk")
    scoped_sdk = MagicMock(name="scoped_sdk")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v2/iam/opa-bundle.tar.gz",
            "headers": [],
            "path_params": {},
        }
    )

    with (
        patch.object(provider, "get_sdk_client", return_value=base_sdk),
        patch("nmp.common.sdk_factory.get_request_scoped_sdk", return_value=scoped_sdk) as scoped,
        patch("nemo_platform_plugin.client.adapter.client_from_platform"),
        patch("nmp.common.entities.client.EntityClient"),
    ):
        provider.get_request_scoped_entity_client(request)

    scoped.assert_called_once_with(base_sdk)


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
