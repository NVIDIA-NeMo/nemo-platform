# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for host port allocation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nemo_deployments_plugin.backends.docker.ports import collect_used_host_ports, is_port_free


def test_collect_used_host_ports() -> None:
    container = MagicMock()
    container.ports = {"8080/tcp": [{"HostPort": "9001"}]}
    assert collect_used_host_ports([container]) == {9001}


def test_is_port_free_skips_check_for_remote_host(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_deployments_plugin.backends.docker import ports as ports_mod

    monkeypatch.setattr(ports_mod, "is_remote_docker_host", lambda: True)
    assert is_port_free(1) is True


class FakeSock:
    """Records what ``is_port_free`` does to its probe socket."""

    def __init__(self, *, bind_error: OSError | None = None) -> None:
        self.bind_error = bind_error
        self.bound: list[tuple[str, int]] = []
        self.sockopts: list[tuple[object, ...]] = []

    def __enter__(self) -> FakeSock:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def setsockopt(self, *args: object) -> None:
        self.sockopts.append(args)

    def bind(self, addr: tuple[str, int]) -> None:
        if self.bind_error is not None:
            raise self.bind_error
        self.bound.append(addr)


def _patch_local_probe(monkeypatch: pytest.MonkeyPatch, sock: FakeSock) -> None:
    from nemo_deployments_plugin.backends.docker import ports as ports_mod

    monkeypatch.setattr(ports_mod, "is_remote_docker_host", lambda: False)
    monkeypatch.setattr(ports_mod.socket, "socket", lambda *args, **kwargs: sock)


def test_is_port_free_returns_false_when_bind_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_local_probe(monkeypatch, FakeSock(bind_error=OSError("Address already in use")))
    assert is_port_free(9000) is False


def test_is_port_free_probes_wildcard_address_without_reuseaddr(monkeypatch: pytest.MonkeyPatch) -> None:
    # Docker publishes on 0.0.0.0, and SO_REUSEADDR would let the probe bind a port
    # a wildcard publisher already holds, reporting it free.
    sock = FakeSock()
    _patch_local_probe(monkeypatch, sock)

    assert is_port_free(9000) is True
    assert sock.bound == [("0.0.0.0", 9000)]
    assert sock.sockopts == []


@pytest.mark.asyncio
async def test_find_available_port_skips_used(mock_docker_client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_deployments_plugin.backends.docker import ports as ports_mod
    from nemo_deployments_plugin.backends.docker.ports import find_available_port

    used = MagicMock()
    used.ports = {"80/tcp": [{"HostPort": "9000"}]}
    mock_docker_client.containers.list.return_value = [used]
    monkeypatch.setattr(ports_mod, "is_port_free", lambda port: port != 9001)

    port = await find_available_port(mock_docker_client, 9000, 9002)
    assert port == 9002


@pytest.mark.asyncio
async def test_find_available_port_skips_unmanaged_containers(
    mock_docker_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Foreign containers (e.g. a test-fixture ClickHouse) compete for host ports too."""
    from nemo_deployments_plugin.backends.docker import ports as ports_mod
    from nemo_deployments_plugin.backends.docker.ports import find_available_port

    foreign = MagicMock()
    foreign.labels = {}
    foreign.ports = {"9000/tcp": [{"HostPort": "9000"}]}
    mock_docker_client.containers.list.return_value = [foreign]
    # The daemon's own reservation is invisible to a host-socket probe.
    monkeypatch.setattr(ports_mod, "is_port_free", lambda port: True)

    port = await find_available_port(mock_docker_client, 9000, 9002)

    assert port == 9001
    assert mock_docker_client.containers.list.call_args.kwargs == {"all": True}


@pytest.mark.asyncio
async def test_find_available_port_excludes_pending_assignments(mock_docker_client: MagicMock) -> None:
    from nemo_deployments_plugin.backends.docker.ports import find_available_port

    mock_docker_client.containers.list.return_value = []

    first = await find_available_port(mock_docker_client, 9000, 9002)
    assert first == 9000
    second = await find_available_port(mock_docker_client, 9000, 9002, exclude_ports={first})

    assert first == 9000
    assert second == 9001
