# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for DockerServiceBackend."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docker.errors import ImageNotFound, NotFound
from nmp.common.config import PlatformConfig
from nmp.core.models.app import ModelWeightsType
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate
from nmp.core.models.controllers.backends.docker import DockerServiceBackend
from nmp.core.models.controllers.backends.docker.creation_reconciler import (
    CreationStage,
    _compute_multi_gpu_shm_size,
)
from nmp.core.models.schemas import (
    ContainerExecutorConfig,
    Engine,
    ModelDeploymentConfigModelSpec,
)

_MODEL_SPEC_FIELDS = {
    "model_type",
    "model_namespace",
    "model_name",
    "model_revision",
    "model_provider",
    "chat_template",
    "tool_call_config",
    "lora_enabled",
}
_EXECUTOR_FIELDS = {
    "gpu",
    "disk_size",
    "image_name",
    "image_tag",
    "additional_envs",
    "additional_args",
    "k8s_nim_operator_config",
    "override_config",
}


def set_deployment_config(config, engine: str = "nim", **kwargs) -> None:
    """Populate a config mock with the engine-split deployment shape.

    Splits flat NIMDeployment-style kwargs into a real ``ModelDeploymentConfigModelSpec``
    and ``ContainerExecutorConfig`` so the flattened ``deployment_config_view`` (which uses
    ``getattr``) reads real attributes rather than MagicMock children.
    """
    model_spec_kwargs = {k: v for k, v in kwargs.items() if k in _MODEL_SPEC_FIELDS}
    executor_kwargs = {k: v for k, v in kwargs.items() if k in _EXECUTOR_FIELDS}
    unknown = set(kwargs) - _MODEL_SPEC_FIELDS - _EXECUTOR_FIELDS
    if unknown:
        raise ValueError(f"Unknown deployment config fields: {unknown}")
    config.engine = Engine(engine)
    config.model_spec = ModelDeploymentConfigModelSpec(**model_spec_kwargs)
    config.executor_config = ContainerExecutorConfig(**executor_kwargs)


async def drive_creation_to_completion(backend: DockerServiceBackend, deployment) -> DeploymentStatusUpdate:
    """Drive the staged creation pipeline to completion by advancing all stages.

    After create_model_deployment() starts the pipeline, this helper awaits
    background tasks and advances each stage until the deployment exits
    the creation pipeline (either successfully or with an error).
    """
    key = backend._get_deployment_key(deployment)
    last_status: DeploymentStatusUpdate | None = None
    for _ in range(20):
        if key not in backend._reconciler._creation_states:
            break
        state = backend._reconciler._creation_states[key]
        if state.task and not state.task.done():
            try:
                await state.task
            except Exception:
                pass
        last_status = await backend._reconciler.advance(key)
        if last_status.status == "ERROR" or key not in backend._reconciler._creation_states:
            return last_status
    if last_status is not None:
        return last_status
    return await backend.get_model_deployment_status(deployment)


@pytest.fixture
def backend_with_mock_client():
    """Create a DockerServiceBackend with a mocked Docker client."""
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.docker.from_env") as mock_from_env,
        patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config"),
        patch("nmp.common.resources.manager.get_platform_config") as mock_resource_config,
        patch("nmp.common.resources.manager.detect_gpu_device_ids") as mock_detect,
    ):
        mock_resource_config.return_value.docker = MagicMock()
        mock_resource_config.return_value.docker.get_reserved_gpu_ids.return_value = [0]
        mock_detect.return_value = [0]
        client = MagicMock()
        mock_from_env.return_value = client
        backend = DockerServiceBackend(nmp_sdk=AsyncMock(), config={})
        backend._client = client
        yield backend, client


class TestComputeMultiGpuShmSize:
    """Unit tests for multi-GPU shm_size calculation."""

    def test_2_gpus_default_per_gpu(self):
        """2 GPUs × 1024 MB per GPU = 2048m."""
        assert _compute_multi_gpu_shm_size("", 1024, 2) == "2048m"

    def test_4_gpus_default_per_gpu(self):
        """4 GPUs × 1024 MB per GPU = 4096m."""
        assert _compute_multi_gpu_shm_size("", 1024, 4) == "4096m"

    def test_2_gpus_fixed_overrides(self):
        """Fixed total is used when set."""
        assert _compute_multi_gpu_shm_size("4g", 1024, 2) == "4g"
        assert _compute_multi_gpu_shm_size("2g", 512, 4) == "2g"

    def test_4_gpus_custom_per_gpu(self):
        """4 GPUs × 512 MB per GPU = 2048m."""
        assert _compute_multi_gpu_shm_size("", 512, 4) == "2048m"

    def test_2_gpus_custom_per_gpu(self):
        """2 GPUs × 512 MB per GPU = 1024m."""
        assert _compute_multi_gpu_shm_size("", 512, 2) == "1024m"

    def test_empty_fixed_uses_per_gpu_calculation(self):
        """Empty fixed uses per_gpu_mb * gpu_count."""
        assert _compute_multi_gpu_shm_size("", 2048, 2) == "4096m"
        assert _compute_multi_gpu_shm_size("", 1024, 8) == "8192m"


class TestPullImageIfNotLocal:
    """Unit tests for _pull_image_if_not_local."""

    def test_image_found_locally_does_not_pull(self, backend_with_mock_client):
        """When image exists locally, _pull_image should not be called."""
        backend, client = backend_with_mock_client
        client.images.get.return_value = MagicMock()

        backend._reconciler.pull_image_if_not_local("myregistry/myimage:v1")

        client.images.get.assert_called_once_with("myregistry/myimage:v1")
        client.images.pull.assert_not_called()

    def test_image_not_found_locally_triggers_pull(self, backend_with_mock_client):
        """When image is not local, it should be pulled via _pull_image."""
        backend, client = backend_with_mock_client
        client.images.get.side_effect = ImageNotFound("not found")
        client.images.pull.return_value = MagicMock()

        backend._reconciler.pull_image_if_not_local("myregistry/myimage:v1")

        client.images.get.assert_called_once_with("myregistry/myimage:v1")
        client.images.pull.assert_called_once_with("myregistry/myimage:v1", tag=None)

    def test_pull_failure_propagates(self, backend_with_mock_client):
        """When image is not local and pull fails, the exception should propagate."""
        backend, client = backend_with_mock_client
        client.images.get.side_effect = ImageNotFound("not found")
        client.images.pull.side_effect = Exception("registry unreachable")

        with pytest.raises(Exception, match="registry unreachable"):
            backend._reconciler.pull_image_if_not_local("myregistry/myimage:v1")

    def test_image_without_tag(self, backend_with_mock_client):
        """Image string without a tag should be handled correctly."""
        backend, client = backend_with_mock_client
        client.images.get.side_effect = ImageNotFound("not found")
        client.images.pull.return_value = MagicMock()

        backend._reconciler.pull_image_if_not_local("myregistry/myimage")

        client.images.get.assert_called_once_with("myregistry/myimage")
        client.images.pull.assert_called_once_with("myregistry/myimage", tag=None)

    def test_non_image_not_found_exception_propagates(self, backend_with_mock_client):
        """Exceptions other than ImageNotFound from images.get should propagate."""
        backend, client = backend_with_mock_client
        client.images.get.side_effect = ConnectionError("docker daemon unavailable")

        with pytest.raises(ConnectionError, match="docker daemon unavailable"):
            backend._reconciler.pull_image_if_not_local("myregistry/myimage:v1")

        client.images.pull.assert_not_called()


class TestPullImage:
    """Unit tests for _pull_image with optional tag."""

    def test_pull_with_name_and_tag(self, backend_with_mock_client):
        """Explicit name + tag should be forwarded to client.images.pull."""
        backend, client = backend_with_mock_client
        backend._reconciler.pull_image("myregistry/myimage", "v1")
        client.images.pull.assert_called_once_with("myregistry/myimage", tag="v1")

    def test_pull_with_name_only(self, backend_with_mock_client):
        """Calling with only the image name should pass tag=None."""
        backend, client = backend_with_mock_client
        backend._reconciler.pull_image("myregistry/myimage:v1")
        client.images.pull.assert_called_once_with("myregistry/myimage:v1", tag=None)

    def test_pull_with_explicit_none_tag(self, backend_with_mock_client):
        """Explicitly passing None as tag should work."""
        backend, client = backend_with_mock_client
        backend._reconciler.pull_image("myregistry/myimage:v1", None)
        client.images.pull.assert_called_once_with("myregistry/myimage:v1", tag=None)


def create_mock_docker_config(reserved_gpu_ids: str = "all") -> MagicMock:
    """Create a mock DockerConfig with the given reserved_gpu_device_ids value."""
    mock_docker_config = MagicMock()
    mock_docker_config.reserved_gpu_device_ids = reserved_gpu_ids

    def get_reserved_gpu_ids():
        if reserved_gpu_ids.lower() == "all":
            return None
        if reserved_gpu_ids.lower() == "none" or not reserved_gpu_ids:
            return []
        return [int(p.strip()) for p in reserved_gpu_ids.split(",") if p.strip()]

    mock_docker_config.get_reserved_gpu_ids = get_reserved_gpu_ids
    return mock_docker_config


@pytest.fixture
def mock_nmp_sdk():
    """Create a mock AsyncNeMoPlatform SDK."""
    mock = AsyncMock()
    mock.secrets = AsyncMock()
    mock.secrets.access = AsyncMock(return_value=MagicMock(value="test-hf-token-value"))
    return mock


@pytest.fixture
def mock_docker_client():
    """Create a mock Docker client."""
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.docker.from_env") as mock,
        patch(
            "nmp.core.models.controllers.backends.docker.creation_reconciler.DockerDeploymentCreationReconciler._is_port_free"
        ) as mock_is_port_free,
        patch(
            "nmp.core.models.controllers.backends.docker.backend.DockerServiceBackend._probe_nim_health"
        ) as probe_nim_health,
    ):
        mock_is_port_free.return_value = True
        probe_nim_health.return_value = (True, "")  # Returns tuple (is_healthy, failure_reason)
        client = MagicMock()
        mock.return_value = client

        # Setup default behaviors
        client.login = MagicMock()
        client.containers.get = MagicMock(side_effect=NotFound("Container not found"))
        client.containers.run = MagicMock()
        client.images.pull = MagicMock()
        client.volumes.create = MagicMock()
        client.volumes.get = MagicMock(side_effect=NotFound("Volume not found"))
        mock_is_port_free.return_value = True

        yield client


@pytest.fixture
def reset_shared_resource_manager_base():
    """Reset SharedResourceManager singleton before and after test."""
    from nmp.common.resources import SharedResourceManager

    SharedResourceManager.reset_instance()
    yield
    SharedResourceManager.reset_instance()


@pytest.fixture
def docker_backend(mock_nmp_sdk, mock_docker_client, reset_shared_resource_manager_base):
    """Create a DockerServiceBackend instance for testing with mocked GPU detection."""
    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config),
        patch("nmp.common.resources.manager.get_platform_config") as mock_resource_config,
        patch("nmp.common.resources.manager.detect_gpu_device_ids") as mock_detect_gpu_device_ids,
    ):
        mock_resource_config.return_value.docker = create_mock_docker_config("0,1,2,3")
        mock_detect_gpu_device_ids.return_value = [0, 1, 2, 3]
        backend = DockerServiceBackend(nmp_sdk=mock_nmp_sdk, config={})
        backend._client = mock_docker_client
        return backend


@pytest.fixture
def sample_deployment():
    """Create a sample ModelDeployment for testing."""
    deployment = MagicMock()
    deployment.workspace = "default"
    deployment.name = "test-deployment"
    deployment.entity_version = 1
    deployment.status = "CREATED"
    deployment.created_at = datetime.now(timezone.utc)
    return deployment


@pytest.fixture
def sample_config():
    """Create a sample ModelDeploymentConfig for testing."""
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",
        image_tag="1.8.6",
        model_name="llama-3.2-1b-instruct",
        model_namespace="meta",
        lora_enabled=False,
        additional_envs=None,
    )
    return config


@pytest.mark.asyncio
async def test_docker_backend_create_model_deployment(
    docker_backend, sample_deployment, sample_config, mock_docker_client
):
    """Test creating a model deployment with Docker backend."""
    # Setup mock container
    mock_container = MagicMock()
    docker_backend._backend_config.models_docker_networking_mode = "dond"
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()  # Mock the start method
    mock_docker_client.containers.create.return_value = mock_container

    # Enable lora to trigger sidecar creation (2 containers)
    sample_config.model_spec.lora_enabled = True

    # Mock image not found locally (will trigger pull)
    from docker.errors import ImageNotFound as DockerImageNotFound

    mock_docker_client.images.get.side_effect = DockerImageNotFound("Image not found")
    mock_docker_client.images.pull.return_value = MagicMock()  # Pull succeeds
    mock_docker_client.containers.list.return_value = []

    # create_model_deployment now starts the image pull and returns PENDING immediately
    initial_status = await docker_backend.create_model_deployment(sample_deployment, sample_config)
    assert initial_status.status == "PENDING"
    assert "pulling container image" in initial_status.status_message.lower()

    # Drive creation to completion (image pull -> container creation)
    status_update = await drive_creation_to_completion(docker_backend, sample_deployment)

    assert status_update is not None
    assert status_update.status == "PENDING"
    assert "container created" in status_update.status_message.lower()
    assert status_update.host_url == "http://md-default-test-deployment:8000"

    # Verify Docker calls (image check + pull for both NIM and sidecar images)
    assert mock_docker_client.images.get.call_count >= 2
    assert mock_docker_client.images.pull.call_count >= 2
    assert mock_docker_client.volumes.create.call_count == 2
    assert mock_docker_client.volumes.create.call_args_list[0][0][0] == "nim-cache-default-test-deployment"
    assert mock_docker_client.volumes.create.call_args_list[1][0][0] == "nim-cache-default-test-deployment-scratch"

    assert mock_docker_client.containers.create.call_count == 2
    nim_create_args = mock_docker_client.containers.create.call_args_list[0][1]
    sidecar_create_args = mock_docker_client.containers.create.call_args_list[1][1]
    assert nim_create_args["name"] == "md-default-test-deployment"
    assert sidecar_create_args["name"] == "md-default-test-deployment-sidecar"
    assert nim_create_args["labels"][MODEL_MANAGED_BY_LABEL] == MODEL_MANAGED_BY_MODELS_CONTROLLER
    assert sidecar_create_args["labels"][MODEL_MANAGED_BY_LABEL] == MODEL_MANAGED_BY_MODELS_CONTROLLER
    assert mock_container.start.call_count == 2


def _make_vllm_config(*, lora_enabled: bool = False, image_name=None, image_tag=None):
    config = MagicMock()
    kwargs = dict(
        engine="vllm",
        model_namespace="default",
        model_name="qwen-2-5-1-5b",
        gpu=1,
        lora_enabled=lora_enabled,
    )
    if image_name is not None:
        kwargs["image_name"] = image_name
    if image_tag is not None:
        kwargs["image_tag"] = image_tag
    set_deployment_config(config, **kwargs)
    return config


def _vllm_model_entity():
    """A Files-service-backed model entity (drives the puller path)."""
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "qwen-2-5-1-5b"
    model_entity.spec = None
    model_entity.trust_remote_code = False
    model_entity.fileset = "hf://default/qwen-2-5-1-5b"
    return model_entity


async def _drive_vllm_with_puller(docker_backend, sample_deployment, mock_docker_client, config):
    """Run the vLLM create pipeline through the puller stage and return container create args."""
    docker_backend._backend_config.models_docker_networking_mode = "dond"

    mock_puller_container = MagicMock()
    mock_puller_container.id = "puller123456789"
    mock_puller_container.wait.return_value = {"StatusCode": 0}
    mock_puller_container.status = "exited"
    mock_puller_container.attrs = {"State": {"ExitCode": 0}}
    mock_puller_container.name = docker_backend._reconciler.get_puller_container_name(
        sample_deployment.workspace, sample_deployment.name
    )

    mock_vllm_container = MagicMock()
    mock_vllm_container.id = "vllm1234567890a"
    mock_vllm_container.start = MagicMock()

    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.run.return_value = mock_puller_container
    mock_docker_client.containers.create.return_value = mock_vllm_container
    mock_docker_client.containers.list.return_value = []

    await docker_backend.create_model_deployment(sample_deployment, config, _vllm_model_entity())

    def get_container_side_effect(name):
        if "puller" in name:
            return mock_puller_container
        raise NotFound("Container not found")

    mock_docker_client.containers.get.side_effect = get_container_side_effect

    return await drive_creation_to_completion(docker_backend, sample_deployment)


@pytest.mark.asyncio
async def test_docker_backend_create_vllm_deployment(docker_backend, sample_deployment, mock_docker_client):
    """Engine=vllm produces a vLLM container with serve args, engine label, and default image."""
    config = _make_vllm_config()
    status_update = await _drive_vllm_with_puller(docker_backend, sample_deployment, mock_docker_client, config)

    assert status_update.status == "PENDING"
    assert status_update.host_url == "http://md-default-test-deployment:8000"

    create_args = mock_docker_client.containers.create.call_args_list[0][1]
    # Default vLLM image is used when none specified (exact version is config-driven).
    cfg = docker_backend._backend_config
    assert create_args["image"] == f"{cfg.default_vllm_image}:{cfg.default_vllm_image_tag}"
    # vLLM serve args are passed as the container command.
    command = create_args["command"]
    assert command[0] == "/model-store"
    assert command[command.index("--served-model-name") + 1] == "default/qwen-2-5-1-5b"
    # Engine label recorded for the health-probe selection.
    assert create_args["labels"]["nmp.nvidia.com/engine"] == "vllm"
    # No LoRA env when lora is disabled.
    assert "VLLM_PLUGINS" not in create_args["environment"]


