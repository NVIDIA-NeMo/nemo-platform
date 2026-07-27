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
import copy
import logging
import time
from typing import Any
from urllib.parse import urlsplit

import yaml
from nemo_agents_plugin.config import AgentsConfig, DeploymentsRunnerConfig
from nemo_agents_plugin.entities import (
    CONTAINER_DEPLOYMENT_MODES,
    DeploymentMode,
    DeploymentStatus,
    Endpoint,
)
from nemo_agents_plugin.runner.backend import DeploymentInfo, ExternalLog, LogLocation, RunnerBackend
from nemo_agents_plugin.utils import get_base_url, get_internal_base_url
from nemo_deployments_plugin.entities import (
    ConfigFile,
    Container,
    ContainerPort,
    Deployment,
    DeploymentConfig,
    EnvVar,
    ExecAction,
    HTTPGetAction,
    Probe,
    VolumeMount,
)
from nemo_platform.resources.entities import AsyncEntitiesResource
from nemo_platform_plugin.config import LOOPBACK_ADDRESSES
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError
from nemo_platform_plugin.jobs.image import get_qualified_image
from nemo_platform_plugin.sdk_provider import get_async_platform_sdk

logger = logging.getLogger(__name__)

_CONTAINER_NAME = "agent"
_HTTP_PORT_NAME = "http"
_PLUGIN_WHEELS_VOLUME = "plugin-wheels"
_PLUGIN_WHEELS_MOUNT = "/opt/nemo/plugin-wheels"
_NAT_CONFIG_ENV = "NAT_CONFIG_PATH"
_AUTH_PROXY_CONTAINER_NAME = "auth-proxy"
_AUTH_PROXY_HOST_ENVVAR = "NMP_AUTH_PROXY_HOST"
_AUTH_PROXY_PORT_ENVVAR = "NMP_AUTH_PROXY_PORT"
_AUTH_PROXY_PRINCIPAL_ENVVAR = "NMP_AUTH_PROXY_PRINCIPAL"
_AUTH_PROXY_PRINCIPAL = "agents"
_NATIVE_SIDECAR_RESTART_POLICY = "Always"


def _platform_auth_enabled() -> bool:
    """Return whether platform auth is enabled (deployed agents then need a principal)."""
    try:
        from nmp.common.config import get_auth_config

        return bool(get_auth_config().enabled)
    except Exception:
        logger.debug("Could not resolve auth config; assuming auth disabled", exc_info=True)
        return False


# On delete, wait up to this long for the deployments controller to tear down the
# container and remove the Deployment entity before we drop the DeploymentConfig.
# Short per-reconcile wait: if the Deployment is still present, return False so
# the controller keeps AgentDeployment in ``deleting`` and retries next cycle
# instead of blocking the reconcile loop for tens of seconds. 5s gives docker
# SDK round-trips a bit more headroom than a 2s budget.
_DELETE_CONFIG_WAIT_S = 5.0
_DELETE_CONFIG_POLL_S = 0.5

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


def map_status(backend_status: str) -> DeploymentStatus:
    """Return the agents lifecycle status for a deployments-plugin status."""
    return _STATUS_MAP.get(backend_status, "starting")


class UnreachableGatewayURLError(ValueError):
    """Raised when no inference base URL reachable from an agent container can be resolved."""


