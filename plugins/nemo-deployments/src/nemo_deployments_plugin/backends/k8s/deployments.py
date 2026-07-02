# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Kubernetes Deployment + Service lifecycle for long-running workloads (Always).

The official kubernetes-client is synchronous; ``asyncio.to_thread`` matches the
Job backend (``jobs.py``). Async client support is not in scope for this phase.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from kubernetes.client.rest import ApiException
from nemo_deployments_plugin.backends.base import BackendStatusUpdate, LogResult
from nemo_deployments_plugin.backends.k8s.client import KubernetesClients, k8s_client_module
from nemo_deployments_plugin.backends.k8s.jobs import (
    DeploymentConfigError,
    build_container_spec,
    build_pod_volumes,
    build_volume_mounts,
    merged_volume_mounts,
    newest_pod,
    resolve_deployment_namespace,
    resolve_k8s_deployment_config,
    trim_log_text,
)
from nemo_deployments_plugin.backends.k8s.status import (
    missing_deployment_status,
    resource_labels_match,
    status_from_deployment,
)
from nemo_deployments_plugin.backends.labels import (
    CONFIG_NAME_LABEL,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    RESTART_POLICY_LABEL,
    deployment_identity_labels,
    k8s_deployment_resource_name,
    managed_by_label_selector,
)
from nemo_deployments_plugin.entities import Container, ContainerPort, DeploymentConfig, Probe, VolumeMount
from nemo_deployments_plugin.types import Endpoint, RestartPolicy

logger = logging.getLogger(__name__)

APP_LABEL = "app"
DEFAULT_SERVICE_PORT = 8080


def app_selector_labels(resource_name: str) -> dict[str, str]:
    return {APP_LABEL: resource_name}


def validate_config_for_deployment(config: DeploymentConfig) -> Container:
    """Return the sole container spec for a Deployment-backed deployment."""
    if config.init_containers:
        # User-specified initContainers are deferred to phase 5. Mesh sidecars (Istio,
        # Linkerd) inject at admission time and do not appear in DeploymentConfig.
        raise DeploymentConfigError("init_containers are not supported by the k8s Deployment backend in this phase")
    if len(config.containers) != 1:
        raise DeploymentConfigError(
            f"k8s Deployment backend supports exactly one container; got {len(config.containers)}"
        )
    if config.restart_policy != "Always":
        raise DeploymentConfigError("restart_policy Always is required for Deployment + Service")
    return config.containers[0]


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


def build_deployment_container_spec(container: Container, *, volume_mounts: list[VolumeMount] | None = None) -> Any:
    k8s = k8s_client_module()
    base = build_container_spec(container, volume_mounts=volume_mounts)
    ports = _build_container_ports(container.ports)
    kwargs: dict[str, Any] = {
        "name": base.name,
        "image": base.image,
        "command": base.command,
        "args": base.args,
        "env": base.env,
        "resources": base.resources,
        "volume_mounts": build_volume_mounts(volume_mounts) if volume_mounts else base.volume_mounts,
        "ports": ports or None,
        "liveness_probe": _build_probe(container.liveness_probe),
        "readiness_probe": _build_probe(container.readiness_probe),
    }
    return k8s.client.V1Container(**{key: value for key, value in kwargs.items() if value is not None})


def build_deployment_body(
    *,
    resource_name: str,
    labels: dict[str, str],
    config: DeploymentConfig,
    container: Container,
    workspace: str,
) -> Any:
    """Build an ``apps/v1.Deployment`` for create."""
    k8s = k8s_client_module()
    selector_labels = app_selector_labels(resource_name)
    pod_labels = selector_labels | labels
    mounts = merged_volume_mounts(config, container)
    pod_spec_kwargs: dict[str, Any] = {
        "containers": [build_deployment_container_spec(container, volume_mounts=mounts or None)],
    }
    volumes = build_pod_volumes(workspace=workspace, mounts=mounts)
    if volumes:
        pod_spec_kwargs["volumes"] = volumes

    return k8s.client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=k8s.client.V1ObjectMeta(name=resource_name, labels=labels),
        spec=k8s.client.V1DeploymentSpec(
            replicas=1,
            selector=k8s.client.V1LabelSelector(match_labels=selector_labels),
            template=k8s.client.V1PodTemplateSpec(
                metadata=k8s.client.V1ObjectMeta(labels=pod_labels),
                spec=k8s.client.V1PodSpec(**pod_spec_kwargs),
            ),
        ),
    )


