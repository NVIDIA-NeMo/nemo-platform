# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compile DeploymentConfig + K8sDeploymentConfig into Kubernetes PodSpec objects.

Native sidecars require Kubernetes >= 1.29 (init container ``restartPolicy=Always``).
On older clusters, omit per-container restart policy on init containers.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from kubernetes.client.rest import ApiException
from nemo_deployments_plugin.backends.k8s.client import k8s_client_module
from nemo_deployments_plugin.backends.k8s.status import resource_labels_match
from nemo_deployments_plugin.backends.labels import k8s_deployment_configmap_name, k8s_volume_resource_name
from nemo_deployments_plugin.entities import (
    Affinity,
    ConfigFile,
    Container,
    ContainerPort,
    DeploymentConfig,
    K8sDeploymentConfig,
    PodSecurityContext,
    Probe,
    Toleration,
    VolumeMount,
)
from nemo_deployments_plugin.types import RestartPolicy

CONFIG_FILES_VOLUME = "config-files"
NATIVE_SIDECAR_RESTART_POLICY: RestartPolicy = "Always"

logger = logging.getLogger(__name__)


class DeploymentConfigError(ValueError):
    """Invalid deployment config for k8s workload compilation."""


def merged_volume_mounts(config: DeploymentConfig, container: Container) -> list[VolumeMount]:
    mounts_by_name: dict[str, VolumeMount] = {}
    for mount in config.volume_mounts:
        mounts_by_name[mount.name] = mount
    for mount in container.volume_mounts:
        mounts_by_name[mount.name] = mount
    return list(mounts_by_name.values())


def build_env_vars(container: Container) -> list[Any]:
    k8s = k8s_client_module()
    return [k8s.client.V1EnvVar(name=item.name, value=item.value) for item in container.env if item.value is not None]


def build_resource_requirements(container: Container) -> Any | None:
    limits = container.resources.limits or None
    requests = container.resources.requests or None
    if not limits and not requests:
        return None
    k8s = k8s_client_module()
    return k8s.client.V1ResourceRequirements(limits=limits, requests=requests)


def build_pod_volumes(*, workspace: str, mounts: list[VolumeMount]) -> list[Any]:
    if not mounts:
        return []
    k8s = k8s_client_module()
    return [
        k8s.client.V1Volume(
            name=mount.name,
            persistent_volume_claim=k8s.client.V1PersistentVolumeClaimVolumeSource(
                claim_name=k8s_volume_resource_name(workspace, mount.name),
            ),
        )
        for mount in mounts
    ]


def build_volume_mounts(mounts: list[VolumeMount]) -> list[Any]:
    if not mounts:
        return []
    k8s = k8s_client_module()
    return [
        k8s.client.V1VolumeMount(
            name=mount.name,
            mount_path=mount.mount_path,
            read_only=mount.read_only,
            sub_path=mount.sub_path,
        )
        for mount in mounts
    ]


def build_container_spec(container: Container, *, volume_mounts: list[VolumeMount] | None = None) -> Any:
    k8s = k8s_client_module()
    kwargs: dict[str, Any] = {
        "name": container.name,
        "image": container.image,
        "env": build_env_vars(container) or None,
        "resources": build_resource_requirements(container),
    }
    if container.command:
        kwargs["command"] = list(container.command)
    if container.args:
        kwargs["args"] = list(container.args)
    if volume_mounts:
        kwargs["volume_mounts"] = build_volume_mounts(volume_mounts)
    return k8s.client.V1Container(**kwargs)


@dataclass(frozen=True)
class CompiledWorkload:
    """Kubernetes objects derived from a DeploymentConfig."""

    pod_spec_kwargs: dict[str, Any]
    configmap_body: Any | None
    configmap_name: str | None
    service_containers: tuple[Container, ...]


def _reraise_api_unless(exc: ApiException, *allowed_statuses: int) -> None:
    if exc.status not in allowed_statuses:
        raise exc


