# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`nmp.common.client_factory` — the rich NemoClient provider.

Covers what the platform provider adds over the plugin's env-var default:
per-service URL routing, endpoint-aware HTTP clients, principal/auth + internal +
OTEL headers, workspace defaults, and explicit test-client injection.
"""

from unittest.mock import patch

import httpx
import pytest
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.types import PreparedRequest
from nemo_platform_plugin.client_provider import NemoClientProvider
from nmp.common import client_factory as cf
from nmp.common.config import Configuration, PlatformConfig
from nmp.common.observability.otel import scoped_otel_headers
from nmp.common.platform_endpoint import _SyncPlatformEndpointRoutingTransport
from nmp.testing.http_clients import routed_async_mock_client, routed_mock_client


@pytest.fixture(autouse=True)
def _reset_client_factory_state():
    """Keep tests order-independent: clear config cache."""
    Configuration.clear_cache()
    Configuration.clear_override(PlatformConfig)
    try:
        yield
    finally:
        Configuration.clear_override(PlatformConfig)
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


def _capture_request_client(sink: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        sink.append(request)
        return httpx.Response(200, json={"ok": True})

    return routed_mock_client(handler)


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

    def test_builds_endpoint_owned_sync_http_client(self):
        client = cf.get_nemo_client()
        assert isinstance(client._http, httpx.Client)

    def test_explicit_http_client_wins(self):
        with httpx.Client() as explicit:
            client = cf.get_nemo_client(http_client=explicit)
            assert client._http is explicit
            assert client._url_resolver is None


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

    def test_builds_endpoint_owned_async_http_client(self):
        client = cf.get_async_nemo_client()
        assert isinstance(client._http, httpx.AsyncClient)


# ---------------------------------------------------------------------------
# URL routing
# ---------------------------------------------------------------------------


class TestUrlRouting:
    def test_routes_service_path_to_discovered_origin(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "https://nemo-gateway:8080")
        Configuration.set_override(
            PlatformConfig(
                base_url="https://nemo-gateway:8080",
                service_discovery={"entities": "http://entities-svc:9999"},
            )
        )
        Configuration.clear_cache()

        captured: list[httpx.Request] = []
        client = cf.get_nemo_client(as_service="entities", internal=True, http_client=_capture_request_client(captured))
        client.send(_get("/apis/entities/v2/foo"))

        assert str(captured[0].url) == "http://entities-svc:9999/apis/entities/v2/foo"
        assert captured[0].headers["X-NMP-Principal-Id"] == "service:entities"
        assert captured[0].headers["X-NMP-Internal"] == "true"

    def test_preserves_query_string_when_routing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "https://nemo-gateway:8080")
        Configuration.set_override(
            PlatformConfig(
                base_url="https://nemo-gateway:8080",
                service_discovery={"entities": "http://entities-svc:9999"},
            )
        )
        Configuration.clear_cache()

        captured: list[httpx.Request] = []
        client = cf.get_nemo_client(http_client=_capture_request_client(captured))
        client.send(_get("/apis/entities/v2/models?limit=5"))

        assert str(captured[0].url) == "http://entities-svc:9999/apis/entities/v2/models?limit=5"

    def test_non_discovered_path_stays_on_platform_origin(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "https://nemo-gateway:8080")
        monkeypatch.delenv("NMP_MODELS_URL", raising=False)
        Configuration.clear_cache()

        captured: list[httpx.Request] = []
        client = cf.get_nemo_client(http_client=_capture_request_client(captured))
        client.send(_get("/apis/models/v1/bar"))

        assert str(captured[0].url) == "https://nemo-gateway:8080/apis/models/v1/bar"

    def test_workspace_default_fills_path_param(self):
        captured: list[httpx.Request] = []
        client = cf.get_nemo_client(workspace="team-a", http_client=_capture_request_client(captured))
        client.send(_get("/apis/entities/v2/workspaces/{workspace}/models"))

        assert "/workspaces/team-a/models" in str(captured[0].url)

    def test_endpoint_owned_client_uses_transport_routing_once(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "http://nemo-gateway:8080")
        Configuration.set_override(
            PlatformConfig(
                base_url="http://nemo-gateway:8080",
                service_discovery={"entities": "http://entities-svc:9999/entities-prefix"},
            )
        )
        Configuration.clear_cache()

        client = cf.get_nemo_client()

        assert client._url_resolver is None
        assert isinstance(client._http._transport, _SyncPlatformEndpointRoutingTransport)


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

    def test_merges_otel_propagation_headers_without_adding_internal_auth(self):
        with scoped_otel_headers({"traceparent": "00-trace-span-01", "X-NMP-Internal": "true"}):
            client = cf.get_nemo_client(as_service="svc")
        assert client._default_headers["traceparent"] == "00-trace-span-01"
        assert client._default_headers["X-NMP-Principal-Id"] == "service:svc"
        assert "X-NMP-Internal" not in client._default_headers

    def test_explicit_auth_headers_win_over_conflicting_otel_context(self):
        with scoped_otel_headers(
            {
                "traceparent": "00-trace-span-01",
                "x-nmp-principal-id": "attacker@example.com",
                "X-NMP-Principal-Groups": "admins",
                "x-NMP-Internal": "false",
            }
        ):
            client = cf.get_async_nemo_client(as_service="evaluator", internal=True)
        assert client._default_headers["traceparent"] == "00-trace-span-01"
        assert client._default_headers["X-NMP-Principal-Id"] == "service:evaluator"
        assert client._default_headers["X-NMP-Internal"] == "true"
        assert all(name.lower() != "x-nmp-principal-groups" for name in client._default_headers)

    def test_no_headers_leaves_default_headers_none(self):
        # No service, no principal context, no OTEL, no internal → no default headers.
        with patch("nmp.common.sdk_factory.get_principal_auth_headers", return_value={}):
            with patch("nmp.common.sdk_factory.principal_from_env", return_value=None):
                client = cf.get_nemo_client()
        assert client._default_headers == {}


# ---------------------------------------------------------------------------
# Test-client injection
# ---------------------------------------------------------------------------


class TestExplicitClientInjection:
    async def test_async_explicit_http_client_is_used(self):
        async with httpx.AsyncClient(base_url="http://explicit") as explicit:
            client = cf.get_async_nemo_client(http_client=explicit)

            assert client._http is explicit
            assert client._url_resolver is None

    async def test_async_explicit_test_client_can_route_service_urls(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "https://nemo-gateway:8080")
        Configuration.set_override(
            PlatformConfig(
                base_url="https://nemo-gateway:8080",
                service_discovery={"entities": "http://entities-svc:9999"},
            )
        )
        Configuration.clear_cache()
        captured: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"ok": True})

        async with routed_async_mock_client(handler) as explicit:
            client = cf.get_async_nemo_client(http_client=explicit)
            await client.send(_get("/apis/entities/v2/foo"))

        assert str(captured[0].url) == "http://entities-svc:9999/apis/entities/v2/foo"


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


# ---------------------------------------------------------------------------
# Task client: creator delegation (PR-800 claim 1)
# ---------------------------------------------------------------------------


class TestTaskClientDelegation:
    def test_task_client_delegates_to_job_creator(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(
            "NMP_PRINCIPAL",
            '{"id": "user:alice@acme.com", "email": "alice@acme.com", "groups": ["team-a"]}',
        )
        client = cf.get_task_nemo_client("evaluator")
        headers = client._default_headers
        assert headers["X-NMP-Internal"] == "true"
        assert headers["X-NMP-Principal-Id"] == "service:evaluator"
        assert headers["X-NMP-Principal-On-Behalf-Of"] == "user:alice@acme.com"
        assert headers["X-NMP-Principal-On-Behalf-Of-Email"] == "alice@acme.com"
        assert headers["X-NMP-Principal-On-Behalf-Of-Groups"] == "team-a"

    def test_task_client_without_principal_warns(self, monkeypatch: pytest.MonkeyPatch, caplog):
        monkeypatch.delenv("NMP_PRINCIPAL", raising=False)
        with caplog.at_level("WARNING"):
            client = cf.get_task_nemo_client("evaluator")
        assert client._default_headers["X-NMP-Principal-Id"] == "service:evaluator"
        assert "X-NMP-Principal-On-Behalf-Of" not in client._default_headers
        assert "without on-behalf-of delegation" in caplog.text

    async def test_async_task_client_delegates(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(
            "NMP_PRINCIPAL",
            '{"id": "user:alice@acme.com", "email": "alice@acme.com", "groups": ["team-a"]}',
        )
        client = cf.get_async_task_nemo_client("evaluator")
        assert client._default_headers["X-NMP-Principal-On-Behalf-Of"] == "user:alice@acme.com"

    def test_provider_exposes_task_methods(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_PRINCIPAL", '{"id": "user:alice@acme.com"}')
        provider = cf.PlatformNemoClientProvider()
        headers = provider.get_task_nemo_client("evaluator")._default_headers
        assert headers["X-NMP-Principal-On-Behalf-Of"] == "user:alice@acme.com"


# ---------------------------------------------------------------------------
# Task client: workload identity (PR-800 claim 2)
# ---------------------------------------------------------------------------


class _FakeExchangeProvider:
    def get_access_token(self) -> str:
        return "exchanged-token"

    async def get_access_token_async(self) -> str:
        return "exchanged-token"


class TestTaskClientWorkloadIdentity:
    @pytest.fixture
    def _stub_exchange(self, monkeypatch: pytest.MonkeyPatch):
        captured: dict[str, str] = {}

        def _fake(*, base_url, subject_token_file):
            captured["base_url"] = base_url
            captured["subject_token_file"] = str(subject_token_file)
            return _FakeExchangeProvider()

        monkeypatch.setattr(
            "nemo_platform_plugin.client.oidc_factory.resolve_workload_exchange_provider",
            _fake,
        )
        return captured

    def test_task_client_bootstraps_workload_identity(self, monkeypatch, tmp_path, _stub_exchange):
        token_file = tmp_path / "token"
        token_file.write_text("subject-token")
        monkeypatch.setenv("NMP_WORKLOAD_IDENTITY_TOKEN_FILE", str(token_file))
        monkeypatch.setenv("NMP_BASE_URL", "http://platform:8080")
        monkeypatch.delenv("NMP_PRINCIPAL", raising=False)
        Configuration.clear_cache()

        client = cf.get_task_nemo_client("evaluator")
        assert isinstance(client._auth, _FakeExchangeProvider)
        assert _stub_exchange["base_url"] == "http://platform:8080"
        # No trusted principal headers in workload-identity mode.
        assert "X-NMP-Principal-Id" not in client._default_headers
        assert client._default_headers.get("X-NMP-Internal") == "true"

    def test_task_client_rejects_workload_identity_with_principal_env(self, monkeypatch, tmp_path, _stub_exchange):
        token_file = tmp_path / "token"
        token_file.write_text("subject-token")
        monkeypatch.setenv("NMP_WORKLOAD_IDENTITY_TOKEN_FILE", str(token_file))
        monkeypatch.setenv("NMP_BASE_URL", "http://platform:8080")
        monkeypatch.setenv("NMP_PRINCIPAL", '{"id": "user:alice@acme.com"}')
        Configuration.clear_cache()

        with pytest.raises(ValueError, match="mutually exclusive"):
            cf.get_task_nemo_client("evaluator")


# ---------------------------------------------------------------------------
# UDS endpoint routing + transport (PR-800 claim 3)
# ---------------------------------------------------------------------------


class TestUdsTransport:
    def test_uds_base_url_is_normalized_not_pathed(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "unix:///tmp/nemo-platform.sock")
        Configuration.clear_cache()
        client = cf.get_nemo_client()
        # base_url is the routable host, not the raw unix:// socket path.
        assert client.base_url == "http://nemo-platform.local"
        # concatenating an API path yields a valid URL, not a broken one.
        assert client.base_url + "/apis/entities/v2/foo" == "http://nemo-platform.local/apis/entities/v2/foo"

    def test_uds_sync_client_binds_socket_transport(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "unix:///tmp/nemo-platform.sock")
        Configuration.clear_cache()
        client = cf.get_nemo_client()
        transport = client._http._transport
        assert isinstance(transport, httpx.HTTPTransport)
        assert getattr(transport._pool, "_uds") == "/tmp/nemo-platform.sock"

    async def test_uds_async_client_binds_socket_transport(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "unix:///tmp/nemo-platform.sock")
        Configuration.clear_cache()
        client = cf.get_async_nemo_client()
        transport = client._http._transport
        assert isinstance(transport, httpx.AsyncHTTPTransport)
        assert getattr(transport._pool, "_uds") == "/tmp/nemo-platform.sock"

    def test_tcp_client_uses_default_client(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NMP_BASE_URL", "http://platform:8080")
        Configuration.clear_cache()
        client = cf.get_nemo_client()
        assert client.base_url == "http://platform:8080"
        assert isinstance(client._http, httpx.Client)
