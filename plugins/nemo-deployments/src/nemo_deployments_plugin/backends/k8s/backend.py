# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Kubernetes substrate backend for the deployments plugin."""

from __future__ import annotations

import logging
from typing import Any

from nemo_deployments_plugin.backends.base import (
    BackendStatusUpdate,
    DeploymentBackend,
    LogResult,
    VolumeStatusUpdate,
)
from nemo_deployments_plugin.backends.k8s import jobs as job_ops
from nemo_deployments_plugin.backends.k8s import volumes as volume_ops
from nemo_deployments_plugin.backends.k8s.client import KubernetesClients
from nemo_deployments_plugin.backends.k8s.config import K8sExecutorConfig
from nemo_deployments_plugin.backends.labels import deployment_identity_labels
from nemo_deployments_plugin.entities import Deployment, DeploymentConfig
from nemo_platform.resources.entities import AsyncEntitiesResource
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError

logger = logging.getLogger(__name__)

_K8S_INSTALL_HINT = (
    "kubernetes package is required for K8sDeploymentBackend. "
    "Install with: uv sync --package nemo-deployments-plugin --extra k8s"
)
_ALWAYS_POLICY_MESSAGE = "restart_policy Always requires Deployment+Service support (AIRCORE-757 phase 4)"


class K8sDeploymentBackend(DeploymentBackend):
    """Manage deployments and volumes as native Kubernetes objects.

    Job-backed deployments (``restart_policy`` Never/OnFailure) are implemented in phase 3.
    Deployment + Service (Always) and full PodSpec compilation land in later phases.
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
        self._entities = NemoEntitiesClient(AsyncEntitiesResource(self._sdk))
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

    async def _load_deployment_config(self, workspace: str, config_name: str) -> DeploymentConfig:
        return await self._entities.get(DeploymentConfig, config_name, workspace=workspace)

    async def _load_deployment_context(
        self,
        workspace: str,
        name: str,
    ) -> tuple[Deployment, DeploymentConfig, dict[str, Any]]:
        deployment = await self._entities.get(Deployment, name, workspace=workspace)
        config = await self._load_deployment_config(workspace, deployment.deployment_config)
        backend_config = config.backend_config.model_dump(by_alias=True, exclude_none=True)
        return deployment, config, backend_config

    async def create_deployment(
        self,
        *,
        workspace: str,
        name: str,
        config_name: str,
        labels: dict[str, str],
        backend_config: dict[str, Any],
    ) -> BackendStatusUpdate:
        try:
            config = await self._load_deployment_config(workspace, config_name)
        except NemoEntityNotFoundError:
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"DeploymentConfig '{config_name}' not found in workspace '{workspace}'",
            )
        except Exception as exc:
            logger.exception("Failed to load deployment config %s/%s", workspace, config_name)
            return BackendStatusUpdate(status="FAILED", status_message=f"Failed to load deployment config: {exc}")

        if config.restart_policy == "Always":
            return BackendStatusUpdate(status="FAILED", status_message=_ALWAYS_POLICY_MESSAGE)

        return await job_ops.create_job(
            self._clients,
            default_namespace=self._executor_config.default_namespace,
            workspace=workspace,
            name=name,
            config_name=config_name,
            labels=labels,
            backend_config=backend_config,
            config=config,
        )

    async def read_status(self, *, workspace: str, name: str) -> BackendStatusUpdate:
        try:
            _, config, backend_config = await self._load_deployment_context(workspace, name)
        except NemoEntityNotFoundError:
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"Deployment '{name}' not found in workspace '{workspace}'",
            )
        except Exception as exc:
            return BackendStatusUpdate(status="FAILED", status_message=f"Failed to load deployment: {exc}")

        if config.restart_policy == "Always":
            return BackendStatusUpdate(status="FAILED", status_message=_ALWAYS_POLICY_MESSAGE)

        return await job_ops.read_job_status(
            self._clients,
            default_namespace=self._executor_config.default_namespace,
            workspace=workspace,
            name=name,
            backend_config=backend_config,
            config_name=config.name,
            restart_policy=config.restart_policy,
            backoff_limit=config.backoff_limit,
        )

    async def delete_deployment(self, workspace: str, name: str) -> BackendStatusUpdate:
        try:
            _, config, backend_config = await self._load_deployment_context(workspace, name)
        except NemoEntityNotFoundError:
            return await job_ops.delete_job(
                self._clients,
                default_namespace=self._executor_config.default_namespace,
                workspace=workspace,
                name=name,
                backend_config={},
                expected_labels=job_ops.deployment_scope_labels(workspace, name),
            )
        except Exception as exc:
            return BackendStatusUpdate(status="FAILED", status_message=f"Failed to load deployment: {exc}")

        if config.restart_policy == "Always":
            return BackendStatusUpdate(status="FAILED", status_message=_ALWAYS_POLICY_MESSAGE)

        return await job_ops.delete_job(
            self._clients,
            default_namespace=self._executor_config.default_namespace,
            workspace=workspace,
            name=name,
            backend_config=backend_config,
            expected_labels=deployment_identity_labels(
                workspace,
                name,
                config.restart_policy,
                config_name=config.name,
                backoff_limit=config.backoff_limit,
            ),
        )

    async def list_managed_deployment_names(self) -> list[str]:
        return await job_ops.list_managed_job_names(
            self._clients,
            default_namespace=self._executor_config.default_namespace,
        )

    async def get_logs(
        self,
        *,
        workspace: str,
        name: str,
        tail: int = 100,
    ) -> LogResult:
        try:
            _, config, backend_config = await self._load_deployment_context(workspace, name)
        except NemoEntityNotFoundError:
            return LogResult(lines=[f"Deployment '{name}' not found in workspace '{workspace}'"])
        except Exception as exc:
            return LogResult(lines=[f"Failed to load deployment: {exc}"])

        if config.restart_policy == "Always":
            return LogResult(lines=[_ALWAYS_POLICY_MESSAGE])

        return await job_ops.get_job_logs(
            self._clients,
            default_namespace=self._executor_config.default_namespace,
            workspace=workspace,
            name=name,
            backend_config=backend_config,
            tail=tail,
        )

    async def create_volume(
        self,
        *,
        workspace: str,
        name: str,
        size: str,
        access_modes: list[str],
        backend_config: dict[str, Any],
    ) -> VolumeStatusUpdate:
        return await volume_ops.create_volume(
            self._clients,
            default_namespace=self._executor_config.default_namespace,
            workspace=workspace,
            name=name,
            size=size,
            access_modes=access_modes,
            backend_config=backend_config,
        )

    async def read_volume_status(
        self,
        *,
        workspace: str,
        name: str,
        backend_config: dict[str, Any] | None = None,
    ) -> VolumeStatusUpdate:
        return await volume_ops.read_volume_status(
            self._clients,
            default_namespace=self._executor_config.default_namespace,
            workspace=workspace,
            name=name,
            backend_config=backend_config,
        )

    async def delete_volume(
        self,
        workspace: str,
        name: str,
        *,
        backend_config: dict[str, Any] | None = None,
    ) -> VolumeStatusUpdate:
        return await volume_ops.delete_volume(
            self._clients,
            default_namespace=self._executor_config.default_namespace,
            workspace=workspace,
            name=name,
            backend_config=backend_config,
        )
