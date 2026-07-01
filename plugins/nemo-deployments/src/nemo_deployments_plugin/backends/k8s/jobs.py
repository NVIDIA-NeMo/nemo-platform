# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Kubernetes Job lifecycle helpers for finite deployments (Never / OnFailure)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from kubernetes.client.rest import ApiException
from nemo_deployments_plugin.backends.base import BackendStatusUpdate, LogResult
from nemo_deployments_plugin.backends.k8s.client import KubernetesClients, _kubernetes_modules
from nemo_deployments_plugin.backends.k8s.status import (
    LOG_MAX_CHARS,
    missing_job_status,
    status_from_job,
)
from nemo_deployments_plugin.backends.labels import (
    BACKOFF_LIMIT_LABEL,
    CONFIG_NAME_LABEL,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    RESTART_POLICY_LABEL,
    deployment_identity_labels,
    k8s_deployment_resource_name,
    k8s_volume_resource_name,
    managed_by_label_selector,
)
from nemo_deployments_plugin.entities import Container, DeploymentConfig, K8sDeploymentConfig, VolumeMount
from nemo_deployments_plugin.types import RestartPolicy

logger = logging.getLogger(__name__)


class DeploymentConfigError(ValueError):
    """Invalid deployment config for k8s Job backend."""


def resolve_k8s_deployment_config(backend_config: dict[str, Any]) -> K8sDeploymentConfig | None:
    """Parse and validate the k8s section of entity backend_config."""
    k8s_section = backend_config.get("k8s")
    if not k8s_section:
        return None
    return K8sDeploymentConfig.model_validate(k8s_section)


def resolve_deployment_namespace(*, default_namespace: str, k8s_config: K8sDeploymentConfig | None) -> str:
    """Resolve target namespace from parsed k8s deployment config."""
    if k8s_config is None or not k8s_config.namespace:
        return default_namespace
    return k8s_config.namespace


def restart_policy_from_labels(job_labels: dict[str, str], *, default: RestartPolicy = "Never") -> RestartPolicy:
    value = job_labels.get(RESTART_POLICY_LABEL, default)
    if value == "Never":
        return "Never"
    if value == "OnFailure":
        return "OnFailure"
    if value == "Always":
        return "Always"
    return default


def validate_config_for_job(config: DeploymentConfig) -> Container:
    """Return the sole container spec for a Job-backed deployment."""
    if config.init_containers:
        raise DeploymentConfigError("init_containers are not supported by the k8s Job backend in this phase")
    if len(config.containers) != 1:
        raise DeploymentConfigError(f"k8s Job backend supports exactly one container; got {len(config.containers)}")
    if config.restart_policy == "Always":
        raise DeploymentConfigError("restart_policy Always uses Deployment, not Job")
    return config.containers[0]


def merged_volume_mounts(config: DeploymentConfig, container: Container) -> list[VolumeMount]:
    by_name: dict[str, VolumeMount] = {}
    for mount in config.volume_mounts:
        by_name[mount.name] = mount
    for mount in container.volume_mounts:
        by_name[mount.name] = mount
    return list(by_name.values())


def job_backoff_limit(config: DeploymentConfig) -> int:
    if config.restart_policy == "Never":
        return 0
    return config.backoff_limit


def build_env_vars(container: Container) -> list[Any]:
    client, _ = _kubernetes_modules()
    return [client.V1EnvVar(name=item.name, value=item.value) for item in container.env if item.value is not None]


def build_resource_requirements(container: Container) -> Any | None:
    limits = container.resources.limits or None
    requests = container.resources.requests or None
    if not limits and not requests:
        return None
    client, _ = _kubernetes_modules()
    return client.V1ResourceRequirements(limits=limits, requests=requests)


def build_pod_volumes(*, workspace: str, mounts: list[VolumeMount]) -> list[Any]:
    if not mounts:
        return []
    client, _ = _kubernetes_modules()
    return [
        client.V1Volume(
            name=mount.name,
            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                claim_name=k8s_volume_resource_name(workspace, mount.name),
            ),
        )
        for mount in mounts
    ]


def build_volume_mounts(mounts: list[VolumeMount]) -> list[Any]:
    if not mounts:
        return []
    client, _ = _kubernetes_modules()
    return [
        client.V1VolumeMount(
            name=mount.name,
            mount_path=mount.mount_path,
            read_only=mount.read_only,
            sub_path=mount.sub_path,
        )
        for mount in mounts
    ]


