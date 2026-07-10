# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DeploymentsRunnerBackend — runs agents as containers via the nemo-deployments plugin.

Translates the :class:`~nemo_agents_plugin.runner.backend.RunnerBackend` interface into
nemo-deployments ``Deployment`` / ``DeploymentConfig`` entity operations. The deployments
controller reconciles those entities onto a configured executor (docker or k8s).

Long-running only (``restart_policy=Always``). Finite / run-to-completion belongs to
AgentRun (Razvan RFCs), not AgentDeployment.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import yaml
from nemo_agents_plugin.config import AgentsConfig, DeploymentsRunnerConfig
from nemo_agents_plugin.entities import DeploymentMode, DeploymentStatus, Endpoint
from nemo_agents_plugin.runner.backend import DeploymentInfo, ExternalLog, LogLocation, RunnerBackend
from nemo_agents_plugin.utils import get_base_url
from nemo_deployments_plugin.entities import (
    ConfigFile,
    Container,
    ContainerPort,
    Deployment,
    DeploymentConfig,
    EnvVar,
    HTTPGetAction,
    Probe,
    VolumeMount,
)
from nemo_platform.resources.entities import AsyncEntitiesResource
from nemo_platform_plugin.config import LOOPBACK_ADDRESSES
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError
from nemo_platform_plugin.sdk_provider import get_async_platform_sdk

logger = logging.getLogger(__name__)

_CONTAINER_NAME = "agent"
_HTTP_PORT_NAME = "http"
_PLUGIN_WHEELS_VOLUME = "plugin-wheels"
_PLUGIN_WHEELS_MOUNT = "/opt/nemo/plugin-wheels"
_NAT_CONFIG_ENV = "NAT_CONFIG_PATH"

# On delete, wait up to this long for the deployments controller to tear down the
# container and remove the Deployment entity before we drop the DeploymentConfig.
_DELETE_CONFIG_WAIT_S = 30.0
_DELETE_CONFIG_POLL_S = 1.0

# agents lifecycle status  <-  deployments-plugin status
_STATUS_MAP: dict[str, DeploymentStatus] = {
    "PENDING": "starting",
    "STARTING": "starting",
    "READY": "running",
    "SUCCEEDED": "failed",  # Always agents should not terminate successfully
    "FAILED": "failed",
    "LOST": "failed",
    "UNKNOWN": "starting",
    "DELETING": "deleting",
}

_CONTAINER_MODES: frozenset[str] = frozenset({"docker", "k8s"})


def map_status(backend_status: str) -> DeploymentStatus:
    """Return the agents lifecycle status for a deployments-plugin status."""
    return _STATUS_MAP.get(backend_status, "starting")


def container_gateway_url(base_url: str, *, mode: DeploymentMode, override: str | None = None) -> str:
    """Return a platform base URL reachable from inside the agent container.

    Docker may rewrite loopback hosts to ``host.docker.internal``. K8s leaves the
    URL as-is (in-cluster IGW Service DNS is AIRCORE-863). *override* wins verbatim.
    """
    if override:
        return override.rstrip("/")
    url = base_url.rstrip("/")
    if mode == "docker":
        for host in LOOPBACK_ADDRESSES:
            marker = f"//{host}"
            if marker in url:
                return url.replace(marker, "//host.docker.internal", 1)
    return url


def executor_for_mode(config: DeploymentsRunnerConfig, mode: DeploymentMode) -> str | None:
    """Resolve the named deployments-plugin executor for *mode*."""
    if mode == "docker":
        return config.docker_executor or config.default_executor
    if mode == "k8s":
        return config.k8s_executor or config.default_executor
    return config.default_executor


def _project_endpoints(deployment: Deployment) -> list[Endpoint]:
    return [
        Endpoint(name=ep.name, url=ep.url, protocol=ep.protocol)  # type: ignore[arg-type]
        for ep in deployment.endpoints
    ]