def _validate_port_names(config: DeploymentConfig) -> None:
    seen_names: set[str] = set()
    seen_ports: set[tuple[int, str]] = set()
    for container in (*config.init_containers, *config.containers):
        for port in container.ports:
            port_name = port.name or f"port-{port.container_port}"
            if port_name in seen_names:
                raise DeploymentConfigError(f"duplicate container port name {port_name!r}")
            seen_names.add(port_name)
            port_key = (port.container_port, port.protocol)
            if port_key in seen_ports:
                raise DeploymentConfigError(
                    f"duplicate container port {port.container_port}/{port.protocol} across containers"
                )
            seen_ports.add(port_key)


def validate_workload_config(config: DeploymentConfig) -> None:
    """Validate container lists shared by Job and Deployment backends."""
    if not config.containers:
        raise DeploymentConfigError("at least one container is required")
    _validate_port_names(config)
    for container in config.containers:
        if container.restart_policy is not None:
            raise DeploymentConfigError(
                f"container {container.name} sets restart_policy; only init_containers may use per-container restart_policy"
            )
    for init_container in config.init_containers:
        if init_container.restart_policy not in (None, NATIVE_SIDECAR_RESTART_POLICY):
            raise DeploymentConfigError(
                f"init container {init_container.name} has unsupported restart_policy "
                f"{init_container.restart_policy!r}; only Always (native sidecar) is supported"
            )


def validate_config_for_job(config: DeploymentConfig) -> None:
    validate_workload_config(config)
    if config.restart_policy == "Always":
        raise DeploymentConfigError("restart_policy Always requires a Deployment workload, not a Job")


def validate_config_for_deployment(config: DeploymentConfig) -> None:
    validate_workload_config(config)
    if config.restart_policy != "Always":
        raise DeploymentConfigError("restart_policy Always is required for Deployment + Service")


