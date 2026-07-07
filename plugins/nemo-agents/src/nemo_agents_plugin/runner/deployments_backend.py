# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DeploymentsRunnerBackend — runs agents as containers via the nemo-deployments plugin.

Translates the :class:`~nemo_agents_plugin.runner.backend.RunnerBackend` interface into
nemo-deployments ``Deployment`` / ``DeploymentConfig`` entity operations. The deployments
controller reconciles those entities onto a configured executor (docker today, k8s later),
so the same code path serves both substrates — the only difference is which executor is
targeted via ``AgentsConfig.deployments.executor``.

Assumes the agent container image is self-contained (NAT config baked in). Gateway routing
is supplied to the container through env vars rather than config rewriting.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from nemo_agents_plugin.config import AgentsConfig, DeploymentsRunnerConfig
from nemo_agents_plugin.entities import DeploymentStatus
from nemo_agents_plugin.runner.backend import DeploymentInfo, ExternalLog, LogLocation, RunnerBackend
from nemo_agents_plugin.utils import get_base_url
from nemo_deployments_plugin.entities import Container, ContainerPort, Deployment, DeploymentConfig, EnvVar
from nemo_platform.resources.entities import AsyncEntitiesResource
from nemo_platform_plugin.config import LOOPBACK_ADDRESSES
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError
from nemo_platform_plugin.sdk_provider import get_async_platform_sdk

logger = logging.getLogger(__name__)

# The deployments docker/k8s backends expect exactly one container.
_CONTAINER_NAME = "agent"
_HTTP_PORT_NAME = "http"
# Prefix for the deployments entities we own, so list/get/delete never collide with
# user-authored deployments in the same workspace.
_ENTITY_PREFIX = "agent-"

# On delete, wait up to this long for the deployments controller to tear down the
# container and remove the Deployment entity before we drop the DeploymentConfig. This
# keeps the config alive while a Deployment still references it, so the controller's
# _load_configs never 404s on a config we deleted out from under it.
_DELETE_CONFIG_WAIT_S = 30.0
_DELETE_CONFIG_POLL_S = 1.0

# agents lifecycle status  <-  deployments-plugin status
_STATUS_MAP: dict[str, DeploymentStatus] = {
    "PENDING": "starting",
    "STARTING": "starting",
    "READY": "running",
    "SUCCEEDED": "running",  # Always-restart agents never reach SUCCEEDED in practice.
    "FAILED": "failed",
    "LOST": "failed",
    "UNKNOWN": "starting",
    "DELETING": "deleting",
}


def map_status(backend_status: str) -> DeploymentStatus:
    """Return the agents lifecycle status for a deployments-plugin status."""
    return _STATUS_MAP.get(backend_status, "starting")


def container_gateway_url(base_url: str, override: str | None = None) -> str:
    """Return an Inference Gateway base URL reachable from inside a container.

    Rewrites a loopback host in *base_url* to ``host.docker.internal`` so an agent
    process inside a container can reach the platform running on the host. When
    *override* is given it wins verbatim.

    Args:
        base_url: The platform base URL as seen from the host.
        override: Optional explicit container-reachable base URL.

    Returns:
        str: A base URL (no trailing slash) reachable from inside the container.

    """
    if override:
        return override.rstrip("/")
    url = base_url.rstrip("/")
    for host in LOOPBACK_ADDRESSES:
        marker = f"//{host}"
        if marker in url:
            return url.replace(marker, "//host.docker.internal", 1)
    return url


def build_deployment_config(
    *,
    name: str,
    workspace: str,
    image: str,
    port: int,
    env: dict[str, str],
) -> DeploymentConfig:
    """Build the DeploymentConfig entity for a single-container agent deployment.

    Args:
        name: Name for the DeploymentConfig entity.
        workspace: Workspace the entity belongs to.
        image: Container image to run.
        port: Container port the agent server listens on.
        env: Environment variables to inject into the container.

    Returns:
        DeploymentConfig: The entity ready to be created in the entity store.

    """
    # Aliased fields (containerPort) use their alias names for the constructor.
    # DeploymentConfig.restart_policy defaults to "Always" (long-running agent server).
    return DeploymentConfig(
        name=name,
        workspace=workspace,
        containers=[
            Container(
                name=_CONTAINER_NAME,
                image=image,
                ports=[ContainerPort(name=_HTTP_PORT_NAME, containerPort=port)],
                env=[EnvVar(name=key, value=value) for key, value in env.items()],
            )
        ],
    )


