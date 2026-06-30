# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compile DeploymentConfig into docker.containers.run kwargs."""

from __future__ import annotations

from typing import Any

from nemo_deployments_plugin.backends.docker.labels import docker_volume_name
from nemo_deployments_plugin.entities import Container, DeploymentConfig, DockerDeploymentConfig, VolumeMount
from nemo_deployments_plugin.types import RestartPolicy


class DeploymentConfigError(ValueError):
    """Invalid deployment config for docker backend."""


def parse_docker_backend_config(backend_config: dict[str, Any]) -> DockerDeploymentConfig:
    docker_section = backend_config.get("docker") or {}
    return DockerDeploymentConfig.model_validate(docker_section)


def validate_config_for_docker(config: DeploymentConfig) -> Container:
    if config.init_containers:
        raise DeploymentConfigError("init_containers are not supported by the docker backend in v1")
    if len(config.containers) != 1:
        raise DeploymentConfigError(f"docker backend v1 supports exactly one container; got {len(config.containers)}")
    return config.containers[0]


def restart_policy_kwargs(restart_policy: RestartPolicy, backoff_limit: int) -> dict[str, Any]:
    if restart_policy == "Always":
        return {"restart_policy": {"Name": "always"}}
    if restart_policy == "OnFailure":
        return {"restart_policy": {"Name": "on-failure", "MaximumRetryCount": backoff_limit}}
    return {}


def env_dict(container: Container) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in container.env:
        if item.value is not None:
            result[item.name] = item.value
    return result


def merged_volume_mounts(config: DeploymentConfig, container: Container) -> list[VolumeMount]:
    by_name: dict[str, VolumeMount] = {}
    for mount in config.volume_mounts:
        by_name[mount.name] = mount
    for mount in container.volume_mounts:
        by_name[mount.name] = mount
    return list(by_name.values())


def build_volume_bindings(
    workspace: str,
    mounts: list[VolumeMount],
) -> dict[str, dict[str, str]]:
    bindings: dict[str, dict[str, str]] = {}
    for mount in mounts:
        vol_name = docker_volume_name(workspace, mount.name)
        bindings[vol_name] = {
            "bind": mount.mount_path,
            "mode": "ro" if mount.read_only else "rw",
        }
    return bindings


def build_port_bindings(
    container: Container,
    host_ports: dict[int, int],
) -> dict[str, int | list[tuple[str, int]] | None]:
    ports: dict[str, int | list[tuple[str, int]] | None] = {}
    for port_spec in container.ports:
        container_port = port_spec.container_port
        protocol = port_spec.protocol.lower()
        key = f"{container_port}/{protocol}"
        host_port = host_ports.get(container_port)
        if host_port is not None:
            ports[key] = host_port
        else:
            ports[key] = container_port
    return ports


def gpu_count_from_container(container: Container) -> int:
    limit = container.resources.limits.get("nvidia.com/gpu")
    if not limit:
        return 0
    try:
        return int(limit)
    except ValueError:
        return 0


def device_requests_for_gpus(gpu_ids: list[int]) -> list[dict[str, Any]]:
    if not gpu_ids:
        return []
    return [
        {
            "Driver": "nvidia",
            "Count": 0,
            "DeviceIDs": [str(gpu_id) for gpu_id in gpu_ids],
            "Capabilities": [["gpu"]],
        }
    ]
