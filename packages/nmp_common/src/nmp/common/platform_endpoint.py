# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed platform endpoint resolution for HTTP(S) and Unix domain sockets."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal

import httpx
from httpx._types import TimeoutTypes
from nemo_platform_plugin.client.tls import client_verify_from_env
from nmp.common.config import Configuration, PlatformConfig
from nmp.common.immutable_http_client import (
    ImmutableAsyncHttpxClient,
    ImmutableDefaultAsyncHttpxClient,
    ImmutableDefaultHttpxClient,
    ImmutableHttpxClient,
)

UDS_BASE_URL = "http://nemo-platform.local"
logger = logging.getLogger(__name__)


def _empty_service_endpoints() -> Mapping[str, "PlatformEndpoint"]:
    return MappingProxyType({})


def _get_platform_config() -> PlatformConfig:
    platform_config = Configuration.get_platform_config()
    if not isinstance(platform_config, PlatformConfig):
        raise TypeError("Expected PlatformConfig from Configuration.get_platform_config()")
    return platform_config


@dataclass(frozen=True)
class PlatformEndpoint:
    connect_base_url: str
    socket_path: Path | None
    transport: Literal["tcp", "uds"]
    service_pattern: re.Pattern[str] | None = field(default=None, repr=False, compare=False)
    service_endpoints: Mapping[str, "PlatformEndpoint"] = field(
        default_factory=_empty_service_endpoints,
        repr=False,
        compare=False,
    )

    def sync_http_client(self, *, timeout: TimeoutTypes | None = None) -> httpx.Client:
        if self.transport == "uds":
            if self.socket_path is None:
                raise ValueError("UDS endpoint is missing a socket path")
            transport = httpx.HTTPTransport(uds=str(self.socket_path))
            if timeout is None:
                return httpx.Client(transport=transport, follow_redirects=True)
            return httpx.Client(transport=transport, follow_redirects=True, timeout=timeout)
        if timeout is None:
            return httpx.Client(follow_redirects=True)
        return httpx.Client(follow_redirects=True, timeout=timeout)

    def async_http_client(self, *, timeout: TimeoutTypes | None = None) -> httpx.AsyncClient:
        if self.transport == "uds":
            if self.socket_path is None:
                raise ValueError("UDS endpoint is missing a socket path")
            transport = httpx.AsyncHTTPTransport(uds=str(self.socket_path))
            if timeout is None:
                return httpx.AsyncClient(transport=transport, follow_redirects=True)
            return httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=timeout)
        if timeout is None:
            return httpx.AsyncClient(follow_redirects=True)
        return httpx.AsyncClient(follow_redirects=True, timeout=timeout)

    def sync_sdk_http_client(self, *, timeout: TimeoutTypes | None = None) -> httpx.Client:
        if self.service_endpoints:
            transport = _SyncPlatformEndpointRoutingTransport(endpoint=self)
            if timeout is None:
                return ImmutableDefaultHttpxClient(transport=transport)
            return ImmutableDefaultHttpxClient(transport=transport, timeout=timeout)
        if self.transport == "uds":
            if self.socket_path is None:
                raise ValueError("UDS endpoint is missing a socket path")
            transport = httpx.HTTPTransport(uds=str(self.socket_path))
            if timeout is None:
                return ImmutableHttpxClient(transport=transport, follow_redirects=True)
            return ImmutableHttpxClient(transport=transport, follow_redirects=True, timeout=timeout)
        if timeout is None:
            return ImmutableDefaultHttpxClient()
        return ImmutableDefaultHttpxClient(timeout=timeout)

    def async_sdk_http_client(self, *, timeout: TimeoutTypes | None = None) -> httpx.AsyncClient:
        if self.service_endpoints:
            transport = _AsyncPlatformEndpointRoutingTransport(endpoint=self)
            if timeout is None:
                return ImmutableDefaultAsyncHttpxClient(transport=transport)
            return ImmutableDefaultAsyncHttpxClient(transport=transport, timeout=timeout)
        if self.transport == "uds":
            if self.socket_path is None:
                raise ValueError("UDS endpoint is missing a socket path")
            transport = httpx.AsyncHTTPTransport(uds=str(self.socket_path))
            if timeout is None:
                return ImmutableAsyncHttpxClient(transport=transport, follow_redirects=True)
            return ImmutableAsyncHttpxClient(transport=transport, follow_redirects=True, timeout=timeout)
        if timeout is None:
            return ImmutableDefaultAsyncHttpxClient()
        return ImmutableDefaultAsyncHttpxClient(timeout=timeout)

    def route_request_url(self, url: str | httpx.URL) -> "RoutedPlatformEndpointRequest":
        """Resolve one outgoing SDK URL using this endpoint's fixed routing table."""

        request_url = httpx.URL(url)
        endpoint = self
        service_name = "unknown"

        match = self.service_pattern.search(request_url.path) if self.service_pattern is not None else None
        if match is not None:
            service_name = match.group(1)
            endpoint = self.service_endpoints.get(service_name) or self
            routed_url = _url_for_endpoint(request_url, endpoint)
        else:
            routed_url = request_url

        logger.debug(
            "Routing SDK URL to service endpoint"
            if service_name != "unknown"
            else "Routing SDK URL to default endpoint",
            extra={
                "service": service_name,
                "path": request_url.path,
                "host": routed_url.host,
                "port": routed_url.port,
                "transport": endpoint.transport,
            },
        )
        return RoutedPlatformEndpointRequest(url=routed_url, endpoint=endpoint)


