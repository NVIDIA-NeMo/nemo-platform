# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Provision the ClickHouse instance owned by a local Intake service."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Final, cast
from uuid import uuid4

import clickhouse_connect
from docker.errors import APIError, DockerException, ImageNotFound, NotFound
from docker.models.containers import Container
from nmp.common.config import nmp_user_data_dir
from nmp.intake.config import DEFAULT_CLICKHOUSE_IMAGE, DEFAULT_CLICKHOUSE_VERSION, IntakeConfig
from nmp.intake.spans.clickhouse_client import ClickHouseSettings
from nmp.intake.spans.clickhouse_migrations import parse_clickhouse_url
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

import docker
from docker import DockerClient

logger = logging.getLogger(__name__)

CLICKHOUSE_VERSION: Final = DEFAULT_CLICKHOUSE_VERSION
CLICKHOUSE_HTTP_PORT: Final = 8123
CLICKHOUSE_HTTP_PORT_KEY: Final = f"{CLICKHOUSE_HTTP_PORT}/tcp"
CLICKHOUSE_NATIVE_PORT: Final = 9000
CLICKHOUSE_NATIVE_PORT_KEY: Final = f"{CLICKHOUSE_NATIVE_PORT}/tcp"
CLICKHOUSE_DATA_PATH: Final = "/var/lib/clickhouse"
LEGACY_CONTAINER_NAME: Final = "nmp-intake-clickhouse"

_MANAGED_BY_LABEL = "nmp.nvidia.com/managed-by"
_COMPONENT_LABEL = "nmp.nvidia.com/component"
_DATA_DIR_LABEL = "nmp.nvidia.com/data-directory-sha256"
_DATA_INSTANCE_LABEL = "nmp.nvidia.com/data-instance-id"
_MANAGED_BY_VALUE = "nemo-platform"
_COMPONENT_VALUE = "intake-clickhouse"
_DATA_IDENTITY_FILE = ".nmp-clickhouse-identity"
_READINESS_TIMEOUT_SECONDS = 60.0
_READINESS_POLL_SECONDS = 0.5
_DOCKER_UNAVAILABLE_GUIDANCE = (
    "Docker daemon is unavailable. Start Docker Desktop on macOS/Windows or the Docker service on Linux, "
    "then rerun `nemo setup` or restart `nemo services run`. To use an externally managed ClickHouse instead, "
    "set NMP_INTAKE_CLICKHOUSE_URL."
)


class LocalClickHouseProvisioningError(RuntimeError):
    """Raised when Intake cannot safely provision its local ClickHouse."""


class DockerUnavailableError(LocalClickHouseProvisioningError):
    """Raised when local ClickHouse cannot start because Docker is unavailable."""


class DataDirectoryIdentityMismatchError(LocalClickHouseProvisioningError):
    """Raised when a managed container points at an earlier data-directory incarnation."""


async def provision_local_clickhouse(
    settings: ClickHouseSettings,
    *,
    image: str = DEFAULT_CLICKHOUSE_IMAGE,
    data_dir: Path | None = None,
) -> str:
    """Ensure Intake's data-directory-owned ClickHouse is running and return its HTTP URL."""

    return await asyncio.to_thread(
        _provision_local_clickhouse,
        settings,
        image=image,
        data_dir=data_dir,
    )