def configmap_data_key(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    key = normalized.lstrip("/").replace("/", "__")
    return key or "config"


def _deserialize_k8s(data: dict[str, Any], klass: str) -> Any:
    k8s = k8s_client_module()
    response = SimpleNamespace(data=json.dumps(data))
    return k8s.client.ApiClient().deserialize(response=response, response_type=klass)


def _build_probe(probe: Probe | None) -> Any | None:
    if probe is None:
        return None
    k8s = k8s_client_module()
    kwargs: dict[str, Any] = {
        "initial_delay_seconds": probe.initial_delay_seconds,
        "period_seconds": probe.period_seconds,
        "timeout_seconds": probe.timeout_seconds,
        "failure_threshold": probe.failure_threshold,
    }
    if probe.exec_action is not None:
        kwargs["exec"] = k8s.client.V1ExecAction(command=list(probe.exec_action.command))
    elif probe.http_get is not None:
        kwargs["http_get"] = k8s.client.V1HTTPGetAction(
            path=probe.http_get.path,
            port=probe.http_get.port,
            scheme=probe.http_get.scheme,
        )
    elif probe.tcp_socket is not None:
        kwargs["tcp_socket"] = k8s.client.V1TCPSocketAction(port=probe.tcp_socket.port)
    else:
        return None
    return k8s.client.V1Probe(**kwargs)


def _build_container_ports(ports: list[ContainerPort]) -> list[Any]:
    if not ports:
        return []
    k8s = k8s_client_module()
    return [
        k8s.client.V1ContainerPort(
            name=port.name or f"port-{port.container_port}",
            container_port=port.container_port,
            protocol=port.protocol,
        )
        for port in ports
    ]


def _config_file_mounts(config_files: list[ConfigFile]) -> list[VolumeMount]:
    return [
        VolumeMount(
            name=CONFIG_FILES_VOLUME,
            mountPath=config_file.path,
            readOnly=True,
            subPath=config_file.path.lstrip("/"),
        )
        for config_file in config_files
    ]


def _collect_pvc_mounts(config: DeploymentConfig) -> list[VolumeMount]:
    mounts_by_name: dict[str, VolumeMount] = {}
    for mount in config.volume_mounts:
        mounts_by_name[mount.name] = mount
    for container in (*config.init_containers, *config.containers):
        for mount in container.volume_mounts:
            mounts_by_name[mount.name] = mount
    return list(mounts_by_name.values())


def build_container(
    container: Container,
    *,
    config: DeploymentConfig,
    include_probes: bool,
) -> Any:
    """Build a V1Container from a plugin Container."""
    k8s = k8s_client_module()
    mounts = merged_volume_mounts(config, container)
    if config.config_files:
        mounts = [*mounts, *_config_file_mounts(config.config_files)]
    base = build_container_spec(container, volume_mounts=mounts or None)
    kwargs: dict[str, Any] = {
        "name": base.name,
        "image": base.image,
        "command": base.command,
        "args": base.args,
        "env": base.env,
        "resources": base.resources,
        "volume_mounts": build_volume_mounts(mounts) if mounts else base.volume_mounts,
        "ports": _build_container_ports(container.ports) or None,
    }
    if include_probes:
        kwargs["liveness_probe"] = _build_probe(container.liveness_probe)
        kwargs["readiness_probe"] = _build_probe(container.readiness_probe)
    if container.restart_policy == NATIVE_SIDECAR_RESTART_POLICY:
        kwargs["restart_policy"] = NATIVE_SIDECAR_RESTART_POLICY
    return k8s.client.V1Container(**{key: value for key, value in kwargs.items() if value is not None})


def _ordered_init_containers(config: DeploymentConfig) -> list[Container]:
    sequential = [c for c in config.init_containers if c.restart_policy != NATIVE_SIDECAR_RESTART_POLICY]
    sidecars = [c for c in config.init_containers if c.restart_policy == NATIVE_SIDECAR_RESTART_POLICY]
    return [*sequential, *sidecars]


def build_tolerations(tolerations: list[Toleration]) -> list[Any]:
    if not tolerations:
        return []
    k8s = k8s_client_module()
    return [k8s.client.V1Toleration(**item.model_dump(by_alias=False, exclude_none=True)) for item in tolerations]


def build_affinity(affinity: Affinity | None) -> Any | None:
    if affinity is None:
        return None
    payload = affinity.model_dump(by_alias=True, exclude_none=True)
    if not payload:
        return None
    return _deserialize_k8s(payload, "V1Affinity")


def build_pod_security_context(security_context: PodSecurityContext | None) -> Any | None:
    if security_context is None:
        return None
    k8s = k8s_client_module()
    payload = security_context.model_dump(by_alias=False, exclude_none=True)
    if not payload:
        return None
    return k8s.client.V1PodSecurityContext(**payload)


def build_configmap_body(
    *,
    workspace: str,
    deployment_name: str,
    labels: dict[str, str],
    config_files: list[ConfigFile],
) -> Any | None:
    if not config_files:
        return None
    k8s = k8s_client_module()
    data = {configmap_data_key(config_file.path): config_file.content for config_file in config_files}
    return k8s.client.V1ConfigMap(
        api_version="v1",
        kind="ConfigMap",
        metadata=k8s.client.V1ObjectMeta(
            name=k8s_deployment_configmap_name(workspace, deployment_name),
            labels=labels,
        ),
        data=data,
    )


def _build_config_file_volume(configmap_name: str, config_files: list[ConfigFile]) -> Any:
    k8s = k8s_client_module()
    items = [
        k8s.client.V1KeyToPath(key=configmap_data_key(config_file.path), path=config_file.path.lstrip("/"))
        for config_file in config_files
    ]
    return k8s.client.V1Volume(
        name=CONFIG_FILES_VOLUME,
        config_map=k8s.client.V1ConfigMapVolumeSource(name=configmap_name, items=items),
    )


def compile_workload(
    *,
    config: DeploymentConfig,
    workspace: str,
    deployment_name: str,
    labels: dict[str, str],
    k8s_config: K8sDeploymentConfig | None,
    pod_restart_policy: RestartPolicy,
) -> CompiledWorkload:
    """Compile pod spec kwargs and optional ConfigMap for a Job or Deployment."""
    validate_workload_config(config)
    pvc_mounts = _collect_pvc_mounts(config)
    volumes = build_pod_volumes(workspace=workspace, mounts=pvc_mounts)
    configmap_body = build_configmap_body(
        workspace=workspace,
        deployment_name=deployment_name,
        labels=labels,
        config_files=config.config_files,
    )
    configmap_name = configmap_body.metadata.name if configmap_body is not None else None
    if configmap_name is not None:
        volumes = [*volumes, _build_config_file_volume(configmap_name, config.config_files)]

    init_containers = [
        build_container(
            container,
            config=config,
            include_probes=container.restart_policy == NATIVE_SIDECAR_RESTART_POLICY,
        )
        for container in _ordered_init_containers(config)
    ]
    main_containers = [
        build_container(container, config=config, include_probes=True) for container in config.containers
    ]

    pod_spec_kwargs: dict[str, Any] = {
        "restart_policy": pod_restart_policy,
        "containers": main_containers,
    }
    if init_containers:
        pod_spec_kwargs["init_containers"] = init_containers
    if volumes:
        pod_spec_kwargs["volumes"] = volumes

    if k8s_config is not None:
        tolerations = build_tolerations(k8s_config.tolerations)
        if tolerations:
            pod_spec_kwargs["tolerations"] = tolerations
        affinity = build_affinity(k8s_config.affinity)
        if affinity is not None:
            pod_spec_kwargs["affinity"] = affinity
        security_context = build_pod_security_context(k8s_config.security_context)
        if security_context is not None:
            pod_spec_kwargs["security_context"] = security_context
        if k8s_config.service_account:
            pod_spec_kwargs["service_account_name"] = k8s_config.service_account

    return CompiledWorkload(
        pod_spec_kwargs=pod_spec_kwargs,
        configmap_body=configmap_body,
        configmap_name=configmap_name,
        service_containers=tuple(config.containers),
    )


def create_configmap(
    core_v1: Any,
    *,
    namespace: str,
    body: Any,
    expected_labels: dict[str, str],
    timeout: float | None,
) -> None:
    try:
        core_v1.create_namespaced_config_map(namespace=namespace, body=body, _request_timeout=timeout)
    except ApiException as exc:
        _reraise_api_unless(exc, 409)
        existing = core_v1.read_namespaced_config_map(
            name=body.metadata.name,
            namespace=namespace,
            _request_timeout=timeout,
        )
        if not resource_labels_match(existing, expected_labels):
            raise


def delete_configmap_best_effort(
    core_v1: Any,
    *,
    namespace: str,
    name: str | None,
    expected_labels: dict[str, str],
    timeout: float | None,
) -> None:
    if name is None:
        return
    try:
        delete_configmap(
            core_v1,
            namespace=namespace,
            name=name,
            expected_labels=expected_labels,
            timeout=timeout,
        )
    except ApiException:
        logger.debug("Best-effort ConfigMap cleanup failed for %s", name, exc_info=True)


def delete_configmap(
    core_v1: Any,
    *,
    namespace: str,
    name: str,
    expected_labels: dict[str, str],
    timeout: float | None,
) -> None:
    try:
        configmap = core_v1.read_namespaced_config_map(name=name, namespace=namespace, _request_timeout=timeout)
    except ApiException as exc:
        _reraise_api_unless(exc, 404)
        return
    if not resource_labels_match(configmap, expected_labels):
        return
    try:
        core_v1.delete_namespaced_config_map(name=name, namespace=namespace, _request_timeout=timeout)
    except ApiException as exc:
        _reraise_api_unless(exc, 404)