def build_deployment_config(
    *,
    name: str,
    workspace: str,
    image: str,
    port: int,
    nat_config: dict[str, Any],
    config_mount_path: str,
    mode: DeploymentMode,
    gateway_base_url: str,
    plugin_wheels_init_image: str | None = None,
    labels: dict[str, str] | None = None,
) -> DeploymentConfig:
    """Compile an agent into a long-running ``DeploymentConfig`` (Always).

    NAT workflow YAML is mounted via ``config_files`` (honoured by the k8s backend;
    docker v1 ignores config_files — use a self-contained image there). The main
    container binds ``0.0.0.0`` and exposes a readiness probe on ``/health``.
    """
    env = [
        EnvVar(name="NMP_GATEWAY_BASE_URL", value=gateway_base_url),
        EnvVar(name="NMP_WORKSPACE", value=workspace),
        EnvVar(name="NMP_AGENT_NAME", value=name),
        EnvVar(name=_NAT_CONFIG_ENV, value=config_mount_path),
    ]
    volume_mounts: list[VolumeMount] = []
    init_containers: list[Container] = []

    # Option B (k8s only): init container pulls workspace plugin wheels into a shared volume.
    # Docker backend rejects init_containers in v1. Full wheel-source contract is AIRCORE-863.
    # Constructors use camelCase aliases (ty + pydantic alias validation).
    if mode == "k8s" and plugin_wheels_init_image:
        volume_mounts.append(VolumeMount(name=_PLUGIN_WHEELS_VOLUME, mountPath=_PLUGIN_WHEELS_MOUNT, readOnly=True))
        init_containers.append(
            Container(
                name="plugin-wheels",
                image=plugin_wheels_init_image,
                command=["sh", "-c"],
                args=[
                    f"echo 'Option B plugin-wheels stub; hardened in AIRCORE-863' "
                    f"&& mkdir -p {_PLUGIN_WHEELS_MOUNT} && touch {_PLUGIN_WHEELS_MOUNT}/.ready"
                ],
            ).model_copy(
                update={
                    "volume_mounts": [
                        VolumeMount(name=_PLUGIN_WHEELS_VOLUME, mountPath=_PLUGIN_WHEELS_MOUNT, readOnly=False)
                    ]
                }
            )
        )
        env.append(EnvVar(name="PYTHONPATH", value=_PLUGIN_WHEELS_MOUNT))

    container = Container(
        name=_CONTAINER_NAME,
        image=image,
        command=["nat", "start", "fastapi"],
        args=[
            "--config_file",
            config_mount_path,
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ],
        ports=[ContainerPort(name=_HTTP_PORT_NAME, containerPort=port)],
        env=env,
    ).model_copy(
        update={
            "volume_mounts": volume_mounts,
            "readiness_probe": Probe(
                httpGet=HTTPGetAction(path="/health", port=port),
                initialDelaySeconds=2,
                periodSeconds=5,
                failureThreshold=12,
            ),
        }
    )

    return DeploymentConfig(
        name=name,
        workspace=workspace,
        containers=[container],
        labels=labels or {},
    ).model_copy(
        update={
            "init_containers": init_containers,
            "config_files": [
                ConfigFile(path=config_mount_path, content=yaml.safe_dump(nat_config, sort_keys=False)),
            ],
            "restart_policy": "Always",
        }
    )


