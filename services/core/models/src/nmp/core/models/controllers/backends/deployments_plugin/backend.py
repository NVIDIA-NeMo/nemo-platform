# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Models ServiceBackend backed by nemo-deployments plugin entities."""

import asyncio
import logging
import time
from typing import Any

from nemo_deployments_plugin.entities import Deployment, DeploymentConfig, Prerequisite, Volume
from nemo_platform import AsyncNeMoPlatform
from nemo_platform.resources.entities import AsyncEntitiesResource
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError
from nemo_platform_plugin.sdk_provider import get_async_platform_sdk
from nmp.common.config import Runtime
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate, ServiceBackend
from nmp.core.models.controllers.backends.common import deployment_elapsed_seconds
from nmp.core.models.controllers.backends.deployments_plugin.compiler import compile_model_deployment
from nmp.core.models.controllers.backends.deployments_plugin.config import DeploymentsPluginConfig
from nmp.core.models.controllers.backends.deployments_plugin.executor import executor_for_runtime
from nmp.core.models.controllers.backends.deployments_plugin.naming import entity_names
from nmp.core.models.controllers.backends.deployments_plugin.resolve import resolve_plugin_deployment
from nmp.core.models.controllers.backends.deployments_plugin.status import aggregate_status, apply_pending_timeout
from nmp.core.models.controllers.backends.engine import ENGINE_GENERIC, config_engine
from nmp.core.models.controllers.context import ModelContext

logger = logging.getLogger(__name__)

_DEPLOYMENT_WORKSPACE_LABEL = "nmp.nvidia.com/deployment-workspace"
_DEPLOYMENT_NAME_LABEL = "nmp.nvidia.com/deployment-name"
_MODELS_ROLE_LABEL = "nmp.nvidia.com/models-role"