def _provision_local_clickhouse(
    settings: ClickHouseSettings,
    *,
    image: str = DEFAULT_CLICKHOUSE_IMAGE,
    data_dir: Path | None = None,
    legacy_script_mode: bool = False,
) -> str:
    resolved_data_dir = _resolve_data_dir(data_dir)
    container_name = LEGACY_CONTAINER_NAME if legacy_script_mode else _managed_container_name(resolved_data_dir)
    client = _connect_docker()
    try:
        data_instance_id = _prepare_data_dir(
            resolved_data_dir,
            manage_permissions=data_dir is None,
        )
        container = _get_container(client, container_name)
        legacy = legacy_script_mode
        if container is None and not legacy_script_mode:
            legacy_container = _get_container(client, LEGACY_CONTAINER_NAME)
            if legacy_container is not None:
                legacy_container.reload()
                legacy_attrs = cast(dict[str, Any], legacy_container.attrs or {})
                if _mounted_clickhouse_data_dir(legacy_attrs) == resolved_data_dir:
                    container = legacy_container
                    legacy = True

        if container is None:
            container = _create_container(
                client,
                name=container_name,
                image=image,
                data_dir=resolved_data_dir,
                data_instance_id=data_instance_id,
                settings=settings,
                legacy_script_mode=legacy_script_mode,
            )
        else:
            try:
                _validate_container(
                    container,
                    expected_name=LEGACY_CONTAINER_NAME if legacy else container_name,
                    image=image,
                    data_dir=resolved_data_dir,
                    data_instance_id=None if legacy else data_instance_id,
                    settings=settings,
                )
            except DataDirectoryIdentityMismatchError:
                logger.warning(
                    "Replacing stale managed ClickHouse container %s after its data directory was recreated",
                    container_name,
                )
                _remove_container(container)
                container = _create_container(
                    client,
                    name=container_name,
                    image=image,
                    data_dir=resolved_data_dir,
                    data_instance_id=data_instance_id,
                    settings=settings,
                    legacy_script_mode=False,
                )
            container.reload()
            if container.status != "running":
                container.start()

        _ensure_clickhouse_tmp_dir(container)
        url = _container_http_url(container)
        _wait_until_ready(replace(settings, url=url))
        logger.info("Local ClickHouse is ready at %s", url, extra={"container": container.name})
        return url
    except LocalClickHouseProvisioningError:
        raise
    except Exception as exc:
        raise LocalClickHouseProvisioningError(f"Failed to provision local ClickHouse: {exc}") from exc
    finally:
        client.close()


def remove_local_clickhouse(*, data_dir: Path | None = None) -> bool:
    """Remove managed ClickHouse containers for a local NeMo data directory."""

    resolved_data_dir = _resolve_data_dir(data_dir)
    managed_container_name = _managed_container_name(resolved_data_dir)
    client = _connect_docker()
    try:
        containers: list[tuple[str, Container]] = []
        if (managed_container := _get_container(client, managed_container_name)) is not None:
            containers.append((managed_container_name, managed_container))
        if (legacy_container := _get_container(client, LEGACY_CONTAINER_NAME)) is not None:
            legacy_container.reload()
            legacy_attrs = cast(dict[str, Any], legacy_container.attrs or {})
            if _mounted_clickhouse_data_dir(legacy_attrs) == resolved_data_dir:
                containers.append((LEGACY_CONTAINER_NAME, legacy_container))
        if not containers:
            return False
        for container_name, container in containers:
            _validate_cleanup_target(
                container,
                expected_name=container_name,
                data_dir=resolved_data_dir,
                allow_unlabeled_legacy=container_name == LEGACY_CONTAINER_NAME,
            )
        for container_name, container in containers:
            _remove_container(container)
            logger.info("Removed managed local ClickHouse container %s", container_name)
        return True
    except LocalClickHouseProvisioningError:
        raise
    except Exception as exc:
        raise LocalClickHouseProvisioningError(f"Failed to remove local ClickHouse: {exc}") from exc
    finally:
        client.close()


def _connect_docker() -> DockerClient:
    client: DockerClient | None = None
    try:
        client = docker.from_env(timeout=10)
        client.ping()
        return client
    except (DockerException, RequestsConnectionError, RequestsTimeout, OSError) as exc:
        if client is not None:
            client.close()
        raise DockerUnavailableError(_DOCKER_UNAVAILABLE_GUIDANCE) from exc


def _resolve_data_dir(data_dir: Path | None) -> Path:
    return (data_dir.expanduser() if data_dir is not None else nmp_user_data_dir() / "intake-clickhouse").resolve()


def _get_container(client: DockerClient, name: str) -> Container | None:
    try:
        return client.containers.get(name)
    except NotFound:
        return None


def _create_container(
    client: DockerClient,
    *,
    name: str,
    image: str,
    data_dir: Path,
    data_instance_id: str,
    settings: ClickHouseSettings,
    legacy_script_mode: bool,
) -> Container:
    try:
        client.images.get(image)
    except ImageNotFound:
        logger.warning(
            "Local ClickHouse image %s is not installed; pulling it before Intake starts. "
            "The first pull may take several minutes.",
            image,
        )
        client.images.pull(image)
        logger.info("Finished pulling local ClickHouse image %s", image)

    run_kwargs = {
        "image": image,
        "name": name,
        "detach": True,
        "environment": {
            "CLICKHOUSE_USER": settings.user,
            "CLICKHOUSE_PASSWORD": settings.password,
            "CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT": "1",
            "CLICKHOUSE_SKIP_USER_SETUP": "1",
        },
        "ports": (
            {
                CLICKHOUSE_HTTP_PORT_KEY: ("127.0.0.1", CLICKHOUSE_HTTP_PORT),
                CLICKHOUSE_NATIVE_PORT_KEY: ("127.0.0.1", CLICKHOUSE_NATIVE_PORT),
            }
            if legacy_script_mode
            else {CLICKHOUSE_HTTP_PORT_KEY: ("127.0.0.1", 0)}
        ),
        "volumes": {str(data_dir): {"bind": CLICKHOUSE_DATA_PATH, "mode": "rw"}},
        "labels": _expected_labels(data_dir, data_instance_id),
        "restart_policy": {"Name": "unless-stopped"},
    }
    try:
        return client.containers.run(**run_kwargs)
    except APIError as exc:
        if exc.status_code != 409:
            raise
        container = _get_container(client, name)
        if container is None:
            raise
        _validate_container(
            container,
            expected_name=name,
            image=image,
            data_dir=data_dir,
            data_instance_id=None if legacy_script_mode else data_instance_id,
            settings=settings,
        )
        return container