def build_service_body(*, resource_name: str, labels: dict[str, str], container: Container) -> Any:
    """Build a ClusterIP ``v1.Service`` exposing container ports in-cluster."""
    k8s = k8s_client_module()
    selector_labels = app_selector_labels(resource_name)
    service_ports: list[Any] = []
    for port in container.ports:
        port_name = port.name or f"port-{port.container_port}"
        service_ports.append(
            k8s.client.V1ServicePort(
                name=port_name,
                port=port.container_port,
                target_port=port_name,
                protocol=port.protocol,
            )
        )
    if not service_ports:
        service_ports.append(
            k8s.client.V1ServicePort(
                name="http",
                port=DEFAULT_SERVICE_PORT,
                target_port=DEFAULT_SERVICE_PORT,
                protocol="TCP",
            )
        )
    return k8s.client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=k8s.client.V1ObjectMeta(name=resource_name, labels=labels),
        spec=k8s.client.V1ServiceSpec(
            type="ClusterIP",
            selector=selector_labels,
            ports=service_ports,
        ),
    )


def build_in_cluster_endpoints(*, resource_name: str, namespace: str, container: Container) -> list[Endpoint]:
    """Build in-cluster HTTP endpoints for exposed container ports."""
    endpoints: list[Endpoint] = []
    host = f"{resource_name}.{namespace}.svc.cluster.local"
    if container.ports:
        for port in container.ports:
            endpoint_name = port.name or f"port-{port.container_port}"
            is_udp = port.protocol == "UDP"
            protocol = "tcp" if is_udp else "http"
            scheme = "tcp" if is_udp else "http"
            endpoints.append(
                Endpoint(
                    name=endpoint_name,
                    url=f"{scheme}://{host}:{port.container_port}",
                    protocol=protocol,
                )
            )
        return endpoints
    endpoints.append(Endpoint(name="http", url=f"http://{host}:{DEFAULT_SERVICE_PORT}", protocol="http"))
    return endpoints


def _label_selector(match_labels: dict[str, str]) -> str:
    return ",".join(f"{key}={value}" for key, value in match_labels.items())


async def _read_newest_pod(
    clients: KubernetesClients,
    *,
    namespace: str,
    match_labels: dict[str, str],
) -> Any | None:
    timeout = clients.request_timeout
    core_v1 = clients.core_v1

    def _list() -> Any | None:
        pods = core_v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=_label_selector(match_labels),
            _request_timeout=timeout,
        )
        if not pods.items:
            return None
        return newest_pod(list(pods.items))

    try:
        return await asyncio.to_thread(_list)
    except Exception:
        logger.debug("Could not list pods for selector %s", match_labels, exc_info=True)
        return None


def _log_cleanup_ignored(resource_name: str, exc: ApiException) -> None:
    logger.debug(
        "Best-effort cleanup of %s failed (resource may already be deleted)",
        resource_name,
        exc_info=exc,
    )