@dataclass(frozen=True)
class RoutedPlatformEndpointRequest:
    url: httpx.URL
    endpoint: PlatformEndpoint


def resolve_platform_endpoint(platform_config: PlatformConfig | None = None) -> PlatformEndpoint:
    """Resolve the default platform endpoint from ``NMP_BASE_URL`` / config."""

    if platform_config is None:
        platform_config = _get_platform_config()
    default_endpoint = parse_platform_endpoint(platform_config.base_url)
    service_endpoints = {
        service_name: resolve_service_endpoint(service_name, platform_config)
        for service_name in sorted(_service_route_names(platform_config, os.environ))
    }
    return PlatformEndpoint(
        connect_base_url=default_endpoint.connect_base_url,
        socket_path=default_endpoint.socket_path,
        transport=default_endpoint.transport,
        service_pattern=platform_config.create_service_pattern(),
        service_endpoints=MappingProxyType(service_endpoints),
    )


def resolve_service_endpoint(service_name: str, platform_config: PlatformConfig | None = None) -> PlatformEndpoint:
    """Resolve a service endpoint using ``NMP_<SERVICE>_URL`` before ``NMP_BASE_URL``."""

    if platform_config is None:
        platform_config = _get_platform_config()
    normalized_name = _normalize_service_name(service_name)
    if normalized_name in {_normalize_service_name(local) for local in platform_config.get_services()}:
        return parse_platform_endpoint(platform_config.get_service_url(normalized_name))
    env_name = _service_url_env_var_name(service_name)
    endpoint = os.environ.get(env_name) or platform_config.get_service_url(normalized_name)
    return parse_platform_endpoint(endpoint)


def parse_platform_endpoint(endpoint: str) -> PlatformEndpoint:
    """Parse an HTTP(S) or ``unix://`` endpoint into a typed transport model."""

    if endpoint.startswith(("http://", "https://")):
        try:
            parsed = httpx.URL(endpoint)
        except httpx.InvalidURL as error:
            raise ValueError(f"Invalid platform endpoint URL {endpoint!r}") from error
        if not parsed.host:
            raise ValueError(f"HTTP(S) platform endpoint must include a host, got {endpoint!r}")
        return PlatformEndpoint(connect_base_url=endpoint.rstrip("/"), socket_path=None, transport="tcp")
    if endpoint.startswith("unix://"):
        socket_path = _parse_unix_socket_path(endpoint)
        return PlatformEndpoint(connect_base_url=UDS_BASE_URL, socket_path=socket_path, transport="uds")
    if endpoint.startswith("/"):
        raise ValueError(f"Raw socket paths are not valid endpoint URLs; use unix://{endpoint}")
    raise ValueError(f"Unsupported platform endpoint URL {endpoint!r}; expected http://, https://, or unix://")


def _parse_unix_socket_path(endpoint: str) -> Path:
    raw_path = endpoint.removeprefix("unix://")
    if not raw_path.startswith("/"):
        raise ValueError(f"UDS endpoint must use an absolute socket path, got {endpoint!r}")
    return Path(raw_path)


