# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the extended ModelsResource / AsyncModelsResource helpers.

These exercise the *source* package (``models.resources``) which drives the
typed ``ModelsClient`` built from the SDK. The route builders are pure (no I/O);
the deployment/provider helpers are driven through a mocked httpx transport
shared by the SDK and the typed client (via ``client_from_platform``).
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from models.resources import AsyncModelsResource, ModelsResource
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform.types.inference import ModelDeployment, ModelProvider
from nemo_platform.types.models import ModelEntity


def _resource(base_url: str = "https://nmp.example.com/", workspace: str | None = None, **kwargs) -> ModelsResource:
    return ModelsResource(NeMoPlatform(base_url=base_url, workspace=workspace, **kwargs))


def _async_resource(
    base_url: str = "https://nmp.example.com/", workspace: str | None = None, **kwargs
) -> AsyncModelsResource:
    return AsyncModelsResource(AsyncNeMoPlatform(base_url=base_url, workspace=workspace, **kwargs))


# ---------------------------------------------------------------------------
# Base URL / route builders
# ---------------------------------------------------------------------------


def test_get_base_url_str_removes_trailing_slash() -> None:
    assert _resource("https://nmp.example.com/")._get_base_url_str() == "https://nmp.example.com"
    assert _resource("https://nmp.example.com")._get_base_url_str() == "https://nmp.example.com"


def test_get_openai_route_base_url_explicit_workspace() -> None:
    r = _resource()
    assert (
        r.get_openai_route_base_url(workspace="default")
        == "https://nmp.example.com/apis/inference-gateway/v2/workspaces/default/openai/-/v1"
    )
    assert "//v2" not in r.get_openai_route_base_url(workspace="default")


def test_get_openai_route_base_url_without_trailing_slash() -> None:
    r = _resource("https://nmp.example.com")
    assert (
        r.get_openai_route_base_url(workspace="default")
        == "https://nmp.example.com/apis/inference-gateway/v2/workspaces/default/openai/-/v1"
    )


def test_provider_route_openai_url_appends_v1() -> None:
    provider = MagicMock(spec=ModelProvider)
    provider.workspace = "default"
    provider.name = "openai-provider"
    provider.host_url = "https://api.openai.com"
    assert (
        _resource().get_provider_route_openai_url(provider)
        == "https://nmp.example.com/apis/inference-gateway/v2/workspaces/default/provider/openai-provider/-/v1"
    )


def test_provider_route_openai_url_no_v1_when_host_ends_with_v1() -> None:
    for host in ("https://nim.example.com/v1", "https://nim.example.com/v1/"):
        provider = MagicMock(spec=ModelProvider)
        provider.workspace = "default"
        provider.name = "nim-provider"
        provider.host_url = host
        assert (
            _resource().get_provider_route_openai_url(provider)
            == "https://nmp.example.com/apis/inference-gateway/v2/workspaces/default/provider/nim-provider/-"
        )


def test_model_entity_route_openai_url_always_v1() -> None:
    model_entity = MagicMock(spec=ModelEntity)
    model_entity.workspace = "ml-team"
    model_entity.name = "custom-model"
    assert (
        _resource().get_model_entity_route_openai_url(model_entity)
        == "https://nmp.example.com/apis/inference-gateway/v2/workspaces/ml-team/model/custom-model/-/v1"
    )


# ---------------------------------------------------------------------------
# Workspace resolution (client-level fallback)
# ---------------------------------------------------------------------------


def test_openai_route_base_url_uses_client_workspace() -> None:
    assert "/workspaces/client-ws/" in _resource(workspace="client-ws").get_openai_route_base_url()


def test_openai_route_base_url_explicit_overrides_client() -> None:
    r = _resource(workspace="client-ws")
    result = r.get_openai_route_base_url(workspace="override")
    assert "/workspaces/override/" in result
    assert "/workspaces/client-ws/" not in result


def test_openai_route_base_url_raises_without_workspace() -> None:
    with pytest.raises(ValueError, match="Missing workspace"):
        _resource().get_openai_route_base_url()


# ---------------------------------------------------------------------------
# OpenAI client factories
# ---------------------------------------------------------------------------


def test_get_openai_client_returns_configured_client() -> None:
    r = _resource()
    with patch("openai.OpenAI") as mock_openai_cls:
        mock_openai_cls.return_value = MagicMock()
        r.get_openai_client(workspace="default")
        mock_openai_cls.assert_called_once_with(
            base_url="https://nmp.example.com/apis/inference-gateway/v2/workspaces/default/openai/-/v1",
            api_key="not-needed",
            default_headers=r.get_client_default_headers(),
        )


def test_get_openai_client_includes_auth_headers() -> None:
    r = ModelsResource(
        NeMoPlatform(
            base_url="https://nmp.example.com/",
            default_headers={"Authorization": "Bearer token-123", "X-NMP-Principal-Id": "user@example.com"},
        )
    )
    with patch("openai.OpenAI") as mock_openai_cls:
        mock_openai_cls.return_value = MagicMock()
        r.get_openai_client(workspace="default")
        headers = mock_openai_cls.call_args.kwargs["default_headers"]
        assert headers["Authorization"] == "Bearer token-123"
        assert headers["X-NMP-Principal-Id"] == "user@example.com"