@pytest.mark.asyncio
async def test_docker_backend_create_vllm_lora_sidecar(docker_backend, sample_deployment, mock_docker_client):
    """Engine=vllm with lora_enabled wires the adapter sidecar and vLLM LoRA env/args."""
    config = _make_vllm_config(lora_enabled=True)
    await _drive_vllm_with_puller(docker_backend, sample_deployment, mock_docker_client, config)

    # Two containers: vLLM server + adapter sidecar.
    assert mock_docker_client.containers.create.call_count == 2
    vllm_args = mock_docker_client.containers.create.call_args_list[0][1]
    sidecar_args = mock_docker_client.containers.create.call_args_list[1][1]
    assert vllm_args["name"] == "md-default-test-deployment"
    assert sidecar_args["name"] == "md-default-test-deployment-sidecar"
    # vLLM LoRA hot-reload env + serve flag.
    env = vllm_args["environment"]
    assert env["VLLM_PLUGINS"] == "lora_filesystem_resolver"
    assert env["VLLM_LORA_RESOLVER_CACHE_DIR"] == "/scratch/loras"
    assert env["VLLM_ALLOW_RUNTIME_LORA_UPDATING"] == "True"
    assert "--enable-lora" in vllm_args["command"]
    # The adapters sidecar is engine-agnostic and reads NIM_PEFT_SOURCE +
    # the model-entity identity. For vLLM these must point at the same
    # directory vLLM's filesystem resolver watches, or the sidecar crashes
    # on startup and never delivers adapters.
    sidecar_env = sidecar_args["environment"]
    assert sidecar_env["NIM_PEFT_SOURCE"] == "/scratch/loras"
    assert sidecar_env["NMP_MODEL_ENTITY_WORKSPACE"] == "default"
    assert sidecar_env["NMP_MODEL_ENTITY_NAME"] == "qwen-2-5-1-5b"
    # vLLM's filesystem resolver requires the adapter's base_model_name_or_path to
    # equal vLLM's --model value, so the sidecar is told to rewrite it to /model-store.
    assert sidecar_env["VLLM_LORA_BASE_MODEL_OVERRIDE"] == "/model-store"
    # vLLM's filesystem resolver validates VLLM_LORA_RESOLVER_CACHE_DIR exists at
    # startup, so the controller pre-creates it in the scratch volume via a busybox
    # run before launching the vLLM container (otherwise vLLM crash-loops).
    run_commands = [
        c.kwargs.get("command") for c in mock_docker_client.containers.run.call_args_list if c.kwargs.get("command")
    ]
    assert any(isinstance(cmd, list) and "mkdir -p /scratch/loras" in " ".join(cmd) for cmd in run_commands), (
        f"expected a busybox mkdir for the LoRA cache dir, got run commands: {run_commands}"
    )


def test_get_health_path_from_container_vllm(docker_backend):
    """vLLM containers probe /health."""
    container = MagicMock()
    container.labels = {"nmp.nvidia.com/engine": "vllm"}
    assert docker_backend._reconciler.get_health_path_from_container(container) == "/health"


def test_get_health_path_from_container_nim(docker_backend):
    """NIM containers probe /v1/health/ready."""
    container = MagicMock()
    container.labels = {"nmp.nvidia.com/engine": "nim"}
    assert docker_backend._reconciler.get_health_path_from_container(container) == "/v1/health/ready"


def test_get_health_path_from_container_defaults_to_nim(docker_backend):
    """Containers without an engine label default to the NIM probe path."""
    container = MagicMock()
    container.labels = {}
    assert docker_backend._reconciler.get_health_path_from_container(container) == "/v1/health/ready"


def test_get_health_path_from_container_explicit_override(docker_backend):
    """An explicit health-path label (from executor_config.health_check_path) wins over the engine default."""
    container = MagicMock()
    container.labels = {"nmp.nvidia.com/engine": "generic", "nmp.nvidia.com/health-path": "/custom/ready"}
    assert docker_backend._reconciler.get_health_path_from_container(container) == "/custom/ready"


def test_resolve_health_path_prefers_explicit():
    """_resolve_health_path uses executor_config.health_check_path when set, else the engine default."""
    from nmp.core.models.controllers.backends.common import DeploymentConfigView
    from nmp.core.models.controllers.backends.docker.creation_reconciler import (
        ENGINE_NIM,
        ENGINE_VLLM,
        _resolve_health_path,
    )

    assert _resolve_health_path(ENGINE_VLLM, DeploymentConfigView()) == "/health"
    assert _resolve_health_path(ENGINE_NIM, DeploymentConfigView()) == "/v1/health/ready"
    assert _resolve_health_path("generic", DeploymentConfigView(health_check_path="/ping")) == "/ping"
    # generic with no explicit path falls back to the NIM path.
    assert _resolve_health_path("generic", DeploymentConfigView()) == "/v1/health/ready"


@pytest.mark.asyncio
async def test_docker_backend_create_sft_model_success(
    docker_backend, sample_deployment, sample_config, mock_docker_client
):
    """Test creating an SFT model with full weights runs puller then NIM."""
    # Mock model entity with SFT full weights and fileset
    model_entity = MagicMock()
    model_entity.workspace = "test"
    model_entity.name = "sft-model"
    model_entity.spec = None
    model_entity.finetuning_type = "all_weights"
    peft_mock = MagicMock()
    peft_mock.finetuning_type = "all_weights"
    model_entity.peft = peft_mock

    # Add fileset (required for SFT model deployment)
    model_entity.fileset = "hf://test/sft-model-weights"

    # Enable lora to trigger sidecar creation (2 containers)
    sample_config.model_spec.lora_enabled = True

    # Setup mock puller container
    mock_puller_container = MagicMock()
    mock_puller_container.id = "puller123456789"
    mock_puller_container.wait.return_value = {"StatusCode": 0}  # Success
    mock_puller_container.remove = MagicMock()

    # Setup mock NIM container
    mock_nim_container = MagicMock()
    mock_nim_container.id = "nim1234567890ab"
    mock_nim_container.start = MagicMock()

    # Mock images.get to return image (no pull needed)
    mock_docker_client.images.get.return_value = MagicMock()

    # Mock containers.run for puller, containers.create for NIM
    mock_docker_client.containers.run.return_value = mock_puller_container
    mock_docker_client.containers.create.return_value = mock_nim_container

    # Mock containers.list to return empty (no ports in use)
    mock_docker_client.containers.list.return_value = []

    # create_model_deployment starts the pipeline; drive it to completion
    await docker_backend.create_model_deployment(sample_deployment, sample_config, model_entity)

    # Mock puller container for get/reload polling
    mock_puller_container.status = "exited"
    mock_puller_container.attrs = {"State": {"ExitCode": 0}}
    mock_puller_container.name = docker_backend._reconciler.get_puller_container_name(
        sample_deployment.workspace, sample_deployment.name
    )

    def get_container_side_effect(name):
        if "puller" in name:
            return mock_puller_container
        raise NotFound("Container not found")

    mock_docker_client.containers.get.side_effect = get_container_side_effect

    status_update = await drive_creation_to_completion(docker_backend, sample_deployment)

    # Verify status update returns PENDING (NIM starting)
    assert status_update is not None
    assert status_update.status == "PENDING"
    assert "container created" in status_update.status_message.lower()

    # Verify puller container was run (busybox for permissions + puller + busybox for chown)
    run_calls = mock_docker_client.containers.run.call_args_list
    puller_calls = [
        c for c in run_calls if c[1].get("labels", {}).get("nmp.nvidia.com/container-type") == "model-puller"
    ]
    assert len(puller_calls) == 1
    assert puller_calls[0][1]["command"][0] == "download"

    # Verify NIM and sidecar containers were created with managed-by label
    assert mock_docker_client.containers.create.call_count == 2
    nim_call_args = mock_docker_client.containers.create.call_args_list[0][1]
    sidecar_call_args = mock_docker_client.containers.create.call_args_list[1][1]
    assert nim_call_args["labels"][MODEL_MANAGED_BY_LABEL] == MODEL_MANAGED_BY_MODELS_CONTROLLER
    assert sidecar_call_args["labels"][MODEL_MANAGED_BY_LABEL] == MODEL_MANAGED_BY_MODELS_CONTROLLER
    assert nim_call_args["environment"]["NIM_FT_MODEL"] == "/model-store"
    assert nim_call_args["environment"]["NIM_CUSTOM_MODEL"] == "/model-store"


@pytest.mark.asyncio
async def test_docker_backend_create_sft_model_puller_fails(
    docker_backend, sample_deployment, sample_config, mock_docker_client
):
    """Test that SFT model deployment fails gracefully when puller fails."""
    # Mock model entity with SFT full weights and artifact
    model_entity = MagicMock()
    model_entity.workspace = "test"
    model_entity.name = "sft-model"
    model_entity.spec = None
    model_entity.finetuning_type = "all_weights"
    peft_mock = MagicMock()
    peft_mock.finetuning_type = "all_weights"
    model_entity.peft = peft_mock

    # Add fileset (required for SFT model deployment)
    model_entity.fileset = "hf://test/sft-model-weights"

    # Setup mock puller container that fails
    mock_puller_container = MagicMock()
    mock_puller_container.id = "puller123456789"
    mock_puller_container.name = "md-puller-default-test-deployment"
    mock_puller_container.logs.return_value = b"Error: Failed to download model"
    mock_puller_container.status = "exited"
    mock_puller_container.attrs = {"State": {"ExitCode": 1}}

    # Mock images.get to return image (no pull needed)
    mock_docker_client.images.get.return_value = MagicMock()

    # Mock containers.run for puller
    mock_docker_client.containers.run.return_value = mock_puller_container

    # Mock containers.list to return empty (no ports in use)
    mock_docker_client.containers.list.return_value = []

    await docker_backend.create_model_deployment(sample_deployment, sample_config, model_entity)

    # Mock get for puller container polling
    def get_container_side_effect(name):
        if "puller" in name:
            return mock_puller_container
        raise NotFound("Container not found")

    mock_docker_client.containers.get.side_effect = get_container_side_effect

    status_update = await drive_creation_to_completion(docker_backend, sample_deployment)

    # Verify status update returns ERROR
    assert status_update is not None
    assert status_update.status == "ERROR"
    assert "model puller failed" in status_update.status_message.lower()
    assert status_update.error_details["stage"] == "model_puller"

    # Verify NIM container was NOT created
    mock_docker_client.containers.create.assert_not_called()


@pytest.mark.asyncio
async def test_docker_backend_get_model_deployment_status_running(
    docker_backend, sample_deployment, mock_docker_client
):
    """Test getting status of a running deployment."""
    # Setup mock container in running state
    mock_container = MagicMock()
    mock_container.status = "running"
    mock_container.id = "1234567890abcdef"
    docker_backend._backend_config.models_docker_networking_mode = "dond"
    mock_docker_client.containers.get.return_value = mock_container
    mock_docker_client.containers.get.side_effect = None

    status_update = await docker_backend.get_model_deployment_status(sample_deployment)

    # Verify status update
    assert status_update is not None
    assert status_update.status == "READY"
    assert "running" in status_update.status_message.lower()
    assert status_update.host_url == "http://md-default-test-deployment:8000"


@pytest.mark.asyncio
async def test_docker_backend_get_model_deployment_status_not_found(
    docker_backend, sample_deployment, mock_docker_client
):
    """Test getting status when container is not found."""
    mock_docker_client.containers.get.side_effect = NotFound("Container not found")

    status_update = await docker_backend.get_model_deployment_status(sample_deployment)

    # Verify status update
    assert status_update is not None
    assert status_update.status == "LOST"
    assert "not found" in status_update.status_message.lower()


@pytest.mark.asyncio
async def test_docker_backend_delete_model_deployment(docker_backend, sample_deployment, mock_docker_client):
    """Test deleting a model deployment."""
    # Setup mock NIM container
    mock_nim_container = MagicMock()
    mock_nim_container.id = "1234567890abcdef"

    # Setup mock puller container (should be cleaned up too)
    mock_puller_container = MagicMock()
    mock_puller_container.id = "puller12345678"

    # containers.get returns different containers based on name
    def mock_get_container(name):
        if "puller" in name:
            return mock_puller_container
        return mock_nim_container

    mock_docker_client.containers.get.side_effect = mock_get_container

    # Setup mock volume
    mock_volume = MagicMock()
    mock_docker_client.volumes.get.return_value = mock_volume
    mock_docker_client.volumes.get.side_effect = None

    status_update = await docker_backend.delete_model_deployment(sample_deployment.workspace, sample_deployment.name)

    # Verify deletion
    assert status_update is not None
    assert status_update.status == "DELETED"
    # Both containers should be stopped and removed
    assert mock_nim_container.stop.call_count == 2
    assert mock_nim_container.remove.call_count == 2
    assert mock_puller_container.stop.call_count == 1
    assert mock_puller_container.remove.call_count == 1
    assert mock_volume.remove.call_count == 2


@pytest.mark.asyncio
async def test_docker_backend_delete_cleans_up_puller_even_when_not_found(
    docker_backend, sample_deployment, mock_docker_client
):
    """Test that delete handles missing puller container gracefully."""
    # Setup mock NIM container
    mock_nim_container = MagicMock()
    mock_nim_container.id = "1234567890abcdef"

    # containers.get raises NotFound for puller but returns NIM container
    def mock_get_container(name):
        if "puller" in name:
            raise NotFound("Puller not found")
        return mock_nim_container

    mock_docker_client.containers.get.side_effect = mock_get_container

    # Setup mock volume
    mock_volume = MagicMock()
    mock_docker_client.volumes.get.return_value = mock_volume
    mock_docker_client.volumes.get.side_effect = None

    status_update = await docker_backend.delete_model_deployment(sample_deployment.workspace, sample_deployment.name)

    # Verify deletion still succeeds
    assert status_update is not None
    assert status_update.status == "DELETED"
    assert mock_nim_container.stop.call_count == 2
    assert mock_nim_container.remove.call_count == 2
    assert mock_volume.remove.call_count == 2


def test_docker_backend_initialization(mock_nmp_sdk, mock_docker_client):
    """Test Docker backend initializes correctly."""
    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config):
        backend = DockerServiceBackend(nmp_sdk=mock_nmp_sdk, config={})

        # Verify backend was created
        assert backend is not None
        assert backend._nmp_sdk == mock_nmp_sdk


def test_docker_backend_container_naming(docker_backend, sample_deployment):
    """Test container naming convention."""
    container_name = docker_backend._reconciler.get_container_name(sample_deployment.workspace, sample_deployment.name)
    assert container_name == "md-default-test-deployment"


def test_docker_backend_volume_naming(docker_backend, sample_deployment):
    """Test volume naming convention."""
    volume_name = docker_backend._reconciler.get_volume_name(sample_deployment.workspace, sample_deployment.name)
    assert volume_name == "nim-cache-default-test-deployment"


def test_docker_backend_deployment_key(docker_backend, sample_deployment):
    """Test deployment key generation."""
    deployment_key = docker_backend._reconciler.get_deployment_key(sample_deployment.workspace, sample_deployment.name)
    assert deployment_key == "default/test-deployment"


def test_docker_backend_puller_container_naming(docker_backend, sample_deployment):
    """Test puller container naming convention."""
    puller_name = docker_backend._reconciler.get_puller_container_name(
        sample_deployment.workspace, sample_deployment.name
    )
    assert puller_name == "md-puller-default-test-deployment"


# =============================================================================
# Tests for DNS label truncation (RFC 1035 - max 63 characters)
# Uses _get_k8s_safe_name from utils.py for consistent naming across backends
# =============================================================================


def test_docker_backend_container_naming_truncates_long_names(docker_backend):
    """Test that _get_container_name_for_model_deployment_id truncates names exceeding DNS limit."""
    # Create deployment with long names that would exceed 63 chars
    deployment = MagicMock()
    deployment.workspace = "e2e-customization-test"
    deployment.name = "customization-bf0cc3016831-deployment-1770393778"

    container_name = docker_backend._reconciler.get_container_name(deployment.workspace, deployment.name)

    # Should be truncated to 63 chars max
    assert len(container_name) <= 63
    # Should start with expected prefix (normalized to lowercase)
    assert container_name.startswith("md-e2e-customization-test-")


def test_docker_backend_puller_naming_truncates_long_names(docker_backend):
    """Test that _get_puller_container_name_for_model_deployment_id truncates names exceeding DNS limit."""
    # Create deployment with long names
    deployment = MagicMock()
    deployment.workspace = "e2e-customization-test"
    deployment.name = "customization-bf0cc3016831-deployment-1770393778"

    puller_name = docker_backend._reconciler.get_puller_container_name(deployment.workspace, deployment.name)

    # Should be truncated to 63 chars max
    assert len(puller_name) <= 63
    # Should start with expected prefix
    assert puller_name.startswith("md-puller-e2e-customization")


def test_docker_backend_volume_naming_truncates_long_names(docker_backend):
    """Test that _get_volume_name_for_model_deployment_id truncates names exceeding DNS limit."""
    deployment = MagicMock()
    deployment.workspace = "e2e-customization-test"
    deployment.name = "customization-bf0cc3016831-deployment-1770393778"

    volume_name = docker_backend._reconciler.get_volume_name(deployment.workspace, deployment.name)

    # Should be truncated to 63 chars max
    assert len(volume_name) <= 63
    # Should start with expected prefix
    assert volume_name.startswith("nim-cache-e2e-customization")


def test_docker_backend_naming_deterministic(docker_backend):
    """Test that container naming is deterministic (same input = same output)."""
    deployment = MagicMock()
    deployment.workspace = "e2e-customization-test"
    deployment.name = "customization-bf0cc3016831-deployment-1770393778"

    result1 = docker_backend._reconciler.get_container_name(deployment.workspace, deployment.name)
    result2 = docker_backend._reconciler.get_container_name(deployment.workspace, deployment.name)

    assert result1 == result2


def test_docker_backend_naming_unique_for_different_deployments(docker_backend):
    """Test that different deployments get different container names."""
    deployment1 = MagicMock()
    deployment1.workspace = "e2e-customization-test"
    deployment1.name = "customization-bf0cc3016831-deployment-1770393778"

    deployment2 = MagicMock()
    deployment2.workspace = "e2e-customization-test"
    deployment2.name = "customization-bf0cc3016831-deployment-9999999999"

    name1 = docker_backend._reconciler.get_container_name(deployment1.workspace, deployment1.name)
    name2 = docker_backend._reconciler.get_container_name(deployment2.workspace, deployment2.name)

    # Both should be 63 chars max
    assert len(name1) <= 63
    assert len(name2) <= 63
    # But they should be different (different hash suffixes)
    assert name1 != name2


@pytest.mark.parametrize(
    "files_url,expected",
    [
        ("http://localhost:8080", "http://localhost:8080/apis/files/v2/hf"),
        ("http://localhost:8080/", "http://localhost:8080/apis/files/v2/hf"),
        ("http://localhost:8080/v2/hf", "http://localhost:8080/apis/files/v2/hf"),
        ("http://localhost:8080/v2/hf/", "http://localhost:8080/apis/files/v2/hf"),
        ("http://localhost:8080/other/path", "http://localhost:8080/apis/files/v2/hf"),
    ],
)
def test_docker_backend_get_hf_compatible_files_url(mock_nmp_sdk, mock_docker_client, files_url, expected):
    """Test HF-compatible files URL generation with various inputs."""
    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={"files": files_url},
    )
    with patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config):
        backend = DockerServiceBackend(nmp_sdk=mock_nmp_sdk, config={})
        assert backend._reconciler._get_hf_compatible_files_url() == expected


@pytest.fixture
def docker_backend_with_dind_mode(mock_nmp_sdk, mock_docker_client, reset_shared_resource_manager_base):
    """Create a DockerServiceBackend instance with DinD networking mode."""
    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={"files": "http://files-service:8000"},
    )
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config),
        patch("nmp.common.resources.manager.get_platform_config") as mock_resource_config,
        patch("nmp.common.resources.manager.detect_gpu_device_ids") as mock_detect_gpu_device_ids,
    ):
        # Use explicit GPU list (simulating reserved_gpu_device_ids: "0,1,2,3")
        mock_resource_config.return_value.docker = create_mock_docker_config("0,1,2,3")
        mock_detect_gpu_device_ids.return_value = [0, 1, 2, 3]
        config = {
            "models_docker_networking_mode": "dind",
            "models_docker_host_service_name": "docker",
            "models_docker_port_range_start": 49152,
            "models_docker_port_range_end": 49652,
        }
        backend = DockerServiceBackend(nmp_sdk=mock_nmp_sdk, config=config)
        backend._client = mock_docker_client

        # Mock containers.list to return empty list by default (no ports in use)
        mock_docker_client.containers.list.return_value = []

        return backend


