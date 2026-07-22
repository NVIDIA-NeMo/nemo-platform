# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed platform endpoint resolution for HTTP(S) and Unix domain sockets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
from httpx._types import TimeoutTypes
from nmp.common.config import PlatformConfig

UDS_BASE_URL = "http://nemo-platform.local"


@dataclass(frozen=True)
class PlatformEndpoint:
    connect_base_url: str
    socket_path: Path | None
    transport: Literal["tcp", "uds"]

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


def resolve_platform_endpoint(platform_config: PlatformConfig | None = None) -> PlatformEndpoint:
    """Resolve the default platform endpoint from ``NMP_BASE_URL`` / config."""

    if platform_config is None:
        from nmp.common.config import Configuration

        platform_config = Configuration.get_platform_config()
    return parse_platform_endpoint(platform_config.base_url)


def resolve_service_endpoint(service_name: str, platform_config: PlatformConfig | None = None) -> PlatformEndpoint:
    """Resolve a service endpoint using ``NMP_<SERVICE>_URL`` before ``NMP_BASE_URL``."""

    if platform_config is None:
        from nmp.common.config import Configuration

        platform_config = Configuration.get_platform_config()
    env_name = f"NMP_{service_name.upper().replace('-', '_')}_URL"
    endpoint = os.environ.get(env_name) or platform_config.get_service_url(service_name)
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
