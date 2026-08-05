# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for local ClickHouse provisioning and ownership."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from docker.errors import DockerException, NotFound
from nmp.intake.config import ClickHouseConfig, should_provision_local_clickhouse
from nmp.intake.local_clickhouse import (
    CLICKHOUSE_DATA_PATH,
    CLICKHOUSE_HTTP_PORT_KEY,
    CLICKHOUSE_NATIVE_PORT_KEY,
    CLICKHOUSE_VERSION,
    LEGACY_CONTAINER_NAME,
    DockerUnavailableError,
    LocalClickHouseProvisioningError,
    _expected_labels,
    _managed_container_name,
    _prepare_data_dir,
    _provision_local_clickhouse,
    remove_local_clickhouse,
)
from nmp.intake.spans.clickhouse_client import ClickHouseSettings


@dataclass
class FakeExecResult:
    exit_code: int = 0
    output: bytes = b""


class FakeContainer:
    def __init__(
        self,
        *,
        name: str,
        image: str,
        labels: dict[str, str] | None = None,
        data_dir: Path | None = None,
        status: str = "running",
        host_port: int = 55123,
        user: str = "default",
        password: str = "",
    ) -> None:
        self.name = name
        self.status = status
        self.labels = labels or {}
        self.ports = {CLICKHOUSE_HTTP_PORT_KEY: [{"HostIp": "127.0.0.1", "HostPort": str(host_port)}]}
        self.attrs = {
            "Config": {
                "Image": image,
                "Env": [f"CLICKHOUSE_USER={user}", f"CLICKHOUSE_PASSWORD={password}"],
            },
            "Mounts": (
                [{"Source": str(data_dir), "Destination": CLICKHOUSE_DATA_PATH}] if data_dir is not None else []
            ),
        }
        self.started = False
        self.stopped = False
        self.removed = False

    def reload(self) -> None:
        return None

    def start(self) -> None:
        self.started = True
        self.status = "running"

    def stop(self, *, timeout: int) -> None:
        assert timeout == 30
        self.stopped = True
        self.status = "exited"

    def exec_run(self, _command: list[str]) -> FakeExecResult:
        return FakeExecResult()

    def remove(self) -> None:
        self.removed = True


class FakeContainers:
    def __init__(self, containers: dict[str, FakeContainer] | None = None) -> None:
        self._containers = containers or {}
        self.run_calls: list[dict[str, object]] = []

    def get(self, name: str) -> FakeContainer:
        container = self._containers.get(name)
        if container is None:
            raise NotFound("missing")
        return container

    def run(self, **kwargs: object) -> FakeContainer:
        self.run_calls.append(kwargs)
        name = str(kwargs["name"])
        image = str(kwargs["image"])
        labels_value = kwargs["labels"]
        environment_value = kwargs["environment"]
        volumes_value = kwargs["volumes"]
        assert isinstance(labels_value, dict)
        assert isinstance(environment_value, dict)
        assert isinstance(volumes_value, dict)
        labels = {str(key): str(value) for key, value in labels_value.items()}
        environment = cast(dict[str, object], environment_value)
        volumes = {str(key): value for key, value in volumes_value.items()}
        data_dir = Path(next(iter(volumes)))
        ports = cast(dict[str, tuple[str, int | None]], kwargs["ports"])
        http_binding = ports[CLICKHOUSE_HTTP_PORT_KEY]
        host_port = http_binding[1] or 55123
        container = FakeContainer(
            name=name,
            image=image,
            labels=labels,
            data_dir=data_dir,
            host_port=host_port,
            user=str(environment["CLICKHOUSE_USER"]),
            password=str(environment["CLICKHOUSE_PASSWORD"]),
        )
        self._containers[name] = container
        return container


