# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
import os
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from nmp.common.config import PlatformConfig, get_common_service_config
from nmp.common.platform_endpoint import (
    UDS_BASE_URL,
    PlatformEndpoint,
    _AsyncPlatformEndpointRoutingTransport,
    _SyncPlatformEndpointRoutingTransport,
    parse_platform_endpoint,
    resolve_platform_endpoint,
    resolve_service_endpoint,
)


@pytest.fixture(autouse=True)
def clear_service_url_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tuple(os.environ):
        if key == "NMP_BASE_URL":
            continue
        if key.startswith("NMP_") and key.endswith("_URL"):
            monkeypatch.delenv(key, raising=False)


def test_parse_tcp_endpoint() -> None:
    endpoint = parse_platform_endpoint("http://127.0.0.1:8080/")

    assert endpoint.transport == "tcp"
    assert endpoint.connect_base_url == "http://127.0.0.1:8080"
    assert endpoint.socket_path is None


@pytest.mark.parametrize("url", ["http://", "https://"])
def test_parse_rejects_hostless_http_endpoint(url: str) -> None:
    with pytest.raises(ValueError, match="must include a host"):
        parse_platform_endpoint(url)


def test_parse_https_endpoint_preserves_normalized_connect_base_url() -> None:
    endpoint = parse_platform_endpoint("https://platform.example.com/api/")

    assert endpoint.transport == "tcp"
    assert endpoint.connect_base_url == "https://platform.example.com/api"
    assert endpoint.socket_path is None


def test_parse_uds_endpoint() -> None:
    endpoint = parse_platform_endpoint("unix:///tmp/nemo-platform.sock")

    assert endpoint.transport == "uds"
    assert endpoint.connect_base_url == UDS_BASE_URL
    assert endpoint.socket_path == Path("/tmp/nemo-platform.sock")


def test_parse_rejects_raw_socket_path() -> None:
    with pytest.raises(ValueError, match="use unix:///tmp/nemo-platform.sock"):
        parse_platform_endpoint("/tmp/nemo-platform.sock")


def test_parse_rejects_relative_uds_socket_path() -> None:
    with pytest.raises(ValueError, match="absolute socket path"):
        parse_platform_endpoint("unix://relative.sock")


def test_resolve_service_endpoint_uses_service_specific_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMP_SECRETS_URL", "unix:///tmp/secrets.sock")
    config = PlatformConfig(base_url="http://platform:8080")

    endpoint = resolve_service_endpoint("secrets", config)

    assert endpoint.transport == "uds"
    assert endpoint.socket_path == Path("/tmp/secrets.sock")


def test_resolve_service_endpoint_falls_back_to_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NMP_SECRETS_URL", raising=False)
    config = PlatformConfig(base_url="http://platform:8080")

    endpoint = resolve_service_endpoint("secrets", config)

    assert endpoint.transport == "tcp"
    assert endpoint.connect_base_url == "http://platform:8080"


def test_endpoint_env_family_is_not_part_of_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMP_SECRETS_ENDPOINT", "unix:///tmp/secrets.sock")
    monkeypatch.delenv("NMP_SECRETS_URL", raising=False)
    config = PlatformConfig(base_url="http://platform:8080")

    endpoint = resolve_service_endpoint("secrets", config)

    assert endpoint.transport == "tcp"
    assert endpoint.connect_base_url == "http://platform:8080"


@pytest.fixture
def platform_config_with_service_discovery() -> PlatformConfig:
    return PlatformConfig(  # type: ignore[abstract]
        base_url="http://platform:8080",
        service_discovery={
            "entities": "http://entities-service:8080",
            "jobs": "http://jobs-service:8080",
        },
    )


def test_resolve_platform_endpoint_carries_service_routes(
    platform_config_with_service_discovery: PlatformConfig,
) -> None:
    endpoint = resolve_platform_endpoint(platform_config_with_service_discovery)

    assert endpoint.connect_base_url == "http://platform:8080"
    assert endpoint.service_endpoints["entities"].connect_base_url == "http://entities-service:8080"
    assert endpoint.service_endpoints["jobs"].connect_base_url == "http://jobs-service:8080"