def _validate_container(
    container: Container,
    *,
    expected_name: str,
    image: str,
    data_dir: Path,
    data_instance_id: str | None,
    settings: ClickHouseSettings,
) -> None:
    container.reload()
    attrs = cast(dict[str, Any], container.attrs or {})
    container_config = cast(dict[str, Any], attrs.get("Config") or {})
    actual_image = str(container_config.get("Image", ""))
    if actual_image != image:
        raise LocalClickHouseProvisioningError(
            f"Container {expected_name} uses {actual_image or 'an unknown image'}, but Intake requires {image}. "
            "Preserve any data you need and remove or rename the container before retrying."
        )

    if data_instance_id is not None:
        labels = container.labels or {}
        identity_labels = {
            _MANAGED_BY_LABEL: _MANAGED_BY_VALUE,
            _COMPONENT_LABEL: _COMPONENT_VALUE,
            _DATA_DIR_LABEL: _data_dir_identity(data_dir),
        }
        if any(labels.get(key) != value for key, value in identity_labels.items()):
            raise LocalClickHouseProvisioningError(
                f"Container name collision: {expected_name} is not the matching Intake-managed ClickHouse"
            )
        if labels.get(_DATA_INSTANCE_LABEL) != data_instance_id:
            raise DataDirectoryIdentityMismatchError(
                f"Container {expected_name} belongs to an earlier incarnation of data directory {data_dir}. "
                "The stale container can be replaced without deleting data from the current directory."
            )
    environment = _container_environment(attrs)
    if (
        environment.get("CLICKHOUSE_USER") != settings.user
        or environment.get("CLICKHOUSE_PASSWORD") != settings.password
    ):
        raise LocalClickHouseProvisioningError(
            f"ClickHouse credentials changed for container {expected_name}. Remove the container to re-provision "
            "it with NMP_INTAKE_CLICKHOUSE_USER and NMP_INTAKE_CLICKHOUSE_PASSWORD, or restore the previous values."
        )

    if _mounted_clickhouse_data_dir(attrs) != data_dir:
        raise LocalClickHouseProvisioningError(
            f"Container {expected_name} does not use the expected data directory {data_dir}"
        )


def _validate_cleanup_target(
    container: Container,
    *,
    expected_name: str,
    data_dir: Path,
    allow_unlabeled_legacy: bool = False,
) -> None:
    container.reload()
    attrs = cast(dict[str, Any], container.attrs or {})
    if _mounted_clickhouse_data_dir(attrs) != data_dir:
        raise LocalClickHouseProvisioningError(
            f"Refusing to remove container {expected_name}: it does not mount {data_dir}"
        )

    labels = container.labels or {}
    expected_labels = {
        _MANAGED_BY_LABEL: _MANAGED_BY_VALUE,
        _COMPONENT_LABEL: _COMPONENT_VALUE,
        _DATA_DIR_LABEL: _data_dir_identity(data_dir),
    }
    if allow_unlabeled_legacy and not any(label in labels for label in expected_labels):
        return
    if any(labels.get(key) != value for key, value in expected_labels.items()):
        raise LocalClickHouseProvisioningError(
            f"Refusing to remove container {expected_name}: it is not owned by Intake for {data_dir}"
        )


def _remove_container(container: Container) -> None:
    container.reload()
    if container.status == "running":
        container.stop(timeout=30)
    container.remove()


def _data_dir_identity(data_dir: Path) -> str:
    return hashlib.sha256(str(data_dir).encode()).hexdigest()


def _managed_container_name(data_dir: Path) -> str:
    return f"nmp-intake-clickhouse-{_data_dir_identity(data_dir)[:12]}"