def build_container_spec(container: Container, *, volume_mounts: list[VolumeMount] | None = None) -> Any:
    client, _ = _kubernetes_modules()
    command: list[str] | None = None
    if container.command or container.args:
        command = list(container.command) + list(container.args)
    kwargs: dict[str, Any] = {
        "name": container.name,
        "image": container.image,
        "env": build_env_vars(container) or None,
        "resources": build_resource_requirements(container),
    }
    if command:
        kwargs["command"] = command
    if volume_mounts:
        kwargs["volume_mounts"] = build_volume_mounts(volume_mounts)
    return client.V1Container(**kwargs)


def build_job_body(
    *,
    job_name: str,
    labels: dict[str, str],
    config: DeploymentConfig,
    container: Container,
    workspace: str,
) -> Any:
    """Build a ``batch/v1.Job`` for create."""
    client, _ = _kubernetes_modules()
    mounts = merged_volume_mounts(config, container)
    pod_spec_kwargs: dict[str, Any] = {
        "restart_policy": "Never",
        "containers": [build_container_spec(container, volume_mounts=mounts or None)],
    }
    volumes = build_pod_volumes(workspace=workspace, mounts=mounts)
    if volumes:
        pod_spec_kwargs["volumes"] = volumes

    return client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=job_name, labels=labels),
        spec=client.V1JobSpec(
            backoff_limit=job_backoff_limit(config),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=client.V1PodSpec(**pod_spec_kwargs),
            ),
        ),
    )


async def read_pod_exit_code(
    clients: KubernetesClients,
    *,
    namespace: str,
    job_name: str,
) -> int | None:
    """Best-effort container exit code from the Job's most recent pod."""
    timeout = clients.request_timeout
    core_v1 = clients.core_v1

    def _read() -> int | None:
        pods = core_v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=f"job-name={job_name}",
            _request_timeout=timeout,
        )
        if not pods.items:
            return None
        pod = pods.items[-1]
        if pod.status is None or not pod.status.container_statuses:
            return None
        for container_status in pod.status.container_statuses:
            terminated = container_status.state.terminated if container_status.state else None
            if terminated is not None:
                return int(terminated.exit_code)
        return None

    try:
        return await asyncio.to_thread(_read)
    except Exception:
        logger.debug("Could not read exit code for Job %s", job_name, exc_info=True)
        return None


async def create_job(
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
    job_name = k8s_deployment_resource_name(workspace, name)
    try:
        container = validate_config_for_job(config)
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
        body = build_job_body(
            job_name=job_name,
            labels=all_labels,
            config=config,
            container=container,
            workspace=workspace,
        )
        timeout = clients.request_timeout
        batch_v1 = clients.batch_v1

        def _create() -> Any:
            try:
                return batch_v1.create_namespaced_job(
                    namespace=namespace,
                    body=body,
                    _request_timeout=timeout,
                )
            except ApiException as exc:
                if exc.status == 409:
                    return batch_v1.read_namespaced_job(
                        name=job_name,
                        namespace=namespace,
                        _request_timeout=timeout,
                    )
                raise

        job = await asyncio.to_thread(_create)
        update = status_from_job(job=job, job_name=job_name, expected_labels=identity_labels)
        if update.status in ("SUCCEEDED", "FAILED"):
            exit_code = await read_pod_exit_code(clients, namespace=namespace, job_name=job_name)
            if exit_code is not None:
                update = update.model_copy(update={"exit_code": exit_code})
        return update
    except DeploymentConfigError as exc:
        return BackendStatusUpdate(status="FAILED", status_message=str(exc))
    except Exception as exc:
        logger.exception("Failed to create Job %s", job_name)
        return BackendStatusUpdate(status="FAILED", status_message=f"Failed to create Job: {exc}")


async def read_job_status(
    clients: KubernetesClients,
    *,
    default_namespace: str,
    workspace: str,
    name: str,
    backend_config: dict[str, Any],
) -> BackendStatusUpdate:
    job_name = k8s_deployment_resource_name(workspace, name)
    try:
        k8s_config = resolve_k8s_deployment_config(backend_config)
        namespace = resolve_deployment_namespace(default_namespace=default_namespace, k8s_config=k8s_config)
        timeout = clients.request_timeout
        batch_v1 = clients.batch_v1

        def _read() -> Any:
            return batch_v1.read_namespaced_job(
                name=job_name,
                namespace=namespace,
                _request_timeout=timeout,
            )

        job = await asyncio.to_thread(_read)
        job_labels = (job.metadata.labels or {}) if job.metadata else {}
        config_name = job_labels.get(CONFIG_NAME_LABEL)
        if not config_name:
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"Job {job_name} is missing deployment config identity labels",
            )
        restart_policy = restart_policy_from_labels(job_labels)
        read_expected = deployment_identity_labels(
            workspace,
            name,
            restart_policy,
            config_name=config_name,
            backoff_limit=int(job_labels.get(BACKOFF_LIMIT_LABEL, "6")),
        )
        update = status_from_job(job=job, job_name=job_name, expected_labels=read_expected)
        if update.status in ("SUCCEEDED", "FAILED"):
            exit_code = await read_pod_exit_code(clients, namespace=namespace, job_name=job_name)
            if exit_code is not None:
                update = update.model_copy(update={"exit_code": exit_code})
        return update
    except ApiException as exc:
        if exc.status == 404:
            return missing_job_status(job_name=job_name)
        return BackendStatusUpdate(status="FAILED", status_message=f"Failed to read Job: {exc}")
    except Exception as exc:
        return BackendStatusUpdate(status="FAILED", status_message=f"Failed to read Job: {exc}")


