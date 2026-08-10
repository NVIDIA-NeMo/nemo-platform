# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Host port allocation for published container ports."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from typing import TYPE_CHECKING

import docker

if TYPE_CHECKING:
    from docker.models.containers import Container as DockerContainer

logger = logging.getLogger(__name__)


class PortEnumerationError(RuntimeError):
    """Raised when the set of ports currently in use could not be determined.

    Distinct from an exhausted range: here we don't know what is free, so the caller must not
    report the range as full (the previous behaviour, which sent operators looking at
    ``port_range_*`` config for what is usually a transient daemon-query failure).
    """


def is_remote_docker_host() -> bool:
    docker_host = os.environ.get("DOCKER_HOST", "")
    return docker_host.startswith("tcp://")


def is_port_free(port: int) -> bool:
    if is_remote_docker_host():
        return True
    try:
        # Do not set SO_REUSEADDR: it can make this bind succeed while a Docker
        # wildcard publisher already holds the port. Binding loopback is enough
        # to detect that conflict without exposing a socket on external interfaces.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


def collect_used_host_ports(containers: list[DockerContainer]) -> set[int]:
    used: set[int] = set()
    for container in containers:
        try:
            ports = container.ports or {}
            for bindings in ports.values():
                if not bindings:
                    continue
                for binding in bindings:
                    if binding and "HostPort" in binding:
                        used.add(int(binding["HostPort"]))
        except Exception as exc:
            logger.warning("Failed to read ports for container %s: %s", getattr(container, "name", "?"), exc)
    return used


async def find_available_port(
    client: docker.DockerClient,
    port_range_start: int,
    port_range_end: int,
    *,
    exclude_ports: set[int] | None = None,
) -> int | None:
    try:
        # Every container on the daemon competes for host ports, not just the ones
        # this platform manages. ``resource_scope`` scopes ownership and cleanup;
        # port safety has to consider foreign containers too.
        #
        # ignore_removed=True is load-bearing: docker-py enumerates containers and then inspects
        # each one individually, so a container removed between those two calls makes the inspect
        # 404 and aborts the entire listing. That is routine whenever containers are being torn
        # down concurrently, and a container that no longer exists holds no host ports.
        containers = await asyncio.to_thread(client.containers.list, all=True, ignore_removed=True)
    except Exception as exc:
        # We do not know which ports are in use, so we cannot claim the range is full.
        raise PortEnumerationError(f"could not list containers to determine ports in use: {exc}") from exc

    used_ports = collect_used_host_ports(containers)
    if exclude_ports:
        used_ports = used_ports | exclude_ports
    for port in range(port_range_start, port_range_end + 1):
        if port not in used_ports and is_port_free(port):
            return port

    logger.error(
        "No available ports in range %s-%s",
        port_range_start,
        port_range_end,
    )
    return None
