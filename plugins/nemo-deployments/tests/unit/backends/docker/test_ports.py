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


def test_is_port_free_skips_check_for_remote_host(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_deployments_plugin.backends.docker import ports as ports_mod

    monkeypatch.setattr(ports_mod, "is_remote_docker_host", lambda: True)
    assert is_port_free(1) is True


def test_is_port_free_returns_false_when_bind_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_deployments_plugin.backends.docker import ports as ports_mod

    class FakeSock:
        def __enter__(self) -> FakeSock:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def setsockopt(self, *args: object, **kwargs: object) -> None:
            return None

        def bind(self, addr: tuple[str, int]) -> None:
            raise OSError("Address already in use")

    monkeypatch.setattr(ports_mod, "is_remote_docker_host", lambda: False)
    monkeypatch.setattr(ports_mod.socket, "socket", lambda *args, **kwargs: FakeSock())
    assert is_port_free(9000) is False


def test_is_port_free_returns_true_when_bind_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_deployments_plugin.backends.docker import ports as ports_mod

    class FakeSock:
        def __enter__(self) -> FakeSock:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def setsockopt(self, *args: object, **kwargs: object) -> None:
            return None

        def bind(self, addr: tuple[str, int]) -> None:
            assert addr == ("127.0.0.1", 9000)
            return None

    monkeypatch.setattr(ports_mod, "is_remote_docker_host", lambda: False)
    monkeypatch.setattr(ports_mod.socket, "socket", lambda *args, **kwargs: FakeSock())
    assert is_port_free(9000) is True


@pytest.mark.asyncio
async def test_find_available_port_skips_used(mock_docker_client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_deployments_plugin.backends.docker import ports as ports_mod
    from nemo_deployments_plugin.backends.docker.ports import find_available_port

    used = MagicMock()
    used.ports = {"80/tcp": [{"HostPort": "9000"}]}
    mock_docker_client.containers.list.return_value = [used]
    monkeypatch.setattr(ports_mod, "is_port_free", lambda port: port != 9001)

    cfg = DockerDeploymentConfig(port_range_start=9000, port_range_end=9002)
    port = await find_available_port(mock_docker_client, cfg)
    assert port == 9002


@pytest.mark.asyncio
async def test_find_available_port_excludes_pending_assignments(mock_docker_client: MagicMock) -> None:
    from nemo_deployments_plugin.backends.docker.ports import find_available_port

    mock_docker_client.containers.list.return_value = []
    cfg = DockerDeploymentConfig(port_range_start=9000, port_range_end=9002)

    first = await find_available_port(mock_docker_client, cfg)
    assert first == 9000
    second = await find_available_port(mock_docker_client, cfg, exclude_ports={first})

    assert first == 9000
    assert second == 9001