async def create_deployment(
    clients: KubernetesClients,
    *,
    default_namespace: str,
    workspace: str,
    name: str,
    config_name: str,
    labels: dict[str, str],
    backend_config: dict[str, Any],
    config: DeploymentConfig,
) -> BackendStatusUpdate:
    resource_name = k8s_deployment_resource_name(workspace, name)
    try:
        container = validate_config_for_deployment(config)
        k8s_config = resolve_k8s_deployment_config(backend_config)
        namespace = resolve_deployment_namespace(default_namespace=default_namespace, k8s_config=k8s_config)
        identity_labels = deployment_identity_labels(
            workspace,
            name,
            config.restart_policy,
            config_name=config_name,
            backoff_limit=config.backoff_limit,
        )
        all_labels = {**labels, **config.labels, **identity_labels}
        deployment_body = build_deployment_body(
            resource_name=resource_name,
            labels=all_labels,
            config=config,
            container=container,
            workspace=workspace,
        )
        service_body = build_service_body(resource_name=resource_name, labels=all_labels, container=container)
        timeout = clients.request_timeout
        apps_v1 = clients.apps_v1
        core_v1 = clients.core_v1

        def _create() -> Any:
            deployment_created = False
            try:
                apps_v1.create_namespaced_deployment(
                    namespace=namespace,
                    body=deployment_body,
                    _request_timeout=timeout,
                )
                deployment_created = True
            except ApiException as exc:
                if exc.status != 409:
                    raise

            deployment = apps_v1.read_namespaced_deployment(
                name=resource_name,
                namespace=namespace,
                _request_timeout=timeout,
            )
            if not resource_labels_match(deployment, identity_labels):
                if deployment_created:
                    try:
                        apps_v1.delete_namespaced_deployment(
                            name=resource_name,
                            namespace=namespace,
                            propagation_policy="Background",
                            _request_timeout=timeout,
                        )
                    except ApiException as cleanup_exc:
                        _log_cleanup_ignored(resource_name, cleanup_exc)
                return deployment

            try:
                core_v1.create_namespaced_service(
                    namespace=namespace,
                    body=service_body,
                    _request_timeout=timeout,
                )
            except ApiException as exc:
                if exc.status == 409:
                    existing_service = core_v1.read_namespaced_service(
                        name=resource_name,
                        namespace=namespace,
                        _request_timeout=timeout,
                    )
                    if not resource_labels_match(existing_service, identity_labels):
                        if deployment_created:
                            try:
                                apps_v1.delete_namespaced_deployment(
                                    name=resource_name,
                                    namespace=namespace,
                                    propagation_policy="Background",
                                    _request_timeout=timeout,
                                )
                            except ApiException as cleanup_exc:
                                _log_cleanup_ignored(resource_name, cleanup_exc)
                        raise
                    return deployment
                if deployment_created:
                    try:
                        apps_v1.delete_namespaced_deployment(
                            name=resource_name,
                            namespace=namespace,
                            propagation_policy="Background",
                            _request_timeout=timeout,
                        )
                    except ApiException as cleanup_exc:
                        _log_cleanup_ignored(resource_name, cleanup_exc)
                raise
            return deployment

        deployment = await asyncio.to_thread(_create)
        endpoints = build_in_cluster_endpoints(resource_name=resource_name, namespace=namespace, container=container)
        pod = await _read_newest_pod(clients, namespace=namespace, match_labels=app_selector_labels(resource_name))
        return status_from_deployment(
            deployment=deployment,
            deployment_name=resource_name,
            expected_labels=identity_labels,
            endpoints=endpoints,
            pod=pod,
        )
    except DeploymentConfigError as exc:
        return BackendStatusUpdate(status="FAILED", status_message=str(exc))
    except Exception as exc:
        logger.exception("Failed to create Deployment %s", resource_name)
        return BackendStatusUpdate(status="FAILED", status_message=f"Failed to create Deployment: {exc}")


async def read_deployment_status(
    clients: KubernetesClients,
    *,
    default_namespace: str,
    workspace: str,
    name: str,
    backend_config: dict[str, Any],
    config_name: str,
    restart_policy: RestartPolicy,
    backoff_limit: int,
    container: Container,
) -> BackendStatusUpdate:
    resource_name = k8s_deployment_resource_name(workspace, name)
    expected_labels = deployment_identity_labels(
        workspace,
        name,
        restart_policy,
        config_name=config_name,
        backoff_limit=backoff_limit,
    )
    try:
        k8s_config = resolve_k8s_deployment_config(backend_config)
        namespace = resolve_deployment_namespace(default_namespace=default_namespace, k8s_config=k8s_config)
        timeout = clients.request_timeout
        apps_v1 = clients.apps_v1

        def _read() -> Any:
            return apps_v1.read_namespaced_deployment(
                name=resource_name,
                namespace=namespace,
                _request_timeout=timeout,
            )

        deployment = await asyncio.to_thread(_read)
        deployment_labels = (deployment.metadata.labels or {}) if deployment.metadata else {}
        if not deployment_labels.get(CONFIG_NAME_LABEL):
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"Deployment {resource_name} is missing deployment config identity labels",
            )
        endpoints = build_in_cluster_endpoints(resource_name=resource_name, namespace=namespace, container=container)
        pod = await _read_newest_pod(clients, namespace=namespace, match_labels=app_selector_labels(resource_name))
        return status_from_deployment(
            deployment=deployment,
            deployment_name=resource_name,
            expected_labels=expected_labels,
            endpoints=endpoints,
            pod=pod,
        )
    except ApiException as exc:
        if exc.status == 404:
            return missing_deployment_status(deployment_name=resource_name)
        return BackendStatusUpdate(status="FAILED", status_message=f"Failed to read Deployment: {exc}")
    except Exception as exc:
        return BackendStatusUpdate(status="FAILED", status_message=f"Failed to read Deployment: {exc}")


