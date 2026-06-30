# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker substrate backend for the deployments plugin."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

from nemo_deployments_plugin.backends.base import (
    BackendStatusUpdate,
    DeploymentBackend,
    LogResult,
    VolumeStatusUpdate,
)
from nemo_deployments_plugin.backends.docker import volumes as volume_ops
from nemo_deployments_plugin.backends.docker.config import DockerExecutorConfig
from nemo_deployments_plugin.backends.docker.containers import (
    DeploymentConfigError,
    build_port_bindings,
    build_volume_bindings,
    device_requests_for_gpus,
    env_dict,
    gpu_count_from_container,
    merged_volume_mounts,
    parse_docker_backend_config,
    restart_policy_kwargs,
    validate_config_for_docker,
)
from nemo_deployments_plugin.backends.docker.gpu import GPUAllocationError, get_shared_gpu_pool
from nemo_deployments_plugin.backends.docker.labels import (
    BACKOFF_LIMIT_LABEL,
    CONFIG_NAME_LABEL,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    MANAGED_BY_KEY,
    RESTART_POLICY_LABEL,
    container_name,
    deployment_identity_labels,
    deployment_key,
    managed_by_filter,
)
from nemo_deployments_plugin.backends.docker.ports import find_available_port
from nemo_deployments_plugin.backends.docker.probes import check_readiness_probe, host_url_for_port
from nemo_deployments_plugin.backends.docker.status import (
    LOG_MAX_CHARS,
    map_docker_state_to_starting,
    map_exited_status,
    missing_container_status,
)
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL
from nemo_deployments_plugin.entities import Container, Deployment, DeploymentConfig
from nemo_deployments_plugin.types import Endpoint, RestartPolicy
from nemo_platform.resources.entities import AsyncEntitiesResource
from nemo_platform_plugin.config import LOOPBACK_ADDRESSES
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ReadTimeout
from urllib3.exceptions import ReadTimeoutError as Urllib3ReadTimeoutError

if TYPE_CHECKING:
    from docker.models.containers import Container as DockerContainer

    import docker

logger = logging.getLogger(__name__)