def test_get_async_openai_client_returns_async_client() -> None:
    r = _async_resource()
    with patch("openai.AsyncOpenAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        r.get_async_openai_client(workspace="production")
        mock_cls.assert_called_once_with(
            base_url="https://nmp.example.com/apis/inference-gateway/v2/workspaces/production/openai/-/v1",
            api_key="not-needed",
            default_headers=r.get_client_default_headers(),
        )


# ---------------------------------------------------------------------------
# get_provider_route_openai_url_for_deployment (drives the typed client)
#
# A real httpx client with a MockTransport is used so the client_from_platform
# bridge (which copies the SDK's transport + headers) works end to end.
# ---------------------------------------------------------------------------


def _capturing_transport(response: httpx.Response) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    return httpx.MockTransport(handler), seen


def _provider_payload(**extra: object) -> dict:
    base = {
        "id": "provider-1",
        "name": "my-provider",
        "workspace": "default",
        "host_url": "https://api.example.com",
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2020-01-01T00:00:00Z",
    }
    base.update(extra)
    return base


def test_provider_route_for_deployment_fetches_provider() -> None:
    transport, seen = _capturing_transport(httpx.Response(200, json=_provider_payload()))
    r = _resource(http_client=httpx.Client(transport=transport))

    deployment = MagicMock(spec=ModelDeployment)
    deployment.name = "my-deployment"
    deployment.model_provider_id = "default/my-provider"

    url = r.get_provider_route_openai_url_for_deployment(deployment)
    assert url == "https://nmp.example.com/apis/inference-gateway/v2/workspaces/default/provider/my-provider/-/v1"
    assert str(seen[0].url).endswith("/apis/models/v2/workspaces/default/providers/my-provider")


def test_provider_route_for_deployment_raises_when_no_provider_id() -> None:
    deployment = MagicMock(spec=ModelDeployment)
    deployment.name = "orphan-deployment"
    deployment.model_provider_id = None
    with pytest.raises(ValueError, match="no associated model_provider_id"):
        _resource().get_provider_route_openai_url_for_deployment(deployment)


@pytest.mark.asyncio
async def test_async_provider_route_for_deployment_fetches_provider() -> None:
    transport, _ = _capturing_transport(httpx.Response(200, json=_provider_payload()))
    r = _async_resource(http_client=httpx.AsyncClient(transport=transport))

    deployment = MagicMock(spec=ModelDeployment)
    deployment.name = "my-deployment"
    deployment.model_provider_id = "default/my-provider"

    url = await r.get_provider_route_openai_url_for_deployment(deployment)
    assert url == "https://nmp.example.com/apis/inference-gateway/v2/workspaces/default/provider/my-provider/-/v1"


# ---------------------------------------------------------------------------
# Deployment status polling (drives the typed client)
# ---------------------------------------------------------------------------


def _deployment_payload(status: str) -> dict:
    return {
        "id": "dep-1",
        "name": "my-deploy",
        "workspace": "default",
        "entity_version": 1,
        "config": "cfg",
        "config_version": 1,
        "status": status,
        "status_message": "",
        "status_history": [],
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2020-01-01T00:00:00Z",
    }


def test_wait_for_status_ready_checks_gateway() -> None:
    transport, _ = _capturing_transport(httpx.Response(200, json=_deployment_payload("READY")))
    r = _resource(workspace="default", http_client=httpx.Client(transport=transport))

    with patch.object(r, "wait_for_gateway", return_value=True) as gw:
        assert r.wait_for_status("my-deploy", "READY") is True
        gw.assert_called_once()


def test_wait_for_status_deployment_not_ready_skips_gateway() -> None:
    transport, _ = _capturing_transport(httpx.Response(200, json=_deployment_payload("ERROR")))
    r = _resource(workspace="default", http_client=httpx.Client(transport=transport))

    with patch.object(r, "wait_for_gateway", return_value=True) as gw:
        assert r.wait_for_status("my-deploy", "READY") is False
        gw.assert_not_called()


# ---------------------------------------------------------------------------
# Provider status polling (drives the typed client)
# ---------------------------------------------------------------------------


def test_wait_for_provider_ready_checks_gateway() -> None:
    transport, _ = _capturing_transport(httpx.Response(200, json=_provider_payload(status="READY")))
    r = _resource(workspace="default", http_client=httpx.Client(transport=transport))

    with patch.object(r, "wait_for_gateway", return_value=True) as gw:
        assert r.wait_for_provider("my-provider", "READY") is True
        gw.assert_called_once()


def test_wait_for_provider_error_skips_gateway() -> None:
    transport, _ = _capturing_transport(httpx.Response(200, json=_provider_payload(status="ERROR")))
    r = _resource(workspace="default", http_client=httpx.Client(transport=transport))

    with patch.object(r, "wait_for_gateway", return_value=True) as gw:
        assert r.wait_for_provider("my-provider", "READY") is False
        gw.assert_not_called()


@pytest.mark.asyncio
async def test_async_wait_for_provider_error_skips_gateway() -> None:
    transport, _ = _capturing_transport(httpx.Response(200, json=_provider_payload(status="ERROR")))
    r = _async_resource(workspace="default", http_client=httpx.AsyncClient(transport=transport))

    with patch.object(r, "wait_for_gateway", return_value=True) as gw:
        assert await r.wait_for_provider("my-provider", "READY") is False
        gw.assert_not_called()