def resolve_agent_gateway_url(
    base_url: str,
    *,
    mode: DeploymentMode,
    override: str | None = None,
    internal_base_url: str | None = None,
) -> str:
    """Return the platform base URL an agent should call, reachable from its container.

    An explicit *override* wins for any mode. Otherwise ``k8s`` uses
    *internal_base_url* (the in-cluster API Service DNS) and ``docker`` rewrites a
    loopback *base_url* to ``host.docker.internal``, passing other hosts through.

    Only ``docker`` and ``k8s`` are supported; ``subprocess`` deployments are
    served by a different backend.

    Raises:
        UnreachableGatewayURLError: k8s mode with no *internal_base_url* or *override*.
        ValueError: *mode* is not a container deployment mode.
    """
    if mode not in CONTAINER_DEPLOYMENT_MODES:
        raise ValueError(
            f"resolve_agent_gateway_url only supports container deployment modes "
            f"{sorted(CONTAINER_DEPLOYMENT_MODES)}, got {mode!r}."
        )

    if override:
        return override.rstrip("/")

    if mode == "k8s":
        if internal_base_url:
            return internal_base_url.rstrip("/")
        raise UnreachableGatewayURLError(
            f"No container-reachable inference base URL for k8s deployment: platform base URL "
            f"{base_url!r} is not usable from an agent pod and no internal API Service URL is set. "
            "Set NEMO_INTERNAL_BASE_URL / NMP_INTERNAL_BASE_URL (or deployments.k8s_internal_base_url), "
            "or deployments.gateway_url_override."
        )

    parts = urlsplit(base_url.rstrip("/"))
    if (parts.hostname or "").lower() in LOOPBACK_ADDRESSES:
        netloc = "host.docker.internal"
        if parts.port is not None:
            netloc = f"{netloc}:{parts.port}"
        return parts._replace(netloc=netloc).geturl()
    return parts.geturl()


def rewrite_config_base_urls(nat_config: dict[str, Any], gateway_url: str) -> dict[str, Any]:
    """Return a copy of *nat_config* with each Inference Gateway LLM base_url rebased onto *gateway_url*.

    Rewrites the scheme, host, and port of ``base_url`` on every ``openai``/``nim``
    LLM that points at the Inference Gateway, preserving the path. LLMs with an
    explicit third-party ``base_url`` are left unchanged.
    """
    reachable = urlsplit(gateway_url.rstrip("/"))
    reachable_origin = f"{reachable.scheme}://{reachable.netloc}"
    config = copy.deepcopy(nat_config)
    for llm_cfg in config.get("llms", {}).values():
        if not isinstance(llm_cfg, dict) or llm_cfg.get("_type") not in ("openai", "nim"):
            continue
        current = llm_cfg.get("base_url")
        if not isinstance(current, str) or "/apis/inference-gateway/" not in current:
            continue
        parts = urlsplit(current)
        llm_cfg["base_url"] = f"{reachable_origin}{parts.path}"
    return config


def executor_for_mode(config: DeploymentsRunnerConfig, mode: DeploymentMode) -> str | None:
    """Resolve the named deployments-plugin executor for *mode*."""
    if mode == "docker":
        return config.docker_executor or config.default_executor
    if mode == "k8s":
        return config.k8s_executor or config.default_executor
    return config.default_executor


_HTTP_PROTOCOLS = frozenset({"http", "https"})


def _project_endpoints(deployment: Deployment) -> list[Endpoint]:
    """Map deployments-plugin endpoints onto the agents entity Endpoint model."""
    return [Endpoint.model_validate(ep.model_dump()) for ep in deployment.endpoints]


def _primary_http_url(endpoints: list[Endpoint]) -> str:
    return next((ep.url for ep in endpoints if ep.protocol in _HTTP_PROTOCOLS and ep.url), "")


def _info_from_deployment(deployment: Deployment) -> DeploymentInfo:
    endpoints = _project_endpoints(deployment)
    info = DeploymentInfo(
        name=deployment.name,
        status=map_status(deployment.status),
        endpoint=_primary_http_url(endpoints),
        endpoints=endpoints,
    )
    if info.status == "failed":
        info.error = deployment.status_message or "Deployment failed."
    return info


class AuthProxySpec:
    """Parameters for injecting the service-principal auth-proxy sidecar."""

    def __init__(self, *, image: str, port: int, upstream_base_url: str, principal: str) -> None:
        self.image = image
        self.port = port
        self.upstream_base_url = upstream_base_url
        self.principal = principal