def test_docker_backend_dind_mode_initialization(docker_backend_with_dind_mode):
    """Test Docker backend with DinD mode initializes correctly."""
    assert docker_backend_with_dind_mode._backend_config.models_docker_networking_mode == "dind"
    assert docker_backend_with_dind_mode._backend_config.models_docker_host_service_name == "docker"
    assert docker_backend_with_dind_mode._backend_config.models_docker_port_range_start == 49152
    assert docker_backend_with_dind_mode._backend_config.models_docker_port_range_end == 49652


def test_docker_backend_local_mode_initialization(mock_nmp_sdk, mock_docker_client):
    """Test Docker backend with local mode (default) initializes correctly."""
    platform_config = PlatformConfig(  # type: ignore[abstract]
        service_discovery={"files": "http://files-service:8000"},
    )
    with patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config):
        config = {"models_docker_networking_mode": "local"}
        backend = DockerServiceBackend(nmp_sdk=mock_nmp_sdk, config=config)
        backend._client = mock_docker_client

        assert backend._backend_config.models_docker_networking_mode == "local"


@pytest.mark.asyncio
async def test_docker_backend_create_with_port_forwarding(
    docker_backend_with_dind_mode, sample_deployment, sample_config, mock_docker_client
):
    """Test creating a deployment with port forwarding enabled."""
    # Setup mock container
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container

    # Mock image found locally
    mock_docker_client.images.get.return_value = MagicMock()

    # Mock containers.list to return empty (no ports in use)
    mock_docker_client.containers.list.return_value = []

    await docker_backend_with_dind_mode.create_model_deployment(sample_deployment, sample_config)
    status_update = await drive_creation_to_completion(docker_backend_with_dind_mode, sample_deployment)

    # Verify status update
    assert status_update is not None
    assert status_update.status == "PENDING"

    # Host URL should use docker service name and first available port (8000)
    assert status_update.host_url == "http://docker:49152"

    # Verify container was created with port mapping
    call_args = mock_docker_client.containers.create.call_args_list[0]
    assert "ports" in call_args[1]
    assert "8000/tcp" in call_args[1]["ports"]
    assert call_args[1]["ports"]["8000/tcp"] == 49152


@pytest.mark.asyncio
async def test_docker_backend_get_status_with_port_forwarding(
    docker_backend_with_dind_mode, sample_deployment, mock_docker_client
):
    """Test getting deployment status with port forwarding uses correct URL."""
    # Mock a running container with port 8001 mapped
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.status = "running"
    mock_container.attrs = {"State": {"StartedAt": "2024-01-01T00:00:00Z"}}
    mock_container.ports = {"8000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "49152"}]}
    mock_container.reload = MagicMock()  # Mock reload method

    # Clear side_effect and set return_value
    mock_docker_client.containers.get.side_effect = None
    mock_docker_client.containers.get.return_value = mock_container

    status_update = await docker_backend_with_dind_mode.get_model_deployment_status(sample_deployment)

    # Verify status and URL uses the port from container bindings
    assert status_update.status == "READY"
    assert status_update.host_url == "http://docker:49152"


@pytest.mark.asyncio
async def test_docker_backend_delete_with_port_forwarding_releases_port(
    docker_backend_with_dind_mode, sample_deployment, sample_config, mock_docker_client
):
    """Test deleting a deployment releases the allocated port (port is freed automatically when container is removed)."""
    # Mock NIM container
    mock_nim_container = MagicMock()
    mock_nim_container.id = "1234567890abcdef"
    mock_nim_container.stop = MagicMock()
    mock_nim_container.remove = MagicMock()

    # Mock puller container (not found - common case when NIM already started)
    def mock_get_container(name):
        if "puller" in name:
            raise NotFound("Puller not found")
        return mock_nim_container

    mock_docker_client.containers.get.side_effect = mock_get_container

    mock_volume = MagicMock()
    mock_docker_client.volumes.get.side_effect = None
    mock_docker_client.volumes.get.return_value = mock_volume

    status_update = await docker_backend_with_dind_mode.delete_model_deployment(
        sample_deployment.workspace, sample_deployment.name
    )

    # Verify deletion succeeded
    assert status_update.status == "DELETED"

    # Verify NIM container was stopped and removed
    assert mock_nim_container.stop.call_count == 2
    assert mock_nim_container.remove.call_count == 2


@pytest.mark.asyncio
async def test_docker_backend_port_exhaustion_error(
    docker_backend_with_dind_mode, sample_deployment, sample_config, mock_docker_client
):
    """Test that deployment fails gracefully when ports are exhausted."""
    # Mock image found locally
    mock_docker_client.images.get.return_value = MagicMock()

    # Mock containers.list to return containers using all ports in range (8000-9000)
    # Create mock containers with all ports allocated
    mock_containers = []
    for port in range(49152, 49652 + 1):  # All ports in range
        mock_cont = MagicMock()
        mock_cont.ports = {"8000/tcp": [{"HostIp": "0.0.0.0", "HostPort": str(port)}]}
        mock_containers.append(mock_cont)

    mock_docker_client.containers.list.return_value = mock_containers

    await docker_backend_with_dind_mode.create_model_deployment(sample_deployment, sample_config)
    status_update = await drive_creation_to_completion(docker_backend_with_dind_mode, sample_deployment)

    # Should return ERROR status (port exhaustion happens during container creation stage)
    assert status_update.status == "ERROR"
    assert "port" in status_update.status_message.lower()
    assert "no ports available" in status_update.status_message.lower()


@pytest.mark.asyncio
async def test_docker_backend_multiple_deployments_unique_ports(
    docker_backend_with_dind_mode, sample_config, mock_docker_client
):
    """Test that multiple deployments get unique ports."""
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.images.get.return_value = MagicMock()

    # Track allocated containers to simulate real Docker state
    allocated_containers = []

    def mock_containers_list(**kwargs):
        return allocated_containers

    mock_docker_client.containers.list.side_effect = mock_containers_list

    # Create three different deployments
    deployments = []
    ports = []

    for i in range(3):
        deployment = MagicMock()
        deployment.workspace = "test"
        deployment.name = f"model-{i}"
        deployments.append(deployment)

        await docker_backend_with_dind_mode.create_model_deployment(deployment, sample_config)
        status = await drive_creation_to_completion(docker_backend_with_dind_mode, deployment)

        # Extract port from host_url (format: http://docker:PORT)
        print(f"status.host_url: {status.host_url}")
        port = int(status.host_url.split(":")[-1])
        ports.append(port)

        # Add mock container with allocated port to the list
        mock_cont = MagicMock()
        mock_cont.ports = {"8000/tcp": [{"HostIp": "0.0.0.0", "HostPort": str(port)}]}
        allocated_containers.append(mock_cont)

    # Verify all ports are unique, valid, and sequential starting from 8000
    assert len(set(ports)) == 3
    assert ports == [49152, 49153, 49154]


# =============================================================================
# Tests for multi-LLM image detection and SFT model handling
# =============================================================================


@pytest.fixture
def multi_llm_config():
    """Create a config using the default multi-LLM image (no image_name specified)."""
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name=None,  # Will use default multi-LLM image
        image_tag=None,
        model_name="test-sft-model",
        model_namespace="default",
        lora_enabled=False,
        additional_envs=None,
    )
    return config


@pytest.fixture
def explicit_multi_llm_config():
    """Create a config explicitly using the multi-LLM image."""
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/nvidia/llm-nim",  # Explicit multi-LLM image
        image_tag="latest",
        model_name="test-sft-model",
        model_namespace="default",
        lora_enabled=False,
        additional_envs=None,
    )
    return config


@pytest.fixture
def model_specific_nim_config():
    """Create a config using a model-specific NIM image (not multi-LLM)."""
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",  # Model-specific NIM
        image_tag="1.8.6",
        model_name="test-sft-model",
        model_namespace="default",
        lora_enabled=False,
        additional_envs=None,
    )
    return config


@pytest.fixture
def sft_model_entity():
    """Create a mock SFT model entity with full weights."""
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-sft-model"
    model_entity.spec = None
    model_entity.finetuning_type = "all_weights"
    peft_mock = MagicMock()
    peft_mock.finetuning_type = "all_weights"
    model_entity.peft = peft_mock
    return model_entity


def _setup_puller_mock_for_polling(mock_docker_client, deployment, exit_code=0):
    """Configure mock containers for the polled puller flow.

    Sets up containers.run to return a puller mock, and containers.get
    to return it for reload-based polling (exited with given exit_code).
    For non-puller containers, falls back to NotFound (the default mock_docker_client behavior).
    """
    mock_puller = MagicMock()
    mock_puller.id = "puller123456789"
    mock_puller.name = f"md-puller-{deployment.workspace}-{deployment.name}"
    mock_puller.status = "exited"
    mock_puller.attrs = {"State": {"ExitCode": exit_code}}
    mock_puller.reload = MagicMock()
    mock_puller.remove = MagicMock()
    mock_puller.logs = MagicMock(return_value=b"puller output")

    mock_docker_client.containers.run.return_value = mock_puller

    def get_container_side_effect(name):
        if "puller" in name:
            return mock_puller
        raise NotFound("Container not found")

    mock_docker_client.containers.get.side_effect = get_container_side_effect
    return mock_puller


@pytest.mark.asyncio
async def test_multi_llm_sft_model_now_runs_puller_old_test_updated(
    docker_backend, sample_deployment, multi_llm_config, sft_model_entity, mock_docker_client
):
    """Test that multi-LLM image with SFT model NOW runs the model puller (updated behavior)."""
    multi_llm_config.model_spec.lora_enabled = True

    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    _setup_puller_mock_for_polling(mock_docker_client, sample_deployment, exit_code=0)

    await docker_backend.create_model_deployment(sample_deployment, multi_llm_config, sft_model_entity)
    status_update = await drive_creation_to_completion(docker_backend, sample_deployment)

    assert status_update is not None
    assert status_update.status == "PENDING"

    puller_calls = [
        call
        for call in mock_docker_client.containers.run.call_args_list
        if call[1].get("labels", {}).get("nmp.nvidia.com/container-type") == "model-puller"
    ]
    assert len(puller_calls) == 1, "Model puller SHOULD run for multi-LLM deployments"

    assert mock_docker_client.containers.create.call_count == 2, "NIM container and sidecar should be created"

    nim_call_args = mock_docker_client.containers.create.call_args_list[0]
    env_vars = nim_call_args[1]["environment"]
    assert env_vars["NIM_MODEL_NAME"] == "/model-store"
    assert "NIM_FT_MODEL" not in env_vars
    assert "HF_ENDPOINT" not in env_vars

    sidecar_call_args = mock_docker_client.containers.create.call_args_list[1]
    sidecar_env_vars = sidecar_call_args[1]["environment"]
    assert "NMP_MODELS_URL" in sidecar_env_vars
    assert "NMP_FILES_URL" in sidecar_env_vars


@pytest.mark.asyncio
async def test_model_specific_nim_sft_model_runs_puller(
    docker_backend, sample_deployment, model_specific_nim_config, sft_model_entity, mock_docker_client
):
    """Test that model-specific NIM with SFT model DOES run the model puller."""
    model_specific_nim_config.model_spec.lora_enabled = True

    mock_nim_container = MagicMock()
    mock_nim_container.id = "nim1234567890ab"
    mock_nim_container.start = MagicMock()

    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.create.return_value = mock_nim_container
    mock_docker_client.containers.list.return_value = []

    _setup_puller_mock_for_polling(mock_docker_client, sample_deployment, exit_code=0)

    await docker_backend.create_model_deployment(sample_deployment, model_specific_nim_config, sft_model_entity)
    status_update = await drive_creation_to_completion(docker_backend, sample_deployment)

    assert status_update is not None
    assert status_update.status == "PENDING"

    puller_calls = [
        call
        for call in mock_docker_client.containers.run.call_args_list
        if call[1].get("labels", {}).get("nmp.nvidia.com/container-type") == "model-puller"
    ]
    assert len(puller_calls) == 1

    assert mock_docker_client.containers.create.call_count == 2
    nim_call_args = mock_docker_client.containers.create.call_args_list[0]
    env_vars = nim_call_args[1]["environment"]
    assert env_vars.get("NIM_FT_MODEL") == "/model-store"
    sidecar_call_args = mock_docker_client.containers.create.call_args_list[1]
    sidecar_env_vars = sidecar_call_args[1]["environment"]
    assert "NMP_MODELS_URL" in sidecar_env_vars
    assert "NMP_FILES_URL" in sidecar_env_vars


@pytest.mark.asyncio
async def test_explicit_multi_llm_image_now_runs_puller(
    docker_backend, sample_deployment, explicit_multi_llm_config, sft_model_entity_with_artifact, mock_docker_client
):
    """Test that explicitly specifying the multi-LLM image now runs the puller."""
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    _setup_puller_mock_for_polling(mock_docker_client, sample_deployment, exit_code=0)

    await docker_backend.create_model_deployment(
        sample_deployment, explicit_multi_llm_config, sft_model_entity_with_artifact
    )
    status_update = await drive_creation_to_completion(docker_backend, sample_deployment)

    assert status_update is not None
    assert status_update.status == "PENDING"

    puller_calls = [
        call
        for call in mock_docker_client.containers.run.call_args_list
        if call[1].get("labels", {}).get("nmp.nvidia.com/container-type") == "model-puller"
    ]
    assert len(puller_calls) == 1


@pytest.mark.asyncio
async def test_multi_llm_non_sft_model_fails_without_supported_weights_type(
    docker_backend, sample_deployment, multi_llm_config, mock_docker_client
):
    """Test that multi-LLM with non-SFT model (no model entity) fails due to unsupported weights type."""
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    await docker_backend.create_model_deployment(sample_deployment, multi_llm_config, model_entity=None)
    status_update = await drive_creation_to_completion(docker_backend, sample_deployment)

    assert status_update is not None
    assert status_update.status == "ERROR"
    assert (
        "model puller" in status_update.status_message.lower()
        or "model weights" in status_update.status_message.lower()
        or "unsupported" in status_update.status_message.lower()
    )


def test_default_multi_llm_image_config():
    """Test that the default NIM image is the multi-LLM image."""
    from nmp.core.models.controllers.backends.docker.config import DockerBackendConfig

    config = DockerBackendConfig()
    assert config.default_nimservice_image == "nvcr.io/nim/nvidia/llm-nim", (
        "Default NIM image should be the multi-LLM image"
    )


def test_default_vllm_image_config():
    """Test that a default vLLM image and tag are configured."""
    from nmp.core.models.controllers.backends.docker.config import DockerBackendConfig

    config = DockerBackendConfig()
    assert config.default_vllm_image == "vllm/vllm-openai", "Default vLLM image should be the vllm-openai image"
    # The exact tag is config-driven and bumped over time; just assert one is set.
    assert config.default_vllm_image_tag, "A default vLLM image tag should be configured"


# =============================================================================
# Tests for model puller with different model weights types
# =============================================================================


@pytest.fixture
def sft_model_entity_with_artifact():
    """Create a mock SFT model entity with fileset."""
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-sft-model"
    model_entity.spec = None
    model_entity.finetuning_type = "all_weights"
    # Setup PEFT mock for SFT model
    peft_mock = MagicMock()
    peft_mock.finetuning_type = "all_weights"
    model_entity.peft = peft_mock
    # Setup fileset
    model_entity.fileset = "hf://workspace/test-fileset"
    return model_entity


@pytest.fixture
def huggingface_model_config():
    """Create a config for HuggingFace model deployment."""
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",
        image_tag="1.8.6",
        model_name="llama-3.2-1b-instruct",
        model_namespace="meta",
        model_revision="main",
        lora_enabled=False,
        additional_envs=None,
    )
    return config


@pytest.mark.asyncio
async def test_multi_llm_now_runs_puller(
    docker_backend, sample_deployment, multi_llm_config, sft_model_entity_with_artifact, mock_docker_client
):
    """Test that multi-LLM deployments now run the model puller (updated behavior)."""
    multi_llm_config.model_spec.lora_enabled = True

    mock_nim_container = MagicMock()
    mock_nim_container.id = "nim1234567890ab"
    mock_nim_container.start = MagicMock()
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.create.return_value = mock_nim_container
    mock_docker_client.containers.list.return_value = []

    _setup_puller_mock_for_polling(mock_docker_client, sample_deployment, exit_code=0)

    await docker_backend.create_model_deployment(sample_deployment, multi_llm_config, sft_model_entity_with_artifact)
    status_update = await drive_creation_to_completion(docker_backend, sample_deployment)

    assert status_update is not None
    assert status_update.status == "PENDING"

    puller_calls = [
        call
        for call in mock_docker_client.containers.run.call_args_list
        if call[1].get("labels", {}).get("nmp.nvidia.com/container-type") == "model-puller"
    ]
    assert len(puller_calls) == 1

    assert mock_docker_client.containers.create.call_count == 2

    nim_call_args = mock_docker_client.containers.create.call_args
    env_vars = nim_call_args[1]["environment"]
    assert env_vars.get("NIM_MODEL_NAME") == "/model-store"
    assert "HF_ENDPOINT" not in env_vars


@pytest.mark.asyncio
async def test_compile_env_vars_multi_llm_updated_behavior(docker_backend, sample_deployment, multi_llm_config):
    """Test that _compile_env_vars for multi-LLM uses updated behavior."""
    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        multi_llm_config,
        model_entity=None,
        model_weights_type=ModelWeightsType.FILES_SERVICE,
        is_multi_llm=True,
    )

    # Multi-LLM should set NIM_MODEL_NAME to /model-store
    assert env_vars.get("NIM_MODEL_NAME") == "/model-store"

    # Should NOT have HF_ENDPOINT (removed in updated behavior)
    assert "HF_ENDPOINT" not in env_vars

    # Should have NIM_SERVED_MODEL_NAME (multi_llm_config has model_name set)
    assert "NIM_SERVED_MODEL_NAME" in env_vars


@pytest.fixture
def nim_only_config():
    """Create a deployment config with only NIM image info, no model_name/model_namespace.

    This simulates deployments like:
        nemo inference deployment-configs create \
            --name "nemoguard-jailbreak-config" \
            --nim-deployment '{"gpu": 1, "image_name": "nvcr.io/nim/nvidia/nemoguard-jailbreak-detect", "image_tag": "1.10.1"}'
    """
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/nvidia/nemoguard-jailbreak-detect",
        image_tag="1.10.1",
        model_name=None,  # Not set
        model_namespace=None,  # Not set
        lora_enabled=False,
        additional_envs=None,
    )
    return config


