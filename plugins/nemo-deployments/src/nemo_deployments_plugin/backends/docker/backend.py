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
    build_docker_plan,
    build_port_bindings,
    build_volume_bindings,
    device_requests_for_gpus,
    env_dict,
    gpu_count_from_container,
    merged_volume_mounts,
    parse_docker_backend_config,
    restart_policy_kwargs,
)
from nemo_deployments_plugin.backends.docker.gpu import GPUAllocationError, get_shared_gpu_pool
from nemo_deployments_plugin.backends.docker.ports import find_available_port
from nemo_deployments_plugin.backends.docker.probes import check_readiness_probe, host_url_for_port
from nemo_deployments_plugin.backends.docker.status import (
    LOG_MAX_CHARS,
    map_docker_state_to_starting,
    map_exited_status,
    missing_container_status,
)
from nemo_deployments_plugin.backends.labels import (
    BACKOFF_LIMIT_LABEL,
    CONFIG_NAME_LABEL,
    CONTAINER_ROLE_LABEL,
    CONTAINER_ROLE_SERVER,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    MANAGED_BY_KEY,
    RESOURCE_SCOPE_LABEL,
    RESTART_POLICY_LABEL,
    companion_container_name,
    container_name,
    deployment_identity_labels,
    deployment_key,
    managed_by_filter,
)
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL
from nemo_deployments_plugin.entities import Container, Deployment, DeploymentConfig
from nemo_deployments_plugin.secrets import SecretResolutionError, resolve_deployment_config_secrets
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

_ONE_SHOT_RESTART_POLICIES = frozenset({"Never", "OnFailure"})
_EXITED_CONTAINER_STATES = frozenset({"exited", "dead"})
NGC_IMAGE_REGISTRY = os.getenv("NGC_IMAGE_REGISTRY", "nvcr.io")
NGC_IMAGE_REGISTRY_USER_NAME = os.getenv("NGC_IMAGE_REGISTRY_USER_NAME", "$oauthtoken")