def _build_auth_proxy_sidecar(spec: AuthProxySpec) -> Container:
    """Build the native-sidecar Container that runs the service-principal auth proxy.

    The sidecar forwards the agent's loopback platform calls to *upstream_base_url*
    with an ``X-NMP-Principal-Id: service:<principal>`` header so they authorize
    under the ServiceSystem role. The deployed agent targets it on localhost.
    """
    return Container(
        name=_AUTH_PROXY_CONTAINER_NAME,
        image=spec.image,
        command=["nemo", "services", "run", "--sidecars", "auth-proxy"],
        env=[
            EnvVar(name="NMP_BASE_URL", value=spec.upstream_base_url),
            EnvVar(name=_AUTH_PROXY_PRINCIPAL_ENVVAR, value=spec.principal),
            EnvVar(name=_AUTH_PROXY_HOST_ENVVAR, value="127.0.0.1"),
            EnvVar(name=_AUTH_PROXY_PORT_ENVVAR, value=str(spec.port)),
        ],
    ).model_copy(
        update={
            "restart_policy": _NATIVE_SIDECAR_RESTART_POLICY,
            # The proxy binds loopback only (reachable solely by the co-located
            # agent), so an httpGet probe against the pod IP would be refused. Use
            # an exec probe that curls localhost from inside the container netns.
            "readiness_probe": Probe(
                exec=ExecAction(
                    command=["sh", "-c", f"curl -sf http://127.0.0.1:{spec.port}/healthz"],
                ),
                initialDelaySeconds=1,
                periodSeconds=5,
                failureThreshold=12,
            ),
        }
    )