@pytest.mark.asyncio
async def test_compile_env_vars_without_model_name(docker_backend, sample_deployment, nim_only_config):
    """Test that _compile_env_vars works when model_name is not provided.

    Regression test: Previously this would raise NameError because model_fqdn
    was only defined inside the 'if nim_config.model_name:' block.
    """
    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        nim_only_config,
        model_entity=None,
        model_weights_type=ModelWeightsType.BAKED_CONTAINER,
        is_multi_llm=False,
    )

    # Should NOT have NIM_SERVED_MODEL_NAME when model_name is not provided
    assert "NIM_SERVED_MODEL_NAME" not in env_vars

    # Should still have other required env vars
    assert "NIM_GUIDED_DECODING_BACKEND" in env_vars


@pytest.mark.asyncio
async def test_compile_env_vars_with_trust_remote_code_false(docker_backend, sample_deployment, sample_config):
    """Test that _compile_env_vars does NOT set NIM_FORCE_TRUST_REMOTE_CODE when trust_remote_code is False."""
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-model"
    model_entity.trust_remote_code = False

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        sample_config,
        model_entity=model_entity,
        model_weights_type=ModelWeightsType.BAKED_CONTAINER,
        is_multi_llm=False,
    )

    # Should have model entity env vars
    assert env_vars.get("NMP_MODEL_ENTITY_WORKSPACE") == "default"
    assert env_vars.get("NMP_MODEL_ENTITY_NAME") == "test-model"

    # Should NOT have NIM_FORCE_TRUST_REMOTE_CODE when trust_remote_code is False
    assert "NIM_FORCE_TRUST_REMOTE_CODE" not in env_vars


@pytest.mark.asyncio
async def test_compile_env_vars_with_trust_remote_code_true(docker_backend, sample_deployment, sample_config):
    """Test that _compile_env_vars sets NIM_FORCE_TRUST_REMOTE_CODE when trust_remote_code is True."""
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-model"
    model_entity.trust_remote_code = True

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        sample_config,
        model_entity=model_entity,
        model_weights_type=ModelWeightsType.BAKED_CONTAINER,
        is_multi_llm=False,
    )

    # Should have model entity env vars
    assert env_vars.get("NMP_MODEL_ENTITY_WORKSPACE") == "default"
    assert env_vars.get("NMP_MODEL_ENTITY_NAME") == "test-model"

    # Should have NIM_FORCE_TRUST_REMOTE_CODE set to "1" when trust_remote_code is True
    assert env_vars.get("NIM_FORCE_TRUST_REMOTE_CODE") == "1"


@pytest.mark.asyncio
async def test_compile_env_vars_without_model_entity(docker_backend, sample_deployment, sample_config):
    """Test that _compile_env_vars works correctly when model_entity is None."""
    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        sample_config,
        model_entity=None,
        model_weights_type=ModelWeightsType.BAKED_CONTAINER,
        is_multi_llm=False,
    )

    # Should NOT have model entity env vars when model_entity is None
    assert "NMP_MODEL_ENTITY_WORKSPACE" not in env_vars
    assert "NMP_MODEL_ENTITY_NAME" not in env_vars
    assert "NIM_FORCE_TRUST_REMOTE_CODE" not in env_vars


# =============================================================================
# Tests for retry logic
# =============================================================================


def test_should_retry_docker_error_with_retryable_errors():
    """Test that _should_retry_docker_error returns True for retryable errors."""
    from docker.errors import APIError
    from nmp.core.models.controllers.backends.docker.creation_reconciler import _should_retry_docker_error
    from requests.exceptions import ConnectionError as RequestsConnectionError
    from requests.exceptions import ReadTimeout
    from urllib3.exceptions import ReadTimeoutError as Urllib3ReadTimeoutError

    # These should be retried
    assert _should_retry_docker_error(APIError("API error")) is True
    assert _should_retry_docker_error(ReadTimeout("Read timeout")) is True
    assert _should_retry_docker_error(Urllib3ReadTimeoutError(None, None, "timeout")) is True
    assert _should_retry_docker_error(RequestsConnectionError("Connection error")) is True
    assert _should_retry_docker_error(TimeoutError("Timeout")) is True


def test_should_retry_docker_error_with_non_retryable_errors():
    """Test that _should_retry_docker_error returns False for non-retryable errors."""
    from docker.errors import ImageNotFound, NotFound
    from nmp.core.models.controllers.backends.docker.creation_reconciler import _should_retry_docker_error

    # These should NOT be retried (resource doesn't exist)
    assert _should_retry_docker_error(NotFound("Container not found")) is False
    assert _should_retry_docker_error(ImageNotFound("Image not found")) is False

    # Other exceptions should not be retried
    assert _should_retry_docker_error(ValueError("Value error")) is False
    assert _should_retry_docker_error(KeyError("Key error")) is False


# =============================================================================
# Tests for remote Docker host detection
# =============================================================================


def test_is_remote_docker_host_with_tcp(docker_backend):
    """Test _is_remote_docker_host returns True for TCP Docker host."""
    with patch.dict("os.environ", {"DOCKER_HOST": "tcp://docker:2375"}):
        assert docker_backend._reconciler._is_remote_docker_host() is True


def test_is_remote_docker_host_with_unix_socket(docker_backend):
    """Test _is_remote_docker_host returns False for Unix socket."""
    with patch.dict("os.environ", {"DOCKER_HOST": "unix:///var/run/docker.sock"}):
        assert docker_backend._reconciler._is_remote_docker_host() is False


def test_is_remote_docker_host_with_no_env(docker_backend):
    """Test _is_remote_docker_host returns False when DOCKER_HOST not set."""
    with patch.dict("os.environ", {}, clear=True):
        assert docker_backend._reconciler._is_remote_docker_host() is False


def test_is_port_free_skips_check_for_remote_docker(docker_backend):
    """Test _is_port_free skips local port check for remote Docker host."""
    with patch.dict("os.environ", {"DOCKER_HOST": "tcp://docker:2375"}):
        # Should return True immediately without attempting to bind
        assert docker_backend._reconciler._is_port_free(8000) is True


# =============================================================================
# Tests for host URL generation
# =============================================================================


def test_get_host_url_dond_mode():
    """Test _get_host_url returns container name URL in DonD mode."""
    from unittest.mock import MagicMock, patch

    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config),
        patch("nmp.core.models.controllers.backends.docker.backend.docker.from_env") as mock_docker,
    ):
        mock_docker.return_value = MagicMock()

        mock_nmp_sdk = AsyncMock()
        config = {"models_docker_networking_mode": "dond"}
        backend = DockerServiceBackend(nmp_sdk=mock_nmp_sdk, config=config)

        url = backend._reconciler.get_host_url(container_name="test-container", host_port=8500)
        assert url == "http://test-container:8000"


def test_get_host_url_dind_mode():
    """Test _get_host_url returns Docker service URL with port in DinD mode."""
    from unittest.mock import AsyncMock, MagicMock, patch

    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config),
        patch("nmp.core.models.controllers.backends.docker.backend.docker.from_env") as mock_docker,
    ):
        mock_docker.return_value = MagicMock()

        mock_nmp_sdk = AsyncMock()
        config = {
            "models_docker_networking_mode": "dind",
            "models_docker_host_service_name": "docker",
        }
        backend = DockerServiceBackend(nmp_sdk=mock_nmp_sdk, config=config)

        url = backend._reconciler.get_host_url(container_name="test-container", host_port=8500)
        assert url == "http://docker:8500"


def test_get_host_url_local_mode():
    """Test _get_host_url returns localhost URL in local mode."""
    from unittest.mock import AsyncMock, MagicMock, patch

    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config),
        patch("nmp.core.models.controllers.backends.docker.backend.docker.from_env") as mock_docker,
    ):
        mock_docker.return_value = MagicMock()

        mock_nmp_sdk = AsyncMock()
        config = {"models_docker_networking_mode": "local"}
        backend = DockerServiceBackend(nmp_sdk=mock_nmp_sdk, config=config)

        url = backend._reconciler.get_host_url(container_name="test-container", host_port=8500)
        assert url == "http://localhost:8500"


# =============================================================================
# Tests for Files service URL handling in DonD mode
# =============================================================================


def test_get_hf_compatible_files_url_replaces_localhost_in_dond():
    """Test _get_hf_compatible_files_url replaces localhost with container name in DonD mode."""
    from unittest.mock import AsyncMock, MagicMock, patch

    # Default base_url is http://localhost:8080; get_service_url("files") returns base_url
    platform_config = PlatformConfig()  # type: ignore[abstract]
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config),
        patch("nmp.core.models.controllers.backends.docker.backend.docker.from_env") as mock_docker,
    ):
        mock_docker.return_value = MagicMock()

        mock_nmp_sdk = AsyncMock()
        config = {
            "models_docker_networking_mode": "dond",
            "models_docker_container_name": "nmp-container",
        }
        backend = DockerServiceBackend(nmp_sdk=mock_nmp_sdk, config=config)

        url = backend._reconciler._get_hf_compatible_files_url()
        assert url == "http://nmp-container:8080/apis/files/v2/hf"


def test_get_hf_compatible_files_url_no_replacement_in_local_mode():
    """Test _get_hf_compatible_files_url doesn't replace localhost in local mode."""
    from unittest.mock import AsyncMock, MagicMock, patch

    # Default base_url is http://localhost:8080
    platform_config = PlatformConfig()  # type: ignore[abstract]
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config),
        patch("nmp.core.models.controllers.backends.docker.backend.docker.from_env") as mock_docker,
    ):
        mock_docker.return_value = MagicMock()

        mock_nmp_sdk = AsyncMock()
        config = {"models_docker_networking_mode": "local"}
        backend = DockerServiceBackend(nmp_sdk=mock_nmp_sdk, config=config)

        url = backend._reconciler._get_hf_compatible_files_url()
        assert url == "http://localhost:8080/apis/files/v2/hf"


@pytest.mark.asyncio
async def test_compile_env_vars_multi_llm_updated(docker_backend, sample_deployment, multi_llm_config):
    """Test that _compile_env_vars sets correct env vars for multi-LLM deployments (updated behavior)."""
    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        multi_llm_config,
        model_entity=None,
        model_weights_type=ModelWeightsType.FILES_SERVICE,
        is_multi_llm=True,
    )

    # Multi-LLM should NOT have HF_ENDPOINT anymore (updated behavior)
    assert "HF_ENDPOINT" not in env_vars, "Multi-LLM should NOT have HF_ENDPOINT in NIM container (updated behavior)"
    assert "NIM_MODEL_NAME" in env_vars
    assert env_vars["NIM_MODEL_NAME"] == "/model-store", "Multi-LLM should use /model-store (updated behavior)"
    assert "NIM_SERVED_MODEL_NAME" in env_vars


@pytest.mark.asyncio
async def test_compile_env_vars_model_specific_nim_sft(docker_backend, sample_deployment, model_specific_nim_config):
    """Test that _compile_env_vars sets NIM_FT_MODEL for model-specific NIM with SFT."""
    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        model_specific_nim_config,
        model_entity=None,
        model_weights_type=ModelWeightsType.FILES_SERVICE,
        is_multi_llm=False,
    )

    assert env_vars.get("NIM_FT_MODEL") == "/model-store", "Model-specific NIM SFT should have NIM_FT_MODEL"
    assert env_vars.get("NIM_CUSTOM_MODEL") == "/model-store", "Model-specific NIM SFT should have NIM_CUSTOM_MODEL"
    # Should NOT have HF_ENDPOINT (model-specific NIMs don't use it)
    assert "HF_ENDPOINT" not in env_vars


@pytest.mark.asyncio
async def test_compile_env_vars_multi_llm_sft_no_ft_model(docker_backend, sample_deployment, multi_llm_config):
    """Test that _compile_env_vars does NOT set NIM_FT_MODEL for multi-LLM even with SFT flag."""
    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        multi_llm_config,
        model_entity=None,
        model_weights_type=ModelWeightsType.FILES_SERVICE,
        is_multi_llm=True,
    )

    # Multi-LLM should NOT have NIM_FT_MODEL even when puller ran (weights from Files).
    assert "NIM_FT_MODEL" not in env_vars, "Multi-LLM should NOT have NIM_FT_MODEL"
    assert "NIM_CUSTOM_MODEL" not in env_vars
    # Updated behavior: HF_ENDPOINT is not set in NIM container for multi-LLM (only in puller)
    assert "HF_ENDPOINT" not in env_vars, "Multi-LLM should NOT have HF_ENDPOINT in NIM container (updated behavior)"
    assert env_vars.get("NIM_MODEL_NAME") == "/model-store", "Multi-LLM should use /model-store"


# =============================================================================
# Tests for DonD networking mode (quickstart setup)
# =============================================================================


@pytest.fixture
def docker_backend_with_dond_mode(mock_nmp_sdk, mock_docker_client, reset_shared_resource_manager_base):
    """Create a DockerServiceBackend instance with DonD networking mode.

    This simulates the DonD (Docker-on-Docker) quickstart setup where NIMs need to
    join the same network as the NeMo Platform container.
    """
    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config),
        patch("nmp.common.resources.manager.get_platform_config") as mock_resource_config,
        patch("nmp.common.resources.manager.detect_gpu_device_ids") as mock_detect_gpu_device_ids,
    ):
        # Use explicit GPU list (simulating reserved_gpu_device_ids: "0,1,2,3")
        mock_resource_config.return_value.docker = create_mock_docker_config("0,1,2,3")
        mock_detect_gpu_device_ids.return_value = [0, 1, 2, 3]
        config = {
            "models_docker_networking_mode": "dond",
            "models_docker_network": "nmp-quickstart-network",
            "models_docker_port_range_start": 49152,
            "models_docker_port_range_end": 49652,
        }
        backend = DockerServiceBackend(nmp_sdk=mock_nmp_sdk, config=config)
        backend._client = mock_docker_client

        # Mock containers.list to return empty list by default (no ports in use)
        mock_docker_client.containers.list.return_value = []

        return backend


def test_should_attach_network_with_dond_mode(docker_backend_with_dond_mode):
    """Test that _should_attach_network returns True when using DonD mode."""
    assert docker_backend_with_dond_mode._reconciler._should_attach_network() is True


def test_should_attach_network_with_local_mode(docker_backend):
    """Test that _should_attach_network returns False when using local mode (default)."""
    assert docker_backend._reconciler._should_attach_network() is False


def test_should_attach_network_with_dind_mode(docker_backend_with_dind_mode):
    """Test that _should_attach_network returns False when using DinD mode."""
    assert docker_backend_with_dind_mode._reconciler._should_attach_network() is False


@pytest.mark.asyncio
async def test_docker_backend_create_with_dond_mode_uses_container_name_url(
    docker_backend_with_dond_mode, sample_deployment, sample_config, mock_docker_client
):
    """Test that create_model_deployment uses container name URL when using DonD mode.

    In DonD mode, containers communicate via the shared network using container names.
    """
    # Setup mock container
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container

    # Mock image found locally
    mock_docker_client.images.get.return_value = MagicMock()

    # Mock containers.list to return empty (no ports in use)
    mock_docker_client.containers.list.return_value = []

    await docker_backend_with_dond_mode.create_model_deployment(sample_deployment, sample_config)
    status_update = await drive_creation_to_completion(docker_backend_with_dond_mode, sample_deployment)

    # Verify status update
    assert status_update is not None
    assert status_update.status == "PENDING"

    # Host URL should use container name (DonD mode uses container names)
    assert status_update.host_url == "http://md-default-test-deployment:8000"

    # Verify container was created with the network
    call_args = mock_docker_client.containers.create.call_args_list[0]
    assert call_args[1]["network"] == "nmp-quickstart-network"


@pytest.mark.asyncio
async def test_docker_backend_get_status_with_dond_mode_uses_container_name_url(
    docker_backend_with_dond_mode, sample_deployment, mock_docker_client
):
    """Test that get_model_deployment_status uses container name URL when using DonD mode."""
    # Mock a running container with port mapping (should be ignored for URL in DonD mode)
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.status = "running"
    mock_container.attrs = {"State": {"StartedAt": "2024-01-01T00:00:00Z"}}
    mock_container.ports = {"8000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "49200"}]}
    mock_container.reload = MagicMock()

    # Clear side_effect and set return_value
    mock_docker_client.containers.get.side_effect = None
    mock_docker_client.containers.get.return_value = mock_container

    status_update = await docker_backend_with_dond_mode.get_model_deployment_status(sample_deployment)

    # Verify status and URL uses container name (DonD mode ignores port bindings)
    assert status_update.status == "READY"
    assert status_update.host_url == "http://md-default-test-deployment:8000"


@pytest.mark.asyncio
async def test_docker_backend_dond_mode_container_joins_network(
    docker_backend_with_dond_mode, sample_deployment, sample_config, mock_docker_client
):
    """Test that NIM container is created with the network attached in DonD mode."""
    # Enable lora to trigger sidecar creation (2 containers)
    sample_config.model_spec.lora_enabled = True

    # Setup mock container
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    await docker_backend_with_dond_mode.create_model_deployment(sample_deployment, sample_config)
    await drive_creation_to_completion(docker_backend_with_dond_mode, sample_deployment)

    # Verify every container was created with network attached
    assert mock_docker_client.containers.create.call_count == 2, "Should create 2 containers"
    call_args = mock_docker_client.containers.create.call_args_list

    assert "network" in call_args[0][1], "Container should have network specified in DonD mode"
    assert call_args[0][1]["network"] == "nmp-quickstart-network"


def test_docker_backend_dond_mode_initialization(docker_backend_with_dond_mode):
    """Test Docker backend with DonD mode initializes correctly."""
    assert docker_backend_with_dond_mode._backend_config.models_docker_networking_mode == "dond"
    assert docker_backend_with_dond_mode._backend_config.models_docker_network == "nmp-quickstart-network"


# =============================================================================
# GPU Pool Tests
# =============================================================================


@pytest.fixture
def reset_shared_resource_manager():
    """Reset SharedResourceManager singleton before and after test."""
    from nmp.common.resources import SharedResourceManager

    SharedResourceManager.reset_instance()
    yield
    SharedResourceManager.reset_instance()


@pytest.fixture
def docker_backend_with_gpu_pool(mock_nmp_sdk, mock_docker_client, reset_shared_resource_manager):
    """Create a DockerServiceBackend instance with GPU pool enabled via explicit config."""
    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config),
        patch("nmp.common.resources.manager.detect_gpu_device_ids") as mock_detect_gpu_device_ids,
        patch("nmp.common.resources.manager.get_platform_config") as mock_resource_config,
    ):
        # Configure mocks to simulate 4 GPUs via explicit config
        mock_detect_gpu_device_ids.return_value = [0, 1, 2, 3]
        mock_resource_config.return_value.docker = create_mock_docker_config("0,1,2,3")
        backend = DockerServiceBackend(
            nmp_sdk=mock_nmp_sdk,
            config={},
        )
        backend._client = mock_docker_client
        return backend


