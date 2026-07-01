# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Kubernetes substrate backend for the deployments plugin (scaffold)."""

from __future__ import annotations

import logging
from typing import Any

from nemo_deployments_plugin.backends.base import (
    BackendStatusUpdate,
    DeploymentBackend,
    LogResult,
    VolumeStatusUpdate,
)
from nemo_deployments_plugin.backends.k8s.client import KubernetesClients
from nemo_deployments_plugin.backends.k8s.config import K8sExecutorConfig

logger = logging.getLogger(__name__)

_K8S_INSTALL_HINT = (
    "kubernetes package is required for K8sDeploymentBackend. "
    "Install with: uv sync --package nemo-deployments-plugin --extra k8s"
)


class K8sDeploymentBackend(DeploymentBackend):
    """Manage deployments and volumes as native Kubernetes objects.

    Lifecycle methods not yet implemented raise ``NotImplementedError`` (not ``...``) so
    accidental calls fail loudly during phased rollout; ``...`` is for ``@abstractmethod``
    stubs on the ABC itself.
    """

    _clients: KubernetesClients

    def init(self) -> None:
        try:
            import kubernetes  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(_K8S_INSTALL_HINT) from exc

        self._executor_config = K8sExecutorConfig.model_validate(self._config)
        self._clients = KubernetesClients(
            kubeconfig_path=self._executor_config.kubeconfig_path,
            request_timeout=self._executor_config.request_timeout,
        )
        logger.debug(
            "K8sDeploymentBackend initialized (default_namespace=%s)",
            self._executor_config.default_namespace,
        )

    def shutdown(self) -> None:
        if hasattr(self, "_clients"):
            self._clients.close()

    @property
    def executor_config(self) -> K8sExecutorConfig:
        return self._executor_config

    @property
    def clients(self) -> KubernetesClients:
        return self._clients

    async def create_deployment(
        self,
        *,
        workspace: str,
        name: str,
        config_name: str,
        labels: dict[str, str],
        backend_config: dict[str, Any],
    ) -> BackendStatusUpdate:
        raise NotImplementedError("K8s create_deployment is implemented in a later phase.")

    async def read_status(self, *, workspace: str, name: str) -> BackendStatusUpdate:
        raise NotImplementedError("K8s read_status is implemented in a later phase.")

    async def delete_deployment(self, workspace: str, name: str) -> BackendStatusUpdate:
        raise NotImplementedError("K8s delete_deployment is implemented in a later phase.")

    async def list_managed_deployment_names(self) -> list[str]:
        raise NotImplementedError("K8s list_managed_deployment_names is implemented in a later phase.")

    async def get_logs(
        self,
        *,
        workspace: str,
        name: str,
        tail: int = 100,
    ) -> LogResult:
        raise NotImplementedError("K8s get_logs is implemented in a later phase.")

    async def create_volume(
        self,
        *,
        workspace: str,
        name: str,
        size: str,
        access_modes: list[str],
        backend_config: dict[str, Any],
    ) -> VolumeStatusUpdate:
        raise NotImplementedError("K8s create_volume is implemented in a later phase.")

    async def read_volume_status(self, *, workspace: str, name: str) -> VolumeStatusUpdate:
        raise NotImplementedError("K8s read_volume_status is implemented in a later phase.")

    async def delete_volume(self, workspace: str, name: str) -> VolumeStatusUpdate:
        raise NotImplementedError("K8s delete_volume is implemented in a later phase.")