def build_deployment_config(
    *,
    name: str,
    workspace: str,
    image: str,
    port: int,
    nat_config: dict[str, Any],
    config_mount_path: str,
    mode: DeploymentMode,
    plugin_wheels_init_image: str | None = None,
    labels: dict[str, str] | None = None,
    auth_proxy: AuthProxySpec | None = None,
) -> DeploymentConfig:
    """Compile an agent into a long-running ``DeploymentConfig`` (Always).

    NAT workflow YAML is always embedded in ``config_files`` (k8s mounts them).
    Docker v1 ignores ``config_files``, so docker mode also injects the YAML via
    ``NAT_CONFIG_YAML`` and a shell preamble that writes the file before ``nat``
    starts. The main container binds ``0.0.0.0`` and exposes a readiness probe on
    ``/health``.

    The inference base URL the agent calls is read from ``nat_config``'s
    ``llms.*.base_url``; the caller is responsible for setting it to a
    container-reachable value.
    """
    nat_yaml = yaml.safe_dump(nat_config, sort_keys=False)
    env = [
        EnvVar(name="NMP_WORKSPACE", value=workspace),
        EnvVar(name="NMP_AGENT_NAME", value=name),
        EnvVar(name=_NAT_CONFIG_ENV, value=config_mount_path),
    ]
    volume_mounts: list[VolumeMount] = []
    init_containers: list[Container] = []

    # K8s only: init container stages workspace plugin wheels into a shared volume.
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
                    f"echo 'plugin-wheels init stub; hardened in AIRCORE-863' "
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

    nat_args = [
        "nat",
        "start",
        "fastapi",
        "--config_file",
        config_mount_path,
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
    ]
    if mode == "docker":
        # Docker backend does not mount config_files; materialize the YAML from env.
        env.append(EnvVar(name="NAT_CONFIG_YAML", value=nat_yaml))
        command = ["sh", "-c"]
        args = [
            f'mkdir -p "$(dirname "{config_mount_path}")" '
            f'&& printf "%s" "$NAT_CONFIG_YAML" > "{config_mount_path}" '
            f"&& exec {' '.join(nat_args)}"
        ]
    else:
        command = ["nat", "start", "fastapi"]
        args = [
            "--config_file",
            config_mount_path,
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ]

    container = Container(
        name=_CONTAINER_NAME,
        image=image,
        command=command,
        args=args,
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

    if auth_proxy is not None:
        # Native sidecar (init container with restartPolicy=Always): starts before
        # the agent and forwards its loopback platform calls with a service-principal
        # identity header so they authorize when auth is on. Modeled as an init
        # container because the deployments plugin only allows per-container
        # restart_policy there (matches the LoRA adapters sidecar pattern).
        init_containers.append(_build_auth_proxy_sidecar(auth_proxy))

    return DeploymentConfig(
        name=name,
        workspace=workspace,
        containers=[container],
        labels=labels or {},
    ).model_copy(
        update={
            "init_containers": init_containers,
            "config_files": [
                ConfigFile(path=config_mount_path, content=nat_yaml),
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
        if deployment_mode not in CONTAINER_DEPLOYMENT_MODES:
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
        # The base_url injected into the agent config at agent-create time is the
        # platform's own base URL, which is not necessarily reachable from inside
        # the agent container. Rebase it onto a container-reachable address.
        try:
            internal_base_url = self._config.k8s_internal_base_url or get_internal_base_url()
            gateway = resolve_agent_gateway_url(
                get_base_url(),
                mode=deployment_mode,
                override=self._config.gateway_url_override,
                internal_base_url=internal_base_url,
            )
        except UnreachableGatewayURLError as exc:
            logger.error("Refusing to deploy agent %r: %s", name, exc)
            return DeploymentInfo(name=name, status="failed", error=str(exc))

        # When platform auth is enabled, the agent carries no platform credential,
        # so route its inference calls through a loopback auth-proxy sidecar that
        # stamps a service-principal identity header. The agent targets the sidecar
        # on localhost; the sidecar forwards to *gateway* (the reachable platform).
        auth_proxy: AuthProxySpec | None = None
        if _platform_auth_enabled():
            proxy_port = self._config.auth_proxy_port
            proxy_base_url = f"http://127.0.0.1:{proxy_port}"
            # The sidecar runs the nmp-api image (it needs the `nemo` CLI), NOT the
            # agent runtime image. Qualify with the platform registry/tag unless an
            # explicit override is configured.
            proxy_image = self._config.auth_proxy_image or get_qualified_image(self._config.auth_proxy_image_name)
            auth_proxy = AuthProxySpec(
                image=proxy_image,
                port=proxy_port,
                upstream_base_url=gateway,
                principal=_AUTH_PROXY_PRINCIPAL,
            )
            config = rewrite_config_base_urls(config, proxy_base_url)
        else:
            config = rewrite_config_base_urls(config, gateway)

        deployment_config = build_deployment_config(
            name=name,
            workspace=workspace,
            image=resolved_image,
            port=self._config.container_port,
            nat_config=config,
            config_mount_path=self._config.config_mount_path,
            mode=deployment_mode,
            plugin_wheels_init_image=self._config.plugin_wheels_init_image,
            labels={
                "nemo.agents/deployment": name,
                "nemo.agents/mode": deployment_mode,
            },
            auth_proxy=auth_proxy,
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
        return _info_from_deployment(deployment)

    async def delete_deployment(self, workspace: str, name: str) -> bool:
        """Tear down plugin Deployment (+ Config).

        Returns ``True`` when the Deployment is gone and DeploymentConfig has
        been deleted (or was already absent) — the agents controller may then
        remove ``AgentDeployment``. Returns ``False`` when the Deployment is
        still present so a later reconcile can finish cleanup.
        """
        entities = self._entity_client()
        deployment_present = False
        try:
            deployment = await entities.get(Deployment, name=name, workspace=workspace)
            if deployment.status != "DELETING":
                deployment.status = "DELETING"
                deployment.desired_state = "STOPPED"
                await entities.update(deployment)
            deployment_present = True
        except NemoEntityNotFoundError:
            pass

        if deployment_present:
            gone = await self._wait_for_deployment_gone(workspace, name)
            if not gone:
                logger.warning(
                    "Deployment '%s/%s' still present after %.1fs; keeping AgentDeployment "
                    "and DeploymentConfig so teardown can finish on a later reconcile.",
                    workspace,
                    name,
                    _DELETE_CONFIG_WAIT_S,
                )
                return False

        try:
            await entities.delete(DeploymentConfig, name=name, workspace=workspace)
        except NemoEntityNotFoundError:
            pass
        return True

    async def _wait_for_deployment_gone(self, workspace: str, dep_name: str) -> bool:
        """Return True if the Deployment entity disappears within the wait budget."""
        entities = self._entity_client()
        deadline = time.monotonic() + _DELETE_CONFIG_WAIT_S
        while time.monotonic() < deadline:
            try:
                await entities.get(Deployment, name=dep_name, workspace=workspace)
            except NemoEntityNotFoundError:
                return True
            await asyncio.sleep(_DELETE_CONFIG_POLL_S)
        return False

    async def list_deployments(self, workspace: str | None = None) -> list[DeploymentInfo]:
        entities = self._entity_client()
        result = await entities.list(Deployment, workspace=workspace or "-")
        return [_info_from_deployment(deployment) for deployment in result.data]

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