class DeploymentsRunnerBackend(RunnerBackend):
    """Runs agent deployments as containers via the nemo-deployments plugin.

    Args:
        config: The agents plugin configuration; ``config.deployments`` selects the
            target executor, default image, container port, and gateway URL override.

    """

    def __init__(self, config: AgentsConfig) -> None:
        self._config: DeploymentsRunnerConfig = config.deployments
        self._entities: NemoEntitiesClient | None = None
        self._http_client: httpx.AsyncClient | None = None

    def _entity_client(self) -> NemoEntitiesClient:
        if self._entities is None:
            sdk = get_async_platform_sdk(as_service="agents", internal=True)
            self._entities = NemoEntitiesClient(AsyncEntitiesResource(sdk))
        return self._entities

    @staticmethod
    def _dep_name(name: str) -> str:
        return f"{_ENTITY_PREFIX}{name}"

    async def create_deployment(
        self,
        workspace: str,
        name: str,
        config: dict[str, Any],
        port: int,
        image: str | None = None,
        env: dict[str, str] | None = None,
    ) -> DeploymentInfo:
        """Create DeploymentConfig + Deployment entities for the agent container.

        The container image is self-contained, so *config* and *port* (the host port,
        which the deployments backend allocates) are unused here. *env* is merged into
        the container environment on top of the platform-supplied gateway variables.
        """
        del config, port
        resolved_image = image or self._config.default_image
        if not resolved_image:
            return DeploymentInfo(
                name=name,
                status="failed",
                error="No container image provided and no deployments.default_image configured.",
            )

        entities = self._entity_client()
        dep_name = self._dep_name(name)
        container_env = {
            "NMP_GATEWAY_BASE_URL": container_gateway_url(get_base_url(), self._config.gateway_url_override),
            "NMP_WORKSPACE": workspace,
            "NMP_AGENT_NAME": name,
        }
        # Caller-supplied env (e.g. NVIDIA_API_KEY passed on the deploy command line)
        # overrides the platform defaults above.
        if env:
            container_env.update(env)
        deployment_config = build_deployment_config(
            name=dep_name,
            workspace=workspace,
            image=resolved_image,
            port=self._config.container_port,
            env=container_env,
        )
        await entities.create(deployment_config)
        deployment = Deployment(
            name=dep_name,
            workspace=workspace,
            deployment_config=dep_name,
            executor=self._config.executor,
            status="PENDING",
        )
        await entities.create(deployment)
        logger.info("Created deployment entities '%s/%s' (image=%s)", workspace, dep_name, resolved_image)
        # Endpoint is assigned asynchronously once the deployments controller schedules
        # the container; the agents controller adopts it on a later reconcile cycle.
        return DeploymentInfo(name=name, status="starting", endpoint="")

    async def get_deployment_status(self, workspace: str, name: str) -> DeploymentInfo | None:
        entities = self._entity_client()
        try:
            deployment = await entities.get(Deployment, name=self._dep_name(name), workspace=workspace)
        except NemoEntityNotFoundError:
            return None
        endpoint = deployment.endpoints[0].url if deployment.endpoints else ""
        info = DeploymentInfo(name=name, status=map_status(deployment.status), endpoint=endpoint)
        if info.status == "failed":
            info.error = deployment.status_message or "Deployment failed."
        return info

    async def delete_deployment(self, workspace: str, name: str) -> bool:
        entities = self._entity_client()
        dep_name = self._dep_name(name)
        found = False
        try:
            deployment = await entities.get(Deployment, name=dep_name, workspace=workspace)
            if deployment.status != "DELETING":
                deployment.status = "DELETING"
                await entities.update(deployment)
            found = True
        except NemoEntityNotFoundError:
            pass
        # The deployments controller removes the container and deletes the Deployment entity
        # on DELETING; the DeploymentConfig is ours to clean up. Wait for the Deployment to
        # be gone first — deleting the config while the controller still holds a DELETING
        # Deployment makes its _load_configs 404 every cycle (harmless but noisy log spam).
        if found:
            await self._wait_for_deployment_gone(workspace, dep_name)
        try:
            await entities.delete(DeploymentConfig, name=dep_name, workspace=workspace)
            found = True
        except NemoEntityNotFoundError:
            pass
        return found

    async def _wait_for_deployment_gone(self, workspace: str, dep_name: str) -> None:
        """Block until the Deployment entity is deleted or the wait budget elapses.

        Args:
            workspace: Workspace the Deployment belongs to.
            dep_name: Prefixed Deployment entity name.

        """
        # ponytail: bounded polling blocks this reconcile iteration for up to
        # _DELETE_CONFIG_WAIT_S; on timeout we delete the config anyway and accept a
        # single 404 warning rather than leak the config or hang the loop. Upgrade path
        # is a multi-cycle, reconcile-driven delete if this ever needs to be non-blocking.
        entities = self._entity_client()
        deadline = time.monotonic() + _DELETE_CONFIG_WAIT_S
        while time.monotonic() < deadline:
            try:
                await entities.get(Deployment, name=dep_name, workspace=workspace)
            except NemoEntityNotFoundError:
                return
            await asyncio.sleep(_DELETE_CONFIG_POLL_S)
        logger.warning(
            "Deployment '%s/%s' still present after %.0fs; deleting its config anyway.",
            workspace,
            dep_name,
            _DELETE_CONFIG_WAIT_S,
        )

    async def list_deployments(self, workspace: str | None = None) -> list[DeploymentInfo]:
        entities = self._entity_client()
        result = await entities.list(Deployment, workspace=workspace or "-")
        infos: list[DeploymentInfo] = []
        for deployment in result.data:
            if not deployment.name.startswith(_ENTITY_PREFIX):
                continue
            endpoint = deployment.endpoints[0].url if deployment.endpoints else ""
            infos.append(
                DeploymentInfo(
                    name=deployment.name[len(_ENTITY_PREFIX) :],
                    status=map_status(deployment.status),
                    endpoint=endpoint,
                )
            )
        return infos

    async def health_check(self, endpoint: str) -> bool:
        if not endpoint:
            return False
        url = endpoint.rstrip("/") + "/health"
        try:
            resp = await self._get_http_client().get(url)
            return resp.status_code < 400
        except Exception:
            return False

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=5.0)
        return self._http_client

    def get_log_location(self, workspace: str, name: str) -> LogLocation:
        del workspace, name
        return ExternalLog(hint="Inspect container logs via the deployments plugin or 'docker logs'.")

    async def shutdown(self) -> None:
        if self._http_client is not None and not self._http_client.is_closed:
            try:
                await self._http_client.aclose()
            except Exception:
                logger.warning("Error closing HTTP client during shutdown", exc_info=True)
            self._http_client = None