async def delete_job(
    clients: KubernetesClients,
    *,
    default_namespace: str,
    workspace: str,
    name: str,
    backend_config: dict[str, Any],
) -> BackendStatusUpdate:
    job_name = k8s_deployment_resource_name(workspace, name)
    try:
        k8s_config = resolve_k8s_deployment_config(backend_config)
        namespace = resolve_deployment_namespace(default_namespace=default_namespace, k8s_config=k8s_config)
        timeout = clients.request_timeout
        batch_v1 = clients.batch_v1

        def _delete() -> None:
            try:
                batch_v1.delete_namespaced_job(
                    name=job_name,
                    namespace=namespace,
                    propagation_policy="Background",
                    _request_timeout=timeout,
                )
            except ApiException as exc:
                if exc.status == 404:
                    return
                raise

        await asyncio.to_thread(_delete)
        return BackendStatusUpdate(status="SUCCEEDED", status_message=f"Job {job_name} deleted")
    except Exception as exc:
        return BackendStatusUpdate(status="FAILED", status_message=f"Failed to delete Job: {exc}")


async def list_managed_job_names(clients: KubernetesClients, *, default_namespace: str) -> list[str]:
    timeout = clients.request_timeout
    batch_v1 = clients.batch_v1
    label_selector = managed_by_label_selector()

    def _list() -> Any:
        return batch_v1.list_namespaced_job(
            namespace=default_namespace,
            label_selector=label_selector,
            _request_timeout=timeout,
        )

    try:
        result = await asyncio.to_thread(_list)
    except Exception:
        logger.warning("Failed to list managed Jobs", exc_info=True)
        return []

    seen: set[str] = set()
    for job in result.items or []:
        labels = (job.metadata.labels or {}) if job.metadata else {}
        workspace = labels.get(DEPLOYMENT_WORKSPACE_LABEL)
        dep_name = labels.get(DEPLOYMENT_NAME_LABEL)
        if workspace and dep_name:
            seen.add(f"{workspace}/{dep_name}")
    return sorted(seen)


async def get_job_logs(
    clients: KubernetesClients,
    *,
    default_namespace: str,
    workspace: str,
    name: str,
    backend_config: dict[str, Any],
    tail: int,
) -> LogResult:
    job_name = k8s_deployment_resource_name(workspace, name)
    try:
        k8s_config = resolve_k8s_deployment_config(backend_config)
        namespace = resolve_deployment_namespace(default_namespace=default_namespace, k8s_config=k8s_config)
        timeout = clients.request_timeout
        core_v1 = clients.core_v1

        def _logs() -> str:
            pods = core_v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"job-name={job_name}",
                _request_timeout=timeout,
            )
            if not pods.items:
                return ""
            pod_name = pods.items[0].metadata.name
            raw = core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                tail_lines=tail,
                timestamps=True,
                _request_timeout=timeout,
            )
            return raw

        text = await asyncio.to_thread(_logs)
        lines = text.splitlines() if text else []
        truncated = len(text) > LOG_MAX_CHARS
        if truncated:
            lines = lines[-tail:]
        return LogResult(lines=lines, truncated=truncated)
    except ApiException as exc:
        if exc.status == 404:
            return LogResult(lines=[])
        return LogResult(lines=[f"Failed to read Job logs: {exc}"])
    except Exception as exc:
        return LogResult(lines=[f"Failed to read Job logs: {exc}"])
