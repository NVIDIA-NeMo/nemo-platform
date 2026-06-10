# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker backend implementation for Models Controller service.

Implements the :class:`ServiceBackend` CRUD interface for managing model
deployments as Docker containers.  Heavy creation-pipeline logic (image
pulling, model downloading, container creation) is delegated to
:class:`DockerDeploymentCreationReconciler`.
"""

import asyncio
import os
from logging import getLogger
from typing import Any, Optional

import docker
import httpx
from docker.errors import APIError, NotFound
from nemo_platform import NotFoundError
from nemo_platform.types.inference.model_deployment import ModelDeployment
from nemo_platform.types.inference.model_deployment_config import ModelDeploymentConfig
from nemo_platform.types.models.model_entity import ModelEntity
from nmp.common.config import get_platform_config
from nmp.common.docker.gpu_pool import DockerGPUPool
from nmp.common.resources import SharedResourceManager
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate, ServiceBackend
from nmp.core.models.controllers.backends.common import (
    LOG_MAX_CHARS,
    LOG_TAIL_LINES,
    deployment_elapsed_seconds,
    format_duration,
)
from nmp.core.models.controllers.backends.docker.config import DockerBackendConfig
from nmp.core.models.controllers.backends.docker.creation_reconciler import (
    NGC_IMAGE_REGISTRY,
    NGC_IMAGE_REGISTRY_USER_NAME,
    DockerDeploymentCreationReconciler,
)
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ReadTimeout
from urllib3.exceptions import ReadTimeoutError as Urllib3ReadTimeoutError

logger = getLogger(__name__)


class DockerServiceBackend(ServiceBackend):
    """Docker-based backend for managing model deployments.

    Schedules models as Docker containers on the local Docker daemon.
    Creation pipeline orchestration is delegated to
    :class:`DockerDeploymentCreationReconciler`; this class owns the
    ``ServiceBackend`` CRUD interface, container health monitoring,
    and deployment lifecycle management.
    """

    def init(self) -> None:
        """Initialize Docker backend."""
        logger.info("Initializing Docker service backend")

        self._backend_config = DockerBackendConfig(**self._config)
        logger.debug(f"Backend config: {self._backend_config.model_dump()}")

        logger.info(
            f"Port forwarding enabled: will allocate ports from "
            f"{self._backend_config.models_docker_port_range_start} "
            f"to {self._backend_config.models_docker_port_range_end}"
        )

        resource_manager = SharedResourceManager.get_instance()
        self._gpu_pool: DockerGPUPool | None = resource_manager.get_gpu_pool()

        if self._gpu_pool is None:
            logger.warning(
                "No GPU pool available - no GPUs were detected on this system. "
                "GPU model deployments will fail until GPUs are available."
            )

        try:
            timeout = self._backend_config.docker_timeout

            env_timeout = os.getenv("DOCKER_TIMEOUT")
            if env_timeout:
                logger.warning(
                    f"DOCKER_TIMEOUT env var is set to {env_timeout}s, which may override "
                    f"the configured timeout of {timeout}s. Consider unsetting DOCKER_TIMEOUT."
                )

            self._client = docker.from_env(timeout=timeout)
            self._client.api.timeout = timeout

            docker_host = os.getenv("DOCKER_HOST", "unix:///var/run/docker.sock")
            logger.info(f"Connected to Docker daemon at {docker_host} with {timeout}s timeout")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise

        self._reconciler = DockerDeploymentCreationReconciler(
            client=self._client,
            backend_config=self._backend_config,
            nmp_sdk=self._nmp_sdk,
            gpu_pool=self._gpu_pool,
        )

    def shutdown(self) -> None:
        """Shutdown Docker backend and release resources."""
        logger.info("Shutting down Docker service backend")
        # Cancel all in-flight image-pull / puller tasks so they don't block
        # the event loop from draining after the controller receives SIGINT/SIGTERM.
        self._reconciler.shutdown()
        if hasattr(self, "_client") and self._client is not None:
            try:
                self._client.close()
                logger.debug("Docker client closed")
            except Exception as e:
                logger.warning(f"Error closing Docker client: {e}")

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def _get_deployment_key(self, deployment: ModelDeployment) -> str:
        """Shorthand for ``_reconciler.get_deployment_key``."""
        return self._reconciler.get_deployment_key(deployment.workspace, deployment.name)

    # ------------------------------------------------------------------
    # NGC authentication
    # ------------------------------------------------------------------

    async def _resolve_ngc_api_key(self) -> str | None:
        """Resolve NGC API key from secrets service (or platform env fallback)."""
        secret_ref = get_platform_config().ngc_api_key_secret.strip()
        if not secret_ref:
            fallback = os.environ.get(get_platform_config().ngc_api_key_env_var)
            if fallback:
                logger.debug("No platform.ngc_api_key_secret configured; using env fallback for NGC API key")
            return fallback or None
        parts = secret_ref.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            logger.warning(
                "platform.ngc_api_key_secret must be 'workspace/name'; got %r, skipping NGC key resolution",
                secret_ref,
            )
            return os.environ.get(get_platform_config().ngc_api_key_env_var) or None
        workspace, name = parts[0], parts[1]
        try:
            response = await self._nmp_sdk.secrets.access(name, workspace=workspace)
            if response.value:
                logger.debug("Resolved NGC API key from secret %s/%s", workspace, name)
                return response.value
            logger.warning("Secret %s/%s has no data", workspace, name)
        except NotFoundError:
            logger.info(
                "NGC API key secret %s/%s not found; falling back to env %s",
                workspace,
                name,
                get_platform_config().ngc_api_key_env_var,
            )
            return os.environ.get(get_platform_config().ngc_api_key_env_var) or None
        except Exception as e:
            logger.warning("Failed to resolve NGC API key from secret %s/%s: %s", workspace, name, e)
            return os.environ.get(get_platform_config().ngc_api_key_env_var) or None
        return None

    async def _ensure_ngc_login(self, ngc_api_key: str | None) -> None:
        """Log in to the NGC Docker registry if an API key is provided."""
        if not ngc_api_key:
            return
        try:
            logger.info("Authenticating to NGC registry: %s", NGC_IMAGE_REGISTRY)
            await asyncio.to_thread(
                self._client.login,
                username=NGC_IMAGE_REGISTRY_USER_NAME,
                password=ngc_api_key,
                registry=NGC_IMAGE_REGISTRY,
            )
            logger.info("Successfully authenticated to NGC registry")
        except Exception as e:
            logger.warning("Failed to authenticate to NGC registry: %s", e)

    # ==================================================================
    # ServiceBackend CRUD interface
    # ==================================================================

    async def create_model_deployment(
        self,
        deployment: ModelDeployment,
        config: ModelDeploymentConfig,
        model_entity: Optional[ModelEntity] = None,
    ) -> DeploymentStatusUpdate:
        """Create a new model deployment as a Docker container.

        Resolves NGC credentials and delegates the multi-stage creation
        pipeline to :class:`DockerDeploymentCreationReconciler`.
        """
        resolved_ngc_key = await self._resolve_ngc_api_key()
        await self._ensure_ngc_login(resolved_ngc_key)

        return await self._reconciler.register_deployment(
            deployment,
            config,
            model_entity,
            resolved_ngc_key,
        )

    async def update_model_deployment(
        self,
        deployment: ModelDeployment,
        config: ModelDeploymentConfig,
        model_entity: Optional[ModelEntity] = None,
    ) -> DeploymentStatusUpdate:
        """Update a model deployment by recreating the container."""
        logger.info(f"Updating Docker deployment: {deployment.workspace}/{deployment.name}")
        delete_result = await self.delete_model_deployment(deployment.workspace, deployment.name)
        if delete_result.status == "ERROR":
            return delete_result
        return await self.create_model_deployment(deployment, config, model_entity)

    async def get_model_deployment_status(self, deployment: ModelDeployment) -> DeploymentStatusUpdate:
        """Get the status of a Docker model deployment.

        While the deployment is still progressing through the creation
        pipeline this delegates to the reconciler's ``advance`` method.
        """
        if self._reconciler.is_deploying(deployment.workspace, deployment.name):
            deployment_key = self._reconciler.get_deployment_key(deployment.workspace, deployment.name)
            return await self._reconciler.advance(deployment_key)

        container_name = self._reconciler.get_container_name(deployment.workspace, deployment.name)

        try:
            container = await asyncio.to_thread(self._reconciler.get_container, container_name)
            await asyncio.to_thread(self._reconciler.reload_container, container)

            state = container.status
            container_id = container.id[:12]

            host_port = None
            ports = container.ports
            if ports and "8000/tcp" in ports:
                bindings = ports["8000/tcp"]
                if bindings and len(bindings) > 0:
                    host_port = bindings[0].get("HostPort")

            host_url = self._reconciler.get_host_url(container_name, host_port)

            logger.debug("Container status check", extra={"container": container_name, "state": state})

            if state == "running":
                started_at = container.attrs.get("State", {}).get("StartedAt", "unknown")
                health_path = self._reconciler.get_health_path_from_container(container)
                is_healthy, health_failure_reason = await self._probe_nim_health(
                    host_url, container_id=container_id, health_path=health_path
                )

                if is_healthy:
                    return DeploymentStatusUpdate(
                        status="READY",
                        status_message=(
                            f"Container is running and ready for inference (ID: {container_id}, started: {started_at})"
                        ),
                        host_url=host_url,
                    )
                else:
                    elapsed = deployment_elapsed_seconds(deployment)
                    timeout = self._backend_config.pending_timeout_seconds
                    restart_count = container.attrs.get("RestartCount", 0)
                    max_restarts = self._backend_config.max_restart_count

                    error_update = await self._check_crash_loop(
                        container_name, container_id, restart_count, max_restarts
                    ) or await self._check_pending_timeout(container_name, container_id, elapsed, timeout)
                    if error_update:
                        return error_update

                    # Use a stable message (no elapsed/timeout) so we don't create a new history entry every poll
                    status_msg = (
                        f"Container is running but the inference engine is still initializing "
                        f"(ID: {container_id}, started: {started_at}, "
                        f"health_url: {host_url}{health_path}"
                    )
                    if health_failure_reason:
                        status_msg += f", probe_result: {health_failure_reason}"
                    if restart_count > 0:
                        status_msg += f", restarts: {restart_count}"
                    status_msg += ")"
                    return DeploymentStatusUpdate(
                        status="PENDING",
                        status_message=status_msg,
                        host_url=host_url,
                    )

            elif state in ["created", "restarting"]:
                elapsed = deployment_elapsed_seconds(deployment)
                timeout = self._backend_config.pending_timeout_seconds
                restart_count = container.attrs.get("RestartCount", 0)
                max_restarts = self._backend_config.max_restart_count

                error_update = await self._check_crash_loop(
                    container_name,
                    container_id,
                    restart_count,
                    max_restarts,
                    container_state=state,
                ) or await self._check_pending_timeout(
                    container_name,
                    container_id,
                    elapsed,
                    timeout,
                    container_state=state,
                )
                if error_update:
                    return error_update

                # Use a stable message (no elapsed/timeout) so we don't create a new history entry every poll
                status_msg = f"Container is starting up (state: {state}, ID: {container_id}"
                if state == "restarting":
                    status_msg += f", restart count: {restart_count}"
                status_msg += ")"
                return DeploymentStatusUpdate(
                    status="PENDING",
                    status_message=status_msg,
                    host_url=host_url,
                )

            elif state in ["exited", "dead"]:
                dk = self._reconciler.get_deployment_key(deployment.workspace, deployment.name)
                if self._gpu_pool is not None:
                    released_gpus = self._gpu_pool.release_gpu(dk)
                    if released_gpus:
                        logger.info(
                            "Released GPUs from terminated deployment",
                            extra={
                                "gpu_ids": released_gpus,
                                "deployment_key": dk,
                                "container_state": state,
                            },
                        )

                exit_code = container.attrs.get("State", {}).get("ExitCode", "unknown")
                error_msg = f"Container exited with code {exit_code}"
                error_stack = ""

                try:
                    raw_logs = await asyncio.to_thread(container.logs, tail=LOG_TAIL_LINES)
                    logs = raw_logs.decode("utf-8", errors="ignore")
                    error_stack = logs
                    if len(error_stack) > LOG_MAX_CHARS:
                        error_stack = error_stack[-LOG_MAX_CHARS:]

                    last_lines = "\n".join([line for line in logs.split("\n")[-5:] if line.strip()])
                    if last_lines:
                        error_msg += f"\n\nLast log lines:\n{last_lines}"
                except Exception as e:
                    logger.warning(
                        "Failed to retrieve container logs",
                        extra={"container_name": container_name, "error": str(e)},
                    )

                return DeploymentStatusUpdate(
                    status="ERROR",
                    status_message=error_msg,
                    error_details={
                        "exit_code": exit_code,
                        "container_state": state,
                        "container_id": container_id,
                        "error_stack": error_stack if error_stack else None,
                    },
                    host_url=None,
                )

            elif state == "removing":
                return DeploymentStatusUpdate(
                    status="DELETING",
                    status_message=f"Container is being removed (ID: {container_id})",
                    host_url=None,
                )
            else:
                return DeploymentStatusUpdate(
                    status="UNKNOWN",
                    status_message=f"Container in unexpected state: {state} (ID: {container_id})",
                    host_url=host_url if state != "paused" else None,
                )

        except NotFound:
            dk = self._reconciler.get_deployment_key(deployment.workspace, deployment.name)
            if self._gpu_pool is not None:
                released_gpus = self._gpu_pool.release_gpu(dk)
                if released_gpus:
                    logger.info(
                        "Released GPUs from lost deployment",
                        extra={"gpu_ids": released_gpus, "deployment_key": dk},
                    )

            logger.warning(
                "Container not found for deployment",
                extra={
                    "container_name": container_name,
                    "deployment": f"{deployment.workspace}/{deployment.name}",
                },
            )
            return DeploymentStatusUpdate(
                status="LOST",
                status_message=(
                    f"Container not found - may have been manually deleted or never created. "
                    f"Expected container name: {container_name}"
                ),
                error_details={"expected_container_name": container_name},
                host_url=None,
            )
        except (APIError, ReadTimeout, Urllib3ReadTimeoutError, RequestsConnectionError) as e:
            logger.error(
                "Docker API error checking container status",
                extra={"container_name": container_name, "error": str(e)},
            )
            return DeploymentStatusUpdate(
                status="UNKNOWN",
                status_message=f"Docker API error while checking container status: {e}",
                error_details={"error": str(e), "container_name": container_name},
                host_url=None,
            )
        except Exception as e:
            logger.error(
                "Unexpected error checking container status",
                extra={"container_name": container_name, "error": str(e)},
                exc_info=True,
            )
            return DeploymentStatusUpdate(
                status="UNKNOWN",
                status_message=f"Failed to get container status: {e}",
                error_details={"error": str(e), "container_name": container_name},
                host_url=None,
            )

    async def delete_model_deployment(self, workspace: str, name: str) -> DeploymentStatusUpdate:
        """Delete a Docker model deployment by workspace and name."""
        return await self._delete_by_model_deployment_id(workspace, name)

    async def list_managed_deployment_names(self) -> list[str]:
        """List deployment names the backend currently manages via Docker labels."""
        try:
            containers = await asyncio.to_thread(
                self._reconciler.list_containers,
                all=True,
                filters={"label": f"{MODEL_MANAGED_BY_LABEL}={MODEL_MANAGED_BY_MODELS_CONTROLLER}"},
            )
        except Exception as e:
            logger.warning(f"Failed to list managed containers for orphan reconciliation: {e}")
            return []

        seen: set[str] = set()
        for container in containers:
            labels = container.labels or {}
            ws = labels.get("nmp.nvidia.com/deployment-workspace")
            n = labels.get("nmp.nvidia.com/deployment-name")
            if ws and n:
                seen.add(f"{ws}/{n}")
        return sorted(seen)

    # ==================================================================
    # Deletion
    # ==================================================================

    async def _delete_by_model_deployment_id(self, workspace: str, name: str) -> DeploymentStatusUpdate:
        """Delete a Docker deployment by workspace/name."""
        container_name = self._reconciler.get_container_name(workspace, name)
        puller_container_name = self._reconciler.get_puller_container_name(workspace, name)
        volume_name = self._reconciler.get_volume_name(workspace, name)
        deployment_key = self._reconciler.get_deployment_key(workspace, name)

        # Cancel any in-progress creation task and clean up the reconciler's state.
        await self._reconciler.cleanup(deployment_key)

        logger.info(
            "Deleting Docker model deployment",
            extra={"workspace": workspace, "deployment_name": name, "container": container_name},
        )

        container_names = [
            (puller_container_name, False),
            (f"{container_name}-sidecar", False),
            (container_name, True),
        ]

        for c_name, fail_on_exception in container_names:
            try:
                container = await asyncio.to_thread(self._reconciler.get_container, c_name)
                container_id = container.id[:12]

                logger.info(f"Stopping container {c_name} (ID: {container_id})")
                try:
                    await asyncio.to_thread(self._reconciler.stop_container, container, timeout=30)
                except NotFound:
                    logger.debug(f"Container {c_name} already stopped/removed")
                except (APIError, ReadTimeout, Urllib3ReadTimeoutError, RequestsConnectionError) as e:
                    logger.warning(f"Failed to stop container {c_name} after retries: {e}")
                except Exception as e:
                    logger.warning(f"Unexpected error stopping container {c_name}: {e}")

                logger.info(f"Removing container {c_name}")
                try:
                    await asyncio.to_thread(self._reconciler.remove_container, container, force=True)
                    logger.info(f"Successfully removed container {c_name}")
                except NotFound:
                    logger.debug(f"Container {c_name} already removed")
                except (APIError, ReadTimeout, Urllib3ReadTimeoutError, RequestsConnectionError) as e:
                    if "removal" in str(e).lower() or "already" in str(e).lower():
                        logger.debug(f"Container {c_name} removal already in progress")
                    else:
                        logger.warning(f"Failed to remove container {c_name} after retries: {e}")
                except Exception as e:
                    logger.warning(f"Unexpected error removing container {c_name}: {e}")

            except NotFound:
                logger.info(f"Container {c_name} not found, may have been already deleted")
            except (APIError, ReadTimeout, Urllib3ReadTimeoutError, RequestsConnectionError) as e:
                logger.error(f"Docker API error deleting container {c_name}: {e}", exc_info=True)
                if fail_on_exception:
                    return DeploymentStatusUpdate(
                        status="ERROR",
                        status_message=f"Failed to delete container due to Docker API error: {e}",
                        error_details={"error": str(e), "container_name": c_name},
                        host_url=None,
                    )
            except Exception as e:
                logger.error(f"Unexpected error deleting container {c_name}: {e}", exc_info=True)
                if fail_on_exception:
                    return DeploymentStatusUpdate(
                        status="ERROR",
                        status_message=f"Failed to delete container: {e}",
                        error_details={"error": str(e), "container_name": c_name},
                        host_url=None,
                    )

        # Remove volumes
        volume_names = [volume_name, f"{volume_name}-scratch"]
        for v_name in volume_names:
            try:
                volume = await asyncio.to_thread(self._client.volumes.get, v_name)
                logger.info(f"Removing volume {v_name}")
                await asyncio.to_thread(volume.remove, force=True)
                logger.info(f"Successfully removed volume {v_name}")
            except NotFound:
                logger.info(f"Volume {v_name} not found, already deleted")
            except Exception as e:
                logger.warning(f"Error removing volume {v_name}: {e}")

        if self._gpu_pool is not None:
            released_gpus = self._gpu_pool.release_gpu(deployment_key)
            if released_gpus:
                logger.debug(f"Released GPU(s) {released_gpus} from deployment {deployment_key}")

        return DeploymentStatusUpdate(
            status="DELETED",
            status_message=f"Successfully deleted container {container_name} and cleaned up volume {volume_name}",
            host_url=None,
        )

    # ==================================================================
    # Container health probing
    # ==================================================================

    async def _fetch_container_error_logs(self, container_name: str) -> str:
        """Fetch recent container logs for error reporting, truncated to LOG_MAX_CHARS."""
        try:
            container = await asyncio.to_thread(self._reconciler.get_container, container_name)
            raw_logs = await asyncio.to_thread(container.logs, tail=LOG_TAIL_LINES)
            logs = raw_logs.decode("utf-8", errors="ignore")
            if len(logs) > LOG_MAX_CHARS:
                logs = logs[-LOG_MAX_CHARS:]
            return logs
        except Exception as e:
            logger.warning(
                "Failed to retrieve container logs for error report",
                extra={"container_name": container_name, "error": str(e)},
            )
            return ""

    async def _build_pending_timeout_error(
        self,
        container_name: str,
        elapsed: float,
    ) -> tuple[str, str]:
        """Build user-facing error message and error_stack for a PENDING timeout."""
        error_stack = await self._fetch_container_error_logs(container_name)
        status_msg = (
            f"Deployment timed out after {format_duration(elapsed)} waiting for NIM "
            f"to pass health checks (timeout: {format_duration(self._backend_config.pending_timeout_seconds)}).\n\n"
            f"Inspect the NIM container logs by running this command where quickstart is installed:\n"
            f"  docker logs {container_name}"
        )
        return status_msg, error_stack

    async def _build_crash_loop_error(
        self,
        container_name: str,
        restart_count: int,
    ) -> tuple[str, str]:
        """Build user-facing error message and error_stack for a crash loop."""
        error_stack = await self._fetch_container_error_logs(container_name)
        status_msg = (
            f"Deployment entered crash loop after {restart_count} container restarts "
            f"(max: {self._backend_config.max_restart_count}).\n\n"
            f"Inspect the NIM container logs by running this command where quickstart is installed:\n"
            f"  docker logs {container_name}"
        )
        return status_msg, error_stack

    async def _check_crash_loop(
        self,
        container_name: str,
        container_id: str,
        restart_count: int,
        max_restarts: int,
        container_state: str | None = None,
    ) -> DeploymentStatusUpdate | None:
        """Return an ERROR status if the container has exceeded the restart limit."""
        if restart_count < max_restarts:
            return None
        logger.warning(
            "Container entered crash loop",
            extra={
                "container_name": container_name,
                "restart_count": restart_count,
                "max_restarts": max_restarts,
            },
        )
        status_msg, error_stack = await self._build_crash_loop_error(container_name, restart_count)
        error_details: dict[str, Any] = {
            "reason": "crash_loop",
            "restart_count": restart_count,
            "max_restart_count": max_restarts,
            "container_name": container_name,
            "container_id": container_id,
            "error_stack": error_stack if error_stack else None,
        }
        if container_state is not None:
            error_details["container_state"] = container_state
        return DeploymentStatusUpdate(
            status="ERROR",
            status_message=status_msg,
            error_details=error_details,
            host_url=None,
        )

    async def _check_pending_timeout(
        self,
        container_name: str,
        container_id: str,
        elapsed: float,
        timeout: int,
        container_state: str | None = None,
    ) -> DeploymentStatusUpdate | None:
        """Return an ERROR status if the pending timeout has been exceeded."""
        if elapsed < timeout:
            return None
        logger.warning(
            "Deployment PENDING timeout exceeded",
            extra={
                "container_name": container_name,
                "elapsed": format_duration(elapsed),
                "timeout": format_duration(timeout),
            },
        )
        status_msg, error_stack = await self._build_pending_timeout_error(container_name, elapsed)
        error_details: dict[str, Any] = {
            "reason": "pending_timeout",
            "elapsed_seconds": int(elapsed),
            "timeout_seconds": timeout,
            "container_name": container_name,
            "container_id": container_id,
            "error_stack": error_stack if error_stack else None,
        }
        if container_state is not None:
            error_details["container_state"] = container_state
        return DeploymentStatusUpdate(
            status="ERROR",
            status_message=status_msg,
            error_details=error_details,
            host_url=None,
        )

    async def _probe_nim_health(
        self,
        host_url: str,
        timeout: float = 5.0,
        container_id: str | None = None,
        health_path: str = "/v1/health/ready",
    ) -> tuple[bool, str]:
        """Probe the inference engine's health endpoint to check readiness.

        NIM exposes /v1/health/ready and vLLM exposes /health; both return 200 when
        the model is fully loaded and ready to serve. The path is engine-specific and
        provided by the caller.

        Args:
            host_url: The base URL of the container (e.g., http://localhost:8500)
            timeout: Request timeout in seconds
            container_id: Optional container ID for logging context
            health_path: Engine-specific readiness path appended to host_url

        Returns:
            Tuple of (is_healthy, failure_reason). failure_reason is empty string if healthy.
        """
        health_url = f"{host_url}{health_path}"
        container_ctx = f" (container: {container_id})" if container_id else ""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(health_url)
                if response.status_code == 200:
                    logger.debug(f"NIM health check passed: {health_url}{container_ctx}")
                    return True, ""
                else:
                    reason = f"HTTP {response.status_code}"
                    try:
                        body = response.text[:200] if response.text else ""
                        if body:
                            reason += f" - {body}"
                    except Exception:
                        pass
                    logger.info(f"NIM health check returned {response.status_code}: {health_url}{container_ctx}")
                    return False, reason
        except httpx.TimeoutException:
            reason = f"timeout after {timeout}s"
            logger.info(f"NIM health check timed out ({timeout}s): {health_url}{container_ctx}")
            return False, reason
        except httpx.ConnectError as e:
            reason = f"connection error: {e}"
            logger.info(f"NIM health check connection error: {health_url}{container_ctx} - {e}")
            return False, reason
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            logger.info(f"NIM health check failed: {health_url}{container_ctx} - {reason}")
            return False, reason