class FakeDockerClient:
    def __init__(self, containers: dict[str, FakeContainer] | None = None) -> None:
        self.containers = FakeContainers(containers)
        self.images = SimpleNamespace(get=MagicMock(), pull=MagicMock())
        self.pinged = False
        self.closed = False

    def ping(self) -> bool:
        self.pinged = True
        return True

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def settings() -> ClickHouseSettings:
    return ClickHouseSettings(
        url="http://localhost:8123",
        user="default",
        password="",
        database="intake",
    )


def _patch_provisioning(monkeypatch: pytest.MonkeyPatch, client: FakeDockerClient, tmp_path: Path) -> None:
    monkeypatch.setenv("NMP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("nmp.intake.local_clickhouse._wait_until_ready", lambda _settings: None)
    monkeypatch.setattr("nmp.intake.local_clickhouse.docker.from_env", lambda **_kwargs: client)


def test_default_unconfigured_url_is_locally_managed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NMP_INTAKE_CLICKHOUSE_URL", raising=False)

    assert should_provision_local_clickhouse(ClickHouseConfig()) is True


def test_explicit_default_url_is_externally_managed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_URL", "http://localhost:8123")

    assert should_provision_local_clickhouse(ClickHouseConfig()) is False


def test_nondefault_config_url_is_externally_managed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NMP_INTAKE_CLICKHOUSE_URL", raising=False)

    assert should_provision_local_clickhouse(ClickHouseConfig(url="https://clickhouse.example.com")) is False


def test_managed_container_config_uses_namespaced_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLICKHOUSE_IMAGE", "ignored:latest")
    monkeypatch.setenv("CLICKHOUSE_DATA_DIR", str(tmp_path / "ignored"))
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_IMAGE", "clickhouse/clickhouse-server:custom")
    monkeypatch.setenv("NMP_INTAKE_CLICKHOUSE_DATA_DIR", str(tmp_path / "configured"))

    config = ClickHouseConfig()

    assert config.image == "clickhouse/clickhouse-server:custom"
    assert config.data_dir == tmp_path / "configured"


def test_provision_creates_data_directory_owned_container_with_dynamic_loopback_port(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: ClickHouseSettings,
) -> None:
    client = FakeDockerClient()
    _patch_provisioning(monkeypatch, client, tmp_path)

    url = _provision_local_clickhouse(settings)

    assert url == "http://127.0.0.1:55123"
    assert client.pinged is True
    assert client.closed is True
    assert len(client.containers.run_calls) == 1
    run = client.containers.run_calls[0]
    data_dir = (tmp_path / "intake-clickhouse").resolve()
    assert run["name"] == _managed_container_name(data_dir)
    assert run["ports"] == {CLICKHOUSE_HTTP_PORT_KEY: ("127.0.0.1", 0)}
    assert run["restart_policy"] == {"Name": "unless-stopped"}


def test_provision_reuses_matching_container(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: ClickHouseSettings,
) -> None:
    data_dir = (tmp_path / "intake-clickhouse").resolve()
    name = _managed_container_name(data_dir)
    image = f"clickhouse/clickhouse-server:{CLICKHOUSE_VERSION}"
    data_instance_id = _prepare_data_dir(data_dir, manage_permissions=True)
    container = FakeContainer(
        name=name,
        image=image,
        labels=_expected_labels(data_dir, data_instance_id),
        data_dir=data_dir,
        host_port=55234,
    )
    client = FakeDockerClient({name: container})
    _patch_provisioning(monkeypatch, client, tmp_path)

    url = _provision_local_clickhouse(settings)

    assert url == "http://127.0.0.1:55234"
    assert client.containers.run_calls == []


def test_provision_restarts_stopped_matching_container(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: ClickHouseSettings,
) -> None:
    data_dir = (tmp_path / "intake-clickhouse").resolve()
    name = _managed_container_name(data_dir)
    image = f"clickhouse/clickhouse-server:{CLICKHOUSE_VERSION}"
    data_instance_id = _prepare_data_dir(data_dir, manage_permissions=True)
    container = FakeContainer(
        name=name,
        image=image,
        labels=_expected_labels(data_dir, data_instance_id),
        data_dir=data_dir,
        status="exited",
    )
    client = FakeDockerClient({name: container})
    _patch_provisioning(monkeypatch, client, tmp_path)

    _provision_local_clickhouse(settings)

    assert container.started is True


def test_provision_rejects_container_identity_collision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: ClickHouseSettings,
) -> None:
    data_dir = (tmp_path / "intake-clickhouse").resolve()
    name = _managed_container_name(data_dir)
    image = f"clickhouse/clickhouse-server:{CLICKHOUSE_VERSION}"
    container = FakeContainer(name=name, image=image, labels={}, data_dir=data_dir)
    client = FakeDockerClient({name: container})
    _patch_provisioning(monkeypatch, client, tmp_path)

    with pytest.raises(LocalClickHouseProvisioningError, match="Container name collision"):
        _provision_local_clickhouse(settings)

    assert client.closed is True


