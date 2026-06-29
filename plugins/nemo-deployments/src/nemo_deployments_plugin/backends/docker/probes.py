# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Readiness probe evaluation for running containers."""

from __future__ import annotations

import asyncio
import logging
import socket
from urllib.parse import urljoin, urlparse

import httpx
from docker.models.containers import Container as DockerContainer
from nemo_deployments_plugin.entities import Probe

logger = logging.getLogger(__name__)


async def check_readiness_probe(
    *,
    container: DockerContainer,
    probe: Probe | None,
    host_url: str | None,
    host_ports: dict[int, int] | None = None,
    named_ports: dict[str, int] | None = None,
) -> tuple[bool, str]:
    """Return (ready, reason). When no probe is configured, running implies ready."""
    if probe is None:
        return True, "no readiness probe configured"

    if probe.exec_action is not None and probe.exec_action.command:
        return await _check_exec_probe(container, probe)

    if probe.http_get is not None:
        if host_url is None:
            return False, "http probe requires a mapped host port — no host_url available"
        return await _check_http_probe(host_url, probe, host_ports=host_ports, named_ports=named_ports)

    if probe.tcp_socket is not None:
        if host_url is None:
            return False, "tcp probe requires a mapped host port — no host_url available"
        return await _check_tcp_probe(host_url, probe, host_ports=host_ports, named_ports=named_ports)

    return True, "probe type not implemented; treating as ready"


async def _check_exec_probe(container: DockerContainer, probe: Probe) -> tuple[bool, str]:
    assert probe.exec_action is not None
    command = probe.exec_action.command
    timeout = probe.timeout_seconds

    def _run() -> tuple[int, str]:
        result = container.exec_run(command, demux=True)
        exit_code = result.exit_code if result.exit_code is not None else 1
        output = ""
        if result.output:
            stdout, stderr = result.output
            chunks = []
            if stdout and isinstance(stdout, bytes):
                chunks.append(stdout.decode("utf-8", errors="ignore"))
            if stderr and isinstance(stderr, bytes):
                chunks.append(stderr.decode("utf-8", errors="ignore"))
            output = "".join(chunks)
        return exit_code, output

    try:
        exit_code, output = await asyncio.wait_for(asyncio.to_thread(_run), timeout=timeout)
    except TimeoutError:
        return False, f"exec probe timed out after {timeout}s"
    except Exception as exc:
        return False, f"exec probe failed: {exc}"

    if exit_code == 0:
        return True, "exec probe succeeded"
    return False, f"exec probe exit {exit_code}: {output[:200]}"


def _probe_host(host_url: str) -> str:
    return urlparse(host_url).hostname or "127.0.0.1"


def _resolve_probe_port(
    port: int | str,
    *,
    host_ports: dict[int, int] | None,
    named_ports: dict[str, int] | None,
) -> int | None:
    if isinstance(port, int):
        return host_ports.get(port, port) if host_ports else port
    if named_ports and port in named_ports:
        return named_ports[port]
    if host_ports:
        for container_port, host_port in host_ports.items():
            if str(container_port) == port:
                return host_port
    return None


async def _check_http_probe(
    host_url: str,
    probe: Probe,
    *,
    host_ports: dict[int, int] | None = None,
    named_ports: dict[str, int] | None = None,
) -> tuple[bool, str]:
    assert probe.http_get is not None
    port = probe.http_get.port
    path = probe.http_get.path
    scheme = probe.http_get.scheme.lower()
    host = _probe_host(host_url)
    resolved_port = _resolve_probe_port(port, host_ports=host_ports, named_ports=named_ports)
    if resolved_port is None:
        return False, f"http probe port not mapped: {port}"
    base = f"{scheme}://{host}:{resolved_port}"
    url = urljoin(f"{base.rstrip('/')}/", path.lstrip("/"))
    timeout = probe.timeout_seconds
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
        if 200 <= response.status_code < 400:
            return True, f"http probe {response.status_code}"
        return False, f"http probe status {response.status_code}"
    except Exception as exc:
        return False, f"http probe failed: {exc}"


async def _check_tcp_probe(
    host_url: str,
    probe: Probe,
    *,
    host_ports: dict[int, int] | None = None,
    named_ports: dict[str, int] | None = None,
) -> tuple[bool, str]:
    assert probe.tcp_socket is not None
    port_value = probe.tcp_socket.port
    host = _probe_host(host_url)
    target_port = _resolve_probe_port(port_value, host_ports=host_ports, named_ports=named_ports)
    if target_port is None:
        return False, f"tcp probe port not mapped: {port_value}"
    timeout = probe.timeout_seconds

    def _connect() -> None:
        with socket.create_connection((host, target_port)):
            return

    try:
        await asyncio.wait_for(asyncio.to_thread(_connect), timeout=timeout)
        return True, "tcp probe connected"
    except Exception as exc:
        return False, f"tcp probe failed: {exc}"


def host_url_for_port(host: str, host_port: int, *, scheme: str = "http") -> str:
    return f"{scheme}://{host}:{host_port}"
