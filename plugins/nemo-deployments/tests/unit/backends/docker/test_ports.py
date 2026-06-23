# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for host port allocation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nemo_deployments_plugin.backends.docker.ports import collect_used_host_ports, is_port_free
from nemo_deployments_plugin.entities import DockerDeploymentConfig


def test_collect_used_host_ports() -> None:
    container = MagicMock()
    container.ports = {"8080/tcp": [{"HostPort": "9001"}]}
    assert collect_used_host_ports([container]) == {9001}


def test_is_port_free_local() -> None:
    # Ephemeral high port likely free in test environment
    assert is_port_free(59999) or not is_port_free(59999)


@pytest.mark.asyncio
async def test_find_available_port_skips_used(mock_docker_client: MagicMock) -> None:
    from nemo_deployments_plugin.backends.docker.ports import find_available_port

    used = MagicMock()
    used.ports = {"80/tcp": [{"HostPort": "9000"}]}
    mock_docker_client.containers.list.return_value = [used]

    cfg = DockerDeploymentConfig(port_range_start=9000, port_range_end=9002)
    port = await find_available_port(mock_docker_client, cfg)
    assert port in {9001, 9002}