def test_resolve_platform_endpoint_rejects_malformed_service_route() -> None:
    config = PlatformConfig(  # type: ignore[abstract]
        base_url="http://platform:8080",
        service_discovery={
            "entities": "http://entities-service:8080",
            "jobs": "not-a-url",
        },
    )

    with pytest.raises(ValueError, match="Unsupported platform endpoint URL 'not-a-url'"):
        resolve_platform_endpoint(config)


def test_resolve_platform_endpoint_rejects_malformed_base_url() -> None:
    config = PlatformConfig(  # type: ignore[abstract]
        base_url="not-a-url",
        service_discovery={"entities": "http://entities-service:8080"},
    )

    with pytest.raises(ValueError, match="Unsupported platform endpoint URL 'not-a-url'"):
        resolve_platform_endpoint(config)


def test_platform_endpoint_routes_api_path_to_service_url(
    platform_config_with_service_discovery: PlatformConfig,
) -> None:
    endpoint = resolve_platform_endpoint(platform_config_with_service_discovery)

    routed = endpoint.route_request_url("http://platform:8080/apis/entities/v2/workspaces?limit=10")

    assert routed.endpoint.connect_base_url == "http://entities-service:8080"
    assert routed.url.scheme == "http"
    assert routed.url.host == "entities-service"
    assert routed.url.port == 8080
    assert routed.url.path == "/apis/entities/v2/workspaces"
    assert routed.url.query == b"limit=10"


def test_platform_endpoint_preserves_service_url_path_prefix() -> None:
    config = PlatformConfig(  # type: ignore[abstract]
        base_url="http://platform:8080",
        service_discovery={"entities": "http://entities-service:8080/entities-prefix"},
    )
    endpoint = resolve_platform_endpoint(config)

    routed = endpoint.route_request_url("http://platform:8080/apis/entities/v2/workspaces?limit=10")

    assert routed.endpoint.connect_base_url == "http://entities-service:8080/entities-prefix"
    assert routed.url.scheme == "http"
    assert routed.url.host == "entities-service"
    assert routed.url.port == 8080
    assert routed.url.path == "/entities-prefix/apis/entities/v2/workspaces"
    assert routed.url.query == b"limit=10"


def test_platform_endpoint_uses_env_override(
    monkeypatch: pytest.MonkeyPatch,
    platform_config_with_service_discovery: PlatformConfig,
) -> None:
    monkeypatch.setenv("NMP_ENTITIES_URL", "http://entities-env:9090")
    endpoint = resolve_platform_endpoint(platform_config_with_service_discovery)

    routed = endpoint.route_request_url("http://platform:8080/apis/entities/v2/workspaces")

    assert routed.endpoint.connect_base_url == "http://entities-env:9090"
    assert routed.url.host == "entities-env"
    assert routed.url.port == 9090