def test_provision_adopts_legacy_container(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: ClickHouseSettings,
) -> None:
    data_dir = (tmp_path / "intake-clickhouse").resolve()
    image = f"clickhouse/clickhouse-server:{CLICKHOUSE_VERSION}"
    legacy = FakeContainer(name=LEGACY_CONTAINER_NAME, image=image, data_dir=data_dir, host_port=8123)
    client = FakeDockerClient({LEGACY_CONTAINER_NAME: legacy})
    _patch_provisioning(monkeypatch, client, tmp_path)

    url = _provision_local_clickhouse(settings)

    assert url == "http://127.0.0.1:8123"
    assert client.containers.run_calls == []
    assert remove_local_clickhouse(data_dir=data_dir) is True
    assert legacy.stopped is True
    assert legacy.removed is True


def test_provision_does_not_adopt_legacy_container_without_expected_data_mount(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: ClickHouseSettings,
) -> None:
    image = f"clickhouse/clickhouse-server:{CLICKHOUSE_VERSION}"
    legacy = FakeContainer(name=LEGACY_CONTAINER_NAME, image=image, host_port=8123)
    client = FakeDockerClient({LEGACY_CONTAINER_NAME: legacy})
    _patch_provisioning(monkeypatch, client, tmp_path)

    assert _provision_local_clickhouse(settings) == "http://127.0.0.1:55123"
    assert len(client.containers.run_calls) == 1
    assert client.containers.run_calls[0]["name"] == _managed_container_name((tmp_path / "intake-clickhouse").resolve())
    assert legacy.removed is False


def test_legacy_script_mode_preserves_container_name_and_ports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: ClickHouseSettings,
) -> None:
    client = FakeDockerClient()
    _patch_provisioning(monkeypatch, client, tmp_path)

    url = _provision_local_clickhouse(settings, legacy_script_mode=True)

    assert url == "http://127.0.0.1:8123"
    run = client.containers.run_calls[0]
    assert run["name"] == LEGACY_CONTAINER_NAME
    assert run["ports"] == {
        CLICKHOUSE_HTTP_PORT_KEY: ("127.0.0.1", 8123),
        CLICKHOUSE_NATIVE_PORT_KEY: ("127.0.0.1", 9000),
    }


def test_provision_reports_docker_daemon_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    settings: ClickHouseSettings,
) -> None:
    docker_factory = MagicMock(side_effect=DockerException("daemon not running"))
    monkeypatch.setattr("nmp.intake.local_clickhouse.docker.from_env", docker_factory)

    with pytest.raises(DockerUnavailableError, match="Docker daemon is unavailable") as error:
        _provision_local_clickhouse(settings)

    assert "Start Docker Desktop on macOS/Windows or the Docker service on Linux" in str(error.value)
    assert "rerun `nemo setup` or restart `nemo services run`" in str(error.value)
    assert "NMP_INTAKE_CLICKHOUSE_URL" in str(error.value)
    docker_factory.assert_called_once_with(timeout=10)


