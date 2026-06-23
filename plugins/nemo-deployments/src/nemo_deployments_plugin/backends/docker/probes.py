# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Readiness probe evaluation for running containers."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import httpx
from nemo_deployments_plugin.entities import Probe

if TYPE_CHECKING:
    from docker.models.containers import Container as DockerContainer

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

    if probe.http_get is not None and host_url is not None:
        return await _check_http_probe(host_url, probe, host_ports=host_ports, named_ports=named_ports)

    if probe.tcp_socket is not None and host_url is not None:
        return await _check_tcp_probe(host_url, probe)

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
            if stdout:
                chunks.append(stdout.decode("utf-8", errors="ignore"))
            if stderr:
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
    base = host_url
    if isinstance(port, int):
        base = f"{scheme}://127.0.0.1:{port}"
    elif isinstance(port, str) and named_ports and port in named_ports:
        base = f"{scheme}://127.0.0.1:{named_ports[port]}"
    elif isinstance(port, str) and host_ports:
        for container_port, host_port in host_ports.items():
            if str(container_port) == port:
                base = f"{scheme}://127.0.0.1:{host_port}"
                break
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


async def _check_tcp_probe(host_url: str, probe: Probe) -> tuple[bool, str]:
    assert probe.tcp_socket is not None
    port_value = probe.tcp_socket.port
    if not isinstance(port_value, int):
        return False, "tcp probe requires numeric port"
    host = "127.0.0.1"
    timeout = probe.timeout_seconds

    def _connect() -> None:
        with socket.create_connection((host, port_value), timeout=timeout):
            return

    try:
        await asyncio.wait_for(asyncio.to_thread(_connect), timeout=timeout)
        return True, "tcp probe connected"
    except Exception as exc:
        return False, f"tcp probe failed: {exc}"


def host_url_for_port(host: str, host_port: int, *, scheme: str = "http") -> str:
    return f"{scheme}://{host}:{host_port}"