class DeploymentsRunnerBackend(RunnerBackend):
    """Runs agent deployments as containers via the nemo-deployments plugin."""

    def __init__(self, config: AgentsConfig) -> None:
        self._config: DeploymentsRunnerConfig = config.deployments
        self._entities: NemoEntitiesClient | None = None

    def _entity_client(self) -> NemoEntitiesClient:
        if self._entities is None:
            sdk = get_async_platform_sdk(as_service="agents", internal=True)
            self._entities = NemoEntitiesClient(AsyncEntitiesResource(sdk))
        return self._entities

    async def create_deployment(
        self,
        workspace: str,
        name: str,
        config: dict[str, Any],
        port: int,
        *,
        image: str | None = None,
        deployment_mode: DeploymentMode = "docker",
    ) -> DeploymentInfo:
        """Create DeploymentConfig + Deployment entities for the agent container."""
        del port  # Host port is allocated by the deployments executor, not agents.
        if deployment_mode not in _CONTAINER_MODES:
            return DeploymentInfo(
                name=name,
                status="failed",
                error=f"DeploymentsRunnerBackend does not support deployment_mode={deployment_mode!r}.",
            )

        resolved_image = image or self._config.default_image
        if not resolved_image:
            return DeploymentInfo(
                name=name,
                status="failed",
                error="No container image provided and no deployments.default_image configured.",
            )

        entities = self._entity_client()
        gateway = container_gateway_url(
            get_base_url(),
            mode=deployment_mode,
            override=self._config.gateway_url_override,
        )
        deployment_config = build_deployment_config(
            name=name,
            workspace=workspace,
            image=resolved_image,
            port=self._config.container_port,
            nat_config=config,
            config_mount_path=self._config.config_mount_path,
            mode=deployment_mode,
            gateway_base_url=gateway,
            plugin_wheels_init_image=self._config.plugin_wheels_init_image,
            labels={
                "nemo.agents/deployment": name,
                "nemo.agents/mode": deployment_mode,
            },
        )
        await entities.create(deployment_config)
        try:
            deployment = Deployment(
                name=name,
                workspace=workspace,
                deployment_config=name,
                executor=executor_for_mode(self._config, deployment_mode),
                desired_state="READY",
                status="PENDING",
            )
            await entities.create(deployment)
        except Exception:
            # Avoid orphaning the config if Deployment create fails.
            try:
                await entities.delete(DeploymentConfig, name=name, workspace=workspace)
            except Exception:
                logger.exception(
                    "Failed to clean up DeploymentConfig '%s/%s' after Deployment create failure",
                    workspace,
                    name,
                )
            raise

        logger.info(
            "Created deployment entities '%s/%s' (image=%s, mode=%s)",
            workspace,
            name,
            resolved_image,
            deployment_mode,
        )
        return DeploymentInfo(name=name, status="starting", endpoint="", endpoints=[])

    async def get_deployment_status(self, workspace: str, name: str) -> DeploymentInfo | None:
        entities = self._entity_client()
        try:
            deployment = await entities.get(Deployment, name=name, workspace=workspace)
        except NemoEntityNotFoundError:
            return None
        endpoints = _project_endpoints(deployment)
        endpoint = next((ep.url for ep in endpoints if ep.protocol in ("http", "https") and ep.url), "")
        info = DeploymentInfo(
            name=name,
            status=map_status(deployment.status),
            endpoint=endpoint,
            endpoints=endpoints,
        )
        if info.status == "failed":
            info.error = deployment.status_message or "Deployment failed."
        return info

    async def delete_deployment(self, workspace: str, name: str) -> bool:
        entities = self._entity_client()
        found = False
        try:
            deployment = await entities.get(Deployment, name=name, workspace=workspace)
            if deployment.status != "DELETING":
                deployment.status = "DELETING"
                deployment.desired_state = "STOPPED"
                await entities.update(deployment)
            found = True
        except NemoEntityNotFoundError:
            pass

        if found:
            await self._wait_for_deployment_gone(workspace, name)

        try:
            await entities.delete(DeploymentConfig, name=name, workspace=workspace)
            found = True
        except NemoEntityNotFoundError:
            pass
        return found

    async def _wait_for_deployment_gone(self, workspace: str, dep_name: str) -> None:
        """Block until the Deployment entity is deleted or the wait budget elapses."""
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
            endpoints = _project_endpoints(deployment)
            endpoint = next((ep.url for ep in endpoints if ep.protocol in ("http", "https") and ep.url), "")
            infos.append(
                DeploymentInfo(
                    name=deployment.name,
                    status=map_status(deployment.status),
                    endpoint=endpoint,
                    endpoints=endpoints,
                )
            )
        return infos

    async def health_check(self, endpoint: str) -> bool:
        # Container modes trust the deployments-plugin readiness projection; the
        # agents controller should not call this for docker/k8s. Kept for ABC parity.
        del endpoint
        return False

    def get_log_location(self, workspace: str, name: str) -> LogLocation:
        del workspace, name
        return ExternalLog(hint="Inspect container logs via the deployments plugin or substrate CLI.")

    async def shutdown(self) -> None:
        self._entities = None