@pytest.fixture
def docker_backend_without_gpu_pool(mock_nmp_sdk, mock_docker_client, reset_shared_resource_manager):
    """Create a DockerServiceBackend instance without GPU pool (empty config)."""
    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config),
        patch("nmp.common.resources.manager.detect_gpu_device_ids") as mock_detect_gpu_device_ids,
        patch("nmp.common.resources.manager.get_platform_config") as mock_resource_config,
    ):
        mock_detect_gpu_device_ids.return_value = None
        # Empty string means no GPUs configured
        mock_resource_config.return_value.docker = create_mock_docker_config("")
        backend = DockerServiceBackend(
            nmp_sdk=mock_nmp_sdk,
            config={},
        )
        backend._client = mock_docker_client
        return backend


def test_docker_backend_gpu_pool_initialization(docker_backend_with_gpu_pool):
    """Test that GPU pool is initialized when GPUs are detected."""
    assert docker_backend_with_gpu_pool._gpu_pool is not None
    assert docker_backend_with_gpu_pool._gpu_pool.num_reserved_gpus == 4
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 4


def test_docker_backend_no_gpu_pool_without_gpus(docker_backend_without_gpu_pool):
    """Test that GPU pool is None when no GPUs are detected."""
    assert docker_backend_without_gpu_pool._gpu_pool is None


@pytest.mark.asyncio
async def test_docker_backend_allocates_gpu_from_pool(
    docker_backend_with_gpu_pool, sample_deployment, sample_config, mock_docker_client
):
    """Test that creating a deployment allocates GPUs from the pool."""
    # Setup mock container
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    # Initially all GPUs available
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 4

    await docker_backend_with_gpu_pool.create_model_deployment(sample_deployment, sample_config)
    await drive_creation_to_completion(docker_backend_with_gpu_pool, sample_deployment)

    # One GPU should be allocated
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 3

    # Verify container was created with specific device_ids
    call_args = mock_docker_client.containers.create.call_args_list[0]
    device_requests = call_args[1]["device_requests"]
    assert len(device_requests) == 1
    # Should have driver="nvidia" and specific device_ids (not count)
    assert device_requests[0].driver == "nvidia"
    assert device_requests[0].device_ids is not None
    assert len(device_requests[0].device_ids) == 1


@pytest.mark.asyncio
async def test_docker_backend_fails_without_gpu_pool(
    docker_backend_without_gpu_pool, sample_deployment, sample_config, mock_docker_client
):
    """Test that without GPU pool (no GPUs detected), deployment returns ERROR."""
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    await docker_backend_without_gpu_pool.create_model_deployment(sample_deployment, sample_config)
    status_update = await drive_creation_to_completion(docker_backend_without_gpu_pool, sample_deployment)

    assert status_update.status == "ERROR"
    assert "no gpus available" in status_update.status_message.lower()

    mock_docker_client.containers.create.assert_not_called()


@pytest.mark.asyncio
async def test_docker_backend_releases_gpu_on_delete(
    docker_backend_with_gpu_pool, sample_deployment, sample_config, mock_docker_client
):
    """Test that deleting a deployment releases GPUs back to the pool."""
    # Setup mock container for creation
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_container.stop = MagicMock()
    mock_container.remove = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    # Create deployment and drive to completion - allocates GPU
    await docker_backend_with_gpu_pool.create_model_deployment(sample_deployment, sample_config)
    await drive_creation_to_completion(docker_backend_with_gpu_pool, sample_deployment)
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 3

    # Setup mock for deletion
    mock_docker_client.containers.get.side_effect = None
    mock_docker_client.containers.get.return_value = mock_container

    mock_volume = MagicMock()
    mock_docker_client.volumes.get.side_effect = None
    mock_docker_client.volumes.get.return_value = mock_volume

    # Delete deployment - should release GPU
    await docker_backend_with_gpu_pool.delete_model_deployment(sample_deployment.workspace, sample_deployment.name)

    # GPU should be released back to pool
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 4


@pytest.mark.asyncio
async def test_docker_backend_gpu_allocation_failure(
    docker_backend_with_gpu_pool, sample_deployment, sample_config, mock_docker_client
):
    """Test that deployment fails gracefully when no GPUs are available."""
    # Setup mock container
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    # Allocate all GPUs first
    for i in range(4):
        docker_backend_with_gpu_pool._gpu_pool.allocate_gpu(f"other-workload-{i}", num_requested=1)

    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 0

    # Try to create deployment - GPU allocation failure happens during container creation stage
    await docker_backend_with_gpu_pool.create_model_deployment(sample_deployment, sample_config)
    status_update = await drive_creation_to_completion(docker_backend_with_gpu_pool, sample_deployment)

    assert status_update.status == "ERROR"
    assert "GPU" in status_update.status_message
    assert status_update.error_details["stage"] == "gpu_allocation"


@pytest.mark.asyncio
async def test_docker_backend_releases_gpu_on_port_allocation_failure(
    docker_backend_with_gpu_pool, sample_deployment, sample_config, mock_docker_client
):
    """Test that GPUs are released when port allocation fails after GPU allocation.

    This test verifies the fix for the GPU leak bug where GPUs were allocated
    but not released when subsequent port allocation failed.
    """
    # Setup mocks
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    # Make _find_available_port return None to simulate port exhaustion
    docker_backend_with_gpu_pool._reconciler.find_available_port = AsyncMock(return_value=None)

    # Initial pool should have 4 GPUs available
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 4

    # Try to create deployment - port allocation failure happens during container creation stage
    await docker_backend_with_gpu_pool.create_model_deployment(sample_deployment, sample_config)
    status_update = await drive_creation_to_completion(docker_backend_with_gpu_pool, sample_deployment)

    assert status_update.status == "ERROR"
    assert "port" in status_update.status_message.lower()
    assert status_update.error_details["error"] == "Port allocation failed"

    # Critical: GPU should be released back to the pool (not leaked)
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 4


@pytest.mark.asyncio
async def test_docker_backend_releases_gpu_on_container_creation_failure(
    docker_backend_with_gpu_pool, sample_deployment, sample_config, mock_docker_client
):
    """Test that GPUs are released when container creation fails after GPU allocation.

    This test verifies the fix for the GPU leak bug where GPUs were allocated
    but not released when Docker container creation raised an exception.
    """
    from docker.errors import APIError

    # Setup mocks
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []
    # Make containers.create raise an APIError
    mock_docker_client.containers.create.side_effect = APIError("Docker API error: container creation failed")

    # Initial pool should have 4 GPUs available
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 4

    # Try to create deployment - container creation failure happens during CREATING_CONTAINER stage
    await docker_backend_with_gpu_pool.create_model_deployment(sample_deployment, sample_config)
    status_update = await drive_creation_to_completion(docker_backend_with_gpu_pool, sample_deployment)

    assert status_update.status == "ERROR"
    assert "Docker API error" in status_update.status_message

    # Critical: GPU should be released back to the pool (not leaked)
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 4


@pytest.mark.asyncio
async def test_docker_backend_multi_gpu_allocation(mock_nmp_sdk, mock_docker_client, reset_shared_resource_manager):
    """Test that multi-GPU deployments allocate the correct number of GPUs."""
    platform_config = PlatformConfig(  # type: ignore[abstract]
        files_url="http://files-service:8000",
    )
    with (
        patch("nmp.core.models.controllers.backends.docker.backend.get_platform_config", return_value=platform_config),
        patch("nmp.common.resources.manager.get_platform_config") as mock_resource_config,
        patch("nmp.common.resources.manager.detect_gpu_device_ids") as mock_detect_gpu_device_ids,
    ):
        mock_resource_config.return_value.docker = create_mock_docker_config("0,1,2,3")
        mock_detect_gpu_device_ids.return_value = [0, 1, 2, 3]
        backend = DockerServiceBackend(
            nmp_sdk=mock_nmp_sdk,
            config={},
        )
        backend._client = mock_docker_client

    # Create deployment config requesting 2 GPUs
    multi_gpu_config = MagicMock()
    set_deployment_config(
        multi_gpu_config,
        gpu=2,  # Request 2 GPUs
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",
        image_tag="1.8.6",
        model_name="llama-3.2-1b-instruct",
        model_namespace="meta",
        lora_enabled=False,
        additional_envs=None,
    )

    sample_deployment = MagicMock()
    sample_deployment.workspace = "default"
    sample_deployment.name = "multi-gpu-deployment"
    sample_deployment.entity_version = 1
    sample_deployment.status = "CREATED"

    # Setup mock container
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    await backend.create_model_deployment(sample_deployment, multi_gpu_config)
    await drive_creation_to_completion(backend, sample_deployment)

    # Should have allocated 2 GPUs
    assert backend._gpu_pool.get_available_count() == 2

    # Verify container was created with 2 device_ids
    call_args = mock_docker_client.containers.create.call_args_list[0]
    device_requests = call_args[1]["device_requests"]
    assert len(device_requests[0].device_ids) == 2


# =============================================================================
# Tests for GPU release during get_model_deployment_status
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "container_state",
    [
        pytest.param("exited", id="exited_container"),
        pytest.param("dead", id="dead_container"),
    ],
)
async def test_docker_backend_releases_gpu_on_status_check_terminated(
    docker_backend_with_gpu_pool, sample_deployment, sample_config, mock_docker_client, container_state
):
    """Test that GPUs are released when status check finds container in exited/dead state.

    This ensures that GPU resources are reclaimed when a container has terminated
    unexpectedly and the status check discovers this.
    """
    # Setup mock container for creation
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_container.reload = MagicMock()
    mock_container.logs = MagicMock(return_value=b"Container terminated")
    mock_container.attrs = {"State": {"ExitCode": 1}}
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    # Create deployment and drive to completion - allocates GPU
    await docker_backend_with_gpu_pool.create_model_deployment(sample_deployment, sample_config)
    await drive_creation_to_completion(docker_backend_with_gpu_pool, sample_deployment)
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 3

    # Simulate container in terminated state
    mock_container.status = container_state
    mock_container.ports = {}
    mock_docker_client.containers.get.side_effect = None
    mock_docker_client.containers.get.return_value = mock_container

    # Check status - should release GPU when container is terminated
    status_update = await docker_backend_with_gpu_pool.get_model_deployment_status(sample_deployment)

    # Verify ERROR status returned
    assert status_update.status == "ERROR"
    assert "exited" in status_update.status_message.lower()

    # GPU should be released back to pool
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 4


@pytest.mark.asyncio
async def test_docker_backend_releases_gpu_on_status_check_lost(
    docker_backend_with_gpu_pool, sample_deployment, sample_config, mock_docker_client
):
    """Test that GPUs are released when status check finds container is missing (LOST).

    This ensures that GPU resources are reclaimed when a container has been
    manually deleted or otherwise disappeared.
    """
    # Setup mock container for creation
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    # Create deployment and drive to completion - allocates GPU
    await docker_backend_with_gpu_pool.create_model_deployment(sample_deployment, sample_config)
    await drive_creation_to_completion(docker_backend_with_gpu_pool, sample_deployment)
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 3

    # Simulate container not found (was deleted externally)
    mock_docker_client.containers.get.side_effect = NotFound("Container not found")

    # Check status - should release GPU when container is missing
    status_update = await docker_backend_with_gpu_pool.get_model_deployment_status(sample_deployment)

    # Verify LOST status returned
    assert status_update.status == "LOST"
    assert "not found" in status_update.status_message.lower()

    # GPU should be released back to pool
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 4


@pytest.mark.asyncio
async def test_docker_backend_status_check_does_not_release_gpu_when_running(
    docker_backend_with_gpu_pool, sample_deployment, sample_config, mock_docker_client
):
    """Test that GPUs are NOT released when container is still running.

    This ensures we don't accidentally release GPUs for healthy deployments.
    """
    # Setup mock container for creation
    mock_container = MagicMock()
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_container.reload = MagicMock()
    mock_container.attrs = {"State": {"StartedAt": "2024-01-01T00:00:00Z"}}
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.list.return_value = []

    # Set networking mode to dond for predictable URL
    docker_backend_with_gpu_pool._backend_config.models_docker_networking_mode = "dond"

    # Create deployment and drive to completion - allocates GPU
    await docker_backend_with_gpu_pool.create_model_deployment(sample_deployment, sample_config)
    await drive_creation_to_completion(docker_backend_with_gpu_pool, sample_deployment)
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 3

    # Simulate container still running
    mock_container.status = "running"
    mock_container.ports = {"8000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8000"}]}
    mock_docker_client.containers.get.side_effect = None
    mock_docker_client.containers.get.return_value = mock_container

    # Check status - should NOT release GPU when container is running
    status_update = await docker_backend_with_gpu_pool.get_model_deployment_status(sample_deployment)

    # Verify READY status returned
    assert status_update.status == "READY"

    # GPU should still be allocated (not released)
    assert docker_backend_with_gpu_pool._gpu_pool.get_available_count() == 3


# =============================================================================
# Tests for FILES_SERVICE weights type (non-SFT models with model_name)
# =============================================================================


@pytest.fixture
def multi_llm_config_with_model_name():
    """Create a config for multi-LLM image with model_name (no model entity).

    This simulates the deployment:
        nemo inference deployment-configs create \
            --name "multi-nim-nemotron-nano-9b-config" \
            --nim-deployment '{
                "gpu": 1,
                "image_name": "nvcr.io/nim/nvidia/llm-nim",
                "image_tag": "1.13.1",
                "model_name": "nvidia/NVIDIA-Nemotron-Nano-9B-v2"
            }'
    """
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/nvidia/llm-nim",  # Multi-LLM image
        image_tag="1.13.1",
        model_name="nvidia/NVIDIA-Nemotron-Nano-9B-v2",  # Model name for Files service
        model_namespace=None,  # Namespace is in model_name
        lora_enabled=False,
        additional_envs=None,
    )
    return config


@pytest.mark.asyncio
async def test_multi_llm_files_service_deployment_succeeds(
    docker_backend, mock_docker_client, multi_llm_config_with_model_name
):
    """Test multi-LLM deployment with FILES_SERVICE weights type succeeds (bug #3759).

    Regression test for the scenario:
    - Use multi-LLM image (nvcr.io/nim/nvidia/llm-nim)
    - Provide model_name (nvidia/NVIDIA-Nemotron-Nano-9B-v2)
    - No model entity

    This triggers ModelWeightsType.FILES_SERVICE which was previously not supported.
    """
    # Setup deployment without model entity
    deployment = MagicMock()
    deployment.workspace = "default"
    deployment.name = "nemotron-deployment"
    deployment.entity_version = 1
    deployment.status = "CREATED"

    # Setup mocks for puller and NIM containers
    mock_puller_container = MagicMock()
    mock_puller_container.id = "puller123456789"
    mock_puller_container.wait.return_value = {"StatusCode": 0}
    mock_puller_container.remove = MagicMock()

    mock_nim_container = MagicMock()
    mock_nim_container.id = "nim1234567890ab"
    mock_nim_container.start = MagicMock()

    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.run.return_value = mock_puller_container
    mock_docker_client.containers.create.return_value = mock_nim_container
    mock_docker_client.containers.list.return_value = []

    _setup_puller_mock_for_polling(mock_docker_client, deployment, exit_code=0)

    # No model entity (matches the bug scenario)
    await docker_backend.create_model_deployment(deployment, multi_llm_config_with_model_name, model_entity=None)
    status_update = await drive_creation_to_completion(docker_backend, deployment)

    # Should succeed with PENDING status
    assert status_update.status == "PENDING", (
        f"Expected PENDING but got {status_update.status}: {status_update.status_message}"
    )
    assert "container created" in status_update.status_message.lower()

    # Verify model puller was called
    puller_calls = [
        call
        for call in mock_docker_client.containers.run.call_args_list
        if call[1].get("labels", {}).get("nmp.nvidia.com/container-type") == "model-puller"
    ]
    assert len(puller_calls) == 1, "Model puller should run for multi-LLM FILES_SERVICE deployment"

    # Verify puller used correct model repo (from model_name)
    puller_command = puller_calls[0][1]["command"]
    assert puller_command[0] == "download"
    assert puller_command[1] == "nvidia/NVIDIA-Nemotron-Nano-9B-v2"

    # Verify puller configured for Files service (HF_ENDPOINT)
    puller_env = puller_calls[0][1]["environment"]
    assert "HF_ENDPOINT" in puller_env
    assert "/apis/files/v2/hf" in puller_env["HF_ENDPOINT"]


@pytest.mark.asyncio
async def test_get_model_repo_from_entity_with_files_service(docker_backend, multi_llm_config_with_model_name):
    """Test _get_model_repo_from_entity handles FILES_SERVICE type.

    FILES_SERVICE (non-SFT) should extract model_name from nim_config.
    """
    from nmp.core.models.app import ModelWeightsType

    # Model entity with fileset but no PEFT (non-SFT)
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-model"
    model_entity.spec = None
    model_entity.peft = None
    model_entity.fileset = "hf://workspace/fileset"

    # Should succeed with FILES_SERVICE (previously raised ValueError)
    model_repo = docker_backend._reconciler._get_model_repo_from_entity(
        model_entity=model_entity,
        model_weights_type=ModelWeightsType.FILES_SERVICE,
        nim_config=multi_llm_config_with_model_name.model_spec,
    )

    # Should extract from fileset when available
    assert model_repo == "workspace/fileset"


@pytest.mark.asyncio
async def test_get_model_repo_from_entity_files_service_uses_nim_config_when_no_artifact(
    docker_backend, multi_llm_config_with_model_name
):
    """Test _get_model_repo_from_entity falls back to nim_config for FILES_SERVICE.

    When model_entity has no fileset, should use model_name from nim_config.
    """
    from nmp.core.models.app import ModelWeightsType

    # Model entity without fileset
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-model"
    model_entity.spec = None
    model_entity.peft = None
    model_entity.fileset = None  # No fileset

    # Should fall back to nim_config.model_name
    model_repo = docker_backend._reconciler._get_model_repo_from_entity(
        model_entity=model_entity,
        model_weights_type=ModelWeightsType.FILES_SERVICE,
        nim_config=multi_llm_config_with_model_name.model_spec,
    )

    assert model_repo == "nvidia/NVIDIA-Nemotron-Nano-9B-v2"


@pytest.mark.asyncio
async def test_get_model_repo_from_entity_files_service_no_entity_uses_nim_config(
    docker_backend, multi_llm_config_with_model_name
):
    """Test _get_model_repo_from_entity uses nim_config when no entity for FILES_SERVICE."""
    from nmp.core.models.app import ModelWeightsType

    # No model entity at all
    model_repo = docker_backend._reconciler._get_model_repo_from_entity(
        model_entity=None,
        model_weights_type=ModelWeightsType.FILES_SERVICE,
        nim_config=multi_llm_config_with_model_name.model_spec,
    )

    assert model_repo == "nvidia/NVIDIA-Nemotron-Nano-9B-v2"


