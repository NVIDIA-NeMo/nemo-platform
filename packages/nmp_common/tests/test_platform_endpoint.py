# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from unittest.mock import patch

import pytest
from nmp.common.config import PlatformConfig
from nmp.common.platform_endpoint import UDS_BASE_URL, parse_platform_endpoint, resolve_service_endpoint


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


def test_uds_sync_http_client_keeps_transport_and_omits_unset_timeout() -> None:
    endpoint = parse_platform_endpoint("unix:///tmp/nemo-platform.sock")

    with patch("nmp.common.platform_endpoint.httpx.Client") as client:
        endpoint.sync_http_client()

    kwargs = client.call_args.kwargs
    assert kwargs["follow_redirects"] is True
    assert "transport" in kwargs
    assert "timeout" not in kwargs


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


def test_uds_async_http_client_keeps_transport_and_omits_unset_timeout() -> None:
    endpoint = parse_platform_endpoint("unix:///tmp/nemo-platform.sock")

    with patch("nmp.common.platform_endpoint.httpx.AsyncClient") as client:
        endpoint.async_http_client()

    kwargs = client.call_args.kwargs
    assert kwargs["follow_redirects"] is True
    assert "transport" in kwargs
    assert "timeout" not in kwargs