class DeploymentsPluginServiceBackend(ServiceBackend):
    """Compile model deployments into Volume and Deployment plugin entities."""

    def __init__(self, nmp_sdk: AsyncNeMoPlatform, config: dict[str, Any], huggingface_model_puller: str) -> None:
        self._backend_config: DeploymentsPluginConfig | None = None
        self._entities: NemoEntitiesClient | None = None
        self._huggingface_model_puller = huggingface_model_puller
        super().__init__(nmp_sdk, config)

    def init(self) -> None:
        self._backend_config = DeploymentsPluginConfig(**self._config)

    def shutdown(self) -> None:
        self._entities = None

    def _entity_client(self) -> NemoEntitiesClient:
        if self._entities is None:
            sdk = get_async_platform_sdk(as_service="models", internal=True)
            self._entities = NemoEntitiesClient(AsyncEntitiesResource(sdk))
        return self._entities

    @property
    def _cfg(self) -> DeploymentsPluginConfig:
        assert self._backend_config is not None
        return self._backend_config

    async def create_model_deployment(self, ctx: ModelContext) -> DeploymentStatusUpdate:
        """Create plugin substrate entities in volume, puller, server order.

        Tears down any leftover substrate first so drift recovery (LOST → recreate)
        does not collide with orphaned Volume / DeploymentConfig / Deployment entities.
        """
        resolved = resolve_plugin_deployment(ctx, self._huggingface_model_puller)
        if resolved.runtime == Runtime.NONE:
            return DeploymentStatusUpdate(
                status="UNKNOWN", status_message="Deployments plugin is unavailable for runtime none."
            )
        lora_enabled = resolved.view.lora_enabled and config_engine(resolved.config) != ENGINE_GENERIC
        if resolved.runtime == Runtime.DOCKER and lora_enabled:
            # Fail fast: the plugin docker runtime is single-container today, so a
            # LoRA deployment (server + adapters sidecar) cannot run there yet.
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=(
                    "LoRA serving is not supported on the docker runtime yet "
                    "(deployments-plugin docker is single-container). Deploy LoRA "
                    "models on the kubernetes runtime instead."
                ),
            )
        teardown = await self.delete_model_deployment(resolved.deployment.workspace, resolved.deployment.name)
        if teardown.status == "DELETING":
            return DeploymentStatusUpdate(
                status="PENDING",
                status_message="Waiting for prior deployments-plugin substrate teardown before recreate.",
            )
        executor = executor_for_runtime(self._cfg, resolved.runtime)
        if executor is None:
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=(
                    "No deployments-plugin executor configured for the current runtime. "
                    "Set docker_executor, k8s_executor, or default_executor under "
                    "models.controller.backends.deployments_plugin."
                ),
                error_details={
                    "reason": "executor_not_configured",
                    "runtime": resolved.runtime.value,
                },
            )
        try:
            compiled = compile_model_deployment(resolved, self._cfg)
            entities = self._entity_client()
            if compiled.volume is not None:
                await entities.create(compiled.volume)
            if compiled.scratch_volume is not None:
                await entities.create(compiled.scratch_volume)
            if compiled.puller_config is not None:
                await entities.create(compiled.puller_config)
                await entities.create(
                    Deployment(
                        name=compiled.names.puller,
                        workspace=resolved.deployment.workspace,
                        deployment_config=compiled.names.puller,
                        executor=executor,
                        desired_state="READY",
                        status="PENDING",
                    )
                )
            await entities.create(compiled.server_config)
            await entities.create(
                Deployment(
                    name=compiled.names.server,
                    workspace=resolved.deployment.workspace,
                    deployment_config=compiled.names.server,
                    executor=executor,
                    desired_state="READY",
                    status="PENDING",
                    prerequisites=(
                        [Prerequisite(deployment_name=compiled.names.puller, condition="succeeded")]
                        if compiled.puller_prerequisite
                        else []
                    ),
                )
            )
        except Exception as exc:
            await self._rollback_create(ctx)
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Unable to create deployments-plugin entities: {exc}",
                error_details={"error": str(exc)},
            )
        return DeploymentStatusUpdate(status="PENDING", status_message="Created deployments-plugin entities.")

    async def _rollback_create(self, ctx: ModelContext) -> None:
        """Best-effort controlled teardown after a partial create failure."""
        if ctx.model_deployment is None:
            return
        try:
            await self.delete_model_deployment(ctx.model_deployment.workspace, ctx.model_deployment.name)
        except Exception:
            logger.warning(
                "Failed to roll back deployments-plugin substrate after a create failure; orphaned entities may remain",
                extra={
                    "workspace": ctx.model_deployment.workspace,
                    "deployment_name": ctx.model_deployment.name,
                },
                exc_info=True,
            )

    async def get_model_deployment_status(self, ctx: ModelContext) -> DeploymentStatusUpdate:
        if ctx.model_deployment is None:
            return DeploymentStatusUpdate(status="UNKNOWN", status_message="Model deployment unavailable.")
        names = entity_names(ctx.model_deployment.name)
        server = await self._get_optional(Deployment, ctx.model_deployment.workspace, names.server)
        puller = await self._get_optional(Deployment, ctx.model_deployment.workspace, names.puller)
        volume = await self._get_optional(Volume, ctx.model_deployment.workspace, names.volume)
        result = aggregate_status(volume, puller, server, previously_ready=ctx.model_deployment.status == "READY")
        elapsed = deployment_elapsed_seconds(ctx.model_deployment)
        return apply_pending_timeout(
            result,
            elapsed_seconds=elapsed,
            timeout_seconds=self._cfg.pending_timeout_seconds,
            deployment_name=ctx.model_deployment.name,
        )

    async def update_model_deployment(self, ctx: ModelContext) -> DeploymentStatusUpdate:
        del ctx
        return DeploymentStatusUpdate(status="ERROR", status_message="Update via recreate not yet supported.")

    async def delete_model_deployment(self, workspace: str, name: str) -> DeploymentStatusUpdate:
        """Stop deployments, wait for each to disappear, then remove their configs."""
        names = entity_names(name)
        for deployment_name, config_name in ((names.server, names.server), (names.puller, names.puller)):
            if not await self._delete_deployment_and_config(workspace, deployment_name, config_name):
                return DeploymentStatusUpdate(
                    status="DELETING", status_message="Waiting for plugin deployment teardown."
                )
        for volume_name in (names.scratch, names.volume):
            try:
                await self._entity_client().delete(Volume, name=volume_name, workspace=workspace)
            except NemoEntityNotFoundError:
                pass
        return DeploymentStatusUpdate(status="DELETED", status_message="Deleted deployments-plugin entities.")

    async def _delete_deployment_and_config(self, workspace: str, deployment_name: str, config_name: str) -> bool:
        deployment = await self._get_optional(Deployment, workspace, deployment_name)
        if deployment is not None:
            if deployment.status != "DELETING":
                deployment.status = "DELETING"
                deployment.desired_state = "STOPPED"
                await self._entity_client().update(deployment)
            if not await self._wait_for_deployment_gone(workspace, deployment_name):
                return False
        try:
            await self._entity_client().delete(DeploymentConfig, name=config_name, workspace=workspace)
        except NemoEntityNotFoundError:
            pass
        return True

    async def _wait_for_deployment_gone(self, workspace: str, name: str) -> bool:
        deadline = time.monotonic() + self._cfg.delete_wait_seconds
        while time.monotonic() < deadline:
            if await self._get_optional(Deployment, workspace, name) is None:
                return True
            await asyncio.sleep(self._cfg.delete_poll_seconds)
        return False

    async def _get_optional(self, entity_type: type[Any], workspace: str, name: str) -> Any | None:
        try:
            return await self._entity_client().get(entity_type, name=name, workspace=workspace)
        except NemoEntityNotFoundError:
            return None

    async def list_managed_deployment_names(self) -> list[str]:
        # Labels live on immutable DeploymentConfig entities; deployments-plugin
        # does not currently mirror them onto Deployment.
        result = await self._entity_client().list(DeploymentConfig, workspace="-")
        names = {
            f"{config.labels[_DEPLOYMENT_WORKSPACE_LABEL]}/{config.labels[_DEPLOYMENT_NAME_LABEL]}"
            for config in result.data
            if config.labels.get(MODEL_MANAGED_BY_LABEL) == MODEL_MANAGED_BY_MODELS_CONTROLLER
            and config.labels.get(_MODELS_ROLE_LABEL) == "server"
            and _DEPLOYMENT_WORKSPACE_LABEL in config.labels
            and _DEPLOYMENT_NAME_LABEL in config.labels
        }
        return sorted(names)