def _is_ngc_image(image: str) -> bool:
    """Return whether an image belongs to the configured NGC registry."""
    return image == NGC_IMAGE_REGISTRY or image.startswith(f"{NGC_IMAGE_REGISTRY}/")


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
                restart_policy = (existing.labels or {}).get(RESTART_POLICY_LABEL, "Always")
                if restart_policy in _ONE_SHOT_RESTART_POLICIES and existing.status in _EXITED_CONTAINER_STATES:
                    logger.info(
                        "Removing exited one-shot container before recreate",
                        extra={
                            "container": c_name,
                            "restart_policy": restart_policy,
                            "status": existing.status,
                        },
                    )
                    try:
                        await asyncio.to_thread(existing.remove, force=True)
                    except self._docker_errors.APIError as exc:
                        return BackendStatusUpdate(
                            status="FAILED",
                            status_message=f"Failed to remove exited container before recreate: {exc}",
                        )
                else:
                    return await self.read_status(workspace=workspace, name=name)
            else:
                return BackendStatusUpdate(
                    status="FAILED",
                    status_message=f"Container name collision: {c_name} exists with different labels",
                )
        except self._docker_errors.NotFound:
            pass

        try:
            config = await self._load_deployment_config(workspace, config_name)
            config = await resolve_deployment_config_secrets(self._sdk, config)
            plan = build_docker_plan(config)
        except DeploymentConfigError as exc:
            return BackendStatusUpdate(status="FAILED", status_message=str(exc))
        except SecretResolutionError as exc:
            return BackendStatusUpdate(status="FAILED", status_message=str(exc))
        except NemoEntityNotFoundError:
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"DeploymentConfig '{config_name}' not found in workspace '{workspace}'",
            )
        except Exception as exc:
            logger.exception("Failed to load deployment config %s/%s", workspace, config_name)
            return BackendStatusUpdate(status="FAILED", status_message=f"Failed to load deployment config: {exc}")

        container_spec = plan.primary
        docker_cfg = parse_docker_backend_config(backend_config)
        if config.backend_config.docker is not None:
            docker_cfg = config.backend_config.docker

        dep_key = deployment_key(workspace, name)
        gpu_ids: list[int] = []
        gpu_pool = self._gpu_pool
        gpu_count = gpu_count_from_container(container_spec)
        if gpu_count > 0:
            if gpu_pool is None:
                return BackendStatusUpdate(
                    status="FAILED",
                    status_message="GPU requested but no GPUs detected on this host",
                )
            try:
                gpu_ids = gpu_pool.allocate_gpu(dep_key, num_requested=gpu_count)
            except GPUAllocationError as exc:
                return BackendStatusUpdate(status="FAILED", status_message=str(exc))

        host_ports: dict[int, int] = {}
        for port_spec in container_spec.ports:
            host_port = await find_available_port(
                self._client,
                self._executor_config.port_range_start,
                self._executor_config.port_range_end,
                exclude_ports=set(host_ports.values()),
            )
            if host_port is None:
                if gpu_ids and gpu_pool is not None:
                    gpu_pool.release_gpu(dep_key)
                return BackendStatusUpdate(
                    status="FAILED", status_message="No host ports available in configured range"
                )
            host_ports[port_spec.container_port] = host_port

        # Pull all images in the group (init + primary + sidecars) up front.
        if self._executor_config.pull_images:
            for container in [*plan.init_containers, container_spec, *plan.sidecars]:
                pull_error = await self._pull_image(
                    container.image,
                    ngc_api_key=env_dict(container).get("NGC_API_KEY"),
                )
                if pull_error is not None:
                    # A pull failure is only fatal if the image is not already
                    # present locally. Locally-built/loaded images (e.g. the LoRA
                    # adapters sidecar `nmp-api:local`) are not pullable from a
                    # registry, so fall back to the local copy when it exists.
                    # Only a genuine "not found locally" is fatal here; other
                    # docker client errors from images.get propagate rather than
                    # being masked as "image present".
                    try:
                        await asyncio.to_thread(self._client.images.get, container.image)
                        logger.info("Image %s not pullable but present locally; using local copy", container.image)
                    except (self._docker_errors.ImageNotFound, self._docker_errors.NotFound):
                        if gpu_ids and gpu_pool is not None:
                            gpu_pool.release_gpu(dep_key)
                        return BackendStatusUpdate(status="FAILED", status_message=pull_error)

        base_labels = {
            **labels,
            **config.labels,
            **deployment_identity_labels(
                workspace,
                name,
                config.restart_policy,
                config_name=config_name,
                backoff_limit=config.backoff_limit,
                resource_scope=self._executor_config.resource_scope,
            ),
        }

        # 1) Init containers run to completion, in order, before the group starts.
        for init in plan.init_containers:
            init_status = await self._run_init_container(
                workspace=workspace,
                name=name,
                config=config,
                init=init,
                base_labels=base_labels,
                dep_key=dep_key,
                gpu_ids=gpu_ids,
            )
            if init_status is not None:
                return init_status

        # 2) Primary (server) container: publishes ports, owns GPUs.
        server_run_kwargs = self._build_run_kwargs(
            workspace=workspace,
            config=config,
            container=container_spec,
            name=c_name,
            labels={**base_labels, CONTAINER_ROLE_LABEL: CONTAINER_ROLE_SERVER},
            host_ports=host_ports,
            gpu_ids=gpu_ids,
            network=docker_cfg.network,
        )
        try:
            server_container = await asyncio.to_thread(self._client.containers.run, **server_run_kwargs)
        except Exception as exc:
            if gpu_ids and gpu_pool is not None:
                gpu_pool.release_gpu(dep_key)
            logger.exception("Failed to start container %s", c_name)
            return BackendStatusUpdate(status="FAILED", status_message=f"Failed to start container: {exc}")

        # 3) Sidecars share the primary's network namespace + volumes; no ports/GPU.
        #
        # Known limitation: a sidecar joins ``network=container:<server>``, so it
        # is tied to *this* server container instance. Docker's Always restart
        # policy restarts the same server container in place (netns preserved), so
        # ordinary server crashes are fine. But if the server container is ever
        # replaced by a *new* container (a fresh create rather than an in-place
        # restart), the sidecar's netns reference dangles and nothing re-runs the
        # sidecars. Today a full recreate goes through delete_model_deployment
        # (which tears down the whole group) before create, so the sidecars are
        # re-run together; a future partial/primary-only recreate would need to
        # recreate the whole group to stay consistent.
        for sidecar in plan.sidecars:
            sidecar_name = companion_container_name(workspace, name, sidecar.name)
            sidecar_run_kwargs = self._build_run_kwargs(
                workspace=workspace,
                config=config,
                container=sidecar,
                name=sidecar_name,
                labels={**base_labels, CONTAINER_ROLE_LABEL: sidecar.name},
                host_ports={},
                gpu_ids=[],
                network=f"container:{c_name}",
            )
            try:
                await asyncio.to_thread(self._client.containers.run, **sidecar_run_kwargs)
            except Exception as exc:
                logger.exception("Failed to start sidecar container %s", sidecar_name)
                # Tear the whole group down so we don't leave a half-started deployment.
                await self.delete_deployment(workspace, name)
                return BackendStatusUpdate(
                    status="FAILED", status_message=f"Failed to start sidecar {sidecar.name}: {exc}"
                )

        endpoints = self._build_endpoints(container_spec, host_ports)
        if config.restart_policy in _ONE_SHOT_RESTART_POLICIES:
            return await self._observe_one_shot_primary_after_create(
                workspace=workspace,
                name=name,
                config=config,
                container=server_container,
                dep_key=dep_key,
                endpoints=endpoints,
            )
        return BackendStatusUpdate(
            status="STARTING",
            status_message=f"Container {c_name} created",
            endpoints=endpoints,
        )

    def _build_run_kwargs(
        self,
        *,
        workspace: str,
        config: DeploymentConfig,
        container: Container,
        name: str,
        labels: dict[str, str],
        host_ports: dict[int, int],
        gpu_ids: list[int],
        network: str | None,
    ) -> dict[str, Any]:
        """Build docker ``containers.run`` kwargs for one container in a group."""
        run_kwargs: dict[str, Any] = {
            "image": container.image,
            "name": name,
            "detach": True,
            "labels": labels,
            "environment": env_dict(container),
            **restart_policy_kwargs(config.restart_policy, config.backoff_limit),
        }
        # Mirror Kubernetes semantics (see the k8s compiler): a container spec's
        # ``command`` is the entrypoint override and ``args`` is the command
        # (CMD). Map them onto docker's distinct ``entrypoint`` / ``command``
        # kwargs so a driven container overrides the image's baked-in ENTRYPOINT
        # instead of appending to it. Conflating both into docker ``command``
        # leaves the image ENTRYPOINT in force and silently drops the spec.
        if container.command:
            run_kwargs["entrypoint"] = list(container.command)
        if container.args:
            run_kwargs["command"] = list(container.args)

        volume_bindings = build_volume_bindings(workspace, merged_volume_mounts(config, container))
        if volume_bindings:
            run_kwargs["volumes"] = volume_bindings

        # When joining another container's network namespace, docker forbids
        # publishing ports (they belong to the primary). Only the primary maps
        # host ports.
        if network is not None and network.startswith("container:"):
            run_kwargs["network"] = network
        else:
            if container.ports:
                run_kwargs["ports"] = build_port_bindings(container, host_ports)
            if network:
                run_kwargs["network"] = network

        device_requests = device_requests_for_gpus(gpu_ids)
        if device_requests:
            run_kwargs["device_requests"] = device_requests

        return run_kwargs

    async def _run_init_container(
        self,
        *,
        workspace: str,
        name: str,
        config: DeploymentConfig,
        init: Container,
        base_labels: dict[str, str],
        dep_key: str,
        gpu_ids: list[int],
    ) -> BackendStatusUpdate | None:
        """Run one init container to completion. Return an error status or None on success."""
        init_name = companion_container_name(workspace, name, f"init-{init.name}")
        # Best-effort clean any stale init container from a prior attempt.
        try:
            stale = await asyncio.to_thread(self._client.containers.get, init_name)
            if self._container_matches_deployment_group(stale, workspace, name):
                await asyncio.to_thread(stale.remove, force=True)
        except self._docker_errors.NotFound:
            pass
        except Exception:
            logger.warning("Failed to remove stale init container %s", init_name, exc_info=True)

        # Init containers are intentionally CPU-only: no device_requests is set,
        # so they never receive a GPU. This suits the current init workload
        # (lora-cache-init prepares the scratch dir). If the models compiler ever
        # emits a GPU-needing init container, this would need to plumb GPUs
        # through here.
        run_kwargs: dict[str, Any] = {
            "image": init.image,
            "name": init_name,
            "detach": True,
            "labels": {**base_labels, CONTAINER_ROLE_LABEL: f"init-{init.name}"},
            "environment": env_dict(init),
        }
        if init.command:
            run_kwargs["entrypoint"] = list(init.command)
        if init.args:
            run_kwargs["command"] = list(init.args)
        volume_bindings = build_volume_bindings(workspace, merged_volume_mounts(config, init))
        if volume_bindings:
            run_kwargs["volumes"] = volume_bindings

        def _run_and_wait() -> int:
            container = self._client.containers.run(**run_kwargs)
            result = container.wait(timeout=self._executor_config.docker_timeout)
            exit_code = self._exit_code_from_wait_result(result)
            try:
                container.remove(force=True)
            except Exception:
                logger.warning("Failed to remove init container %s", init_name, exc_info=True)
            return exit_code

        try:
            exit_code = await asyncio.to_thread(_run_and_wait)
        except Exception as exc:
            if gpu_ids and self._gpu_pool is not None:
                self._gpu_pool.release_gpu(dep_key)
            logger.exception("Init container %s failed to run", init_name)
            return BackendStatusUpdate(status="FAILED", status_message=f"Init container {init.name} failed: {exc}")

        if exit_code != 0:
            if gpu_ids and self._gpu_pool is not None:
                self._gpu_pool.release_gpu(dep_key)
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"Init container {init.name} exited with code {exit_code}",
            )
        return None

    async def read_status(self, *, workspace: str, name: str) -> BackendStatusUpdate:
        c_name = container_name(workspace, name)
        dep_key = deployment_key(workspace, name)
        try:
            container = await asyncio.to_thread(self._client.containers.get, c_name)
            if not self._container_matches_deployment_group(container, workspace, name):
                restart_policy = await self._resolve_restart_policy(workspace, name)
                return missing_container_status(restart_policy, container_name=c_name)
            await asyncio.to_thread(container.reload)
        except self._docker_errors.NotFound:
            restart_policy = await self._resolve_restart_policy(workspace, name)
            status_update = missing_container_status(restart_policy, container_name=c_name)
            if restart_policy in _ONE_SHOT_RESTART_POLICIES and self._gpu_pool is not None:
                self._gpu_pool.release_gpu(dep_key)
            return status_update
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
                sidecar_ok, sidecar_reason = await self._sidecars_healthy(workspace, name, config)
                if not sidecar_ok:
                    return BackendStatusUpdate(
                        status="STARTING",
                        status_message=f"Server ready but sidecar not ready ({sidecar_reason})",
                        endpoints=endpoints,
                    )
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
            restart_count = int(container.attrs.get("RestartCount", 0))
            return self._status_from_exited_container(
                exit_code=exit_code,
                restart_policy=restart_policy,
                labels=labels,
                dep_key=dep_key,
                restart_count=restart_count,
                endpoints=endpoints,
            )

        if state == "removing":
            return BackendStatusUpdate(status="DELETING", status_message=f"Container removing (ID: {container_id})")

        return BackendStatusUpdate(status="STARTING", status_message=f"Container state: {state}")

    @staticmethod
    def _exit_code_from_wait_result(result: dict[str, Any] | int) -> int:
        """Normalize a docker `container.wait()` result to an exit code."""
        return int(result.get("StatusCode", 1)) if isinstance(result, dict) else int(result)

    def _status_from_exited_container(
        self,
        *,
        exit_code: int,
        restart_policy: RestartPolicy,
        labels: dict[str, str],
        dep_key: str,
        restart_count: int = 0,
        endpoints: list[Endpoint] | None = None,
    ) -> BackendStatusUpdate:
        """Map a stopped container's exit code to a deployment status update."""
        resolved_endpoints = endpoints or []
        if exit_code == 0 and restart_policy in ("Never", "OnFailure"):
            if self._gpu_pool is not None:
                self._gpu_pool.release_gpu(dep_key)
            return BackendStatusUpdate(
                status="SUCCEEDED",
                status_message="Container exited successfully (code 0)",
                exit_code=exit_code,
                endpoints=resolved_endpoints,
            )
        if restart_policy == "Always":
            return BackendStatusUpdate(
                status="STARTING",
                status_message=f"Container exited (code {exit_code}); restart policy will recreate it",
                exit_code=exit_code,
                endpoints=resolved_endpoints,
            )
        if restart_policy == "OnFailure":
            backoff_limit = int(labels.get(BACKOFF_LIMIT_LABEL, "6"))
            if restart_count < backoff_limit:
                return BackendStatusUpdate(
                    status="STARTING",
                    status_message=(f"Container exited (code {exit_code}); retry {restart_count}/{backoff_limit}"),
                    exit_code=exit_code,
                    endpoints=resolved_endpoints,
                )
        if self._gpu_pool is not None:
            self._gpu_pool.release_gpu(dep_key)
        status = map_exited_status(exit_code, restart_policy)
        return BackendStatusUpdate(
            status=status,
            status_message=f"Container exited with code {exit_code}",
            exit_code=exit_code,
            endpoints=resolved_endpoints,
        )

    async def _observe_one_shot_primary_after_create(
        self,
        *,
        workspace: str,
        name: str,
        config: DeploymentConfig,
        container: DockerContainer,
        dep_key: str,
        endpoints: list[Endpoint],
    ) -> BackendStatusUpdate:
        """Observe a one-shot primary container immediately after create."""
        restart_policy = config.restart_policy
        labels = container.labels or {}

        if restart_policy == "Never":
            observe_timeout = self._executor_config.oneshot_observe_timeout_seconds

            def _wait_for_exit() -> int:
                return self._exit_code_from_wait_result(container.wait(timeout=observe_timeout))

            try:
                exit_code = await asyncio.to_thread(_wait_for_exit)
            except (
                ReadTimeout,
                Urllib3ReadTimeoutError,
                RequestsConnectionError,
                self._docker_errors.APIError,
            ):
                return BackendStatusUpdate(
                    status="STARTING",
                    status_message=(
                        f"Container {container.name} still running or status unavailable "
                        f"after observe wait ({observe_timeout}s)"
                    ),
                    endpoints=endpoints,
                )
            except Exception as exc:
                logger.exception("Failed waiting for one-shot container %s to exit", container.name)
                await self.delete_deployment(workspace, name)
                return BackendStatusUpdate(
                    status="FAILED",
                    status_message=f"Failed waiting for container to exit: {exc}",
                )
            return self._status_from_exited_container(
                exit_code=exit_code,
                restart_policy=restart_policy,
                labels=labels,
                dep_key=dep_key,
                endpoints=endpoints,
            )

        try:
            await asyncio.to_thread(container.reload)
        except (
            self._docker_errors.APIError,
            ReadTimeout,
            Urllib3ReadTimeoutError,
            RequestsConnectionError,
        ) as exc:
            return BackendStatusUpdate(
                status="STARTING",
                status_message=f"Container created but status check failed: {exc}",
                endpoints=endpoints,
            )
        if container.status in _EXITED_CONTAINER_STATES:
            attrs = container.attrs or {}
            exit_code = int(attrs.get("State", {}).get("ExitCode", 1))
            restart_count = int(attrs.get("RestartCount", 0))
            return self._status_from_exited_container(
                exit_code=exit_code,
                restart_policy=restart_policy,
                labels=labels,
                dep_key=dep_key,
                restart_count=restart_count,
                endpoints=endpoints,
            )

        container_name_label = container.name or "primary"
        return BackendStatusUpdate(
            status="STARTING",
            status_message=f"Container {container_name_label} created",
            endpoints=endpoints,
        )

    async def _sidecars_healthy(self, workspace: str, name: str, config: DeploymentConfig | None) -> tuple[bool, str]:
        """Return (all_healthy, reason) for a deployment's expected sidecar containers.

        The set of expected sidecars is derived from the deployment ``config``
        (every container after the primary), so a sidecar that has been *removed*
        entirely — not just exited — is still detected as not-ready. A sidecar is
        healthy only when a container for its role is present AND running; an
        exited or missing sidecar keeps the deployment out of READY (its Always
        restart policy recreates an exited one; a missing one signals a broken
        group).

        Deployments with no sidecars (the common single-container case) skip the
        Docker enumeration entirely.
        """
        expected_roles = {sidecar.name for sidecar in build_docker_plan(config).sidecars} if config else set()
        if not expected_roles:
            return True, "no sidecars"

        def _list() -> list[Any]:
            return self._client.containers.list(
                all=True,
                filters={
                    "label": [
                        f"{MANAGED_BY_KEY}={MANAGED_BY_LABEL}",
                        f"{DEPLOYMENT_WORKSPACE_LABEL}={workspace}",
                        f"{DEPLOYMENT_NAME_LABEL}={name}",
                        *self._resource_scope_filter_label(),
                    ]
                },
            )

        try:
            containers = await asyncio.to_thread(_list)
        except Exception:
            # If we cannot enumerate the group, do not block readiness on it.
            logger.warning("Failed to list sidecars for %s/%s", workspace, name, exc_info=True)
            return True, "sidecar check skipped"

        running_roles: set[str] = set()
        for container in containers:
            if not self._container_matches_deployment_group(container, workspace, name):
                continue
            role = (container.labels or {}).get(CONTAINER_ROLE_LABEL, "")
            if role not in expected_roles:
                continue
            if container.status != "running":
                return False, f"sidecar '{role}' is {container.status}"
            running_roles.add(role)

        missing = expected_roles - running_roles
        if missing:
            return False, f"sidecar '{sorted(missing)[0]}' is missing"
        return True, "sidecars running"

    async def delete_deployment(self, workspace: str, name: str) -> BackendStatusUpdate:
        c_name = container_name(workspace, name)
        dep_key = deployment_key(workspace, name)

        def _delete() -> None:
            # Remove every container in the deployment group: the primary
            # (dep-<hash>) plus any companion sidecar/init containers, which are
            # discoverable by the shared deployment identity labels.
            group: dict[str, Any] = {}
            try:
                for container in self._client.containers.list(
                    all=True,
                    filters={
                        "label": [
                            f"{MANAGED_BY_KEY}={MANAGED_BY_LABEL}",
                            f"{DEPLOYMENT_WORKSPACE_LABEL}={workspace}",
                            f"{DEPLOYMENT_NAME_LABEL}={name}",
                            *self._resource_scope_filter_label(),
                        ]
                    },
                ):
                    if self._container_matches_deployment_group(container, workspace, name):
                        group[container.name] = container
            except Exception:
                logger.warning("Failed to list group containers for %s; falling back to primary", c_name, exc_info=True)
            # Ensure the primary is included even if the label list query missed it.
            if c_name not in group:
                try:
                    primary = self._client.containers.get(c_name)
                    if self._container_matches_deployment_group(primary, workspace, name):
                        group[c_name] = primary
                except self._docker_errors.NotFound:
                    pass
            for container in group.values():
                try:
                    container.stop(timeout=30)
                    container.remove(force=True)
                except self._docker_errors.NotFound:
                    continue

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
                filters=managed_by_filter(resource_scope=self._executor_config.resource_scope),
            )
        except Exception:
            logger.warning("Failed to list managed containers", exc_info=True)
            return []

        seen: set[str] = set()
        for container in containers:
            container_labels = container.labels or {}
            if container_labels.get(MANAGED_BY_KEY) != MANAGED_BY_LABEL:
                continue
            if not self._labels_match_resource_scope(container_labels):
                continue
            ws = container_labels.get(DEPLOYMENT_WORKSPACE_LABEL)
            dep_name = container_labels.get(DEPLOYMENT_NAME_LABEL)
            if ws and dep_name:
                seen.add(f"{ws}/{dep_name}")
        return sorted(seen)

    def _resource_scope_filter_label(self) -> list[str]:
        return [f"{RESOURCE_SCOPE_LABEL}={self._executor_config.resource_scope}"]

    def _labels_match_resource_scope(self, labels: dict[str, Any]) -> bool:
        return labels.get(RESOURCE_SCOPE_LABEL) == self._executor_config.resource_scope

    def _container_matches_deployment_group(self, container: DockerContainer, workspace: str, name: str) -> bool:
        labels = container.labels or {}
        return (
            labels.get(DEPLOYMENT_WORKSPACE_LABEL) == workspace
            and labels.get(DEPLOYMENT_NAME_LABEL) == name
            and labels.get(MANAGED_BY_KEY) == MANAGED_BY_LABEL
            and self._labels_match_resource_scope(labels)
        )

    async def get_logs(self, *, workspace: str, name: str, tail: int = 100) -> LogResult:
        c_name = container_name(workspace, name)

        def _logs() -> bytes:
            container = self._client.containers.get(c_name)
            if not self._container_matches_deployment_group(container, workspace, name):
                raise self._docker_errors.NotFound(f"Container {c_name} not found")
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
        init_chmod: str | None = None
        init_image: str | None = None
        docker_section = backend_config.get("docker") or {}
        if isinstance(docker_section, dict):
            if docker_section.get("driver"):
                driver = str(docker_section["driver"])
            # initChmod/initImage let the compiler request the volume be made
            # writable by non-root workloads (docker analogue of k8s fsGroup).
            if docker_section.get("initChmod"):
                init_chmod = str(docker_section["initChmod"])
            if docker_section.get("initImage"):
                init_image = str(docker_section["initImage"])
        return await volume_ops.create_volume(
            self._client,
            workspace=workspace,
            name=name,
            driver=driver,
            init_chmod=init_chmod,
            init_image=init_image,
            resource_scope=self._executor_config.resource_scope,
        )

    async def read_volume_status(
        self,
        *,
        workspace: str,
        name: str,
        backend_config: dict[str, Any] | None = None,
    ) -> VolumeStatusUpdate:
        # backend_config is part of the DeploymentBackend ABC so the reconciler can pass
        # K8s namespace overrides; Docker volume names are global to the daemon.
        return await volume_ops.read_volume_status(self._client, workspace=workspace, name=name)

    async def delete_volume(
        self,
        workspace: str,
        name: str,
        *,
        backend_config: dict[str, Any] | None = None,
    ) -> VolumeStatusUpdate:
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
            self._container_matches_deployment_group(container, workspace, name)
            and labels.get(CONFIG_NAME_LABEL) == config_name
        )

    async def _pull_image(self, image: str, *, ngc_api_key: str | None) -> str | None:
        """Pull ``image``, authenticating to NGC when needed. Returns an error message or None."""
        pull_kwargs: dict[str, Any] = {}
        if _is_ngc_image(image):
            if ngc_api_key:
                pull_kwargs["auth_config"] = {
                    "username": NGC_IMAGE_REGISTRY_USER_NAME,
                    "password": ngc_api_key,
                }
            else:
                logger.warning(
                    "Pulling NGC image without NGC credentials",
                    extra={"image": image},
                )
        try:
            await asyncio.to_thread(self._client.images.pull, image, **pull_kwargs)
        except (self._docker_errors.APIError, self._docker_errors.ImageNotFound) as exc:
            message = f"Failed to pull image {image}: {exc}"
            if _is_ngc_image(image):
                message += (
                    ". Ensure the image exists and NGC_API_KEY (or platform.ngc_api_key_secret) is set correctly."
                )
            return message
        return None

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