class DockerDeploymentBackend(DeploymentBackend):
    """Manage deployments and volumes as Docker containers and volumes."""

    _client: docker.DockerClient

    def init(self) -> None:
        try:
            import docker
            from docker import errors as docker_errors
        except ImportError as exc:
            raise RuntimeError(
                "docker package is required for DockerDeploymentBackend. "
                "Install with: uv sync --package nemo-deployments-plugin --extra docker"
            ) from exc

        self._docker = docker
        self._docker_errors = docker_errors
        self._executor_config = DockerExecutorConfig.model_validate(self._config)
        self._entities = NemoEntitiesClient(AsyncEntitiesResource(self._sdk))
        self._gpu_pool = get_shared_gpu_pool()
        self._client = self._create_client()

    def _create_client(self) -> docker.DockerClient:
        kwargs: dict[str, Any] = {"timeout": self._executor_config.docker_timeout}
        if self._executor_config.docker_host:
            kwargs["base_url"] = self._executor_config.docker_host
        client = self._docker.from_env(**kwargs)
        client.api.timeout = self._executor_config.docker_timeout
        return client

    def shutdown(self) -> None:
        if hasattr(self, "_client") and self._client is not None:
            self._client.close()

    async def _load_deployment_config(self, workspace: str, config_name: str) -> DeploymentConfig:
        return await self._entities.get(DeploymentConfig, config_name, workspace=workspace)

    async def create_deployment(
        self,
        *,
        workspace: str,
        name: str,
        config_name: str,
        labels: dict[str, str],
        backend_config: dict[str, Any],
    ) -> BackendStatusUpdate:
        c_name = container_name(workspace, name)
        try:
            existing = await asyncio.to_thread(self._client.containers.get, c_name)
            if self._container_matches_deployment(existing, workspace, name, config_name):
                return await self.read_status(workspace=workspace, name=name)
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"Container name collision: {c_name} exists with different labels",
            )
        except self._docker_errors.NotFound:
            pass

        try:
            config = await self._load_deployment_config(workspace, config_name)
            container_spec = validate_config_for_docker(config)
        except DeploymentConfigError as exc:
            return BackendStatusUpdate(status="FAILED", status_message=str(exc))
        except NemoEntityNotFoundError:
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"DeploymentConfig '{config_name}' not found in workspace '{workspace}'",
            )
        except Exception as exc:
            logger.exception("Failed to load deployment config %s/%s", workspace, config_name)
            return BackendStatusUpdate(status="FAILED", status_message=f"Failed to load deployment config: {exc}")

        docker_cfg = parse_docker_backend_config(backend_config)
        if config.backend_config.docker is not None:
            docker_cfg = config.backend_config.docker

        dep_key = deployment_key(workspace, name)
        gpu_ids: list[int] = []
        gpu_count = gpu_count_from_container(container_spec)
        if gpu_count > 0:
            if self._gpu_pool is None:
                return BackendStatusUpdate(
                    status="FAILED",
                    status_message="GPU requested but no GPUs detected on this host",
                )
            try:
                gpu_ids = self._gpu_pool.allocate_gpu(dep_key, num_requested=gpu_count)
            except GPUAllocationError as exc:
                return BackendStatusUpdate(status="FAILED", status_message=str(exc))

        host_ports: dict[int, int] = {}
        for port_spec in container_spec.ports:
            host_port = await find_available_port(
                self._client,
                docker_cfg,
                exclude_ports=set(host_ports.values()),
            )
            if host_port is None:
                if gpu_ids:
                    self._gpu_pool.release_gpu(dep_key)  # type: ignore[union-attr]
                return BackendStatusUpdate(
                    status="FAILED", status_message="No host ports available in configured range"
                )
            host_ports[port_spec.container_port] = host_port

        if self._executor_config.pull_images:
            try:
                await asyncio.to_thread(self._client.images.pull, container_spec.image)
            except (self._docker_errors.APIError, self._docker_errors.ImageNotFound) as exc:
                if gpu_ids:
                    self._gpu_pool.release_gpu(dep_key)  # type: ignore[union-attr]
                return BackendStatusUpdate(status="FAILED", status_message=f"Failed to pull image: {exc}")

        all_labels = {
            **labels,
            **config.labels,
            **deployment_identity_labels(
                workspace,
                name,
                config.restart_policy,
                config_name=config_name,
                backoff_limit=config.backoff_limit,
            ),
        }
        run_kwargs: dict[str, Any] = {
            "image": container_spec.image,
            "name": c_name,
            "detach": True,
            "labels": all_labels,
            "environment": env_dict(container_spec),
            **restart_policy_kwargs(config.restart_policy, config.backoff_limit),
        }
        if container_spec.command:
            run_kwargs["command"] = container_spec.command
        if container_spec.args:
            run_kwargs["command"] = list(container_spec.command) + list(container_spec.args)

        volume_bindings = build_volume_bindings(workspace, merged_volume_mounts(config, container_spec))
        if volume_bindings:
            run_kwargs["volumes"] = volume_bindings

        if container_spec.ports:
            run_kwargs["ports"] = build_port_bindings(container_spec, host_ports)

        device_requests = device_requests_for_gpus(gpu_ids)
        if device_requests:
            run_kwargs["device_requests"] = device_requests

        if docker_cfg.network:
            run_kwargs["network"] = docker_cfg.network

        try:
            await asyncio.to_thread(self._client.containers.run, **run_kwargs)
        except Exception as exc:
            if gpu_ids:
                self._gpu_pool.release_gpu(dep_key)  # type: ignore[union-attr]
            logger.exception("Failed to start container %s", c_name)
            return BackendStatusUpdate(status="FAILED", status_message=f"Failed to start container: {exc}")

        endpoints = self._build_endpoints(container_spec, host_ports)
        return BackendStatusUpdate(
            status="STARTING",
            status_message=f"Container {c_name} created",
            endpoints=endpoints,
        )

    async def read_status(self, *, workspace: str, name: str) -> BackendStatusUpdate:
        c_name = container_name(workspace, name)
        try:
            container = await asyncio.to_thread(self._client.containers.get, c_name)
            await asyncio.to_thread(container.reload)
        except self._docker_errors.NotFound:
            restart_policy = await self._resolve_restart_policy(workspace, name)
            return missing_container_status(restart_policy, container_name=c_name)
        except (
            self._docker_errors.APIError,
            ReadTimeout,
            Urllib3ReadTimeoutError,
            RequestsConnectionError,
        ) as exc:
            logger.error("Transient Docker API error checking container %s: %s", c_name, exc)
            return BackendStatusUpdate(
                status="UNKNOWN",
                status_message=f"Docker API error while checking container status: {exc}",
                error_details={"error": str(exc), "container_name": c_name},
            )
        except Exception as exc:
            return BackendStatusUpdate(status="FAILED", status_message=f"Docker API error: {exc}")

        labels = container.labels or {}
        restart_policy: RestartPolicy = labels.get(RESTART_POLICY_LABEL, "Always")
        state = container.status
        container_id = (container.id or "")[:12]
        host_ports = self._extract_host_ports(container)
        endpoints = self._endpoints_from_container_ports(container, host_ports)

        if state in ("created", "restarting"):
            return map_docker_state_to_starting(container_id, state)

        if state == "running":
            host_url = self._primary_host_url(host_ports)
            config = await self._load_config_from_labels(workspace, labels)
            probe = None
            if config is not None and config.containers:
                probe = config.containers[0].readiness_probe
            ready, reason = await check_readiness_probe(
                container=container,
                probe=probe,
                host_url=host_url,
                host_ports=host_ports,
            )
            if ready and restart_policy == "Always":
                return BackendStatusUpdate(
                    status="READY",
                    status_message=f"Container running and ready ({reason})",
                    endpoints=endpoints,
                )
            if ready and restart_policy in ("OnFailure", "Never"):
                return BackendStatusUpdate(
                    status="STARTING",
                    status_message=f"Container running ({reason})",
                    endpoints=endpoints,
                )
            return BackendStatusUpdate(
                status="STARTING",
                status_message=f"Container running but not ready ({reason})",
                endpoints=endpoints,
            )

        if state in ("exited", "dead"):
            exit_code = int(container.attrs.get("State", {}).get("ExitCode", 1))
            if exit_code == 0 and restart_policy in ("Never", "OnFailure"):
                dep_key = deployment_key(workspace, name)
                if self._gpu_pool is not None:
                    self._gpu_pool.release_gpu(dep_key)
                return BackendStatusUpdate(
                    status="SUCCEEDED",
                    status_message="Container exited successfully (code 0)",
                    exit_code=exit_code,
                    endpoints=endpoints,
                )
            if restart_policy == "Always":
                return BackendStatusUpdate(
                    status="STARTING",
                    status_message=f"Container exited (code {exit_code}); restart policy will recreate it",
                    exit_code=exit_code,
                    endpoints=endpoints,
                )
            if restart_policy == "OnFailure":
                restart_count = int(container.attrs.get("RestartCount", 0))
                backoff_limit = int(labels.get(BACKOFF_LIMIT_LABEL, "6"))
                if restart_count < backoff_limit:
                    return BackendStatusUpdate(
                        status="STARTING",
                        status_message=f"Container exited (code {exit_code}); retry {restart_count}/{backoff_limit}",
                        exit_code=exit_code,
                        endpoints=endpoints,
                    )
            dep_key = deployment_key(workspace, name)
            if self._gpu_pool is not None:
                self._gpu_pool.release_gpu(dep_key)
            status = map_exited_status(exit_code, restart_policy)
            message = f"Container exited with code {exit_code}"
            return BackendStatusUpdate(
                status=status,
                status_message=message,
                exit_code=exit_code,
                endpoints=endpoints,
            )

        if state == "removing":
            return BackendStatusUpdate(status="DELETING", status_message=f"Container removing (ID: {container_id})")

        return BackendStatusUpdate(status="STARTING", status_message=f"Container state: {state}")

    async def delete_deployment(self, workspace: str, name: str) -> BackendStatusUpdate:
        c_name = container_name(workspace, name)
        dep_key = deployment_key(workspace, name)

        def _delete() -> None:
            try:
                container = self._client.containers.get(c_name)
                container.stop(timeout=30)
                container.remove(force=True)
            except self._docker_errors.NotFound:
                return

        try:
            await asyncio.to_thread(_delete)
        except Exception as exc:
            return BackendStatusUpdate(status="FAILED", status_message=f"Failed to delete container: {exc}")
        finally:
            if self._gpu_pool is not None:
                self._gpu_pool.release_gpu(dep_key)

        return BackendStatusUpdate(status="SUCCEEDED", status_message=f"Container {c_name} deleted")

    async def list_managed_deployment_names(self) -> list[str]:
        try:
            containers = await asyncio.to_thread(
                self._client.containers.list,
                all=True,
                filters=managed_by_filter(),
            )
        except Exception:
            logger.warning("Failed to list managed containers", exc_info=True)
            return []

        seen: set[str] = set()
        for container in containers:
            container_labels = container.labels or {}
            if container_labels.get(MANAGED_BY_KEY) != MANAGED_BY_LABEL:
                continue
            ws = container_labels.get(DEPLOYMENT_WORKSPACE_LABEL)
            dep_name = container_labels.get(DEPLOYMENT_NAME_LABEL)
            if ws and dep_name:
                seen.add(f"{ws}/{dep_name}")
        return sorted(seen)

    async def get_logs(self, *, workspace: str, name: str, tail: int = 100) -> LogResult:
        c_name = container_name(workspace, name)

        def _logs() -> bytes:
            container = self._client.containers.get(c_name)
            return container.logs(tail=tail, timestamps=True)

        try:
            raw = await asyncio.to_thread(_logs)
            text = raw.decode("utf-8", errors="ignore")
            lines = text.splitlines()
            truncated = len(text) > LOG_MAX_CHARS
            if truncated:
                lines = lines[-tail:]
            return LogResult(lines=lines, truncated=truncated)
        except self._docker_errors.NotFound:
            return LogResult(lines=[f"Container {c_name} not found"])
        except Exception as exc:
            return LogResult(lines=[f"Failed to fetch logs: {exc}"])

    async def create_volume(
        self,
        *,
        workspace: str,
        name: str,
        size: str,
        access_modes: list[str],
        backend_config: dict[str, Any],
    ) -> VolumeStatusUpdate:
        del size, access_modes
        driver = "local"
        docker_section = backend_config.get("docker") or {}
        if isinstance(docker_section, dict) and docker_section.get("driver"):
            driver = str(docker_section["driver"])
        return await volume_ops.create_volume(
            self._client,
            workspace=workspace,
            name=name,
            driver=driver,
        )

    async def read_volume_status(self, *, workspace: str, name: str) -> VolumeStatusUpdate:
        return await volume_ops.read_volume_status(self._client, workspace=workspace, name=name)

    async def delete_volume(self, workspace: str, name: str) -> VolumeStatusUpdate:
        return await volume_ops.delete_volume(self._client, workspace=workspace, name=name)

    def _container_matches_deployment(
        self,
        container: DockerContainer,
        workspace: str,
        name: str,
        config_name: str,
    ) -> bool:
        labels = container.labels or {}
        return (
            labels.get(DEPLOYMENT_WORKSPACE_LABEL) == workspace
            and labels.get(DEPLOYMENT_NAME_LABEL) == name
            and labels.get(CONFIG_NAME_LABEL) == config_name
            and labels.get(MANAGED_BY_KEY) == MANAGED_BY_LABEL
        )

    async def _resolve_restart_policy(self, workspace: str, name: str) -> RestartPolicy:
        config = await self._load_config_for_deployment_entity(workspace, name)
        if config is not None:
            return config.restart_policy
        return "Always"

    async def _load_config_from_labels(self, workspace: str, labels: dict[str, str]) -> DeploymentConfig | None:
        config_name = labels.get(CONFIG_NAME_LABEL)
        if not config_name:
            return await self._load_config_for_deployment_entity(
                workspace,
                labels.get(DEPLOYMENT_NAME_LABEL, ""),
            )
        try:
            return await self._entities.get(DeploymentConfig, config_name, workspace=workspace)
        except Exception:
            return None

    async def _load_config_for_deployment_entity(
        self,
        workspace: str,
        deployment_name: str,
    ) -> DeploymentConfig | None:
        if not deployment_name:
            return None
        try:
            deployment = await self._entities.get(Deployment, deployment_name, workspace=workspace)
            return await self._entities.get(
                DeploymentConfig,
                deployment.deployment_config,
                workspace=workspace,
            )
        except Exception:
            return None

    def _extract_host_ports(self, container: DockerContainer) -> dict[int, int]:
        result: dict[int, int] = {}
        ports = container.ports or {}
        for key, bindings in ports.items():
            if not bindings:
                continue
            container_port = int(str(key).split("/")[0])
            host_port = bindings[0].get("HostPort")
            if host_port:
                result[container_port] = int(host_port)
        return result

    def _primary_host_url(self, host_ports: dict[int, int]) -> str | None:
        if not host_ports:
            return None
        host_port = next(iter(host_ports.values()))
        host = os.environ.get("NMP_LOOPBACK_ADDRESS", LOOPBACK_ADDRESSES[0])
        return host_url_for_port(host, host_port)

    def _build_endpoints(self, container_spec: Container, host_ports: dict[int, int]) -> list[Endpoint]:
        endpoints: list[Endpoint] = []
        host = os.environ.get("NMP_LOOPBACK_ADDRESS", LOOPBACK_ADDRESSES[0])
        for port_spec in container_spec.ports:
            host_port = host_ports.get(port_spec.container_port)
            if host_port is None:
                continue
            endpoint_name = port_spec.name or f"port-{port_spec.container_port}"
            protocol = "tcp" if port_spec.protocol == "UDP" else "http"
            scheme = "http"
            endpoints.append(
                Endpoint(
                    name=endpoint_name,
                    url=host_url_for_port(host, host_port, scheme=scheme),
                    protocol=protocol,
                )
            )
        return endpoints

    def _endpoints_from_container_ports(self, container: DockerContainer, host_ports: dict[int, int]) -> list[Endpoint]:
        if not host_ports:
            return []
        host = os.environ.get("NMP_LOOPBACK_ADDRESS", LOOPBACK_ADDRESSES[0])
        endpoints: list[Endpoint] = []
        for container_port, host_port in host_ports.items():
            endpoints.append(
                Endpoint(
                    name=f"port-{container_port}",
                    url=host_url_for_port(host, host_port),
                    protocol="http",
                )
            )
        return endpoints