@pytest.mark.asyncio
async def test_multi_llm_huggingface_deployment_succeeds_with_hf_token(
    docker_backend, mock_docker_client, mock_nmp_sdk
):
    """Test multi-LLM deployment with HuggingFace token succeeds (bug #3716).

    Regression test for the scenario from docs/run-inference/tutorials/deploy-models.md:
    - Omit image_name to auto-select multi-LLM image
    - Provide hf_token_secret_name for HuggingFace authentication
    - No model entity (deploying directly from HuggingFace)

    Before the fix, this failed with "ModelWeightsType.UNKNOWN is not supported"
    because get_model_weights_type() was called without deployment/config context.
    """
    # Setup deployment with HF token (matches docs example)
    deployment = MagicMock()
    deployment.workspace = "default"
    deployment.name = "qwen-deployment"
    deployment.entity_version = 1
    deployment.status = "CREATED"
    deployment.hf_token_secret_name = "hf-token-secret"  # KEY: HF token provided

    # Config without image_name (multi-LLM) but with model_name (matches docs)
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name=None,  # KEY: Omitted to use multi-LLM
        image_tag=None,
        model_name="Qwen2.5-1.5B-Instruct",
        model_namespace="Qwen",
        lora_enabled=False,
        additional_envs=None,
    )

    # Setup mocks for puller and NIM containers
    mock_puller_container = MagicMock()
    mock_puller_container.id = "puller123456789"
    mock_puller_container.wait.return_value = {"StatusCode": 0}
    mock_puller_container.remove = MagicMock()

    mock_nim_container = MagicMock()
    mock_nim_container.id = "nim1234567890ab"
    mock_nim_container.start = MagicMock()

    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.create.return_value = mock_nim_container
    mock_docker_client.containers.list.return_value = []

    _setup_puller_mock_for_polling(mock_docker_client, deployment, exit_code=0)

    await docker_backend.create_model_deployment(deployment, config, model_entity=None)
    status_update = await drive_creation_to_completion(docker_backend, deployment)

    assert status_update.status == "PENDING", (
        f"Expected PENDING but got {status_update.status}: {status_update.status_message}"
    )
    assert "container created" in status_update.status_message.lower()

    puller_calls = [
        call
        for call in mock_docker_client.containers.run.call_args_list
        if call[1].get("labels", {}).get("nmp.nvidia.com/container-type") == "model-puller"
    ]
    assert len(puller_calls) == 1

    puller_command = puller_calls[0][1]["command"]
    assert puller_command[0] == "download"
    assert "Qwen" in puller_command[1]


# ============================================================================
# GPU Cleanup for Drift Recovery Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_releases_stale_gpu_allocation_single(
    docker_backend, sample_deployment, sample_config, mock_docker_client
):
    """Test that create_model_deployment releases stale GPU allocation for single GPU."""
    from nmp.common.docker.gpu_pool import DockerGPUPool

    # Create a real GPU pool with 2 GPUs
    gpu_pool = DockerGPUPool(reserved_gpu_device_ids=[0, 1])
    docker_backend._gpu_pool = gpu_pool
    docker_backend._reconciler._gpu_pool = gpu_pool

    # Pre-allocate GPU 0 to this deployment (simulating stale allocation from lost container)
    deployment_key = f"{sample_deployment.workspace}/{sample_deployment.name}"
    gpu_pool.allocate_gpu(deployment_key, num_requested=1)

    # Verify GPU is allocated
    assert gpu_pool.get_available_count() == 1
    allocated = gpu_pool.get_allocated_workloads()
    assert deployment_key in allocated.values()

    # Setup mock container
    mock_container = MagicMock()
    docker_backend._backend_config.models_docker_networking_mode = "dond"
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.containers.list.return_value = []

    # Create deployment and drive to completion (should release stale allocation first, then reallocate)
    await docker_backend.create_model_deployment(sample_deployment, sample_config, None)
    status_update = await drive_creation_to_completion(docker_backend, sample_deployment)

    assert status_update.status == "PENDING"

    # Verify GPU is still allocated (released then reallocated)
    assert gpu_pool.get_available_count() == 1
    allocated = gpu_pool.get_allocated_workloads()
    assert deployment_key in allocated.values()


@pytest.mark.asyncio
async def test_create_releases_stale_gpu_allocation_multi(docker_backend, sample_deployment, mock_docker_client):
    """Test that create_model_deployment releases stale GPU allocation for multiple GPUs."""
    from nmp.common.docker.gpu_pool import DockerGPUPool

    gpu_pool = DockerGPUPool(reserved_gpu_device_ids=[0, 1, 2, 3])
    docker_backend._gpu_pool = gpu_pool
    docker_backend._reconciler._gpu_pool = gpu_pool

    deployment_key = f"{sample_deployment.workspace}/{sample_deployment.name}"
    gpu_pool.allocate_gpu(deployment_key, num_requested=2)
    assert gpu_pool.get_available_count() == 2

    config = MagicMock()
    set_deployment_config(
        config,
        gpu=2,
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",
        image_tag="1.8.6",
        model_name="llama-3.2-1b-instruct",
        model_namespace="meta",
        lora_enabled=False,
        additional_envs=None,
    )

    mock_container = MagicMock()
    docker_backend._backend_config.models_docker_networking_mode = "dond"
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.containers.list.return_value = []

    await docker_backend.create_model_deployment(sample_deployment, config, None)
    status_update = await drive_creation_to_completion(docker_backend, sample_deployment)

    assert status_update.status == "PENDING"
    assert gpu_pool.get_available_count() == 2
    allocated = gpu_pool.get_allocated_workloads()
    assert list(allocated.values()).count(deployment_key) == 2


@pytest.mark.asyncio
async def test_create_without_stale_allocation_succeeds(
    docker_backend, sample_deployment, sample_config, mock_docker_client
):
    """Test that create_model_deployment works when there's no stale allocation."""
    from nmp.common.docker.gpu_pool import DockerGPUPool

    gpu_pool = DockerGPUPool(reserved_gpu_device_ids=[0, 1])
    docker_backend._gpu_pool = gpu_pool
    docker_backend._reconciler._gpu_pool = gpu_pool
    assert gpu_pool.get_available_count() == 2

    mock_container = MagicMock()
    docker_backend._backend_config.models_docker_networking_mode = "dond"
    mock_container.id = "1234567890abcdef"
    mock_container.start = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container
    mock_docker_client.containers.list.return_value = []

    await docker_backend.create_model_deployment(sample_deployment, sample_config, None)
    status_update = await drive_creation_to_completion(docker_backend, sample_deployment)

    assert status_update.status == "PENDING"

    deployment_key = f"{sample_deployment.workspace}/{sample_deployment.name}"
    assert gpu_pool.get_available_count() == 1
    allocated = gpu_pool.get_allocated_workloads()
    assert deployment_key in allocated.values()


# ============================================================================
# Tool Call Config & Chat Template — _compile_env_vars Tests
# ============================================================================


@pytest.mark.asyncio
async def test_compile_env_vars_model_entity_chat_template(docker_backend, sample_deployment, sample_config):
    """Test that chat_template from model entity spec sets NIM_CHAT_TEMPLATE."""
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-model"
    model_entity.spec = MagicMock()
    model_entity.spec.chat_template = "{% for msg in messages %}{{ msg.role }}{% endfor %}"
    model_entity.spec.tool_call_config = None

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        sample_config,
        model_entity=model_entity,
        is_multi_llm=False,
    )

    assert env_vars["NIM_CHAT_TEMPLATE"] == "{% for msg in messages %}{{ msg.role }}{% endfor %}"
    assert "NIM_TOOL_PARSER_PLUGIN" not in env_vars
    assert "NIM_ENABLE_AUTO_TOOL_CHOICE" not in env_vars


@pytest.mark.asyncio
async def test_compile_env_vars_model_entity_tool_call_config(docker_backend, sample_deployment, sample_config):
    """Test that tool_call_config from model entity spec sets NIM env vars."""
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-model"
    model_entity.spec = MagicMock()
    model_entity.spec.chat_template = None
    model_entity.spec.tool_call_config = MagicMock()
    model_entity.spec.tool_call_config.tool_call_parser = "hermes"
    model_entity.spec.tool_call_config.tool_call_plugin = None
    model_entity.spec.tool_call_config.auto_tool_choice = True

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        sample_config,
        model_entity=model_entity,
        is_multi_llm=False,
    )

    assert "NIM_CHAT_TEMPLATE" not in env_vars
    assert env_vars["NIM_TOOL_CALL_PARSER"] == "hermes"
    assert env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] == "1"
    assert "NIM_TOOL_PARSER_PLUGIN" not in env_vars


@pytest.mark.asyncio
async def test_compile_env_vars_auto_tool_choice_false(docker_backend, sample_deployment, sample_config):
    """Test that auto_tool_choice=False does NOT set NIM_ENABLE_AUTO_TOOL_CHOICE from model entity."""
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-model"
    model_entity.spec = MagicMock()
    model_entity.spec.chat_template = None
    model_entity.spec.tool_call_config = MagicMock()
    model_entity.spec.tool_call_config.tool_call_parser = None
    model_entity.spec.tool_call_config.tool_call_plugin = None
    model_entity.spec.tool_call_config.auto_tool_choice = False

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        sample_config,
        model_entity=model_entity,
        is_multi_llm=False,
    )

    # auto_tool_choice=False explicitly disables auto tool choice
    assert env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] == "0"
    assert "NIM_TOOL_CALL_PARSER" not in env_vars
    assert "NIM_TOOL_PARSER_PLUGIN" not in env_vars
    assert "NIM_CHAT_TEMPLATE" not in env_vars


@pytest.mark.asyncio
async def test_compile_env_vars_tool_call_plugin_path(docker_backend, sample_deployment, sample_config):
    """Test that tool_call_plugin_path sets NIM_TOOL_PARSER_PLUGIN."""
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-model"
    model_entity.spec = MagicMock()
    model_entity.spec.chat_template = None
    model_entity.spec.tool_call_config = MagicMock()
    model_entity.spec.tool_call_config.tool_call_parser = "pythonic"
    model_entity.spec.tool_call_config.tool_call_plugin = "ws/my-plugin"
    model_entity.spec.tool_call_config.auto_tool_choice = None

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        sample_config,
        model_entity=model_entity,
        is_multi_llm=False,
        tool_call_plugin_path="/model-store/tool_call_plugin/custom.py",
    )

    assert env_vars["NIM_TOOL_CALL_PARSER"] == "pythonic"
    assert env_vars["NIM_TOOL_PARSER_PLUGIN"] == "/model-store/tool_call_plugin/custom.py"
    assert "NIM_CHAT_TEMPLATE" not in env_vars
    assert "NIM_ENABLE_AUTO_TOOL_CHOICE" not in env_vars


@pytest.mark.asyncio
async def test_compile_env_vars_no_spec_no_tool_vars(docker_backend, sample_deployment, sample_config):
    """When model entity has no spec, no tool call env vars should be set."""
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-model"
    model_entity.spec = None

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        sample_config,
        model_entity=model_entity,
        is_multi_llm=False,
    )

    assert "NIM_CHAT_TEMPLATE" not in env_vars
    assert "NIM_TOOL_CALL_PARSER" not in env_vars
    assert "NIM_TOOL_PARSER_PLUGIN" not in env_vars
    assert "NIM_ENABLE_AUTO_TOOL_CHOICE" not in env_vars


# ============================================================================
# Deployment-level Overrides — _compile_env_vars Tests
# ============================================================================


@pytest.mark.asyncio
async def test_compile_env_vars_deployment_overrides_model_entity(docker_backend, sample_deployment):
    """Deployment-level chat_template/tool_call_config override model entity spec."""
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",
        image_tag="1.8.6",
        model_name="llama-3.2-1b-instruct",
        model_namespace="meta",
        lora_enabled=False,
        additional_envs=None,
        chat_template="deployment-template",
        tool_call_config={
            "tool_call_parser": "openai",
            "auto_tool_choice": True,
        },
    )

    # Model entity also has spec values (should be overridden)
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-model"
    model_entity.spec = MagicMock()
    model_entity.spec.chat_template = "entity-template"
    model_entity.spec.tool_call_config = MagicMock()
    model_entity.spec.tool_call_config.tool_call_parser = "hermes"
    model_entity.spec.tool_call_config.tool_call_plugin = None
    model_entity.spec.tool_call_config.auto_tool_choice = False

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        config,
        model_entity=model_entity,
        is_multi_llm=False,
    )

    # Deployment-level should win
    assert env_vars["NIM_CHAT_TEMPLATE"] == "deployment-template"
    assert env_vars["NIM_TOOL_CALL_PARSER"] == "openai"
    assert env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] == "1"


@pytest.mark.asyncio
async def test_compile_env_vars_deployment_auto_tool_choice_false_overrides(docker_backend, sample_deployment):
    """Deployment auto_tool_choice=False overrides entity's True."""
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",
        image_tag="1.8.6",
        model_name="llama-3.2-1b-instruct",
        model_namespace="meta",
        lora_enabled=False,
        additional_envs=None,
        tool_call_config={"auto_tool_choice": False},
    )

    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-model"
    model_entity.spec = MagicMock()
    model_entity.spec.chat_template = None
    model_entity.spec.tool_call_config = MagicMock()
    model_entity.spec.tool_call_config.tool_call_parser = None
    model_entity.spec.tool_call_config.tool_call_plugin = None
    model_entity.spec.tool_call_config.auto_tool_choice = True

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        config,
        model_entity=model_entity,
        is_multi_llm=False,
    )

    # Deployment False should override entity True → "0"
    assert env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] == "0"


@pytest.mark.asyncio
async def test_compile_env_vars_deployment_only_no_entity(docker_backend, sample_deployment):
    """Deployment-level config sets env vars even without a model entity."""
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",
        image_tag="1.8.6",
        model_name="llama-3.2-1b-instruct",
        model_namespace="meta",
        lora_enabled=False,
        additional_envs=None,
        chat_template="dep-tmpl",
        tool_call_config={"tool_call_parser": "mistral", "auto_tool_choice": True},
    )

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        config,
        model_entity=None,
        is_multi_llm=False,
    )

    assert env_vars["NIM_CHAT_TEMPLATE"] == "dep-tmpl"
    assert env_vars["NIM_TOOL_CALL_PARSER"] == "mistral"
    assert env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] == "1"


# ============================================================================
# Chat Template & Tool Call Config — Scenario-Based Tests
#
# These 7 scenarios mirror test_chat_template_tool_calling.py and verify
# that _compile_env_vars produces the correct NIM_* environment variables
# for every combination of model entity spec and deployment-level config.
# ============================================================================


@pytest.mark.asyncio
async def test_scenario1_fileset_custom_fields_only(docker_backend, sample_deployment, sample_config):
    """Scenario 1: chat_template + tool_call_config from model entity spec only.

    Simulates fileset custom_fields being merged into model spec by the
    model spec task.  NIMDeployment has no overrides.
    """
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "llama-3-2-1b-instruct-fileset-only"
    model_entity.trust_remote_code = False
    model_entity.spec = MagicMock()
    model_entity.spec.chat_template = (
        "{%- set loop_messages = messages %}"
        "{%- for message in loop_messages %}"
        "{%- set content = '<|start_header_id|>' + message['role'] + '<|end_header_id|>\\n\\n'"
        " + message['content'] | trim + '<|eot_id|>' %}"
        "{%- if loop.index0 == 0 %}{%- set content = '<|begin_of_text|>' + content %}{%- endif %}"
        "{{ content }}{%- endfor %}"
        "{%- if add_generation_prompt %}{{ '<|start_header_id|>assistant<|end_header_id|>\\n\\n' }}{%- endif %}"
    )
    model_entity.spec.tool_call_config = MagicMock()
    model_entity.spec.tool_call_config.tool_call_parser = "llama3_json"
    model_entity.spec.tool_call_config.tool_call_plugin = None
    model_entity.spec.tool_call_config.auto_tool_choice = True

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        sample_config,
        model_entity=model_entity,
        is_multi_llm=True,
    )

    assert env_vars["NIM_CHAT_TEMPLATE"] == model_entity.spec.chat_template
    assert env_vars["NIM_TOOL_CALL_PARSER"] == "llama3_json"
    assert env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] == "1"
    assert "NIM_TOOL_PARSER_PLUGIN" not in env_vars


@pytest.mark.asyncio
async def test_scenario2_deployment_config_only(docker_backend, sample_deployment):
    """Scenario 2: chat_template + tool_call_config from NIMDeployment only.

    Fileset has no custom_fields, model entity spec has nothing.
    Both values come entirely from the deployment config.
    """
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",
        image_tag="1.8.6",
        model_name="llama-3.2-1b-instruct",
        model_namespace="meta",
        lora_enabled=False,
        additional_envs=None,
        chat_template="{%- for message in messages %}{{ message.role }}{% endfor %}",
        tool_call_config={
            "tool_call_parser": "openai",
            "auto_tool_choice": True,
        },
    )

    # Model entity has no spec values
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "llama-3-2-1b-instruct-deploy-only"
    model_entity.trust_remote_code = False
    model_entity.spec = None

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        config,
        model_entity=model_entity,
        is_multi_llm=True,
    )

    assert env_vars["NIM_CHAT_TEMPLATE"] == "{%- for message in messages %}{{ message.role }}{% endfor %}"
    assert env_vars["NIM_TOOL_CALL_PARSER"] == "openai"
    assert env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] == "1"
    assert "NIM_TOOL_PARSER_PLUGIN" not in env_vars


@pytest.mark.asyncio
async def test_scenario3_both_deployment_wins(docker_backend, sample_deployment):
    """Scenario 3: Both model entity spec and NIMDeployment set values.

    Deployment-level overrides should take precedence over model entity spec.
    """
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",
        image_tag="1.8.6",
        model_name="llama-3.2-1b-instruct",
        model_namespace="meta",
        lora_enabled=False,
        additional_envs=None,
        chat_template=(
            "{% for message in messages %}"
            "{{ '<|im_start|>' + message['role'] + '\\n' + message['content'] + '<|im_end|>\\n' }}"
            "{% endfor %}"
            "{% if add_generation_prompt %}{{ '<|im_start|>assistant\\n' }}{% endif %}"
        ),
        tool_call_config={
            "tool_call_parser": "openai",
            "auto_tool_choice": True,
        },
    )

    # Model entity has different values (should be overridden by deployment)
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "llama-3-2-1b-instruct-both-override"
    model_entity.trust_remote_code = False
    model_entity.spec = MagicMock()
    model_entity.spec.chat_template = "entity-llama-template"
    model_entity.spec.tool_call_config = MagicMock()
    model_entity.spec.tool_call_config.tool_call_parser = "llama3_json"
    model_entity.spec.tool_call_config.tool_call_plugin = None
    model_entity.spec.tool_call_config.auto_tool_choice = False

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        config,
        model_entity=model_entity,
        is_multi_llm=True,
    )

    # Deployment-level values should win
    assert env_vars["NIM_CHAT_TEMPLATE"] == config.model_spec.chat_template
    assert env_vars["NIM_TOOL_CALL_PARSER"] == "openai"
    assert env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] == "1"
    assert "NIM_TOOL_PARSER_PLUGIN" not in env_vars