def _service_route_names(platform_config: PlatformConfig, env: Mapping[str, str]) -> set[str]:
    names = {_normalize_service_name(service_name) for service_name in platform_config.service_discovery}
    names.update(_normalize_service_name(service_name) for service_name in platform_config.get_services())
    names.update(_service_route_names_from_env(env))
    names.discard("")
    return names


def _service_route_names_from_env(env: Mapping[str, str]) -> set[str]:
    names: set[str] = set()
    for env_name in env:
        if not env_name.startswith("NMP_") or not env_name.endswith("_URL"):
            continue
        raw_service_name = env_name.removeprefix("NMP_").removesuffix("_URL")
        if raw_service_name == "BASE":
            continue
        names.add(_normalize_service_name(raw_service_name))
    return names


def _service_url_env_var_name(service_name: str) -> str:
    return f"NMP_{_normalize_service_name(service_name).upper().replace('-', '_')}_URL"


def _normalize_service_name(service_name: str) -> str:
    return service_name.strip().lower().replace("_", "-")


def _url_for_endpoint(url: httpx.URL, endpoint: PlatformEndpoint) -> httpx.URL:
    if endpoint.transport == "uds":
        return url.copy_with(scheme="http", host=httpx.URL(UDS_BASE_URL).host, port=None)
    endpoint_url = httpx.URL(endpoint.connect_base_url)
    return url.copy_with(scheme=endpoint_url.scheme, host=endpoint_url.host, port=endpoint_url.port)


def _set_request_url(request: httpx.Request, url: httpx.URL) -> None:
    if request.url == url:
        return
    request.url = url
    if url.host:
        request.headers["Host"] = url.netloc.decode("ascii")


def _uds_socket_paths(endpoint: PlatformEndpoint) -> frozenset[Path]:
    paths: set[Path] = set()
    for candidate in (endpoint, *endpoint.service_endpoints.values()):
        if candidate.transport != "uds":
            continue
        if candidate.socket_path is None:
            raise ValueError("UDS endpoint is missing a socket path")
        paths.add(candidate.socket_path)
    return frozenset(paths)


class _SyncPlatformEndpointRoutingTransport(httpx.BaseTransport):
    def __init__(self, *, endpoint: PlatformEndpoint) -> None:
        self._endpoint = endpoint
        verify = client_verify_from_env()
        self._tcp_transport = httpx.HTTPTransport() if verify is True else httpx.HTTPTransport(verify=verify)
        self._uds_transports = {
            socket_path: httpx.HTTPTransport(uds=str(socket_path)) for socket_path in _uds_socket_paths(endpoint)
        }

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        routed = self._endpoint.route_request_url(request.url)
        _set_request_url(request, routed.url)
        return self._transport_for_endpoint(routed.endpoint).handle_request(request)

    def close(self) -> None:
        self._tcp_transport.close()
        for transport in self._uds_transports.values():
            transport.close()

    def _transport_for_endpoint(self, endpoint: PlatformEndpoint) -> httpx.HTTPTransport:
        if endpoint.transport == "tcp":
            return self._tcp_transport
        if endpoint.socket_path is None:
            raise ValueError("UDS endpoint is missing a socket path")
        return self._uds_transports[endpoint.socket_path]


class _AsyncPlatformEndpointRoutingTransport(httpx.AsyncBaseTransport):
    def __init__(self, *, endpoint: PlatformEndpoint) -> None:
        self._endpoint = endpoint
        verify = client_verify_from_env()
        self._tcp_transport = httpx.AsyncHTTPTransport() if verify is True else httpx.AsyncHTTPTransport(verify=verify)
        self._uds_transports = {
            socket_path: httpx.AsyncHTTPTransport(uds=str(socket_path)) for socket_path in _uds_socket_paths(endpoint)
        }

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        routed = self._endpoint.route_request_url(request.url)
        _set_request_url(request, routed.url)
        return await self._transport_for_endpoint(routed.endpoint).handle_async_request(request)

    async def aclose(self) -> None:
        await self._tcp_transport.aclose()
        for transport in self._uds_transports.values():
            await transport.aclose()

    def _transport_for_endpoint(self, endpoint: PlatformEndpoint) -> httpx.AsyncHTTPTransport:
        if endpoint.transport == "tcp":
            return self._tcp_transport
        if endpoint.socket_path is None:
            raise ValueError("UDS endpoint is missing a socket path")
        return self._uds_transports[endpoint.socket_path]
