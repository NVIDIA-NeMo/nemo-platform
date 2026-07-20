# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`nmp.common.client_factory` — the rich NemoClient provider.

Covers what the platform provider adds over the plugin's env-var default:
per-service URL routing, shared HTTP clients, principal/auth + internal +
OTEL headers, workspace defaults, and test-client injection.
"""

from unittest.mock import patch

import httpx
import pytest
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.types import PreparedRequest
from nemo_platform_plugin.client_provider import NemoClientProvider
from nmp.common import client_factory as cf
from nmp.common.config import Configuration
from nmp.common.observability.otel import scoped_otel_headers


@pytest.fixture(autouse=True)
def _reset_client_factory_state():
    """Keep tests order-independent: clear the injected test client and config cache."""
    old = cf._test_http_client
    cf._test_http_client = None
    Configuration.clear_cache()
    try:
        yield
    finally:
        cf._test_http_client = old
        Configuration.clear_cache()


def _get(path_template: str, **path_params: str) -> PreparedRequest:
    return PreparedRequest(
        method="GET",
        path_template=path_template,
        path_params=path_params,
        content=None,
        content_type=None,
        response_type=None,
    )


def _mock_client(sink: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        sink.append(request)
        return httpx.Response(200, json={"ok": True})

    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# Sync construction
# ---------------------------------------------------------------------------


class TestSyncConstruction:
    def test_base_url_from_config(self):
        client = cf.get_nemo_client()
        assert isinstance(client, NemoClient)
        assert client.base_url == str(Configuration.get_platform_config().base_url).rstrip("/")

    def test_service_principal_and_internal_headers(self):
        client = cf.get_nemo_client(as_service="evaluator", internal=True)
        assert client._default_headers["X-NMP-Principal-Id"] == "service:evaluator"
        assert client._default_headers["X-NMP-Internal"] == "true"

    def test_on_behalf_of(self):
        client = cf.get_nemo_client(as_service="svc", on_behalf_of="user@example.com")
        assert client._default_headers["X-NMP-Principal-On-Behalf-Of"] == "user@example.com"

    def test_workspace_passthrough(self):
        client = cf.get_nemo_client(workspace="team-a")
        assert client.workspace == "team-a"

    def test_reuses_shared_sync_http_client(self):
        client = cf.get_nemo_client()
        assert client._http is cf.shared_sync_http_client()

    def test_explicit_http_client_wins(self):
        with httpx.Client() as explicit:
            client = cf.get_nemo_client(http_client=explicit)
            assert client._http is explicit


# ---------------------------------------------------------------------------
# Async construction
# ---------------------------------------------------------------------------


class TestAsyncConstruction:
    def test_base_url_from_config(self):
        client = cf.get_async_nemo_client()
        assert isinstance(client, AsyncNemoClient)
        assert client.base_url == str(Configuration.get_platform_config().base_url).rstrip("/")

    def test_service_principal_and_internal_headers(self):
        client = cf.get_async_nemo_client(as_service="evaluator", internal=True)
        assert client._default_headers["X-NMP-Principal-Id"] == "service:evaluator"
        assert client._default_headers["X-NMP-Internal"] == "true"

    def test_falls_back_to_shared_async_client(self):
        client = cf.get_async_nemo_client()
        assert isinstance(client._http, httpx.AsyncClient)


# ---------------------------------------------------------------------------
# URL routing
# ---------------------------------------------------------------------------


class TestUrlRouting:
    def test_routes_service_path_to_discovered_origin(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "https://nemo-gateway:8080")
        monkeypatch.setenv("NMP_ENTITIES_URL", "http://entities-svc:9999")
        Configuration.clear_cache()

        captured: list[httpx.Request] = []
        client = cf.get_nemo_client(as_service="entities", internal=True, http_client=_mock_client(captured))
        client.send(_get("/apis/entities/v2/foo"))

        assert str(captured[0].url) == "http://entities-svc:9999/apis/entities/v2/foo"
        assert captured[0].headers["X-NMP-Principal-Id"] == "service:entities"
        assert captured[0].headers["X-NMP-Internal"] == "true"

    def test_preserves_query_string_when_routing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "https://nemo-gateway:8080")
        monkeypatch.setenv("NMP_ENTITIES_URL", "http://entities-svc:9999")
        Configuration.clear_cache()

        captured: list[httpx.Request] = []
        client = cf.get_nemo_client(http_client=_mock_client(captured))
        client.send(_get("/apis/entities/v2/models?limit=5"))

        assert str(captured[0].url) == "http://entities-svc:9999/apis/entities/v2/models?limit=5"

    def test_non_discovered_path_stays_on_platform_origin(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "https://nemo-gateway:8080")
        monkeypatch.delenv("NMP_MODELS_URL", raising=False)
        Configuration.clear_cache()

        captured: list[httpx.Request] = []
        client = cf.get_nemo_client(http_client=_mock_client(captured))
        client.send(_get("/apis/models/v1/bar"))

        assert str(captured[0].url) == "https://nemo-gateway:8080/apis/models/v1/bar"

    def test_workspace_default_fills_path_param(self):
        captured: list[httpx.Request] = []
        client = cf.get_nemo_client(workspace="team-a", http_client=_mock_client(captured))
        client.send(_get("/apis/entities/v2/workspaces/{workspace}/models"))

        assert "/workspaces/team-a/models" in str(captured[0].url)


# ---------------------------------------------------------------------------
# Headers / auth
# ---------------------------------------------------------------------------


class TestHeadersAuth:
    def test_propagates_request_principal_when_no_service(self):
        auth_headers = {"X-NMP-Principal-Id": "user@example.com", "X-NMP-Principal-Groups": "g1,g2"}
        # _get_default_headers reads the request principal via sdk_factory's binding.
        with patch("nmp.common.sdk_factory.get_principal_auth_headers", return_value=auth_headers):
            client = cf.get_nemo_client()
        assert client._default_headers["X-NMP-Principal-Id"] == "user@example.com"
        assert client._default_headers["X-NMP-Principal-Groups"] == "g1,g2"

    def test_merges_otel_propagation_headers(self):
        with scoped_otel_headers({"traceparent": "00-trace-span-01", "X-NMP-Internal": "true"}):
            client = cf.get_nemo_client(as_service="svc")
        assert client._default_headers["traceparent"] == "00-trace-span-01"
        assert client._default_headers["X-NMP-Principal-Id"] == "service:svc"

    def test_no_headers_leaves_default_headers_none(self):
        # No service, no principal context, no OTEL, no internal → no default headers.
        with patch("nmp.common.sdk_factory.get_principal_auth_headers", return_value={}):
            with patch("nmp.common.sdk_factory.principal_from_env", return_value=None):
                client = cf.get_nemo_client()
        assert client._default_headers == {}


# ---------------------------------------------------------------------------
# Test-client injection
# ---------------------------------------------------------------------------


class TestTestClientInjection:
    def test_async_uses_module_level_test_client(self):
        test_client = httpx.AsyncClient(base_url="http://testserver")
        cf._test_http_client = test_client
        try:
            client = cf.get_async_nemo_client(as_service="evaluator")
            assert client._http is test_client
        finally:
            cf._test_http_client = None

    def test_async_explicit_http_client_beats_module_level(self):
        module_client = httpx.AsyncClient(base_url="http://module")
        explicit = httpx.AsyncClient(base_url="http://explicit")
        cf._test_http_client = module_client
        try:
            client = cf.get_async_nemo_client(http_client=explicit)
            assert client._http is explicit
        finally:
            cf._test_http_client = None


# ---------------------------------------------------------------------------
# Provider class
# ---------------------------------------------------------------------------


class TestPlatformNemoClientProvider:
    def test_satisfies_protocol(self):
        assert isinstance(cf.PlatformNemoClientProvider(), NemoClientProvider)

    def test_get_nemo_client_returns_routed_sync_client(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "https://nemo-gateway:8080")
        Configuration.clear_cache()
        provider = cf.PlatformNemoClientProvider()
        client = provider.get_nemo_client(as_service="svc", internal=True, workspace="ws1")
        assert isinstance(client, NemoClient)
        assert client.base_url == "https://nemo-gateway:8080"
        assert client.workspace == "ws1"
        assert client._default_headers["X-NMP-Principal-Id"] == "service:svc"

    def test_get_async_nemo_client_returns_async_client(self):
        provider = cf.PlatformNemoClientProvider()
        client = provider.get_async_nemo_client(as_service="svc")
        assert isinstance(client, AsyncNemoClient)
        assert client._default_headers["X-NMP-Principal-Id"] == "service:svc"