def _container_environment(attrs: dict[str, Any]) -> dict[str, str]:
    container_config = cast(dict[str, Any], attrs.get("Config") or {})
    entries = cast(list[str], container_config.get("Env") or [])
    return {key: value for entry in entries if "=" in entry for key, value in [entry.split("=", 1)]}


def _mounted_clickhouse_data_dir(attrs: dict[str, Any]) -> Path | None:
    mounts = cast(list[dict[str, Any]], attrs.get("Mounts") or [])
    source = next(
        (mount.get("Source") for mount in mounts if mount.get("Destination") == CLICKHOUSE_DATA_PATH),
        None,
    )
    return Path(str(source)).resolve() if source is not None else None


def _expected_labels(data_dir: Path, data_instance_id: str) -> dict[str, str]:
    return {
        _MANAGED_BY_LABEL: _MANAGED_BY_VALUE,
        _COMPONENT_LABEL: _COMPONENT_VALUE,
        _DATA_DIR_LABEL: _data_dir_identity(data_dir),
        _DATA_INSTANCE_LABEL: data_instance_id,
    }


def _prepare_data_dir(data_dir: Path, *, manage_permissions: bool) -> str:
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = data_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    if manage_permissions:
        data_dir.chmod(0o755)
        tmp_dir.chmod(0o755)

    identity_path = data_dir / _DATA_IDENTITY_FILE
    try:
        file_descriptor = os.open(identity_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as identity_file:
            identity_file.write(f"{uuid4().hex}\n")

    for _attempt in range(10):
        data_instance_id = identity_path.read_text(encoding="utf-8").strip()
        if data_instance_id:
            return data_instance_id
        time.sleep(0.01)
    raise LocalClickHouseProvisioningError(
        f"ClickHouse data identity marker {identity_path} is empty; remove it only if this data can be re-provisioned"
    )


def _ensure_clickhouse_tmp_dir(container: Container) -> None:
    result = container.exec_run(
        [
            "sh",
            "-c",
            "mkdir -p /var/lib/clickhouse/tmp && chown clickhouse:clickhouse /var/lib/clickhouse/tmp",
        ]
    )
    if result.exit_code != 0:
        output = result.output.decode(errors="replace") if isinstance(result.output, bytes) else str(result.output)
        raise LocalClickHouseProvisioningError(
            f"Could not prepare ClickHouse temporary storage in {container.name}: {output.strip()}"
        )


def _container_http_url(container: Container) -> str:
    container.reload()
    bindings = (container.ports or {}).get(CLICKHOUSE_HTTP_PORT_KEY)
    if not bindings:
        raise LocalClickHouseProvisioningError(
            f"Container {container.name} does not publish ClickHouse HTTP port {CLICKHOUSE_HTTP_PORT}"
        )
    host_port = bindings[0].get("HostPort")
    if not host_port:
        raise LocalClickHouseProvisioningError(f"Container {container.name} has no assigned ClickHouse host port")
    return f"http://127.0.0.1:{int(host_port)}"


def _wait_until_ready(settings: ClickHouseSettings) -> None:
    deadline = time.monotonic() + _READINESS_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            _ping_clickhouse(settings)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(_READINESS_POLL_SECONDS)
    raise LocalClickHouseProvisioningError(
        f"ClickHouse at {settings.url} did not become ready within {_READINESS_TIMEOUT_SECONDS:g} seconds"
    ) from last_error


def _ping_clickhouse(settings: ClickHouseSettings) -> None:
    parsed = parse_clickhouse_url(settings.url)
    client = clickhouse_connect.get_client(
        host=parsed.host,
        port=parsed.port,
        secure=parsed.secure,
        username=settings.user,
        password=settings.password,
        database="default",
        connect_timeout=2,
    )
    try:
        client.command("SELECT 1")
    finally:
        client.close()


def main() -> int:
    """Provision or remove local ClickHouse for compatibility and teardown commands."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--remove", action="store_true", help="remove the data-directory-owned ClickHouse container")
    args = parser.parse_args()
    config = IntakeConfig()
    settings = ClickHouseSettings.from_config(config)
    try:
        if args.remove:
            removed = remove_local_clickhouse(data_dir=config.clickhouse_config.data_dir)
            print(
                "Removed managed local ClickHouse container"
                if removed
                else "No managed local ClickHouse container found"
            )
            return 0
        url = _provision_local_clickhouse(
            settings,
            image=config.clickhouse_config.image,
            data_dir=config.clickhouse_config.data_dir,
            legacy_script_mode=True,
        )
    except LocalClickHouseProvisioningError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Local ClickHouse is ready at {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
