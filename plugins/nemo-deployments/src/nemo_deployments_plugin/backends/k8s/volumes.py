# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Kubernetes PVC lifecycle helpers for the deployments plugin."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from kubernetes.client.rest import ApiException
from nemo_deployments_plugin.backends.base import VolumeStatusUpdate
from nemo_deployments_plugin.backends.k8s.client import KubernetesClients, k8s_client_module
from nemo_deployments_plugin.backends.labels import k8s_volume_resource_name, volume_identity_labels
from nemo_deployments_plugin.entities import K8sVolumeConfig

logger = logging.getLogger(__name__)


def resolve_volume_config(backend_config: dict[str, Any]) -> K8sVolumeConfig | None:
    """Parse and validate the k8s section of entity backend_config."""
    k8s_section = backend_config.get("k8s")
    if not k8s_section:
        return None
    return K8sVolumeConfig.model_validate(k8s_section)


def resolve_volume_namespace(*, default_namespace: str, volume_config: K8sVolumeConfig | None) -> str:
    """Resolve target namespace from parsed volume config with executor default fallback."""
    if volume_config is not None and volume_config.namespace:
        return volume_config.namespace
    return default_namespace


def build_pvc_body(
    *,
    pvc_name: str,
    labels: dict[str, str],
    size: str,
    access_modes: list[str],
    storage_class: str | None,
) -> Any:
    """Build a ``V1PersistentVolumeClaim`` for create."""
    k8s = k8s_client_module()
    spec_kwargs: dict[str, Any] = {
        "access_modes": list(access_modes),
        "resources": k8s.client.V1VolumeResourceRequirements(requests={"storage": size}),
    }
    if storage_class is not None:
        spec_kwargs["storage_class_name"] = storage_class
    return k8s.client.V1PersistentVolumeClaim(
        api_version="v1",
        kind="PersistentVolumeClaim",
        metadata=k8s.client.V1ObjectMeta(name=pvc_name, labels=labels),
        spec=k8s.client.V1PersistentVolumeClaimSpec(**spec_kwargs),
    )


def map_pvc_phase_to_status(*, pvc_name: str, phase: str | None) -> VolumeStatusUpdate:
    """Map Kubernetes PVC phase to plugin ``VolumeStatus``."""
    if phase == "Bound":
        return VolumeStatusUpdate(status="BOUND", status_message=f"PVC {pvc_name} is bound")
    if phase == "Lost":
        return VolumeStatusUpdate(status="FAILED", status_message=f"PVC {pvc_name} is lost")
    return VolumeStatusUpdate(status="PENDING", status_message=f"PVC {pvc_name} is pending")


def _phase_from_pvc(pvc: Any) -> str | None:
    if pvc.status is None:
        return None
    return pvc.status.phase


def _pvc_is_deleting(pvc: Any) -> bool:
    metadata = getattr(pvc, "metadata", None)
    return bool(metadata and getattr(metadata, "deletion_timestamp", None))


def _pvc_labels_match(pvc: Any, expected_labels: dict[str, str]) -> bool:
    metadata = getattr(pvc, "metadata", None)
    if metadata is None or not metadata.labels:
        return False
    return all(metadata.labels.get(key) == value for key, value in expected_labels.items())


def status_from_pvc(*, pvc: Any, pvc_name: str, expected_labels: dict[str, str]) -> VolumeStatusUpdate:
    """Map a PVC object to plugin status, enforcing identity labels and delete propagation."""
    if not _pvc_labels_match(pvc, expected_labels):
        return VolumeStatusUpdate(
            status="FAILED",
            status_message=f"PVC {pvc_name} exists but is not managed by this plugin",
        )
    if _pvc_is_deleting(pvc):
        return VolumeStatusUpdate(status="DELETING", status_message=f"PVC {pvc_name} is terminating")
    return map_pvc_phase_to_status(pvc_name=pvc_name, phase=_phase_from_pvc(pvc))