@pytest.mark.asyncio
async def test_scenario4_baseline_nothing_set(docker_backend, sample_deployment, sample_config):
    """Scenario 4: No chat_template or tool_call_config anywhere.

    NIM uses its built-in defaults from the tokenizer.
    None of the tool-calling env vars should be present.
    """
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "llama-3-2-1b-instruct-baseline"
    model_entity.trust_remote_code = False
    model_entity.spec = MagicMock()
    model_entity.spec.chat_template = None
    model_entity.spec.tool_call_config = None

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        sample_config,
        model_entity=model_entity,
        is_multi_llm=True,
    )

    assert "NIM_CHAT_TEMPLATE" not in env_vars
    assert "NIM_TOOL_CALL_PARSER" not in env_vars
    assert "NIM_TOOL_PARSER_PLUGIN" not in env_vars
    assert "NIM_ENABLE_AUTO_TOOL_CHOICE" not in env_vars


@pytest.mark.asyncio
async def test_scenario5_mixed_fileset_chat_template_deploy_tool_config(docker_backend, sample_deployment):
    """Scenario 5: chat_template from model entity spec, tool_call_config from deployment.

    Tests that individual fields can come from different layers.
    """
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",
        image_tag="1.8.6",
        model_name="llama-3.2-1b-instruct",
        model_namespace="meta",
        lora_enabled=False,
        additional_envs=None,
        # No chat_template at deployment level
        tool_call_config={
            "tool_call_parser": "hermes",
            "auto_tool_choice": True,
        },
    )

    # Model entity has chat_template but no tool_call_config
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "llama-3-2-1b-instruct-mixed"
    model_entity.trust_remote_code = False
    model_entity.spec = MagicMock()
    model_entity.spec.chat_template = "llama-template-from-fileset"
    model_entity.spec.tool_call_config = None

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        config,
        model_entity=model_entity,
        is_multi_llm=True,
    )

    # chat_template from model entity, tool config from deployment
    assert env_vars["NIM_CHAT_TEMPLATE"] == "llama-template-from-fileset"
    assert env_vars["NIM_TOOL_CALL_PARSER"] == "hermes"
    assert env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] == "1"
    assert "NIM_TOOL_PARSER_PLUGIN" not in env_vars


@pytest.mark.asyncio
async def test_scenario6_plugin_from_model_entity_spec(docker_backend, sample_deployment, sample_config):
    """Scenario 6: tool_call_plugin fileset reference in model entity spec.

    The plugin puller has already discovered the .py file and passed
    its path via tool_call_plugin_path.
    """
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "llama-3-2-1b-instruct-plugin"
    model_entity.trust_remote_code = False
    model_entity.spec = MagicMock()
    model_entity.spec.chat_template = "llama-chat-template"
    model_entity.spec.tool_call_config = MagicMock()
    model_entity.spec.tool_call_config.tool_call_parser = "pythonic"
    model_entity.spec.tool_call_config.tool_call_plugin = "default/my-tool-plugin"
    model_entity.spec.tool_call_config.auto_tool_choice = True

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        sample_config,
        model_entity=model_entity,
        is_multi_llm=True,
        tool_call_plugin_path="/model-store/tool_call_plugin/my_plugin.py",
    )

    assert env_vars["NIM_CHAT_TEMPLATE"] == "llama-chat-template"
    assert env_vars["NIM_TOOL_CALL_PARSER"] == "pythonic"
    assert env_vars["NIM_TOOL_PARSER_PLUGIN"] == "/model-store/tool_call_plugin/my_plugin.py"
    assert env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] == "1"


@pytest.mark.asyncio
async def test_scenario7_plugin_from_deployment_config(docker_backend, sample_deployment):
    """Scenario 7: chat_template + tool_call_config (including tool_call_plugin)
    set entirely from the deployment config, bypassing model entity spec.

    The plugin puller has already discovered the .py file path.
    """
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",
        image_tag="1.8.6",
        model_name="llama-3.2-1b-instruct",
        model_namespace="meta",
        lora_enabled=False,
        additional_envs=None,
        chat_template="llama-deploy-template",
        tool_call_config={
            "tool_call_parser": "pythonic",
            "tool_call_plugin": "default/my-tool-plugin",
            "auto_tool_choice": True,
        },
    )

    # Model entity has no spec (spec not yet populated, or no custom_fields)
    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "llama-3-2-1b-instruct-plugin-deploy"
    model_entity.trust_remote_code = False
    model_entity.spec = None

    env_vars = await docker_backend._reconciler._compile_env_vars(
        sample_deployment,
        config,
        model_entity=model_entity,
        is_multi_llm=True,
        tool_call_plugin_path="/model-store/tool_call_plugin/my_plugin.py",
    )

    assert env_vars["NIM_CHAT_TEMPLATE"] == "llama-deploy-template"
    assert env_vars["NIM_TOOL_CALL_PARSER"] == "pythonic"
    assert env_vars["NIM_TOOL_PARSER_PLUGIN"] == "/model-store/tool_call_plugin/my_plugin.py"
    assert env_vars["NIM_ENABLE_AUTO_TOOL_CHOICE"] == "1"


# ============================================================================
# Plugin Puller Tests
# ============================================================================


@pytest.mark.asyncio
async def test_plugin_puller_success(docker_backend, sample_deployment, mock_docker_client):
    """Test _run_plugin_puller discovers a single .py file and returns its path."""
    volume_name = "nim-cache-default-test-deployment"

    # Mock puller container
    mock_puller_container = MagicMock()
    mock_puller_container.id = "pluginpuller1234"
    mock_puller_container.wait.return_value = {"StatusCode": 0}
    mock_puller_container.remove = MagicMock()

    # containers.run is called for: busybox mkdir, puller, busybox chown, busybox find
    mock_docker_client.containers.run.side_effect = [
        None,  # busybox mkdir
        mock_puller_container,  # puller
        None,  # busybox chown
        b"/model-store/tool_call_plugin/my_plugin.py\n",  # busybox find
    ]
    mock_docker_client.images.get.return_value = MagicMock()

    plugin_path, error = await docker_backend._reconciler._run_plugin_puller(
        deployment=sample_deployment,
        fileset_ref="workspace/my-tool-plugin",
        volume_name=volume_name,
        target_subdir="tool_call_plugin",
    )

    assert error is None
    assert plugin_path == "/model-store/tool_call_plugin/my_plugin.py"


@pytest.mark.asyncio
async def test_plugin_puller_no_py_files(docker_backend, sample_deployment, mock_docker_client):
    """Test _run_plugin_puller returns error when no .py files found."""
    volume_name = "nim-cache-default-test-deployment"

    mock_puller_container = MagicMock()
    mock_puller_container.id = "pluginpuller1234"
    mock_puller_container.wait.return_value = {"StatusCode": 0}
    mock_puller_container.remove = MagicMock()

    mock_docker_client.containers.run.side_effect = [
        None,  # busybox mkdir
        mock_puller_container,  # puller
        None,  # busybox chown
        b"\n",  # busybox find (empty result)
    ]
    mock_docker_client.images.get.return_value = MagicMock()

    plugin_path, error = await docker_backend._reconciler._run_plugin_puller(
        deployment=sample_deployment,
        fileset_ref="workspace/empty-plugin",
        volume_name=volume_name,
    )

    assert plugin_path is None
    assert "no .py files" in error


@pytest.mark.asyncio
async def test_plugin_puller_multiple_py_files(docker_backend, sample_deployment, mock_docker_client):
    """Test _run_plugin_puller returns error when multiple .py files found."""
    volume_name = "nim-cache-default-test-deployment"

    mock_puller_container = MagicMock()
    mock_puller_container.id = "pluginpuller1234"
    mock_puller_container.wait.return_value = {"StatusCode": 0}
    mock_puller_container.remove = MagicMock()

    mock_docker_client.containers.run.side_effect = [
        None,
        mock_puller_container,
        None,
        b"/model-store/tool_call_plugin/a.py\n/model-store/tool_call_plugin/b.py\n",
    ]
    mock_docker_client.images.get.return_value = MagicMock()

    plugin_path, error = await docker_backend._reconciler._run_plugin_puller(
        deployment=sample_deployment,
        fileset_ref="workspace/multi-plugin",
        volume_name=volume_name,
    )

    assert plugin_path is None
    assert "2 .py files" in error


@pytest.mark.asyncio
async def test_plugin_puller_container_fails(docker_backend, sample_deployment, mock_docker_client):
    """Test _run_plugin_puller returns error when puller container exits with non-zero."""
    volume_name = "nim-cache-default-test-deployment"

    mock_puller_container = MagicMock()
    mock_puller_container.id = "pluginpuller1234"
    mock_puller_container.wait.return_value = {"StatusCode": 1}
    mock_puller_container.logs.return_value = b"download failed"
    mock_puller_container.remove = MagicMock()

    mock_docker_client.containers.run.side_effect = [
        None,
        mock_puller_container,
    ]
    mock_docker_client.images.get.return_value = MagicMock()

    plugin_path, error = await docker_backend._reconciler._run_plugin_puller(
        deployment=sample_deployment,
        fileset_ref="workspace/bad-plugin",
        volume_name=volume_name,
    )

    assert plugin_path is None
    assert error is not None
    assert "exit code 1" in error.lower() or "failed" in error.lower()


# ============================================================================
# End-to-end: create_model_deployment with tool_call_config
# ============================================================================


@pytest.mark.asyncio
async def test_create_deployment_with_tool_call_plugin_from_entity(
    docker_backend, sample_deployment, mock_docker_client
):
    """Test that create_model_deployment pulls tool_call_plugin fileset from model entity spec."""
    config = MagicMock()
    set_deployment_config(
        config,
        gpu=1,
        disk_size="50Gi",
        image_name="nvcr.io/nim/meta/llama-3.2-1b-instruct",
        image_tag="1.8.6",
        model_name="llama-3.2-1b-instruct",
        model_namespace="meta",
        lora_enabled=False,
        additional_envs=None,
    )

    model_entity = MagicMock()
    model_entity.workspace = "default"
    model_entity.name = "test-model"
    model_entity.spec = MagicMock()
    model_entity.spec.chat_template = None
    model_entity.spec.tool_call_config = MagicMock()
    model_entity.spec.tool_call_config.tool_call_parser = "hermes"
    model_entity.spec.tool_call_config.tool_call_plugin = "ws/my-tool-fileset"
    model_entity.spec.tool_call_config.auto_tool_choice = True
    model_entity.peft = None
    model_entity.fileset = None
    model_entity.finetuning_type = None

    # Setup mock containers
    mock_puller_container = MagicMock()
    mock_puller_container.id = "pluginpuller1234"
    mock_puller_container.wait.return_value = {"StatusCode": 0}
    mock_puller_container.remove = MagicMock()

    mock_nim_container = MagicMock()
    mock_nim_container.id = "nim1234567890ab"
    mock_nim_container.start = MagicMock()

    mock_docker_client.images.get.return_value = MagicMock()
    mock_docker_client.containers.run.side_effect = [
        None,  # busybox mkdir
        mock_puller_container,  # plugin puller
        None,  # busybox chown
        b"/model-store/tool_call_plugin/tool.py\n",  # busybox find
    ]
    mock_docker_client.containers.create.return_value = mock_nim_container
    mock_docker_client.containers.list.return_value = []

    await docker_backend.create_model_deployment(sample_deployment, config, model_entity)
    status_update = await drive_creation_to_completion(docker_backend, sample_deployment)

    assert status_update.status == "PENDING"

    # Verify the NIM container was created with the right env vars
    create_call = mock_docker_client.containers.create.call_args
    nim_env = create_call[1]["environment"]
    assert nim_env["NIM_TOOL_CALL_PARSER"] == "hermes"
    assert nim_env["NIM_TOOL_PARSER_PLUGIN"] == "/model-store/tool_call_plugin/tool.py"
    assert nim_env["NIM_ENABLE_AUTO_TOOL_CHOICE"] == "1"


# ============================================================================
# PENDING Timeout and Crash Loop Detection Tests
# ============================================================================


@pytest.fixture
def make_mock_container(docker_backend, mock_docker_client):
    """Factory to create a mock container wired into the docker backend for status tests.

    Handles the boilerplate of creating a MagicMock container, setting sensible
    attrs for the given state, wiring it into ``mock_docker_client.containers.get``,
    and switching the backend to "dond" networking mode.
    """

    def _make(
        status="running",
        restart_count=0,
        logs=None,
        exit_code=None,
    ):
        container = MagicMock()
        container.status = status
        container.id = "1234567890abcdef"
        container.ports = {}
        container.reload = MagicMock()

        if status == "running":
            container.attrs = {
                "State": {"StartedAt": "2024-01-01T00:00:00Z"},
                "RestartCount": restart_count,
            }
        elif status in ("exited", "dead"):
            container.attrs = {"State": {"ExitCode": exit_code if exit_code is not None else 1}}
        else:
            container.attrs = {"RestartCount": restart_count}

        if logs is not None:
            container.logs = MagicMock(return_value=logs)

        mock_docker_client.containers.get.side_effect = None
        mock_docker_client.containers.get.return_value = container
        docker_backend._backend_config.models_docker_networking_mode = "dond"

        return container

    return _make


