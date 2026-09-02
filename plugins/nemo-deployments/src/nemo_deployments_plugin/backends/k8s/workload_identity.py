# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Kubernetes workload identity delegation reconciliation for deployments."""

from __future__ import annotations

import logging
from typing import Any

from nemo_deployments_plugin.backends.workload_identity import (
    workload_id,
    workload_identity_activation_error,
    workload_identity_requested,
    workload_kind,
)
from nemo_deployments_plugin.entities import DeploymentConfig, K8sDeploymentConfig
from nemo_platform_plugin.auth import AuthContext
from nemo_platform_plugin.auth.workload_delegations import (
    KUBERNETES_POD_UID_REFERENCE_NAME,
    WorkloadDelegationConflictError,
    WorkloadDelegationStore,
)
from nemo_platform_plugin.auth.workload_identity import (
    build_kubernetes_pod_uid_workload_delegation,
    get_workload_delegation_audience,
)

logger = logging.getLogger(__name__)

DEFAULT_SERVICE_ACCOUNT = "default"
_TERMINAL_POD_PHASES = frozenset({"Succeeded", "Failed"})


def service_account_name(
    *,
    config: DeploymentConfig,
    k8s_config: K8sDeploymentConfig | None,
) -> str:
    spec = config.workload_identity
    if spec is not None and spec.service_account_name:
        return spec.service_account_name
    if k8s_config is not None and k8s_config.service_account:
        return k8s_config.service_account
    return DEFAULT_SERVICE_ACCOUNT


async def reconcile_pod_uid_delegations(
    store: WorkloadDelegationStore | None,
    *,
    config: DeploymentConfig,
    auth_context: AuthContext | None,
    workspace: str,
    deployment_name: str,
    namespace: str,
    k8s_config: K8sDeploymentConfig | None,
    pods: list[Any],
) -> None:
    """Register live Pod UID-bound delegations and revoke stale ones for a workload."""
    if store is None or not workload_identity_requested(config):
        return
    error = workload_identity_activation_error(config=config, auth_context=auth_context)
    if error is not None:
        raise ValueError(error)
    if auth_context is None or config.workload_identity is None:
        return

    kind = workload_kind(config)
    logical_id = workload_id(config, deployment_name)
    existing = await store.list_by_workload(
        workload_workspace=workspace,
        workload_kind=kind,
        workload_id=logical_id,
    )
    existing_by_pod_uid = {
        entity.bound_reference_value: entity
        for entity in existing
        if entity.bound_reference_name == KUBERNETES_POD_UID_REFERENCE_NAME and entity.bound_reference_value
    }
    live_pod_uid_set: set[str] = set()
    for pod in pods:
        pod_uid = _pod_uid(pod)
        if pod_uid is not None and _pod_is_live(pod):
            live_pod_uid_set.add(pod_uid)
    live_pod_uids = sorted(live_pod_uid_set)

    for pod_uid in live_pod_uids:
        current = existing_by_pod_uid.get(pod_uid)
        if current is not None and current.is_active():
            continue
        delegation = build_kubernetes_pod_uid_workload_delegation(
            workload_workspace=workspace,
            workload_audience=get_workload_delegation_audience(),
            workload_kind=kind,
            workload_id=logical_id,
            workload_generation=pod_uid,
            namespace=namespace,
            service_account_name=service_account_name(config=config, k8s_config=k8s_config),
            pod_uid=pod_uid,
            auth_context=auth_context,
            ttl_seconds_active=config.workload_identity.token_expiration_seconds,
        )
        try:
            await store.register(delegation)
        except WorkloadDelegationConflictError:
            logger.debug("Pod UID workload delegation already active", extra={"delegation_name": delegation.name})

    live_set = set(live_pod_uids)
    for pod_uid, entity in existing_by_pod_uid.items():
        if pod_uid not in live_set and entity.is_active():
            await store.revoke(entity.name)


def deployment_pod_uid_delegation_pods(
    *,
    config: DeploymentConfig,
    k8s_config: K8sDeploymentConfig | None,
    resource_name: str,
    pods: list[Any],
) -> list[Any]:
    """Return Pods eligible for Deployment-owned Pod UID delegation."""
    return _pod_uid_delegation_pods(
        config=config,
        k8s_config=k8s_config,
        controller_kind="ReplicaSet",
        controller_name_prefix=f"{resource_name}-",
        pods=pods,
    )


def job_pod_uid_delegation_pods(
    *,
    config: DeploymentConfig,
    k8s_config: K8sDeploymentConfig | None,
    job_name: str,
    pods: list[Any],
) -> list[Any]:
    """Return Pods eligible for Job-owned Pod UID delegation."""
    return _pod_uid_delegation_pods(
        config=config,
        k8s_config=k8s_config,
        controller_kind="Job",
        controller_name=job_name,
        pods=pods,
    )


async def revoke_workload_delegations(
    store: WorkloadDelegationStore | None,
    *,
    config: DeploymentConfig | None,
    workspace: str,
    deployment_name: str,
) -> None:
    """Revoke all delegation rows owned by one logical deployment workload."""
    if store is None or config is None or not workload_identity_requested(config):
        return
    await store.revoke_by_workload(
        workload_workspace=workspace,
        workload_kind=workload_kind(config),
        workload_id=workload_id(config, deployment_name),
    )


def _pod_uid_delegation_pods(
    *,
    config: DeploymentConfig,
    k8s_config: K8sDeploymentConfig | None,
    controller_kind: str,
    pods: list[Any],
    controller_name: str | None = None,
    controller_name_prefix: str | None = None,
) -> list[Any]:
    expected_service_account = service_account_name(config=config, k8s_config=k8s_config)
    return [
        pod
        for pod in pods
        if _pod_has_controller_owner(
            pod,
            controller_kind=controller_kind,
            controller_name=controller_name,
            controller_name_prefix=controller_name_prefix,
        )
        and _pod_service_account_name(pod) == expected_service_account
    ]


def _pod_has_controller_owner(
    pod: Any,
    *,
    controller_kind: str,
    controller_name: str | None,
    controller_name_prefix: str | None,
) -> bool:
    metadata = getattr(pod, "metadata", None)
    owner_references = getattr(metadata, "owner_references", None) if metadata is not None else None
    for owner_reference in owner_references or []:
        if getattr(owner_reference, "controller", False) is not True:
            continue
        if getattr(owner_reference, "kind", None) != controller_kind:
            continue
        owner_name = getattr(owner_reference, "name", None)
        if not isinstance(owner_name, str):
            continue
        if controller_name is not None and owner_name == controller_name:
            return True
        if controller_name_prefix is not None and owner_name.startswith(controller_name_prefix):
            return True
    return False


def _pod_service_account_name(pod: Any) -> str:
    spec = getattr(pod, "spec", None)
    if spec is None:
        return DEFAULT_SERVICE_ACCOUNT
    name = getattr(spec, "service_account_name", None) or getattr(spec, "service_account", None)
    return name if isinstance(name, str) and name else DEFAULT_SERVICE_ACCOUNT


def _pod_uid(pod: Any) -> str | None:
    metadata = getattr(pod, "metadata", None)
    uid = getattr(metadata, "uid", None) if metadata is not None else None
    return uid if isinstance(uid, str) and uid else None


def _pod_is_live(pod: Any) -> bool:
    metadata = getattr(pod, "metadata", None)
    if metadata is not None and getattr(metadata, "deletion_timestamp", None):
        return False
    status = getattr(pod, "status", None)
    phase = getattr(status, "phase", None) if status is not None else None
    return phase not in _TERMINAL_POD_PHASES