async def create_volume(
    clients: KubernetesClients,
    *,
    default_namespace: str,
    workspace: str,
    name: str,
    size: str,
    access_modes: list[str],
    backend_config: dict[str, Any],
) -> VolumeStatusUpdate:
    pvc_name = k8s_volume_resource_name(workspace, name)
    try:
        volume_config = resolve_volume_config(backend_config)
        namespace = resolve_volume_namespace(default_namespace=default_namespace, volume_config=volume_config)
        storage_class = volume_config.storage_class if volume_config else None
        labels = volume_identity_labels(workspace, name)
        body = build_pvc_body(
            pvc_name=pvc_name,
            labels=labels,
            size=size,
            access_modes=access_modes,
            storage_class=storage_class,
        )
        timeout = clients.request_timeout
        core_v1 = clients.core_v1

        def _create() -> Any:
            try:
                return core_v1.create_namespaced_persistent_volume_claim(
                    namespace=namespace,
                    body=body,
                    _request_timeout=timeout,
                )
            except ApiException as exc:
                if exc.status == 409:
                    return core_v1.read_namespaced_persistent_volume_claim(
                        name=pvc_name,
                        namespace=namespace,
                        _request_timeout=timeout,
                    )
                raise

        pvc = await asyncio.to_thread(_create)
        return status_from_pvc(pvc=pvc, pvc_name=pvc_name, expected_labels=labels)
    except Exception as exc:
        logger.exception("Failed to create PVC %s", pvc_name)
        return VolumeStatusUpdate(status="FAILED", status_message=f"Failed to create PVC: {exc}")


async def read_volume_status(
    clients: KubernetesClients,
    *,
    default_namespace: str,
    workspace: str,
    name: str,
    backend_config: dict[str, Any] | None = None,
) -> VolumeStatusUpdate:
    pvc_name = k8s_volume_resource_name(workspace, name)
    expected_labels = volume_identity_labels(workspace, name)
    try:
        volume_config = resolve_volume_config(backend_config or {})
        namespace = resolve_volume_namespace(default_namespace=default_namespace, volume_config=volume_config)
        timeout = clients.request_timeout
        core_v1 = clients.core_v1

        def _read() -> Any:
            return core_v1.read_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=namespace,
                _request_timeout=timeout,
            )

        pvc = await asyncio.to_thread(_read)
        return status_from_pvc(pvc=pvc, pvc_name=pvc_name, expected_labels=expected_labels)
    except ApiException as exc:
        if exc.status == 404:
            return VolumeStatusUpdate(status="FAILED", status_message=f"PVC {pvc_name} not found")
        return VolumeStatusUpdate(status="FAILED", status_message=f"Failed to read PVC: {exc}")
    except Exception as exc:
        return VolumeStatusUpdate(status="FAILED", status_message=f"Failed to read PVC: {exc}")


async def delete_volume(
    clients: KubernetesClients,
    *,
    default_namespace: str,
    workspace: str,
    name: str,
    backend_config: dict[str, Any] | None = None,
) -> VolumeStatusUpdate:
    pvc_name = k8s_volume_resource_name(workspace, name)
    try:
        volume_config = resolve_volume_config(backend_config or {})
        namespace = resolve_volume_namespace(default_namespace=default_namespace, volume_config=volume_config)
        timeout = clients.request_timeout
        core_v1 = clients.core_v1

        def _delete() -> None:
            try:
                core_v1.delete_namespaced_persistent_volume_claim(
                    name=pvc_name,
                    namespace=namespace,
                    _request_timeout=timeout,
                )
            except ApiException as exc:
                if exc.status == 404:
                    return
                raise

        await asyncio.to_thread(_delete)
        return VolumeStatusUpdate(status="RELEASED", status_message=f"PVC {pvc_name} released")
    except Exception as exc:
        return VolumeStatusUpdate(status="FAILED", status_message=f"Failed to delete PVC: {exc}")
