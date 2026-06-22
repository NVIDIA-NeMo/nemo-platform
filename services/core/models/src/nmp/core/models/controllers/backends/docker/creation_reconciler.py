# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker deployment creation reconciler for the Models Controller service.

Manages the multi-stage, non-blocking pipeline that creates a model deployment
as a Docker container:  image pull → (optional) model puller → container creation.

The DockerServiceBackend delegates to this class for all creation-related Docker
orchestration, keeping the backend focused on the ServiceBackend CRUD interface,
container health monitoring, and lifecycle management.
"""

import asyncio
import logging
import os
import socket
from dataclasses import dataclass, field
from enum import Enum
from logging import getLogger
from typing import Any, Dict, Optional
from urllib.parse import urljoin

from docker.errors import APIError, ImageNotFound, NotFound
from docker.models.containers import Container
from docker.models.volumes import Volume
from nemo_platform.types.inference.model_deployment import ModelDeployment
from nemo_platform.types.inference.model_deployment_config import ModelDeploymentConfig
from nemo_platform.types.models.model_entity import ModelEntity
from nemo_platform_plugin.jobs.image import get_qualified_image
from nmp.common.config import get_auth_config, get_platform_config
from nmp.common.config.base import LOOPBACK_ADDRESSES
from nmp.common.docker.gpu_pool import DockerGPUPool, GPUAllocationError
from nmp.common.sdk_factory import get_sdk_on_behalf_of
from nmp.core.models.app import ModelWeightsType, get_model_weights_type, is_multi_llm_image, parse_model_name_revision
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.app.utils import _get_k8s_safe_name
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate
from nmp.core.models.controllers.backends.common import DeploymentConfigView, deployment_config_view
from nmp.core.models.controllers.backends.docker import vllm_compiler
from nmp.core.models.controllers.backends.docker.config import (
    MODELS_DOCKER_NIM_MULTI_GPU_SHM_SIZE,
    MODELS_DOCKER_NIM_MULTI_GPU_SHM_SIZE_PER_GPU,
    DockerBackendConfig,
)
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ReadTimeout
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential
from urllib3.exceptions import ReadTimeoutError as Urllib3ReadTimeoutError

import docker

logger = getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration for Docker operations
# ---------------------------------------------------------------------------

DOCKER_RETRY_ATTEMPTS = int(os.getenv("MODELS_DOCKER_RETRY_ATTEMPTS", "7"))
DOCKER_RETRY_WAIT_MIN = 2
DOCKER_RETRY_WAIT_MAX = 10

HUGGINGFACE_HUB_URL = "https://huggingface.co"

NGC_IMAGE_REGISTRY = os.getenv("NGC_IMAGE_REGISTRY", "nvcr.io")
NGC_IMAGE_REGISTRY_USER_NAME = os.getenv("NGC_IMAGE_REGISTRY_USER_NAME", "$oauthtoken")

ENGINE_NIM = "nim"
ENGINE_VLLM = "vllm"
ENGINE_GENERIC = "generic"

# Docker label recording the engine, read back at status time to pick the health probe.
ENGINE_LABEL = "nmp.nvidia.com/engine"

# Docker label recording the resolved readiness-probe path, read back at status
# time. Stamped at create so status polling doesn't need the deployment config.
HEALTH_PATH_LABEL = "nmp.nvidia.com/health-path"

# Per-engine readiness probe paths (relative to the container host URL).
ENGINE_HEALTH_PATHS: dict[str, str] = {
    ENGINE_NIM: "/v1/health/ready",
    ENGINE_VLLM: "/health",
}


def _config_engine(config: Any) -> str:
    """Return the engine discriminant as a lowercase string (defaults to nim)."""
    engine = getattr(config, "engine", None)
    if engine is None:
        return ENGINE_NIM
    # engine may be an enum or a plain string depending on the SDK model.
    return str(getattr(engine, "value", engine)).lower()


def _resolve_health_path(engine: str, view: DeploymentConfigView) -> str:
    """Resolve the readiness-probe path for a deployment.

    Precedence: an explicit ``executor_config.health_check_path`` wins; otherwise
    fall back to the engine's standard endpoint. ``generic`` containers have no
    engine default, so they fall back to the NIM path unless they set their own.
    """
    if getattr(view, "health_check_path", None):
        return view.health_check_path
    return ENGINE_HEALTH_PATHS.get(engine, ENGINE_HEALTH_PATHS[ENGINE_NIM])


def _should_retry_docker_error(exception: BaseException) -> bool:
    """Determine if a Docker exception should be retried."""
    if isinstance(exception, (NotFound, ImageNotFound)):
        return False
    if isinstance(exception, APIError) and exception.status_code == 409:
        return False
    return isinstance(
        exception, (ReadTimeout, Urllib3ReadTimeoutError, RequestsConnectionError, TimeoutError, APIError)
    )


docker_retry = retry(
    stop=stop_after_attempt(DOCKER_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=DOCKER_RETRY_WAIT_MIN, max=DOCKER_RETRY_WAIT_MAX),
    retry=_should_retry_docker_error,
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


def _compute_multi_gpu_shm_size(fixed_total: str, per_gpu_mb: int, gpu_count: int) -> str:
    """Compute shm_size for multi-GPU deployment.

    Returns fixed_total if non-empty (e.g. '4g'), else per_gpu_mb * gpu_count as '{n}m'.
    """
    if fixed_total:
        return fixed_total
    return f"{per_gpu_mb * gpu_count}m"


# ---------------------------------------------------------------------------
# Creation pipeline data types
# ---------------------------------------------------------------------------


class CreationStage(str, Enum):
    """Stages of the non-blocking deployment creation pipeline."""

    PULLING_NIM_IMAGE = "pulling_nim_image"
    PULLING_PULLER_IMAGE = "pulling_puller_image"
    RUNNING_PULLER = "running_puller"
    CREATING_CONTAINER = "creating_container"


@dataclass
class CreationState:
    """In-memory state for a deployment progressing through the creation pipeline."""

    stage: CreationStage
    task: asyncio.Task | None = None
    deployment: Any = None
    config: Any = None
    model_entity: Any = None
    model_weights_type: Any = None
    volume_name: str = ""
    scratch_volume_name: str = ""
    nim_image: str = ""
    ngc_api_key: str | None = None
    is_multi_llm: bool = False
    puller_container_name: str = ""
    tool_call_plugin_path: str | None = None
    plugin_fileset: str | None = None
    error_details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# DockerDeploymentCreationReconciler
# ---------------------------------------------------------------------------


class DockerDeploymentCreationReconciler:
    """Manages the multi-stage deployment creation pipeline and Docker operations.

    Handles image pulling, model weight downloading (via the HuggingFace puller
    container), GPU/port allocation, and final NIM container creation.

    Owns the in-progress creation state for all deployments; the backend delegates
    to :meth:`register_deployment`, :meth:`is_deploying`, :meth:`advance`,
    :meth:`cleanup`, and :meth:`shutdown`.
    """

    def __init__(
        self,
        client: docker.DockerClient,
        backend_config: DockerBackendConfig,
        nmp_sdk: Any,
        gpu_pool: DockerGPUPool | None,
    ) -> None:
        self._client = client
        self._backend_config = backend_config
        self._nmp_sdk = nmp_sdk
        self._gpu_pool = gpu_pool
        # In-progress creation state: maps deployment key -> CreationState.
        self._creation_states: dict[str, CreationState] = {}

    # ======================================================================
    # Helpers
    # ======================================================================

    def _get_busybox_image(self) -> str:
        """Return the configured BusyBox image reference."""
        return f"{self._backend_config.busybox_image}:{self._backend_config.busybox_image_tag}"

    # ======================================================================
    # Docker SDK wrappers (retry-decorated)
    # ======================================================================

    @docker_retry
    def get_container(self, container_name: str) -> Container:
        return self._client.containers.get(container_name)

    @docker_retry
    def reload_container(self, container: Container) -> None:
        container.reload()

    @docker_retry
    def stop_container(self, container: Container, timeout: int = 30) -> None:
        container.stop(timeout=timeout)

    @docker_retry
    def remove_container(self, container: Container, force: bool = True) -> None:
        container.remove(force=force)

    @docker_retry
    def list_containers(self, **kwargs: Any) -> list[Container]:
        return self._client.containers.list(**kwargs)

    @docker_retry
    def create_volume(self, volume_name: str) -> Volume:
        return self._client.volumes.create(volume_name)

    @docker_retry
    def pull_image(self, image_name: str, image_tag: str | None = None) -> None:
        self._client.images.pull(image_name, tag=image_tag)

    @docker_retry
    def run_container(self, **kwargs: Any) -> Container:
        return self._client.containers.run(**kwargs)

    @docker_retry
    def create_and_start_container(self, create_args: Dict[str, Any]) -> Container:
        container = self._client.containers.create(**create_args)
        container.start()
        return container

    def pull_image_if_not_local(self, image: str) -> None:
        """Pull an image only when it is not already available locally."""
        logger.info(f"Checking for image {image}...")
        try:
            self._client.images.get(image)
            logger.info(f"Image {image} found locally")
        except ImageNotFound:
            logger.info(f"Image {image} not found locally, pulling from registry...")
            self.pull_image(image)
            logger.info(f"Successfully pulled image {image}")

    # ======================================================================
    # Name / key generators
    # ======================================================================

    def get_container_name(self, workspace: str, name: str) -> str:
        label_name = f"md-{workspace}-{name}"
        return _get_k8s_safe_name(label_name, max_length=63, name_type="label")

    def get_volume_name(self, workspace: str, name: str) -> str:
        label_name = f"nim-cache-{workspace}-{name}"
        return _get_k8s_safe_name(label_name, max_length=63, name_type="label")

    def get_puller_container_name(self, workspace: str, name: str) -> str:
        label_name = f"md-puller-{workspace}-{name}"
        return _get_k8s_safe_name(label_name, max_length=63, name_type="label")

    def get_deployment_key(self, workspace: str, name: str) -> str:
        return f"{workspace}/{name}"

    def get_health_path_from_container(self, container: Container) -> str:
        """Resolve the readiness probe path from the container's labels.

        Prefers the explicit health-path label (which already accounts for a
        user-supplied ``executor_config.health_check_path`` resolved at create
        time). Falls back to the engine label's standard endpoint, then the NIM
        path for older containers that predate these labels.
        """
        try:
            labels = container.labels or {}
        except Exception:
            labels = {}
        explicit_path = labels.get(HEALTH_PATH_LABEL)
        if explicit_path:
            return explicit_path
        engine = str(labels.get(ENGINE_LABEL, ENGINE_NIM)).lower()
        return ENGINE_HEALTH_PATHS.get(engine, ENGINE_HEALTH_PATHS[ENGINE_NIM])

    # ======================================================================
    # Network / URL helpers
    # ======================================================================

    def get_host_url(self, container_name: str, host_port: int | None) -> str:
        match self._backend_config.models_docker_networking_mode:
            case "dond":
                return f"http://{container_name}:8000"
            case "dind":
                return f"http://{self._backend_config.models_docker_host_service_name}:{host_port}"
            case _:
                return f"http://localhost:{host_port}"

    def _should_attach_network(self) -> bool:
        return self._backend_config.models_docker_networking_mode == "dond"

    def _assign_network(self, run_kwargs: dict) -> None:
        if self._backend_config.models_docker_networking_mode == "local":
            run_kwargs["network_mode"] = "host"
            logger.info("Container will use host network (local mode)")
        elif self._should_attach_network() and self._backend_config.models_docker_network:
            run_kwargs["network"] = self._backend_config.models_docker_network
            logger.info(f"Container will join network: {self._backend_config.models_docker_network}")

    def _get_hf_compatible_files_url(self) -> str:
        files_url = get_platform_config().get_service_url("files")
        if (
            self._backend_config.models_docker_networking_mode == "dond"
            and self._backend_config.models_docker_container_name
        ):
            for loopback in LOOPBACK_ADDRESSES:
                if loopback in files_url:
                    files_url = files_url.replace(loopback, self._backend_config.models_docker_container_name)
                    logger.info(
                        f"DOND mode: replaced {loopback} with {self._backend_config.models_docker_container_name} in files_url"
                    )
                    break
        return urljoin(files_url, "/apis/files/v2/hf")

    # ======================================================================
    # Port allocation
    # ======================================================================

    def _is_remote_docker_host(self) -> bool:
        docker_host = os.environ.get("DOCKER_HOST", "")
        return docker_host.startswith("tcp://")

    def _is_port_free(self, port: int) -> bool:
        if self._is_remote_docker_host():
            logger.debug(f"Remote Docker host detected, skipping local port check for {port}")
            return True
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))  # noqa: S104  # nosec B104
                return True
        except OSError:
            logger.debug(f"Port {port} is not free (system process may be using it)")
            return False

    async def find_available_port(self) -> Optional[int]:
        try:
            all_containers = await asyncio.to_thread(
                self.list_containers,
                all=True,
                filters={"label": f"{MODEL_MANAGED_BY_LABEL}={MODEL_MANAGED_BY_MODELS_CONTROLLER}"},
            )
        except Exception as e:
            logger.error(f"Failed to list containers: {e}")
            return None

        used_ports: set[int] = set()
        for container in all_containers:
            try:
                ports = container.ports
                if ports:
                    for port_bindings in ports.values():
                        if port_bindings:
                            for binding in port_bindings:
                                if binding and "HostPort" in binding:
                                    used_ports.add(int(binding["HostPort"]))
            except Exception as e:
                logger.warning(f"Failed to get ports for container {container.name}: {e}")

        for port in range(
            self._backend_config.models_docker_port_range_start,
            self._backend_config.models_docker_port_range_end + 1,
        ):
            if port not in used_ports and self._is_port_free(port):
                logger.debug(f"Found available port: {port}")
                return port

        logger.error(
            f"No available ports in range "
            f"{self._backend_config.models_docker_port_range_start}-{self._backend_config.models_docker_port_range_end}"
        )
        return None

    # ======================================================================
    # Model helpers
    # ======================================================================

    def _extract_model_repo_from_artifact(self, model_entity: ModelEntity) -> str:
        if not model_entity.fileset:
            raise ValueError("Model entity fileset is required for Files service weights")
        files_url_str = str(model_entity.fileset)
        model_repo = files_url_str.removeprefix("hf://").removeprefix("fileset://")
        return model_repo

    def _get_model_repo_from_entity(
        self,
        model_entity: ModelEntity | None,
        model_weights_type: ModelWeightsType,
        nim_config: Any = None,
    ) -> str:
        if model_weights_type == ModelWeightsType.FILES_SERVICE:
            if model_entity and model_entity.fileset:
                return self._extract_model_repo_from_artifact(model_entity)
            if not nim_config:
                raise ValueError("nim_config is required for FILES_SERVICE without model entity artifact")
            model_workspace, model_name, _ = parse_model_name_revision(
                model_namespace=nim_config.model_namespace,
                model_name=nim_config.model_name,
                model_revision=nim_config.model_revision,
            )
            if not model_workspace or not model_name:
                raise ValueError(
                    f"Cannot determine fileset path: missing workspace or name "
                    f"(workspace={model_workspace}, name={model_name})"
                )
            return f"{model_workspace}/{model_name}"
        elif model_weights_type == ModelWeightsType.HUGGINGFACE:
            if not nim_config:
                raise ValueError("nim_config is required for HUGGINGFACE model type")
            model_workspace, model_name, _ = parse_model_name_revision(
                model_namespace=nim_config.model_namespace,
                model_name=nim_config.model_name,
                model_revision=nim_config.model_revision,
            )
            if not model_workspace or not model_name:
                raise ValueError(
                    f"Cannot determine HF model repo: missing model workspace or name "
                    f"(workspace={model_workspace}, name={model_name})"
                )
            return f"{model_workspace}/{model_name}"
        else:
            raise ValueError(
                f"Model weights type: {model_weights_type} is not supported. "
                f"Supported types: {ModelWeightsType.FILES_SERVICE}, {ModelWeightsType.HUGGINGFACE}"
            )

    # ======================================================================
    # Creation pipeline – public entry points
    # ======================================================================

    async def register_deployment(
        self,
        deployment: ModelDeployment,
        config: ModelDeploymentConfig,
        model_entity: Optional[ModelEntity],
        ngc_api_key: str | None,
    ) -> DeploymentStatusUpdate:
        """Kick off the creation pipeline for a new deployment.

        Performs quick validation and setup, then starts the first long-running
        phase (NIM image pull) as a background task.  Stores the ``CreationState``
        internally and returns an initial PENDING status (or ERROR on setup failure).
        """
        container_name = self.get_container_name(deployment.workspace, deployment.name)
        deployment_key = self.get_deployment_key(deployment.workspace, deployment.name)
        logger.info(
            f"Creating Docker deployment: {deployment.workspace}/{deployment.name} (container: {container_name})"
        )

        # Release any stale GPU allocations from a previous deployment attempt.
        if self._gpu_pool is not None:
            released_gpus = self._gpu_pool.release_gpu(deployment_key)
            if released_gpus:
                logger.info(f"Released stale GPU allocation {released_gpus} for {deployment_key} before recreation")

        model_weights_type = get_model_weights_type(
            model_deployment=deployment,
            model_deployment_config=config,
            model_entity=model_entity,
        )
        weights_from_files = model_weights_type == ModelWeightsType.FILES_SERVICE
        if weights_from_files:
            logger.info(
                f"Pulling weights from Files service for {deployment.workspace}/{deployment.name}, "
                "will run model puller first"
            )

        # Check if container already exists
        try:
            existing_container = await asyncio.to_thread(self.get_container, container_name)
            logger.warning(f"Container {container_name} already exists, removing it first")
            try:
                await asyncio.to_thread(existing_container.stop, timeout=10)
            except Exception:
                pass
            await asyncio.to_thread(existing_container.remove, force=True)
        except NotFound:
            pass
        except Exception as e:
            logger.error(f"Error checking for existing container {container_name}: {e}")
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Failed to check for existing container: {e}",
                error_details={"error": str(e)},
                host_url=None,
            )

        engine = _config_engine(config)
        view = deployment_config_view(config)
        if engine == ENGINE_VLLM:
            image_name, image_tag = vllm_compiler.resolve_vllm_image(
                view,
                self._backend_config.default_vllm_image,
                self._backend_config.default_vllm_image_tag,
            )
        else:
            image_name = view.image_name or self._backend_config.default_nimservice_image
            image_tag = view.image_tag or self._backend_config.default_nimservice_image_tag
        full_image = f"{image_name}:{image_tag}"
        logger.info(f"Using image: {full_image} (engine={engine})")

        # Create volumes for model cache
        volume_name = self.get_volume_name(deployment.workspace, deployment.name)
        try:
            await asyncio.to_thread(self.create_volume, volume_name)
            logger.info(f"Created volume: {volume_name}")
        except Exception as e:
            logger.warning(f"Failed to create volume {volume_name} (may already exist): {e}")

        scratch_volume_name = volume_name + "-scratch"
        try:
            await asyncio.to_thread(self.create_volume, scratch_volume_name)
            logger.info(f"Created volume: {scratch_volume_name}")
        except Exception as e:
            logger.warning(f"Failed to create volume {scratch_volume_name} (may already exist): {e}")

        # Multi-LLM detection only applies to NIM images; vLLM/generic are never multi-LLM.
        is_multi_llm = False
        if engine == ENGINE_NIM:
            effective_image = view.image_name or self._backend_config.default_nimservice_image
            is_multi_llm = is_multi_llm_image(effective_image)
            logger.debug(f"Detected multi-LLM image: {is_multi_llm} (effective_image={effective_image})")

        plugin_fileset: str | None = None
        if view.tool_call_config and view.tool_call_config.tool_call_plugin:
            plugin_fileset = view.tool_call_config.tool_call_plugin
        elif (
            model_entity
            and model_entity.spec
            and model_entity.spec.tool_call_config
            and model_entity.spec.tool_call_config.tool_call_plugin
        ):
            plugin_fileset = model_entity.spec.tool_call_config.tool_call_plugin

        # Start NIM image pull in background
        logger.info(f"Starting background image pull for {full_image}")
        pull_task = asyncio.ensure_future(asyncio.to_thread(self.pull_image_if_not_local, full_image))

        state = CreationState(
            stage=CreationStage.PULLING_NIM_IMAGE,
            task=pull_task,
            deployment=deployment,
            config=config,
            model_entity=model_entity,
            model_weights_type=model_weights_type,
            volume_name=volume_name,
            scratch_volume_name=scratch_volume_name,
            nim_image=full_image,
            ngc_api_key=ngc_api_key,
            is_multi_llm=is_multi_llm,
            plugin_fileset=plugin_fileset,
        )

        self._creation_states[deployment_key] = state

        return DeploymentStatusUpdate(
            status="PENDING",
            status_message=(
                f"Pulling container image {full_image}. This may take several minutes for large NIM images."
            ),
        )

    def is_deploying(self, workspace: str, name: str) -> bool:
        """Return True while the deployment is still progressing through the creation pipeline."""
        return self.get_deployment_key(workspace, name) in self._creation_states

    async def advance(self, deployment_key: str) -> DeploymentStatusUpdate:
        """Advance the creation pipeline one step and return the current status.

        The full lifecycle is readable here:
          PULLING_NIM_IMAGE → (needs puller?) PULLING_PULLER_IMAGE → RUNNING_PULLER
                                              (no puller?)           CREATING_CONTAINER

        RUNNING_PULLER and CREATING_CONTAINER are complex enough to warrant their
        own helpers; the transitions into and out of those stages remain visible below.
        """
        state = self._creation_states.get(deployment_key)
        if state is None:
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message="Internal error: creation state lost",
                error_details={"error": "creation_state_missing", "deployment_key": deployment_key},
            )
        try:
            match state.stage:
                # ── Stage 1: pull NIM container image ───────────────────────────
                case CreationStage.PULLING_NIM_IMAGE:
                    if not self._is_task_complete(state):
                        return DeploymentStatusUpdate(
                            status="PENDING",
                            status_message=(
                                f"Pulling container image {state.nim_image}. "
                                "This may take several minutes for large NIM images."
                            ),
                        )

                    error = self._get_task_error(state)
                    if error is not None:
                        error_str = str(error)
                        logger.error("Image pull failed for %s: %s", deployment_key, error_str)
                        self._creation_states.pop(deployment_key, None)
                        if isinstance(error, ImageNotFound):
                            return DeploymentStatusUpdate(
                                status="ERROR",
                                status_message=(
                                    f"Image not found in registry: {state.nim_image}. "
                                    "Ensure the image exists and platform.ngc_api_key_secret "
                                    "(or NGC_API_KEY env) is set correctly."
                                ),
                                error_details={"error": error_str, "image": state.nim_image},
                            )
                        return DeploymentStatusUpdate(
                            status="ERROR",
                            status_message=f"Failed to pull image {state.nim_image}: {error_str}",
                            error_details={"error": error_str, "image": state.nim_image, "stage": "image_pull"},
                        )

                    logger.info("NIM image pull complete for %s", deployment_key)

                    if self._needs_puller(state):
                        # ── Transition → PULLING_PULLER_IMAGE ───────────────────
                        puller_image = self._backend_config.huggingface_model_puller
                        logger.info("Starting background puller image pull for %s", deployment_key)
                        state.task = asyncio.ensure_future(
                            asyncio.to_thread(self.pull_image_if_not_local, puller_image)
                        )
                        state.stage = CreationStage.PULLING_PULLER_IMAGE
                        return DeploymentStatusUpdate(
                            status="PENDING",
                            status_message=f"NIM image ready. Pulling model puller image {puller_image}...",
                        )

                    # ── Transition → CREATING_CONTAINER ─────────────────────────
                    state.stage = CreationStage.CREATING_CONTAINER
                    state.task = None
                    status, complete = await self._advance_creating_container(deployment_key, state)
                    if complete:
                        self._creation_states.pop(deployment_key, None)
                    return status

                # ── Stage 2 (optional): pull model-puller image ──────────────────
                case CreationStage.PULLING_PULLER_IMAGE:
                    if not self._is_task_complete(state):
                        return DeploymentStatusUpdate(
                            status="PENDING",
                            status_message="Pulling model puller image...",
                        )

                    error = self._get_task_error(state)
                    if error is not None:
                        error_str = str(error)
                        logger.error("Puller image pull failed for %s: %s", deployment_key, error_str)
                        self._creation_states.pop(deployment_key, None)
                        return DeploymentStatusUpdate(
                            status="ERROR",
                            status_message=f"Failed to pull model puller image: {error_str}",
                            error_details={"error": error_str, "stage": "puller_image_pull"},
                        )

                    logger.info("Puller image ready for %s, starting model puller container", deployment_key)
                    try:
                        puller_container = await self._start_model_puller_container(state)
                    except Exception as e:
                        logger.error("Failed to start model puller for %s: %s", deployment_key, e)
                        self._creation_states.pop(deployment_key, None)
                        return DeploymentStatusUpdate(
                            status="ERROR",
                            status_message=f"Failed to start model puller: {e}",
                            error_details={"error": str(e), "stage": "model_puller"},
                        )

                    # ── Transition → RUNNING_PULLER ──────────────────────────────
                    state.puller_container_name = puller_container.name
                    state.stage = CreationStage.RUNNING_PULLER
                    state.task = None
                    return DeploymentStatusUpdate(
                        status="PENDING",
                        status_message="Downloading model weights. This may take several minutes.",
                    )

                # ── Stage 3 (optional): run model-puller container ───────────────
                case CreationStage.RUNNING_PULLER:
                    status, complete = await self._advance_running_puller(deployment_key, state)
                    if complete:
                        self._creation_states.pop(deployment_key, None)
                    return status

                # ── Stage 4: create and start NIM container ──────────────────────
                case CreationStage.CREATING_CONTAINER:
                    status, complete = await self._advance_creating_container(deployment_key, state)
                    if complete:
                        self._creation_states.pop(deployment_key, None)
                    return status

        except Exception as e:
            logger.error("Unexpected error advancing creation for %s: %s", deployment_key, e, exc_info=True)
            self._creation_states.pop(deployment_key, None)
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Unexpected error during deployment creation: {e}",
                error_details={"error": str(e), "stage": state.stage.value},
            )

        self._creation_states.pop(deployment_key, None)
        return DeploymentStatusUpdate(
            status="ERROR",
            status_message=f"Internal error: unknown creation stage {state.stage}",
            error_details={"stage": state.stage.value},
        )

    def shutdown(self) -> None:
        """Cancel all in-flight creation tasks on service shutdown."""
        for key, state in list(self._creation_states.items()):
            if state.task is not None and not state.task.done():
                state.task.cancel()
                logger.info("Cancelled in-flight creation task for %s on shutdown", key)
        self._creation_states.clear()

    async def cleanup(self, deployment_key: str) -> None:
        """Cancel any in-flight background task and clean up resources for a deployment."""
        state = self._creation_states.pop(deployment_key, None)
        if state is None:
            return
        if state.task is not None and not state.task.done():
            state.task.cancel()
            logger.info("Cancelled in-flight creation task for %s (stage: %s)", deployment_key, state.stage.value)
        if state.puller_container_name:
            try:
                puller = await asyncio.to_thread(self.get_container, state.puller_container_name)
                try:
                    await asyncio.to_thread(puller.stop, timeout=10)
                except Exception:
                    pass
                await asyncio.to_thread(puller.remove, force=True)
                logger.info("Cleaned up puller container %s for %s", state.puller_container_name, deployment_key)
            except NotFound:
                pass
            except Exception as e:
                logger.warning("Error cleaning up puller container for %s: %s", deployment_key, e)

    # ======================================================================
    # Stage status checking
    # ======================================================================

    def _is_task_complete(self, state: CreationState) -> bool:
        """Return True when the current async task has finished (or is absent)."""
        return state.task is None or state.task.done()

    def _get_task_error(self, state: CreationState) -> Exception | None:
        """Return the exception from the completed task, or None on success/cancel."""
        if state.task is None:
            return None
        if state.task.cancelled():
            return asyncio.CancelledError()
        return state.task.exception()

    # ======================================================================
    # Stage machine
    # ======================================================================

    def _needs_puller(self, state: CreationState) -> bool:
        """Return True when a model-puller container is required before NIM can start."""
        return state.model_weights_type == ModelWeightsType.FILES_SERVICE or state.is_multi_llm

    # ------------------------------------------------------------------
    # RUNNING_PULLER
    # ------------------------------------------------------------------

    async def _advance_running_puller(
        self, deployment_key: str, state: CreationState
    ) -> tuple[DeploymentStatusUpdate, bool]:
        # Check puller container status
        try:
            puller = await asyncio.to_thread(self.get_container, state.puller_container_name)
            await asyncio.to_thread(self.reload_container, puller)
        except NotFound:
            logger.error("Puller container %s not found for %s", state.puller_container_name, deployment_key)
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message="Model puller container disappeared unexpectedly",
                error_details={"stage": "model_puller", "puller_container": state.puller_container_name},
            ), True
        except Exception as e:
            logger.warning("Error checking puller container for %s: %s", deployment_key, e)
            return DeploymentStatusUpdate(
                status="PENDING",
                status_message="Downloading model weights (checking puller status...)",
            ), False

        container_status = puller.status

        # Still running — keep waiting
        if container_status == "running":
            return DeploymentStatusUpdate(
                status="PENDING",
                status_message="Downloading model weights. This may take several minutes.",
            ), False

        # Finished — check exit code
        if container_status in ("exited", "dead"):
            exit_code = puller.attrs.get("State", {}).get("ExitCode", -1)
            if exit_code == 0:
                logger.info("Model puller completed successfully for %s", deployment_key)
                try:
                    await asyncio.to_thread(
                        self._client.containers.run,
                        image=self._get_busybox_image(),
                        command=["sh", "-c", "chown -R 1000:1000 /model-store"],
                        volumes={state.volume_name: {"bind": "/model-store", "mode": "rw"}},
                        remove=True,
                    )
                except Exception as e:
                    logger.warning("Post-puller chown failed (continuing): %s", e)
                try:
                    await asyncio.to_thread(puller.remove, force=True)
                except Exception as e:
                    logger.warning("Failed to remove puller container: %s", e)

                # Handle plugin puller if needed
                if state.plugin_fileset:
                    logger.info("Running plugin puller for %s", deployment_key)
                    plugin_path, plugin_error = await self._run_plugin_puller(
                        state.deployment,
                        state.plugin_fileset,
                        state.volume_name,
                        target_subdir="tool_call_plugin",
                    )
                    if plugin_error:
                        logger.error("Plugin puller failed for %s: %s", deployment_key, plugin_error)
                        return DeploymentStatusUpdate(
                            status="ERROR",
                            status_message=f"Failed to download tool_call_plugin fileset: {plugin_error}",
                            error_details={"error": plugin_error, "stage": "plugin_puller"},
                        ), True
                    state.tool_call_plugin_path = plugin_path

                state.stage = CreationStage.CREATING_CONTAINER
                state.task = None
                return await self._advance_creating_container(deployment_key, state)
            else:
                logs = ""
                try:
                    raw_logs = await asyncio.to_thread(puller.logs, tail=50)
                    logs = raw_logs.decode("utf-8", errors="ignore")
                    logger.error("Puller logs:\n%s", logs)
                except Exception:
                    logs = "Unable to retrieve logs"
                error_msg = (
                    f"Model puller failed with exit code {exit_code}. "
                    f"Last logs: {logs[-500:] if len(logs) > 500 else logs}"
                )
                return DeploymentStatusUpdate(
                    status="ERROR",
                    status_message=f"Failed to download model weights: {error_msg}",
                    error_details={"error": error_msg, "stage": "model_puller"},
                ), True

        # Still starting up or unknown state
        return DeploymentStatusUpdate(
            status="PENDING",
            status_message=f"Model puller container is {container_status}...",
        ), False

    # ------------------------------------------------------------------
    # CREATING_CONTAINER  (final stage)
    # ------------------------------------------------------------------

    async def _advance_creating_container(
        self, deployment_key: str, state: CreationState
    ) -> tuple[DeploymentStatusUpdate, bool]:
        deployment = state.deployment
        config = state.config
        engine = _config_engine(config)
        view = deployment_config_view(config)
        nim_config = view
        container_name = self.get_container_name(deployment.workspace, deployment.name)
        full_image = state.nim_image

        # Run plugin puller if needed and not yet done
        if state.plugin_fileset and not state.tool_call_plugin_path:
            logger.info("Running plugin puller for %s", deployment_key)
            plugin_path, plugin_error = await self._run_plugin_puller(
                deployment,
                state.plugin_fileset,
                state.volume_name,
                target_subdir="tool_call_plugin",
            )
            if plugin_error:
                logger.error("Plugin puller failed for %s: %s", deployment_key, plugin_error)
                return DeploymentStatusUpdate(
                    status="ERROR",
                    status_message=f"Failed to download tool_call_plugin fileset: {plugin_error}",
                    error_details={"error": plugin_error, "stage": "plugin_puller"},
                ), True
            state.tool_call_plugin_path = plugin_path

        # Compile engine-specific environment variables (and serve args for vLLM).
        vllm_serve_args: list[str] | None = None
        if engine == ENGINE_VLLM:
            env_vars = vllm_compiler.compile_vllm_env_vars(view)
            vllm_serve_args = vllm_compiler.compile_vllm_args(view, state.model_entity)
            if view.lora_enabled:
                # vLLM's lora_filesystem_resolver validates that
                # VLLM_LORA_RESOLVER_CACHE_DIR exists at startup, before the adapter
                # sidecar has a chance to create it. Pre-create the directory in the
                # shared scratch volume so the vLLM container doesn't crash-loop while
                # waiting for the first adapter to land.
                lora_subdir = vllm_compiler.VLLM_LORA_CACHE_DIR.removeprefix("/scratch/")
                try:
                    await asyncio.to_thread(
                        self._client.containers.run,
                        image=self._get_busybox_image(),
                        command=["sh", "-c", f"mkdir -p /scratch/{lora_subdir} && chmod -R 777 /scratch/{lora_subdir}"],
                        volumes={state.scratch_volume_name: {"bind": "/scratch", "mode": "rw"}},
                        remove=True,
                    )
                    logger.info("Pre-created LoRA cache dir %s in scratch volume", vllm_compiler.VLLM_LORA_CACHE_DIR)
                except Exception as e:
                    logger.warning("Failed to pre-create LoRA cache dir (continuing anyway): %s", e)
        else:
            env_vars = await self._compile_env_vars(
                deployment,
                config,
                state.model_entity,
                model_weights_type=state.model_weights_type,
                is_multi_llm=state.is_multi_llm,
                ngc_api_key=state.ngc_api_key,
                tool_call_plugin_path=state.tool_call_plugin_path,
            )

        # GPU allocation
        device_requests: list = []
        allocated_gpu_ids: list[int] = []
        container: Container | None = None
        sidecar_container: Container | None = None

        async def cleanup_and_error(status_message: str, error_details: dict) -> tuple[DeploymentStatusUpdate, bool]:
            if allocated_gpu_ids and self._gpu_pool is not None:
                self._gpu_pool.release_gpu(deployment_key)
                logger.info(f"Released GPU(s) {allocated_gpu_ids} after container creation failure")
            for ctr in [sidecar_container, container]:
                if ctr:
                    try:
                        await asyncio.to_thread(self.stop_container, ctr, timeout=30)
                        await asyncio.to_thread(self.remove_container, ctr, force=True)
                    except NotFound:
                        pass
                    except (APIError, ReadTimeout, Urllib3ReadTimeoutError, RequestsConnectionError) as e:
                        logger.warning(f"Failed to stop container {ctr} after retries: {e}")
                    except Exception as e:
                        logger.warning(f"Unexpected error stopping container {ctr}: {e}")
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=status_message,
                error_details=error_details,
                host_url=None,
            ), True

        if nim_config.gpu > 0:
            if self._gpu_pool is None:
                logger.error(f"Cannot deploy {deployment_key}: no GPUs detected on this system")
                return await cleanup_and_error(
                    status_message="No GPUs available on this system. GPU model deployments require NVIDIA GPUs.",
                    error_details={"error": "No GPUs detected", "stage": "gpu_allocation"},
                )
            try:
                allocated_gpu_ids = self._gpu_pool.allocate_gpu(deployment_key, num_requested=nim_config.gpu)
                device_requests = [
                    docker.types.DeviceRequest(
                        driver="nvidia",
                        device_ids=[str(gpu_id) for gpu_id in allocated_gpu_ids],
                        capabilities=[["gpu"]],
                    )
                ]
                logger.info("Allocated GPU(s) %s for deployment %s", allocated_gpu_ids, deployment_key)
            except GPUAllocationError as e:
                logger.error(f"Failed to allocate GPU(s) for deployment {deployment_key}: {e}")
                return await cleanup_and_error(
                    status_message=f"Failed to allocate GPU resources: {e}",
                    error_details={"error": str(e), "stage": "gpu_allocation"},
                )

        # Port allocation
        host_port = await self.find_available_port()
        if host_port is None:
            logger.error(f"Failed to allocate port for deployment {deployment_key}")
            if allocated_gpu_ids and self._gpu_pool is not None:
                self._gpu_pool.release_gpu(deployment_key)
                logger.info("Released GPU(s) %s after port allocation failure", allocated_gpu_ids)
            return await cleanup_and_error(
                status_message=(
                    f"Failed to allocate host port for deployment. No ports available in range "
                    f"{self._backend_config.models_docker_port_range_start}"
                    f"-{self._backend_config.models_docker_port_range_end}."
                ),
                error_details={"error": "Port allocation failed"},
            )

        ports = {"8000/tcp": host_port}
        logger.info("Allocated port %s for deployment %s", host_port, deployment_key)

        try:
            logger.info("Creating container %s with image %s...", container_name, full_image)

            create_args: dict[str, Any] = {
                "image": full_image,
                "name": container_name,
                "environment": env_vars,
                "detach": True,
                "device_requests": device_requests,
                "volumes": {
                    state.volume_name: {"bind": "/model-store", "mode": "rw"},
                    state.scratch_volume_name: {"bind": "/scratch", "mode": "rw"},
                },
                "labels": {
                    "nmp.nvidia.com/deployment-workspace": deployment.workspace,
                    "nmp.nvidia.com/deployment-name": deployment.name,
                    ENGINE_LABEL: engine,
                    HEALTH_PATH_LABEL: _resolve_health_path(engine, view),
                    MODEL_MANAGED_BY_LABEL: MODEL_MANAGED_BY_MODELS_CONTROLLER,
                },
                "restart_policy": {"Name": "unless-stopped"},
            }

            # vLLM serve args are passed as the container command (appended to the
            # image's `vllm serve` entrypoint). NIM is configured purely via env.
            if vllm_serve_args is not None:
                create_args["command"] = vllm_serve_args

            if nim_config.gpu > 1:
                fixed = MODELS_DOCKER_NIM_MULTI_GPU_SHM_SIZE or self._backend_config.nim_multi_gpu_shm_size
                per_gpu_mb = (
                    int(MODELS_DOCKER_NIM_MULTI_GPU_SHM_SIZE_PER_GPU)
                    if MODELS_DOCKER_NIM_MULTI_GPU_SHM_SIZE_PER_GPU
                    else self._backend_config.nim_multi_gpu_shm_size_per_gpu
                )
                shm_size = _compute_multi_gpu_shm_size(fixed, per_gpu_mb, nim_config.gpu)
                create_args["shm_size"] = shm_size
                logger.info("Using shm_size=%s for multi-GPU deployment (%s GPU(s))", shm_size, nim_config.gpu)

            create_args["ports"] = ports

            if self._should_attach_network():
                network = self._backend_config.models_docker_network
                if network:
                    create_args["network"] = network
                    logger.info("NIM container will join network: %s", network)
                else:
                    logger.warning(
                        "MODELS_DOCKER_NETWORKING_MODE='dond' but MODELS_DOCKER_NETWORK is not set. "
                        "NIM container may not be reachable."
                    )

            container = await asyncio.to_thread(self.create_and_start_container, create_args)

            container_id = container.id[:12]
            logger.info("Container %s started successfully (ID: %s)", container_name, container_id)

            if view.lora_enabled:
                cfg = get_platform_config()
                image = get_qualified_image(self._backend_config.lora_sidecar_image_name)
                sidecar_envs = cfg.to_shared_envvars()
                sidecar_envs.update(env_vars)
                # The adapters sidecar is engine-agnostic: it downloads enabled LoRA
                # adapter filesets for the base model entity into NIM_PEFT_SOURCE. NIM
                # already sets NIM_PEFT_SOURCE + the model-entity env in its env_vars;
                # vLLM watches VLLM_LORA_RESOLVER_CACHE_DIR instead, so point the
                # sidecar's NIM_PEFT_SOURCE at that same directory and supply the
                # model-entity identity the sidecar needs to resolve adapters.
                if engine == ENGINE_VLLM:
                    sidecar_envs["NIM_PEFT_SOURCE"] = vllm_compiler.VLLM_LORA_CACHE_DIR
                    sidecar_envs["NIM_PEFT_REFRESH_INTERVAL"] = str(self._backend_config.peft_refresh_interval)
                    # vLLM's filesystem resolver only loads an adapter whose
                    # base_model_name_or_path equals vLLM's --model value (the local
                    # model path). Tell the sidecar to rewrite each adapter to match.
                    sidecar_envs["VLLM_LORA_BASE_MODEL_OVERRIDE"] = vllm_compiler.MODEL_STORE_PATH
                    # Endpoint the sidecar uses to eagerly (un)load adapters via vLLM's
                    # runtime LoRA API. Without this the filesystem resolver only loads an
                    # adapter on the first request that names it, so it never appears in
                    # /v1/models and model-provider discovery never surfaces it. Reuse the
                    # same host URL the controller uses to reach the deployment, which is
                    # reachable from the sidecar across the supported networking modes.
                    sidecar_envs["VLLM_ENDPOINT"] = self.get_host_url(container_name, host_port)
                    if state.model_entity is not None:
                        sidecar_envs["NMP_MODEL_ENTITY_WORKSPACE"] = state.model_entity.workspace
                        sidecar_envs["NMP_MODEL_ENTITY_NAME"] = state.model_entity.name
                sidecar_args: dict[str, Any] = {
                    "image": image,
                    "name": f"{container_name}-sidecar",
                    "environment": sidecar_envs,
                    "command": self._backend_config.lora_sidecar_command,
                    "detach": True,
                    "volumes": {
                        state.volume_name: {"bind": "/model-store", "mode": "rw"},
                        state.scratch_volume_name: {"bind": "/scratch", "mode": "rw"},
                    },
                    "labels": {
                        "nmp.nvidia.com/deployment-workspace": deployment.workspace,
                        "nmp.nvidia.com/deployment-name": deployment.name,
                        MODEL_MANAGED_BY_LABEL: MODEL_MANAGED_BY_MODELS_CONTROLLER,
                    },
                    "restart_policy": {"Name": "unless-stopped"},
                    "healthcheck": {"test": ["NONE"]},
                    "ports": {},
                }
                if self._backend_config.lora_sidecar_entrypoint:
                    sidecar_args["entrypoint"] = self._backend_config.lora_sidecar_entrypoint

                self._assign_network(sidecar_args)

                await asyncio.to_thread(self.pull_image_if_not_local, image)
                sidecar_container = await asyncio.to_thread(self.create_and_start_container, sidecar_args)
                sidecar_container_id = sidecar_container.id[:12]
                logger.info("Container %s-sidecar started successfully (ID: %s)", container_name, sidecar_container_id)

            host_url = self.get_host_url(container_name, host_port)
            logger.info(
                "Successfully created container %s (ID: %s) for %s/%s. Host URL: %s",
                container_name,
                container_id,
                deployment.workspace,
                deployment.name,
                host_url,
            )

            return DeploymentStatusUpdate(
                status="PENDING",
                status_message=(
                    f"Container created and starting with image {full_image} (ID: {container_id}). "
                    "The inference engine is initializing, this may take several minutes."
                ),
                host_url=host_url,
            ), True  # pipeline complete

        except APIError as e:
            logger.error(f"Docker API error creating container {container_name}: {e}")
            return await cleanup_and_error(
                status_message=f"Docker API error: {e}",
                error_details={"error": str(e)},
            )

    # ======================================================================
    # Model puller container
    # ======================================================================

    async def _start_model_puller_container(self, state: CreationState) -> Container:
        """Start the model puller container (detached, no wait)."""
        deployment = state.deployment
        config = state.config
        model_entity = state.model_entity
        model_weights_type = state.model_weights_type
        volume_name = state.volume_name

        puller_container_name = self.get_puller_container_name(deployment.workspace, deployment.name)
        puller_image = self._backend_config.huggingface_model_puller
        nim_config = deployment_config_view(config)

        model_repo = self._get_model_repo_from_entity(model_entity, model_weights_type, nim_config)

        # Build environment vars based on weights type
        if model_weights_type == ModelWeightsType.FILES_SERVICE:
            logger.info("Configuring model puller for Files service model source")
            files_url = self._get_hf_compatible_files_url()
            env_vars = {"HF_ENDPOINT": files_url, "HF_TOKEN": "service:models"}
            model_revision = None
        elif model_weights_type == ModelWeightsType.HUGGINGFACE:
            logger.info("Configuring model puller for Hugging Face model source")
            _, _, model_revision = parse_model_name_revision(
                model_namespace=nim_config.model_namespace,
                model_name=nim_config.model_name,
                model_revision=nim_config.model_revision,
            )
            hf_token = None
            if deployment.hf_token_secret_name:
                try:
                    sdk = self._nmp_sdk
                    if deployment.auth_context:
                        sdk = get_sdk_on_behalf_of(self._nmp_sdk, deployment.auth_context.principal_id)
                    elif get_auth_config().enabled:
                        logger.warning(
                            "Deployment %s/%s has no auth_context; accessing secret as service principal",
                            deployment.workspace,
                            deployment.name,
                        )
                    response = await sdk.secrets.access(deployment.hf_token_secret_name, workspace=deployment.workspace)
                    hf_token = response.value
                    logger.info("Retrieved HF token from secrets service")
                except Exception as e:
                    logger.warning("Failed to retrieve HF token from secrets service: %s", e)
            env_vars = {"HF_ENDPOINT": HUGGINGFACE_HUB_URL}
            if hf_token:
                env_vars["HF_TOKEN"] = hf_token
            else:
                logger.warning("No HF token found, might not be able to pull model from Hugging Face Hub")
        else:
            raise ValueError(f"Unsupported model weights type for puller: {model_weights_type}")

        logger.info(
            "Running model puller for %s (container: %s, image: %s)",
            model_repo,
            puller_container_name,
            puller_image,
        )

        # Clean up any existing puller container
        try:
            existing_puller = await asyncio.to_thread(self.get_container, puller_container_name)
            logger.warning("Puller container %s already exists, removing it", puller_container_name)
            try:
                await asyncio.to_thread(existing_puller.stop, timeout=10)
            except Exception:
                pass
            await asyncio.to_thread(existing_puller.remove, force=True)
        except NotFound:
            pass
        except Exception as e:
            logger.warning("Error cleaning up existing puller container: %s", e)

        # Build download command
        command = ["download", model_repo, "--local-dir", "/model-store"]
        if model_revision:
            command.extend(["--revision", model_revision])

        # Fix volume permissions
        try:
            logger.info("Setting volume permissions for %s...", volume_name)
            await asyncio.to_thread(
                self._client.containers.run,
                image=self._get_busybox_image(),
                command=["sh", "-c", "chown -R 1000:1000 /model-store && chmod -R 755 /model-store"],
                volumes={volume_name: {"bind": "/model-store", "mode": "rw"}},
                remove=True,
            )
            logger.info("Volume permissions set successfully")
        except Exception as e:
            logger.warning("Failed to set volume permissions (continuing anyway): %s", e)

        run_kwargs: dict = {
            "image": puller_image,
            "name": puller_container_name,
            "command": command,
            "environment": env_vars,
            "user": "1000:1000",
            "volumes": {volume_name: {"bind": "/model-store", "mode": "rw"}},
            "labels": {
                "nmp.nvidia.com/deployment-workspace": deployment.workspace,
                "nmp.nvidia.com/deployment-name": deployment.name,
                "nmp.nvidia.com/managed-by": "models-controller",
                "nmp.nvidia.com/container-type": "model-puller",
            },
            "detach": True,
            "remove": False,
        }

        if self._backend_config.models_docker_networking_mode == "local":
            run_kwargs["network_mode"] = "host"
            logger.info("Puller container will use host network (local mode)")
        elif self._should_attach_network() and self._backend_config.models_docker_network:
            run_kwargs["network"] = self._backend_config.models_docker_network
            logger.info("Puller container will join network: %s", self._backend_config.models_docker_network)

        puller_container = await asyncio.to_thread(self.run_container, **run_kwargs)
        logger.info("Puller container %s started (ID: %s)", puller_container_name, puller_container.id[:12])
        return puller_container

    # ======================================================================
    # Plugin puller
    # ======================================================================

    async def _run_plugin_puller(
        self,
        deployment: ModelDeployment,
        fileset_ref: str,
        volume_name: str,
        target_subdir: str = "tool_call_plugin",
    ) -> tuple[str | None, str | None]:
        """Pull a plugin fileset and discover the Python file inside it.

        Returns ``(container_path_to_py_file, None)`` on success,
        or ``(None, error_message)`` on failure.
        """
        container_name = f"md-plugin-{deployment.workspace}-{deployment.name}"
        container_name = _get_k8s_safe_name(container_name, max_length=63, name_type="label")
        puller_image = self._backend_config.huggingface_model_puller
        target_path = f"/model-store/{target_subdir}"

        logger.info(
            f"Pulling plugin fileset '{fileset_ref}' into {target_path} for {deployment.workspace}/{deployment.name}"
        )

        files_url = self._get_hf_compatible_files_url()
        env_vars = {"HF_ENDPOINT": files_url, "HF_TOKEN": "service:models"}
        command = ["download", fileset_ref, "--local-dir", target_path]

        # Clean up any existing plugin puller container
        try:
            existing = await asyncio.to_thread(self.get_container, container_name)
            logger.warning(f"Plugin puller container {container_name} already exists, removing")
            try:
                await asyncio.to_thread(existing.stop, timeout=10)
            except Exception:
                logger.warning(f"Failed to stop existing plugin puller container {container_name}")
            await asyncio.to_thread(existing.remove, force=True)
        except NotFound:
            pass
        except Exception as e:
            logger.warning(f"Error cleaning up existing plugin puller container: {e}")

        try:
            await asyncio.to_thread(self.pull_image_if_not_local, puller_image)
        except Exception as e:
            return None, f"Failed to pull plugin puller image {puller_image}: {e}"

        # Create the target subdirectory and fix permissions
        try:
            await asyncio.to_thread(
                self._client.containers.run,
                image=self._get_busybox_image(),
                command=["sh", "-c", f"mkdir -p {target_path} && chown -R 1000:1000 {target_path}"],
                volumes={volume_name: {"bind": "/model-store", "mode": "rw"}},
                remove=True,
            )
        except Exception as e:
            logger.warning(f"Failed to create plugin directory (continuing): {e}")

        # Run the puller container
        try:
            run_kwargs: dict = {
                "image": puller_image,
                "name": container_name,
                "command": command,
                "environment": env_vars,
                "user": "1000:1000",
                "volumes": {volume_name: {"bind": "/model-store", "mode": "rw"}},
                "labels": {
                    "nmp.nvidia.com/deployment-workspace": deployment.workspace,
                    "nmp.nvidia.com/deployment-name": deployment.name,
                    MODEL_MANAGED_BY_LABEL: MODEL_MANAGED_BY_MODELS_CONTROLLER,
                    "nmp.nvidia.com/container-type": "plugin-puller",
                },
                "detach": True,
                "remove": False,
            }

            self._assign_network(run_kwargs)

            puller_container = await asyncio.to_thread(self.run_container, **run_kwargs)
            logger.info(f"Plugin puller container {container_name} started (ID: {puller_container.id[:12]})")

            timeout = self._backend_config.model_puller_timeout
            try:
                result = await asyncio.to_thread(puller_container.wait, timeout=timeout)
                exit_code = result.get("StatusCode", -1)

                if exit_code == 0:
                    logger.info(f"Plugin puller completed successfully for fileset '{fileset_ref}'")
                    try:
                        await asyncio.to_thread(
                            self._client.containers.run,
                            image=self._get_busybox_image(),
                            command=["sh", "-c", f"chown -R 1000:1000 {target_path}"],
                            volumes={volume_name: {"bind": "/model-store", "mode": "rw"}},
                            remove=True,
                        )
                    except Exception as e:
                        logger.warning(f"Post-puller chown failed for plugin (continuing): {e}")
                    try:
                        await asyncio.to_thread(puller_container.remove, force=True)
                    except Exception as e:
                        logger.warning(f"Failed to remove plugin puller container: {e}")

                    # Discover the .py file in the pulled fileset
                    try:
                        find_result = await asyncio.to_thread(
                            self._client.containers.run,
                            image=self._get_busybox_image(),
                            command=["find", target_path, "-name", "*.py", "-type", "f"],
                            volumes={volume_name: {"bind": "/model-store", "mode": "rw"}},
                            remove=True,
                        )
                        py_files = [f.strip() for f in find_result.decode("utf-8").strip().split("\n") if f.strip()]
                    except Exception as e:
                        return None, f"Failed to discover Python files in plugin fileset: {e}"

                    if len(py_files) == 0:
                        return None, (
                            f"tool_call_plugin fileset '{fileset_ref}' contains no .py files. "
                            "The fileset must contain exactly one Python file."
                        )
                    if len(py_files) > 1:
                        return None, (
                            f"tool_call_plugin fileset '{fileset_ref}' contains {len(py_files)} .py files: "
                            f"{py_files}. The fileset must contain exactly one Python file."
                        )

                    plugin_path = py_files[0]
                    logger.info(f"Discovered tool_call_plugin Python file: {plugin_path}")
                    return plugin_path, None
                else:
                    try:
                        raw_logs = await asyncio.to_thread(puller_container.logs, tail=50)
                        logs = raw_logs.decode("utf-8", errors="ignore")
                        logger.error(f"Plugin puller logs:\n{logs}")
                    except Exception:
                        logs = "Unable to retrieve logs"
                    return (
                        None,
                        f"Plugin puller failed with exit code {exit_code}. "
                        f"Last logs: {logs[-500:] if len(logs) > 500 else logs}",
                    )

            except Exception as wait_error:
                logger.error(f"Error waiting for plugin puller container: {wait_error}")
                try:
                    await asyncio.to_thread(puller_container.stop, timeout=10)
                except Exception:
                    logger.warning("Failed to stop plugin puller container", exc_info=True)
                return None, f"Plugin puller timed out or failed: {wait_error}"

        except APIError as e:
            return None, f"Docker API error running plugin puller: {e}"
        except Exception as e:
            return None, f"Failed to run plugin puller: {e}"

    # ======================================================================
    # Environment variable compilation
    # ======================================================================

    async def _compile_env_vars(
        self,
        deployment: ModelDeployment,
        config: ModelDeploymentConfig,
        model_entity: Optional[ModelEntity] = None,
        model_weights_type: Optional[ModelWeightsType] = None,
        is_multi_llm: bool = False,
        ngc_api_key: str | None = None,
        tool_call_plugin_path: str | None = None,
    ) -> Dict[str, str]:
        """Compile environment variables for the NIM container."""
        nim_config = deployment_config_view(config)
        env_vars: Dict[str, str] = {
            "NIM_GUIDED_DECODING_BACKEND": self._backend_config.nim_guided_decoding_backend,
        }

        model_fqdn: str | None = None
        if nim_config.model_name:
            if nim_config.model_namespace:
                model_fqdn = f"{nim_config.model_namespace}/{nim_config.model_name}"
            else:
                model_fqdn = nim_config.model_name

        if model_fqdn:
            env_vars["NIM_SERVED_MODEL_NAME"] = model_fqdn

        weights_from_files = model_weights_type is not None and model_weights_type == ModelWeightsType.FILES_SERVICE
        puller_ran = weights_from_files or is_multi_llm
        if puller_ran:
            env_vars["NIM_MODEL_NAME"] = "/model-store"
            env_vars["NIM_MODEL_PATH"] = "/model-store"

        if puller_ran and not is_multi_llm:
            logger.info("Adding fine-tuned model environment variables for pre-downloaded weights")
            env_vars["NIM_FT_MODEL"] = "/model-store"
            env_vars["NIM_CUSTOM_MODEL"] = "/model-store"

        if nim_config.lora_enabled:
            env_vars["NIM_PEFT_SOURCE"] = "/scratch/loras"
            env_vars["NIM_PEFT_REFRESH_INTERVAL"] = str(self._backend_config.peft_refresh_interval)

        if ngc_api_key:
            env_vars["NGC_API_KEY"] = ngc_api_key
            logger.info("Passing NGC_API_KEY to container for model downloads")

        if nim_config.additional_envs:
            env_vars.update(nim_config.additional_envs)

        if model_entity:
            env_vars["NMP_MODEL_ENTITY_WORKSPACE"] = model_entity.workspace
            env_vars["NMP_MODEL_ENTITY_NAME"] = model_entity.name

            if model_entity.trust_remote_code:
                env_vars["NIM_FORCE_TRUST_REMOTE_CODE"] = "1"
            if model_entity.spec:
                if model_entity.spec.chat_template:
                    env_vars["NIM_CHAT_TEMPLATE"] = model_entity.spec.chat_template

                if model_entity.spec.tool_call_config:
                    tool_cfg = model_entity.spec.tool_call_config
                    if tool_cfg.tool_call_parser:
                        env_vars["NIM_TOOL_CALL_PARSER"] = tool_cfg.tool_call_parser
                    if tool_call_plugin_path:
                        env_vars["NIM_TOOL_PARSER_PLUGIN"] = tool_call_plugin_path
                    if tool_cfg.auto_tool_choice is not None:
                        env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] = "1" if tool_cfg.auto_tool_choice else "0"

        # Deployment-level overrides (highest priority)
        if nim_config.chat_template:
            env_vars["NIM_CHAT_TEMPLATE"] = nim_config.chat_template

        if nim_config.tool_call_config:
            deploy_cfg = nim_config.tool_call_config
            if deploy_cfg.tool_call_parser:
                env_vars["NIM_TOOL_CALL_PARSER"] = deploy_cfg.tool_call_parser
            if deploy_cfg.tool_call_plugin:
                if tool_call_plugin_path:
                    env_vars["NIM_TOOL_PARSER_PLUGIN"] = tool_call_plugin_path
                else:
                    logger.warning(
                        "Deployment tool_call_config.tool_call_plugin is set but no plugin .py file "
                        "was discovered. Ensure the fileset was pulled successfully."
                    )
            if deploy_cfg.auto_tool_choice is not None:
                env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] = "1" if deploy_cfg.auto_tool_choice else "0"

        return env_vars
