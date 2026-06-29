# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Host port allocation for published container ports."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from typing import TYPE_CHECKING

from nemo_deployments_plugin.backends.docker.labels import managed_by_filter
from nemo_deployments_plugin.entities import DockerDeploymentConfig

import docker

if TYPE_CHECKING:
    from docker.models.containers import Container as DockerContainer

logger = logging.getLogger(__name__)


def is_remote_docker_host() -> bool:
    docker_host = os.environ.get("DOCKER_HOST", "")
    return docker_host.startswith("tcp://")


def is_port_free(port: int) -> bool:
    if is_remote_docker_host():
        return True
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
    docker_cfg: DockerDeploymentConfig,
    *,
    exclude_ports: set[int] | None = None,
) -> int | None:
    try:
        containers = await asyncio.to_thread(
            client.containers.list,
            all=True,
            filters=managed_by_filter(),
        )
    except Exception:
        logger.exception("Failed to list containers for port allocation")
        return None

    used_ports = collect_used_host_ports(containers)
    if exclude_ports:
        used_ports = used_ports | exclude_ports
    for port in range(docker_cfg.port_range_start, docker_cfg.port_range_end + 1):
        if port not in used_ports and is_port_free(port):
            return port

    logger.error(
        "No available ports in range %s-%s",
        docker_cfg.port_range_start,
        docker_cfg.port_range_end,
    )
    return None
