# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker integration coverage for Intake's local ClickHouse provisioner."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from docker.errors import DockerException, NotFound
from nmp.intake.local_clickhouse import (
    CLICKHOUSE_HTTP_PORT_KEY,
    LEGACY_CONTAINER_NAME,
    _get_container,
    _managed_container_name,
    _provision_local_clickhouse,
    remove_local_clickhouse,
)
from nmp.intake.spans.clickhouse_client import ClickHouseSettings

import docker


def _docker_is_available() -> bool:
    client = None
    try:
        client = docker.from_env(timeout=10)
        client.ping()
    except (DockerException, OSError):
        return False
    finally:
        if client is not None:
            client.close()
    return True


@pytest.mark.integration
def test_data_directory_owned_container_uses_dynamic_loopback_port_and_is_reused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if not _docker_is_available():
        pytest.skip("Docker is not available; skipping local ClickHouse provisioning test")

    data_dir = (tmp_path / "intake-clickhouse").resolve()
    container_name = _managed_container_name(data_dir)
    settings = ClickHouseSettings(
        url="http://localhost:8123",
        user="default",
        password="",
        database=f"intake_test_{uuid4().hex}",
    )
    # An unrelated legacy ClickHouse may already own localhost:8123 on a developer machine.
    monkeypatch.setattr("nmp.intake.local_clickhouse._can_connect", lambda _settings: False)
    monkeypatch.setattr(
        "nmp.intake.local_clickhouse._get_container",
        lambda docker_client, name: None if name == LEGACY_CONTAINER_NAME else _get_container(docker_client, name),
    )

    client = docker.from_env(timeout=10)
    try:
        first_url = _provision_local_clickhouse(settings, data_dir=data_dir)
        container = client.containers.get(container_name)
        first_id = container.id
        container.reload()
        binding = container.ports[CLICKHOUSE_HTTP_PORT_KEY][0]

        assert first_url == f"http://127.0.0.1:{binding['HostPort']}"
        assert binding["HostIp"] == "127.0.0.1"

        second_url = _provision_local_clickhouse(settings, data_dir=data_dir)
        reused = client.containers.get(container_name)

        assert second_url == first_url
        assert reused.id == first_id

        assert remove_local_clickhouse(data_dir=data_dir) is True
        with pytest.raises(NotFound):
            client.containers.get(container_name)
    finally:
        try:
            client.containers.get(container_name).remove(force=True)
        except NotFound:
            pass
        client.close()