class TestPendingTimeoutStatusTransition:
    """Tests for PENDING -> ERROR transition after timeout."""

    @pytest.mark.asyncio
    async def test_running_not_healthy_within_timeout_returns_pending(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """A running container that isn't healthy should return PENDING with timing info."""
        make_mock_container(status="running")

        with patch.object(docker_backend, "_probe_nim_health", new_callable=AsyncMock) as mock_probe:
            mock_probe.return_value = (False, "connection refused")
            status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "PENDING"
        assert "still initializing" in status.status_message
        # No elapsed/timeout in message (stable message to avoid new history entry every poll)

    @pytest.mark.asyncio
    async def test_running_not_healthy_exceeds_timeout_returns_error(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """A running container that isn't healthy and exceeds timeout should transition to ERROR."""
        make_mock_container(status="running", logs=b"NIM failed to start: model not supported")
        docker_backend._backend_config.pending_timeout_seconds = 7200
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(hours=3)

        with patch.object(docker_backend, "_probe_nim_health", new_callable=AsyncMock) as mock_probe:
            mock_probe.return_value = (False, "connection refused")
            status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "ERROR"
        assert "timed out" in status.status_message
        assert "docker logs" in status.status_message
        assert "md-default-test-deployment" in status.status_message
        assert status.error_details["reason"] == "pending_timeout"
        assert status.error_details["container_name"] == "md-default-test-deployment"

    @pytest.mark.asyncio
    async def test_created_state_within_timeout_returns_pending(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """A container in 'created' state should return PENDING with timing info."""
        make_mock_container(status="created")

        status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "PENDING"
        assert "starting up" in status.status_message
        # No elapsed/timeout in message (stable message to avoid new history entry every poll)

    @pytest.mark.asyncio
    async def test_restarting_state_within_timeout_returns_pending_with_restart_count(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """A container in 'restarting' state should include restart count."""
        make_mock_container(status="restarting", restart_count=3)

        status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "PENDING"
        assert "restart count: 3" in status.status_message
        # No elapsed/timeout in message (stable message to avoid new history entry every poll)

    @pytest.mark.asyncio
    async def test_restarting_state_exceeds_timeout_returns_error(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """A container in 'restarting' state that exceeds timeout should transition to ERROR."""
        make_mock_container(status="restarting", restart_count=3, logs=b"Segfault in model loading")
        docker_backend._backend_config.pending_timeout_seconds = 3600
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(hours=2)

        status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "ERROR"
        assert "timed out" in status.status_message
        assert "docker logs" in status.status_message
        assert status.error_details["reason"] == "pending_timeout"
        assert status.error_details["container_state"] == "restarting"

    @pytest.mark.asyncio
    async def test_ready_returns_ready_status(self, docker_backend, sample_deployment, make_mock_container):
        """A healthy container should return READY."""
        make_mock_container(status="running")

        status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "READY"

    @pytest.mark.asyncio
    async def test_exited_returns_error(self, docker_backend, sample_deployment, make_mock_container):
        """A terminated container should return ERROR."""
        make_mock_container(status="exited", logs=b"Error occurred")

        status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "ERROR"

    @pytest.mark.asyncio
    async def test_lost_returns_lost(self, docker_backend, sample_deployment, mock_docker_client):
        """A missing container (LOST) should return LOST."""
        mock_docker_client.containers.get.side_effect = NotFound("Container not found")

        status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "LOST"


class TestPendingTimeoutErrorMessage:
    """Tests for the content of the error message on PENDING timeout."""

    @pytest.mark.asyncio
    async def test_error_message_includes_docker_logs_command(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """Timeout error message includes a runnable docker logs command."""
        make_mock_container(status="running", logs=b"Error: model architecture not supported")
        docker_backend._backend_config.pending_timeout_seconds = 300
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(seconds=400)

        with patch.object(docker_backend, "_probe_nim_health", new_callable=AsyncMock) as mock_probe:
            mock_probe.return_value = (False, "connection refused")
            status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "ERROR"
        assert "docker logs md-default-test-deployment" in status.status_message

    @pytest.mark.asyncio
    async def test_error_details_contain_container_logs(self, docker_backend, sample_deployment, make_mock_container):
        """error_details should include the container log tail as error_stack."""
        make_mock_container(
            status="running",
            logs=b"ERROR: NemotronHForCausalLM is not supported\nFatal: exiting",
        )
        docker_backend._backend_config.pending_timeout_seconds = 300
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(seconds=400)

        with patch.object(docker_backend, "_probe_nim_health", new_callable=AsyncMock) as mock_probe:
            mock_probe.return_value = (False, "")
            status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.error_details["error_stack"] is not None
        assert "NemotronHForCausalLM" in status.error_details["error_stack"]

    @pytest.mark.asyncio
    async def test_running_not_healthy_shows_restart_count_in_pending_message(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """PENDING message for running-not-healthy container includes restart count when > 0."""
        make_mock_container(status="running", restart_count=3)

        with patch.object(docker_backend, "_probe_nim_health", new_callable=AsyncMock) as mock_probe:
            mock_probe.return_value = (False, "connection refused")
            status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "PENDING"
        assert "restarts: 3" in status.status_message


class TestCrashLoopDetection:
    """Tests for crash loop detection: PENDING -> ERROR after too many restarts."""

    @pytest.mark.asyncio
    async def test_running_not_healthy_exceeds_max_restarts_returns_error(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """A running container that isn't healthy and exceeds max restarts should transition to ERROR."""
        make_mock_container(status="running", restart_count=5, logs=b"CUDA error: out of memory")
        docker_backend._backend_config.max_restart_count = 5

        with patch.object(docker_backend, "_probe_nim_health", new_callable=AsyncMock) as mock_probe:
            mock_probe.return_value = (False, "connection refused")
            status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "ERROR"
        assert "crash loop" in status.status_message
        assert "5 container restarts" in status.status_message
        assert "docker logs" in status.status_message
        assert status.error_details["reason"] == "crash_loop"
        assert status.error_details["restart_count"] == 5
        assert status.error_details["max_restart_count"] == 5

    @pytest.mark.asyncio
    async def test_running_not_healthy_below_max_restarts_returns_pending(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """A running container below max restarts should remain PENDING."""
        make_mock_container(status="running", restart_count=3)
        docker_backend._backend_config.max_restart_count = 5

        with patch.object(docker_backend, "_probe_nim_health", new_callable=AsyncMock) as mock_probe:
            mock_probe.return_value = (False, "connection refused")
            status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "PENDING"
        assert "restarts: 3" in status.status_message

    @pytest.mark.asyncio
    async def test_restarting_state_exceeds_max_restarts_returns_error(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """A container in 'restarting' state that exceeds max restarts should transition to ERROR."""
        make_mock_container(status="restarting", restart_count=7, logs=b"Segfault in model loading")
        docker_backend._backend_config.max_restart_count = 5

        status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "ERROR"
        assert "crash loop" in status.status_message
        assert "7 container restarts" in status.status_message
        assert status.error_details["reason"] == "crash_loop"
        assert status.error_details["restart_count"] == 7
        assert status.error_details["container_state"] == "restarting"

    @pytest.mark.asyncio
    async def test_restarting_state_below_max_restarts_returns_pending(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """A container in 'restarting' state below max restarts should remain PENDING."""
        make_mock_container(status="restarting", restart_count=2)
        docker_backend._backend_config.max_restart_count = 5

        status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "PENDING"
        assert "restart count: 2" in status.status_message

    @pytest.mark.asyncio
    async def test_crash_loop_takes_priority_over_pending_timeout(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """Crash loop detection should fire even when pending timeout is also exceeded."""
        make_mock_container(status="running", restart_count=6, logs=b"OOM killed")
        docker_backend._backend_config.pending_timeout_seconds = 300
        docker_backend._backend_config.max_restart_count = 5
        sample_deployment.created_at = datetime.now(timezone.utc) - timedelta(seconds=400)

        with patch.object(docker_backend, "_probe_nim_health", new_callable=AsyncMock) as mock_probe:
            mock_probe.return_value = (False, "connection refused")
            status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "ERROR"
        assert status.error_details["reason"] == "crash_loop"

    @pytest.mark.asyncio
    async def test_custom_max_restart_count(self, docker_backend, sample_deployment, make_mock_container):
        """Custom max_restart_count should be respected."""
        make_mock_container(status="running", restart_count=10, logs=b"")
        docker_backend._backend_config.max_restart_count = 15

        with patch.object(docker_backend, "_probe_nim_health", new_callable=AsyncMock) as mock_probe:
            mock_probe.return_value = (False, "connection refused")
            status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "PENDING"
        assert "restarts: 10" in status.status_message

    @pytest.mark.asyncio
    async def test_crash_loop_error_includes_container_logs(
        self, docker_backend, sample_deployment, make_mock_container
    ):
        """Crash loop error_details should include container logs as error_stack."""
        make_mock_container(status="restarting", restart_count=5, logs=b"RuntimeError: CUDA out of memory")
        docker_backend._backend_config.max_restart_count = 5

        status = await docker_backend.get_model_deployment_status(sample_deployment)

        assert status.status == "ERROR"
        assert "CUDA out of memory" in status.error_details["error_stack"]


# =============================================================================
# Orphan reconciliation: list_managed_deployment_names, delete_model_deployment (by workspace/name)
# =============================================================================


@pytest.mark.asyncio
async def test_list_managed_deployment_names_returns_dedupe_workspace_name(backend_with_mock_client):
    """list_managed_deployment_names returns sorted unique workspace/name from container labels."""
    backend, _ = backend_with_mock_client
    c1 = MagicMock()
    c1.labels = {
        MODEL_MANAGED_BY_LABEL: MODEL_MANAGED_BY_MODELS_CONTROLLER,
        "nmp.nvidia.com/deployment-workspace": "ws-a",
        "nmp.nvidia.com/deployment-name": "dep1",
    }
    c2 = MagicMock()
    c2.labels = {
        MODEL_MANAGED_BY_LABEL: MODEL_MANAGED_BY_MODELS_CONTROLLER,
        "nmp.nvidia.com/deployment-workspace": "ws-b",
        "nmp.nvidia.com/deployment-name": "dep2",
    }
    c3 = MagicMock()
    c3.labels = c1.labels  # same deployment (e.g. puller) - should dedupe
    with patch.object(backend._reconciler, "list_containers", return_value=[c1, c2, c3]):
        names = await backend.list_managed_deployment_names()
    assert names == ["ws-a/dep1", "ws-b/dep2"]


@pytest.mark.asyncio
async def test_list_managed_deployment_names_empty_when_no_containers(backend_with_mock_client):
    """list_managed_deployment_names returns empty list when no managed containers."""
    backend, _ = backend_with_mock_client
    with patch.object(backend._reconciler, "list_containers", return_value=[]):
        names = await backend.list_managed_deployment_names()
    assert names == []


@pytest.mark.asyncio
async def test_list_managed_deployment_names_skips_missing_labels(backend_with_mock_client):
    """list_managed_deployment_names skips containers missing workspace/name labels."""
    backend, _ = backend_with_mock_client
    c1 = MagicMock()
    c1.labels = {MODEL_MANAGED_BY_LABEL: MODEL_MANAGED_BY_MODELS_CONTROLLER}
    with patch.object(backend._reconciler, "list_containers", return_value=[c1]):
        names = await backend.list_managed_deployment_names()
    assert names == []


@pytest.mark.asyncio
async def test_delete_model_deployment_by_id_calls_delete_by_model_deployment_id(backend_with_mock_client):
    """delete_model_deployment(workspace, name) delegates to _delete_by_model_deployment_id."""
    backend, _ = backend_with_mock_client
    with patch.object(backend, "_delete_by_model_deployment_id", new_callable=AsyncMock) as mock_delete:
        mock_delete.return_value = DeploymentStatusUpdate(status="DELETED", status_message="")
        result = await backend.delete_model_deployment("my-ws", "my-name")
    mock_delete.assert_called_once_with("my-ws", "my-name")
    assert result.status == "DELETED"


# ============================================================================
# Stepped Creation Pipeline Tests
# ============================================================================


class TestSteppedCreation:
    """Tests for the non-blocking, staged deployment creation pipeline."""

    @pytest.mark.asyncio
    async def test_create_returns_pending_with_pulling_message(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """create_model_deployment returns PENDING immediately with pulling message."""
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        status = await docker_backend.create_model_deployment(sample_deployment, sample_config)

        assert status.status == "PENDING"
        assert "pulling container image" in status.status_message.lower()
        assert status.host_url is None

    @pytest.mark.asyncio
    async def test_creation_state_stored_after_create(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """CreationState is stored in _creation_states after create_model_deployment."""
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        await docker_backend.create_model_deployment(sample_deployment, sample_config)

        key = docker_backend._get_deployment_key(sample_deployment)
        assert key in docker_backend._reconciler._creation_states
        state = docker_backend._reconciler._creation_states[key]
        assert state.stage == CreationStage.PULLING_NIM_IMAGE
        assert state.task is not None

    @pytest.mark.asyncio
    async def test_get_status_delegates_to_advance_creation(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """get_model_deployment_status delegates to _advance_creation when in creation pipeline."""
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        await docker_backend.create_model_deployment(sample_deployment, sample_config)

        key = docker_backend._get_deployment_key(sample_deployment)
        assert key in docker_backend._reconciler._creation_states

        # The image pull mock completes instantly, so status check should advance the stage
        state = docker_backend._reconciler._creation_states[key]
        if state.task and not state.task.done():
            await state.task

        status = await docker_backend.get_model_deployment_status(sample_deployment)
        assert status.status == "PENDING"

    @pytest.mark.asyncio
    async def test_image_pull_failure_returns_error(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """If image pull fails, _advance_creation returns ERROR."""
        mock_docker_client.images.get.side_effect = ImageNotFound("not found")
        mock_docker_client.images.pull.side_effect = ImageNotFound("Image not found in registry")
        mock_docker_client.containers.list.return_value = []

        await docker_backend.create_model_deployment(sample_deployment, sample_config)

        status = await drive_creation_to_completion(docker_backend, sample_deployment)

        assert status.status == "ERROR"
        assert "image not found" in status.status_message.lower()

    @pytest.mark.asyncio
    async def test_creation_state_removed_after_completion(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """CreationState is removed from _creation_states after creation completes."""
        docker_backend._backend_config.models_docker_networking_mode = "dond"
        mock_container = MagicMock()
        mock_container.id = "1234567890abcdef"
        mock_container.start = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        await docker_backend.create_model_deployment(sample_deployment, sample_config)
        await drive_creation_to_completion(docker_backend, sample_deployment)

        key = docker_backend._get_deployment_key(sample_deployment)
        assert key not in docker_backend._reconciler._creation_states

    @pytest.mark.asyncio
    async def test_delete_during_creation_cancels_task(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """Deleting a deployment during creation cancels the background task."""
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        mock_volume = MagicMock()
        mock_docker_client.volumes.get.side_effect = None
        mock_docker_client.volumes.get.return_value = mock_volume

        await docker_backend.create_model_deployment(sample_deployment, sample_config)

        key = docker_backend._get_deployment_key(sample_deployment)
        assert key in docker_backend._reconciler._creation_states

        result = await docker_backend.delete_model_deployment(sample_deployment.workspace, sample_deployment.name)

        assert result.status == "DELETED"
        assert key not in docker_backend._reconciler._creation_states

    @pytest.mark.asyncio
    async def test_shutdown_cancels_all_creation_tasks(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """shutdown() cancels all in-flight creation tasks."""
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        await docker_backend.create_model_deployment(sample_deployment, sample_config)

        key = docker_backend._get_deployment_key(sample_deployment)
        assert key in docker_backend._reconciler._creation_states

        docker_backend.shutdown()

        assert key not in docker_backend._reconciler._creation_states

    @pytest.mark.asyncio
    async def test_puller_stage_with_files_service_weights(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """When model needs Files service weights, creation goes through puller stages."""
        model_entity = MagicMock()
        model_entity.workspace = "test"
        model_entity.name = "sft-model"
        model_entity.spec = None
        model_entity.finetuning_type = "all_weights"
        peft_mock = MagicMock()
        peft_mock.finetuning_type = "all_weights"
        model_entity.peft = peft_mock
        model_entity.fileset = "hf://test/sft-model-weights"

        mock_container = MagicMock()
        mock_container.id = "1234567890abcdef"
        mock_container.start = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        _setup_puller_mock_for_polling(mock_docker_client, sample_deployment, exit_code=0)

        await docker_backend.create_model_deployment(sample_deployment, sample_config, model_entity)

        key = docker_backend._get_deployment_key(sample_deployment)
        state = docker_backend._reconciler._creation_states[key]
        assert state.stage == CreationStage.PULLING_NIM_IMAGE

        status = await drive_creation_to_completion(docker_backend, sample_deployment)

        assert status.status == "PENDING"
        assert "container created" in status.status_message.lower()
        assert key not in docker_backend._reconciler._creation_states

    @pytest.mark.asyncio
    async def test_puller_running_stage_reports_downloading(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """While puller is running, status reports downloading weights."""
        model_entity = MagicMock()
        model_entity.workspace = "test"
        model_entity.name = "sft-model"
        model_entity.spec = None
        model_entity.finetuning_type = "all_weights"
        peft_mock = MagicMock()
        peft_mock.finetuning_type = "all_weights"
        model_entity.peft = peft_mock
        model_entity.fileset = "hf://test/sft-model-weights"

        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        mock_puller = _setup_puller_mock_for_polling(mock_docker_client, sample_deployment, exit_code=0)
        mock_puller.status = "running"

        await docker_backend.create_model_deployment(sample_deployment, sample_config, model_entity)

        key = docker_backend._get_deployment_key(sample_deployment)
        # Advance through PULLING_NIM_IMAGE and PULLING_PULLER_IMAGE
        for _ in range(5):
            state = docker_backend._reconciler._creation_states.get(key)
            if state is None:
                break
            if state.task and not state.task.done():
                try:
                    await state.task
                except Exception:
                    pass
            if state.stage == CreationStage.RUNNING_PULLER:
                break
            await docker_backend._reconciler.advance(key)

        assert key in docker_backend._reconciler._creation_states
        state = docker_backend._reconciler._creation_states[key]
        assert state.stage == CreationStage.RUNNING_PULLER

        status = await docker_backend._reconciler.advance(key)
        assert status.status == "PENDING"
        assert "downloading model weights" in status.status_message.lower()

    @pytest.mark.asyncio
    async def test_concurrent_deployments_not_blocked(self, docker_backend, sample_config, mock_docker_client):
        """Multiple deployments can have creation states concurrently."""
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        deployments = []
        for i in range(3):
            d = MagicMock()
            d.workspace = "test"
            d.name = f"model-{i}"
            d.hf_token_secret_name = None
            deployments.append(d)

        for d in deployments:
            await docker_backend.create_model_deployment(d, sample_config)

        # All three should have creation states
        for d in deployments:
            key = docker_backend._get_deployment_key(d)
            assert key in docker_backend._reconciler._creation_states

        assert len(docker_backend._reconciler._creation_states) == 3


class TestAsyncioToThreadOffloading:
    """Verify blocking Docker operations are offloaded via asyncio.to_thread."""

    @pytest.mark.asyncio
    async def test_nim_image_pull_uses_to_thread(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """create_model_deployment offloads the NIM image pull to asyncio.to_thread."""
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        to_thread_calls: list[tuple] = []
        original_to_thread = asyncio.to_thread

        async def spy_to_thread(func, *args, **kwargs):
            to_thread_calls.append((func, args, kwargs))
            return await original_to_thread(func, *args, **kwargs)

        with patch(
            "nmp.core.models.controllers.backends.docker.creation_reconciler.asyncio.to_thread",
            side_effect=spy_to_thread,
        ):
            await docker_backend.create_model_deployment(sample_deployment, sample_config)

            key = docker_backend._get_deployment_key(sample_deployment)
            state = docker_backend._reconciler._creation_states[key]
            if state.task and not state.task.done():
                await state.task

        pull_calls = [c for c in to_thread_calls if getattr(c[0], "__name__", "") == "pull_image_if_not_local"]
        assert len(pull_calls) >= 1, "NIM image pull should be offloaded to asyncio.to_thread"

    @pytest.mark.asyncio
    async def test_container_creation_uses_to_thread(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """Container creation and start are offloaded to asyncio.to_thread."""
        mock_container = MagicMock()
        mock_container.id = "1234567890abcdef"
        mock_container.start = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        to_thread_calls: list[tuple] = []
        original_to_thread = asyncio.to_thread

        async def spy_to_thread(func, *args, **kwargs):
            to_thread_calls.append((func, args, kwargs))
            return await original_to_thread(func, *args, **kwargs)

        with patch(
            "nmp.core.models.controllers.backends.docker.creation_reconciler.asyncio.to_thread",
            side_effect=spy_to_thread,
        ):
            await docker_backend.create_model_deployment(sample_deployment, sample_config)
            status = await drive_creation_to_completion(docker_backend, sample_deployment)

        assert status.status != "ERROR", f"Creation failed: {status.status_message}"
        container_calls = [c for c in to_thread_calls if getattr(c[0], "__name__", "") == "create_and_start_container"]
        assert len(container_calls) >= 1, "create_and_start_container should be offloaded to asyncio.to_thread"

    @pytest.mark.asyncio
    async def test_puller_image_pull_uses_to_thread(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """When model puller is needed, its image pull is offloaded to asyncio.to_thread."""
        model_entity = MagicMock()
        model_entity.workspace = "test"
        model_entity.name = "sft-model"
        model_entity.spec = None
        model_entity.finetuning_type = "all_weights"
        peft_mock = MagicMock()
        peft_mock.finetuning_type = "all_weights"
        model_entity.peft = peft_mock
        model_entity.fileset = "hf://test/sft-model-weights"

        mock_container = MagicMock()
        mock_container.id = "1234567890abcdef"
        mock_container.start = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        _setup_puller_mock_for_polling(mock_docker_client, sample_deployment, exit_code=0)

        to_thread_calls: list[tuple] = []
        original_to_thread = asyncio.to_thread

        async def spy_to_thread(func, *args, **kwargs):
            to_thread_calls.append((func, args, kwargs))
            return await original_to_thread(func, *args, **kwargs)

        with patch(
            "nmp.core.models.controllers.backends.docker.creation_reconciler.asyncio.to_thread",
            side_effect=spy_to_thread,
        ):
            await docker_backend.create_model_deployment(sample_deployment, sample_config, model_entity)
            await drive_creation_to_completion(docker_backend, sample_deployment)

        pull_calls = [c for c in to_thread_calls if getattr(c[0], "__name__", "") == "pull_image_if_not_local"]
        assert len(pull_calls) >= 2, "Both NIM image and puller image pulls should be offloaded to asyncio.to_thread"

    @pytest.mark.asyncio
    async def test_sidecar_creation_uses_to_thread(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """Sidecar container creation is offloaded to asyncio.to_thread."""
        sample_config.model_spec.lora_enabled = True

        mock_container = MagicMock()
        mock_container.id = "1234567890abcdef"
        mock_container.start = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        to_thread_calls: list[tuple] = []
        original_to_thread = asyncio.to_thread

        async def spy_to_thread(func, *args, **kwargs):
            to_thread_calls.append((func, args, kwargs))
            return await original_to_thread(func, *args, **kwargs)

        with patch(
            "nmp.core.models.controllers.backends.docker.creation_reconciler.asyncio.to_thread",
            side_effect=spy_to_thread,
        ):
            await docker_backend.create_model_deployment(sample_deployment, sample_config)
            await drive_creation_to_completion(docker_backend, sample_deployment)

        container_calls = [c for c in to_thread_calls if getattr(c[0], "__name__", "") == "create_and_start_container"]
        assert len(container_calls) >= 2, (
            "Both NIM and sidecar container creation should be offloaded to asyncio.to_thread"
        )

    @pytest.mark.asyncio
    async def test_no_blocking_calls_on_event_loop(
        self, docker_backend, sample_deployment, sample_config, mock_docker_client
    ):
        """Verify blocking operations go through asyncio.to_thread, not directly on the loop."""
        mock_docker_client.images.get.return_value = MagicMock()
        mock_docker_client.containers.list.return_value = []

        mock_container = MagicMock()
        mock_container.id = "1234567890abcdef"
        mock_container.start = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        to_thread_funcs: list[str] = []
        original_to_thread = asyncio.to_thread

        async def spy_to_thread(func, *args, **kwargs):
            name = getattr(func, "__name__", None) or getattr(func, "_mock_name", "unknown")
            to_thread_funcs.append(str(name))
            return await original_to_thread(func, *args, **kwargs)

        with patch(
            "nmp.core.models.controllers.backends.docker.creation_reconciler.asyncio.to_thread",
            side_effect=spy_to_thread,
        ):
            await docker_backend.create_model_deployment(sample_deployment, sample_config)
            await drive_creation_to_completion(docker_backend, sample_deployment)

        assert any("pull" in name.lower() for name in to_thread_funcs), (
            f"Image pull should go through asyncio.to_thread, got: {to_thread_funcs}"
        )
        assert any("create" in name.lower() or "container" in name.lower() for name in to_thread_funcs), (
            f"Container creation should go through asyncio.to_thread, got: {to_thread_funcs}"
        )