def test_provision_closes_client_when_docker_ping_fails(
    monkeypatch: pytest.MonkeyPatch,
    settings: ClickHouseSettings,
) -> None:
    client = FakeDockerClient()
    client.ping = MagicMock(side_effect=DockerException("connection disappeared"))
    monkeypatch.setattr("nmp.intake.local_clickhouse.docker.from_env", lambda **_kwargs: client)

    with pytest.raises(DockerUnavailableError, match="Docker daemon is unavailable"):
        _provision_local_clickhouse(settings)

    assert client.closed is True


def test_prepare_operator_data_dir_does_not_change_permissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    chmod = MagicMock()
    monkeypatch.setattr(Path, "chmod", chmod)

    data_dir = tmp_path / "operator-clickhouse"
    data_instance_id = _prepare_data_dir(data_dir, manage_permissions=False)

    assert data_instance_id
    assert (data_dir / ".nmp-clickhouse-identity").stat().st_mode & 0o777 == 0o600
    chmod.assert_not_called()


def test_prepare_data_dir_reuses_unreadable_identity_marker(tmp_path: Path) -> None:
    data_dir = tmp_path / "intake-clickhouse"
    data_instance_id = _prepare_data_dir(data_dir, manage_permissions=True)
    identity_path = data_dir / ".nmp-clickhouse-identity"
    identity_path.chmod(0)

    assert _prepare_data_dir(data_dir, manage_permissions=True) == data_instance_id


def test_data_directory_permission_failure_is_wrapped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: ClickHouseSettings,
) -> None:
    client = FakeDockerClient()
    _patch_provisioning(monkeypatch, client, tmp_path)
    monkeypatch.setattr(
        "nmp.intake.local_clickhouse._prepare_data_dir",
        MagicMock(side_effect=PermissionError("read-only directory")),
    )

    with pytest.raises(LocalClickHouseProvisioningError, match="Failed to provision local ClickHouse") as error:
        _provision_local_clickhouse(settings)

    assert isinstance(error.value.__cause__, PermissionError)
    assert client.closed is True


def test_changed_credentials_report_actionable_remediation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: ClickHouseSettings,
) -> None:
    data_dir = (tmp_path / "intake-clickhouse").resolve()
    name = _managed_container_name(data_dir)
    image = f"clickhouse/clickhouse-server:{CLICKHOUSE_VERSION}"
    data_instance_id = _prepare_data_dir(data_dir, manage_permissions=True)
    container = FakeContainer(
        name=name,
        image=image,
        labels=_expected_labels(data_dir, data_instance_id),
        data_dir=data_dir,
        password="old-password",
    )
    client = FakeDockerClient({name: container})
    _patch_provisioning(monkeypatch, client, tmp_path)

    with pytest.raises(LocalClickHouseProvisioningError, match="credentials changed") as error:
        _provision_local_clickhouse(settings)

    assert "Remove the container to re-provision" in str(error.value)
    assert "NMP_INTAKE_CLICKHOUSE_PASSWORD" in str(error.value)