def test_platform_endpoint_uses_matching_env_route_without_mutating_config(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PlatformConfig(base_url="http://platform:8080")  # type: ignore[abstract]
    monkeypatch.setenv("NMP_ENTITIES_URL", "http://entities-env:9090")

    endpoint = resolve_platform_endpoint(config)
    routed = endpoint.route_request_url("http://platform:8080/apis/entities/v2/workspaces")

    assert "entities" not in endpoint.service_endpoints
    assert "entities" not in config.service_discovery
    assert routed.endpoint.connect_base_url == "http://platform:8080"
    assert routed.url.host == "platform"


def test_platform_endpoint_keeps_configured_local_service_on_local_url(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PlatformConfig(base_url="http://platform:8080", services="hello-world")  # type: ignore[abstract]
    monkeypatch.setenv("NMP_HELLO_WORLD_URL", "http://hello-world-service:8080")
    endpoint = resolve_platform_endpoint(config)

    routed = endpoint.route_request_url("http://platform:8080/apis/hello-world/v2/workspaces/default/hello")

    assert routed.endpoint.connect_base_url == get_common_service_config().get_host_url()
    assert routed.url.host == "127.0.0.1"


def test_platform_endpoint_ignores_unknown_service_url_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    config = PlatformConfig(base_url="http://platform:8080")  # type: ignore[abstract]
    monkeypatch.setenv("NMP_NOT_A_SERVICE_URL", "http://not-a-service:8080")

    endpoint = resolve_platform_endpoint(config)
    routed = endpoint.route_request_url("http://platform:8080/apis/entities/v2/workspaces/default")

    assert "not-a-service" not in endpoint.service_endpoints
    assert routed.endpoint.connect_base_url == "http://platform:8080"
    assert routed.url.host == "platform"


def test_platform_endpoint_routes_uds_service() -> None:
    config = PlatformConfig(  # type: ignore[abstract]
        base_url="http://platform:8080",
        service_discovery={"entities": "unix:///tmp/entities.sock"},
    )
    endpoint = resolve_platform_endpoint(config)

    routed = endpoint.route_request_url("http://platform:8080/apis/entities/v2/workspaces")

    assert routed.endpoint.transport == "uds"
    assert routed.endpoint.socket_path == Path("/tmp/entities.sock")
    assert str(routed.url) == "http://nemo-platform.local/apis/entities/v2/workspaces"


def test_platform_endpoint_keeps_non_api_path_on_default_endpoint(
    platform_config_with_service_discovery: PlatformConfig,
) -> None:
    endpoint = resolve_platform_endpoint(platform_config_with_service_discovery)

    routed = endpoint.route_request_url("http://platform:8080/health/ready")

    assert routed.endpoint.connect_base_url == "http://platform:8080"
    assert str(routed.url) == "http://platform:8080/health/ready"


def test_platform_endpoint_keeps_non_api_service_url(
    platform_config_with_service_discovery: PlatformConfig,
) -> None:
    endpoint = resolve_platform_endpoint(platform_config_with_service_discovery)

    routed = endpoint.route_request_url("http://entities-service:8080/status")

    assert routed.endpoint.connect_base_url == "http://platform:8080"
    assert str(routed.url) == "http://entities-service:8080/status"


def test_platform_endpoint_logs_path_without_raw_url(
    caplog: pytest.LogCaptureFixture,
    platform_config_with_service_discovery: PlatformConfig,
) -> None:
    caplog.set_level(logging.DEBUG, logger="nmp.common.platform_endpoint")
    endpoint = resolve_platform_endpoint(platform_config_with_service_discovery)

    endpoint.route_request_url("http://platform:8080/health/ready?token=secret")
    endpoint.route_request_url("http://platform:8080/apis/entities/v2/workspaces?token=secret")

    default_record = next(
        record for record in caplog.records if record.message == "Routing SDK URL to default endpoint"
    )
    service_record = next(
        record for record in caplog.records if record.message == "Routing SDK URL to service endpoint"
    )

    assert not hasattr(default_record, "url")
    assert getattr(default_record, "service") == "unknown"
    assert getattr(default_record, "path") == "/health/ready"

    assert not hasattr(service_record, "url")
    assert getattr(service_record, "service") == "entities"
    assert getattr(service_record, "path") == "/apis/entities/v2/workspaces"
    assert getattr(service_record, "host") == "entities-service"
    assert getattr(service_record, "port") == 8080

    for record in (default_record, service_record):
        assert "token=secret" not in str(record.__dict__)


def test_sync_http_client_omits_unset_timeout() -> None:
    endpoint = parse_platform_endpoint("http://127.0.0.1:8080")

    with patch("nmp.common.platform_endpoint.httpx.Client") as client:
        endpoint.sync_http_client()

    client.assert_called_once_with(follow_redirects=True)


def test_sync_http_client_passes_explicit_timeout() -> None:
    endpoint = parse_platform_endpoint("http://127.0.0.1:8080")

    with patch("nmp.common.platform_endpoint.httpx.Client") as client:
        endpoint.sync_http_client(timeout=2.0)

    client.assert_called_once_with(follow_redirects=True, timeout=2.0)


def test_sync_sdk_http_client_uses_sdk_default_for_tcp() -> None:
    endpoint = parse_platform_endpoint("http://127.0.0.1:8080")

    with patch("nmp.common.platform_endpoint.ImmutableDefaultHttpxClient") as client:
        endpoint.sync_sdk_http_client()

    client.assert_called_once_with()


def test_sync_sdk_http_client_passes_explicit_timeout() -> None:
    endpoint = parse_platform_endpoint("http://127.0.0.1:8080")

    with patch("nmp.common.platform_endpoint.ImmutableDefaultHttpxClient") as client:
        endpoint.sync_sdk_http_client(timeout=2.0)

    client.assert_called_once_with(timeout=2.0)


def test_uds_sync_http_client_keeps_transport_and_omits_unset_timeout() -> None:
    endpoint = parse_platform_endpoint("unix:///tmp/nemo-platform.sock")

    with patch("nmp.common.platform_endpoint.httpx.Client") as client:
        endpoint.sync_http_client()

    kwargs = client.call_args.kwargs
    assert kwargs["follow_redirects"] is True
    assert "transport" in kwargs
    assert "timeout" not in kwargs


def test_uds_sync_sdk_http_client_keeps_transport_and_omits_unset_timeout() -> None:
    endpoint = parse_platform_endpoint("unix:///tmp/nemo-platform.sock")

    with (
        patch("nmp.common.platform_endpoint.ImmutableDefaultHttpxClient") as sdk_client,
        patch("nmp.common.platform_endpoint.ImmutableHttpxClient") as client,
    ):
        endpoint.sync_sdk_http_client()

    sdk_client.assert_not_called()
    kwargs = client.call_args.kwargs
    assert kwargs["follow_redirects"] is True
    assert "transport" in kwargs
    assert "timeout" not in kwargs


def test_sync_routing_transport_prebuilds_uds_service_transports() -> None:
    service_endpoint = parse_platform_endpoint("unix:///tmp/entities.sock")
    constructed_transports: list[object] = []
    closed_transports: list[object] = []

    class FakeHTTPTransport:
        def __init__(self, *, uds: str | None = None) -> None:
            self.uds = uds
            if uds is not None:
                constructed_transports.append(self)

        def close(self) -> None:
            if self.uds is not None:
                closed_transports.append(self)

    with patch("nmp.common.platform_endpoint.httpx.HTTPTransport", FakeHTTPTransport):
        routing_transport = _SyncPlatformEndpointRoutingTransport(
            endpoint=PlatformEndpoint(
                connect_base_url="http://platform:8080",
                socket_path=None,
                transport="tcp",
                service_endpoints={"entities": service_endpoint},
            )
        )
        returned_transport = routing_transport._transport_for_endpoint(service_endpoint)

    routing_transport.close()

    assert len(constructed_transports) == 1
    assert returned_transport is constructed_transports[0]
    assert closed_transports == constructed_transports


def test_sync_routing_transport_preserves_non_api_service_status_url(
    platform_config_with_service_discovery: PlatformConfig,
) -> None:
    captured_urls: list[str] = []

    class FakeHTTPTransport:
        def __init__(self, **kwargs) -> None:
            pass

        def handle_request(self, request) -> httpx.Response:
            captured_urls.append(str(request.url))
            return httpx.Response(200, request=request)

        def close(self) -> None:
            pass

    endpoint = resolve_platform_endpoint(platform_config_with_service_discovery)
    with patch("nmp.common.platform_endpoint.httpx.HTTPTransport", FakeHTTPTransport):
        routing_transport = _SyncPlatformEndpointRoutingTransport(endpoint=endpoint)
        request = httpx.Request("GET", "http://entities-service:8080/status")
        routing_transport.handle_request(request)

    assert captured_urls == ["http://entities-service:8080/status"]


def test_routing_transports_pass_custom_ca_to_tcp_transport(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cert_file = tmp_path / "ca.pem"
    cert_file.write_text("certificate", encoding="utf-8")
    monkeypatch.setenv("NMP_CLIENT_SSL_CERT_FILE", str(cert_file))
    sync_kwargs: list[dict] = []
    async_kwargs: list[dict] = []

    class FakeHTTPTransport:
        def __init__(self, **kwargs) -> None:
            sync_kwargs.append(kwargs)

        def close(self) -> None:
            pass

    class FakeAsyncHTTPTransport:
        def __init__(self, **kwargs) -> None:
            async_kwargs.append(kwargs)

        async def aclose(self) -> None:
            pass

    endpoint = resolve_platform_endpoint(
        PlatformConfig(
            base_url="https://platform:8443",
            service_discovery={"entities": "https://entities-service:9443"},
        )
    )
    with (
        patch("nmp.common.platform_endpoint.httpx.HTTPTransport", FakeHTTPTransport),
        patch("nmp.common.platform_endpoint.httpx.AsyncHTTPTransport", FakeAsyncHTTPTransport),
    ):
        _SyncPlatformEndpointRoutingTransport(endpoint=endpoint)
        _AsyncPlatformEndpointRoutingTransport(endpoint=endpoint)

    assert sync_kwargs[0] == {"verify": str(cert_file)}
    assert async_kwargs[0] == {"verify": str(cert_file)}


def test_async_http_client_omits_unset_timeout() -> None:
    endpoint = parse_platform_endpoint("http://127.0.0.1:8080")

    with patch("nmp.common.platform_endpoint.httpx.AsyncClient") as client:
        endpoint.async_http_client()

    client.assert_called_once_with(follow_redirects=True)


def test_async_http_client_passes_explicit_timeout() -> None:
    endpoint = parse_platform_endpoint("http://127.0.0.1:8080")

    with patch("nmp.common.platform_endpoint.httpx.AsyncClient") as client:
        endpoint.async_http_client(timeout=2.0)

    client.assert_called_once_with(follow_redirects=True, timeout=2.0)


def test_async_sdk_http_client_uses_sdk_default_for_tcp() -> None:
    endpoint = parse_platform_endpoint("http://127.0.0.1:8080")

    with patch("nmp.common.platform_endpoint.ImmutableDefaultAsyncHttpxClient") as client:
        endpoint.async_sdk_http_client()

    client.assert_called_once_with()


def test_async_sdk_http_client_passes_explicit_timeout() -> None:
    endpoint = parse_platform_endpoint("http://127.0.0.1:8080")

    with patch("nmp.common.platform_endpoint.ImmutableDefaultAsyncHttpxClient") as client:
        endpoint.async_sdk_http_client(timeout=2.0)

    client.assert_called_once_with(timeout=2.0)


def test_uds_async_http_client_keeps_transport_and_omits_unset_timeout() -> None:
    endpoint = parse_platform_endpoint("unix:///tmp/nemo-platform.sock")

    with patch("nmp.common.platform_endpoint.httpx.AsyncClient") as client:
        endpoint.async_http_client()

    kwargs = client.call_args.kwargs
    assert kwargs["follow_redirects"] is True
    assert "transport" in kwargs
    assert "timeout" not in kwargs


def test_uds_async_sdk_http_client_keeps_transport_and_omits_unset_timeout() -> None:
    endpoint = parse_platform_endpoint("unix:///tmp/nemo-platform.sock")

    with (
        patch("nmp.common.platform_endpoint.ImmutableDefaultAsyncHttpxClient") as sdk_client,
        patch("nmp.common.platform_endpoint.ImmutableAsyncHttpxClient") as client,
    ):
        endpoint.async_sdk_http_client()

    sdk_client.assert_not_called()
    kwargs = client.call_args.kwargs
    assert kwargs["follow_redirects"] is True
    assert "transport" in kwargs
    assert "timeout" not in kwargs