async def delete_deployment(
    clients: KubernetesClients,
    *,
    default_namespace: str,
    workspace: str,
    name: str,
    backend_config: dict[str, Any],
    expected_labels: dict[str, str],
) -> BackendStatusUpdate:
    resource_name = k8s_deployment_resource_name(workspace, name)
    try:
        k8s_config = resolve_k8s_deployment_config(backend_config)
        namespace = resolve_deployment_namespace(default_namespace=default_namespace, k8s_config=k8s_config)
        timeout = clients.request_timeout
        apps_v1 = clients.apps_v1
        core_v1 = clients.core_v1

        def _delete() -> str | None:
            try:
                deployment = apps_v1.read_namespaced_deployment(
                    name=resource_name,
                    namespace=namespace,
                    _request_timeout=timeout,
                )
            except ApiException as exc:
                if exc.status == 404:
                    try:
                        service = core_v1.read_namespaced_service(
                            name=resource_name,
                            namespace=namespace,
                            _request_timeout=timeout,
                        )
                    except ApiException as service_read_exc:
                        if service_read_exc.status != 404:
                            raise
                        return None
                    if resource_labels_match(service, expected_labels):
                        try:
                            core_v1.delete_namespaced_service(
                                name=resource_name,
                                namespace=namespace,
                                _request_timeout=timeout,
                            )
                        except ApiException as service_exc:
                            if service_exc.status != 404:
                                raise
                    return None
                raise
            if not resource_labels_match(deployment, expected_labels):
                return "foreign"
            apps_v1.delete_namespaced_deployment(
                name=resource_name,
                namespace=namespace,
                propagation_policy="Background",
                _request_timeout=timeout,
            )
            try:
                core_v1.delete_namespaced_service(
                    name=resource_name,
                    namespace=namespace,
                    _request_timeout=timeout,
                )
            except ApiException as exc:
                if exc.status != 404:
                    raise
            return "deleted"

        result = await asyncio.to_thread(_delete)
        if result == "foreign":
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"Deployment {resource_name} exists but is not managed by this plugin",
            )
        return BackendStatusUpdate(status="SUCCEEDED", status_message=f"Deployment {resource_name} deleted")
    except Exception as exc:
        return BackendStatusUpdate(status="FAILED", status_message=f"Failed to delete Deployment: {exc}")


async def list_managed_deployment_names(clients: KubernetesClients, *, default_namespace: str) -> list[str]:
    """List plugin-managed Deployments with restart_policy Always in the default namespace."""
    timeout = clients.request_timeout
    apps_v1 = clients.apps_v1
    label_selector = f"{managed_by_label_selector()},{RESTART_POLICY_LABEL}=Always"

    def _list() -> Any:
        return apps_v1.list_namespaced_deployment(
            namespace=default_namespace,
            label_selector=label_selector,
            _request_timeout=timeout,
        )

    try:
        result = await asyncio.to_thread(_list)
    except Exception:
        logger.warning("Failed to list managed Deployments", exc_info=True)
        return []

    seen: set[str] = set()
    for deployment in result.items or []:
        labels = (deployment.metadata.labels or {}) if deployment.metadata else {}
        workspace = labels.get(DEPLOYMENT_WORKSPACE_LABEL)
        dep_name = labels.get(DEPLOYMENT_NAME_LABEL)
        if workspace and dep_name:
            seen.add(f"{workspace}/{dep_name}")
    return sorted(seen)


async def get_deployment_logs(
    clients: KubernetesClients,
    *,
    default_namespace: str,
    workspace: str,
    name: str,
    backend_config: dict[str, Any],
    tail: int,
) -> LogResult:
    resource_name = k8s_deployment_resource_name(workspace, name)
    try:
        k8s_config = resolve_k8s_deployment_config(backend_config)
        namespace = resolve_deployment_namespace(default_namespace=default_namespace, k8s_config=k8s_config)
        timeout = clients.request_timeout
        core_v1 = clients.core_v1
        selector = _label_selector(app_selector_labels(resource_name))

        def _logs() -> str:
            pods = core_v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=selector,
                _request_timeout=timeout,
            )
            if not pods.items:
                return ""
            pod = newest_pod(list(pods.items))
            if pod is None or pod.metadata is None:
                return ""
            return core_v1.read_namespaced_pod_log(
                name=pod.metadata.name,
                namespace=namespace,
                tail_lines=tail,
                timestamps=True,
                _request_timeout=timeout,
            )

        text = await asyncio.to_thread(_logs)
        lines, truncated = trim_log_text(text)
        return LogResult(lines=lines, truncated=truncated)
    except ApiException as exc:
        if exc.status == 404:
            return LogResult(lines=[])
        return LogResult(lines=[f"Failed to read Deployment logs: {exc}"])
    except Exception as exc:
        return LogResult(lines=[f"Failed to read Deployment logs: {exc}"])