def test_recreated_data_directory_replaces_stale_container(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: ClickHouseSettings,
) -> None:
    data_dir = (tmp_path / "intake-clickhouse").resolve()
    name = _managed_container_name(data_dir)
    image = f"clickhouse/clickhouse-server:{CLICKHOUSE_VERSION}"
    original_data_instance_id = _prepare_data_dir(data_dir, manage_permissions=True)
    container = FakeContainer(
        name=name,
        image=image,
        labels=_expected_labels(data_dir, original_data_instance_id),
        data_dir=data_dir,
    )
    original_identity_stat = (data_dir / ".nmp-clickhouse-identity").stat()
    for identity_path in data_dir.glob(".nmp-clickhouse-identity*"):
        identity_path.unlink()
    new_data_instance_id = _prepare_data_dir(data_dir, manage_permissions=True)
    assert new_data_instance_id != original_data_instance_id

    real_stat = Path.stat

    def stat_with_reused_identity_metadata(
        path: Path,
        *,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        if path.name.startswith(".nmp-clickhouse-identity"):
            return original_identity_stat
        return real_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", stat_with_reused_identity_metadata)
    assert _prepare_data_dir(data_dir, manage_permissions=True) == new_data_instance_id

    client = FakeDockerClient({name: container})
    _patch_provisioning(monkeypatch, client, tmp_path)

    assert _provision_local_clickhouse(settings) == "http://127.0.0.1:55123"
    assert container.stopped is True
    assert container.removed is True
    assert len(client.containers.run_calls) == 1


def test_remove_local_clickhouse_validates_and_removes_owned_container(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings: ClickHouseSettings,
) -> None:
    data_dir = (tmp_path / "intake-clickhouse").resolve()
    name = _managed_container_name(data_dir)
    data_instance_id = _prepare_data_dir(data_dir, manage_permissions=True)
    container = FakeContainer(
        name=name,
        image=f"clickhouse/clickhouse-server:{CLICKHOUSE_VERSION}",
        labels=_expected_labels(data_dir, data_instance_id),
        data_dir=data_dir,
    )
    client = FakeDockerClient({name: container})
    monkeypatch.setattr("nmp.intake.local_clickhouse.docker.from_env", lambda **_kwargs: client)

    assert remove_local_clickhouse(data_dir=data_dir) is True
    assert container.stopped is True
    assert container.removed is True
    assert client.closed is True


def test_remove_local_clickhouse_refuses_unowned_container(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = (tmp_path / "intake-clickhouse").resolve()
    name = _managed_container_name(data_dir)
    container = FakeContainer(
        name=name,
        image=f"clickhouse/clickhouse-server:{CLICKHOUSE_VERSION}",
        labels={},
        data_dir=data_dir,
    )
    client = FakeDockerClient({name: container})
    monkeypatch.setattr("nmp.intake.local_clickhouse.docker.from_env", lambda **_kwargs: client)

    with pytest.raises(LocalClickHouseProvisioningError, match="Refusing to remove"):
        remove_local_clickhouse(data_dir=data_dir)

    assert container.removed is False


def test_remove_local_clickhouse_removes_owned_legacy_container(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = (tmp_path / "intake-clickhouse").resolve()
    data_instance_id = _prepare_data_dir(data_dir, manage_permissions=True)
    container = FakeContainer(
        name=LEGACY_CONTAINER_NAME,
        image=f"clickhouse/clickhouse-server:{CLICKHOUSE_VERSION}",
        labels=_expected_labels(data_dir, data_instance_id),
        data_dir=data_dir,
    )
    client = FakeDockerClient({LEGACY_CONTAINER_NAME: container})
    monkeypatch.setattr("nmp.intake.local_clickhouse.docker.from_env", lambda **_kwargs: client)

    assert remove_local_clickhouse(data_dir=data_dir) is True
    assert container.stopped is True
    assert container.removed is True


def test_remove_local_clickhouse_ignores_legacy_container_for_another_data_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_dir = (tmp_path / "intake-clickhouse").resolve()
    legacy = FakeContainer(
        name=LEGACY_CONTAINER_NAME,
        image=f"clickhouse/clickhouse-server:{CLICKHOUSE_VERSION}",
        data_dir=tmp_path / "unrelated-clickhouse",
    )
    client = FakeDockerClient({LEGACY_CONTAINER_NAME: legacy})
    monkeypatch.setattr("nmp.intake.local_clickhouse.docker.from_env", lambda **_kwargs: client)

    assert remove_local_clickhouse(data_dir=data_dir) is False
    assert legacy.removed is False


def test_clickhouse_image_version_matches_service_pin() -> None:
    version_file = Path(__file__).parents[1] / ".clickhouse-version"

    assert version_file.read_text(encoding="utf-8").strip() == CLICKHOUSE_VERSION
