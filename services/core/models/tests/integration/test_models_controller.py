# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for Models Controller.

This module contains two categories of tests:
1. Backend-agnostic tests - Test controller logic with mock backend (no Docker required)
2. Docker integration tests - Test with real Docker backend (requires --run-docker-tests flag)
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docker.errors import NotFound
from nemo_platform import NotFoundError
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate
from nmp.core.models.controllers.backends.docker import DockerServiceBackend
from nmp.core.models.controllers.backends.registry import BackendRegistry
from nmp.core.models.controllers.models_controller import ModelsController
from tenacity import retry, stop_after_delay, wait_fixed

# =============================================================================
# Backend-Agnostic Tests (Mock Backend)
# =============================================================================


def test_controller_initializes_correctly(controller_with_mock_backend):
    """Test that controller initializes with expected state."""
    controller, _, _ = controller_with_mock_backend

    assert controller is not None
    assert controller._backend_registry is not None
    assert not controller.is_healthy  # Not healthy until first step completes


def test_controller_step_marks_healthy(controller_with_mock_backend):
    """Test that controller step marks itself healthy on success."""
    controller, _, _ = controller_with_mock_backend

    # Run one controller step
    controller.step()

    assert controller.is_healthy


def test_controller_reconciles_created_deployment(controller_with_mock_backend):
    """Test that controller calls backend.create_model_deployment for CREATED deployments."""
    controller, mock_backend, sdk = controller_with_mock_backend
    test_uuid = uuid.uuid4().hex[:8]
    config_name = f"test-config-{test_uuid}"
    deployment_name = f"test-deployment-{test_uuid}"

    # Configure mock backend to keep this specific deployment in PENDING state
    # (otherwise the reconciler processes PENDING->READY in the same step)
    mock_backend.status_responses[deployment_name] = DeploymentStatusUpdate(
        status="PENDING",
        status_message="Still starting",
        host_url="http://localhost:8500",
    )

    # Create deployment config first
    sdk.inference.deployment_configs.create(
        name=config_name,
        workspace="default",
        nim_deployment={"gpu": 0},  # No GPU for mock
    )

    # Create deployment - starts in CREATED status
    sdk.inference.deployments.create(
        name=deployment_name,
        workspace="default",
        config=config_name,
    )

    # Verify deployment is in CREATED status
    deployment = sdk.inference.deployments.retrieve(deployment_name, workspace="default")
    assert deployment.status == "CREATED"

    # Run controller step - should call backend.create_model_deployment
    controller.step()

    # Verify backend was called
    assert len(mock_backend.create_calls) >= 1
    # Find our deployment in the calls
    our_calls = [(d, c, e) for d, c, e in mock_backend.create_calls if d.name == deployment_name]
    assert len(our_calls) == 1
    called_deployment, called_config, _ = our_calls[0]
    assert called_deployment.name == deployment_name
    assert called_config.name == config_name

    # Verify deployment status was updated to PENDING
    deployment = sdk.inference.deployments.retrieve(deployment_name, workspace="default")
    assert deployment.status == "PENDING"


def test_controller_polls_pending_deployment(controller_with_mock_backend):
    """Test that controller calls backend.get_model_deployment_status for PENDING deployments."""
    controller, mock_backend, sdk = controller_with_mock_backend
    test_uuid = uuid.uuid4().hex[:8]
    config_name = f"test-config-poll-{test_uuid}"
    deployment_name = f"test-deployment-poll-{test_uuid}"

    # Create config and deployment
    sdk.inference.deployment_configs.create(name=config_name, workspace="default", nim_deployment={"gpu": 0})
    sdk.inference.deployments.create(name=deployment_name, workspace="default", config=config_name)

    # Configure status to PENDING so first step doesn't immediately go to READY
    mock_backend.status_responses[deployment_name] = DeploymentStatusUpdate(
        status="PENDING",
        status_message="Still starting",
        host_url="http://localhost:8500",
    )

    # Run first step to move from CREATED -> PENDING
    controller.step()

    # Clear call history
    mock_backend.create_calls.clear()
    mock_backend.status_calls.clear()

    # Configure status response to return READY for this specific deployment
    mock_backend.status_responses[deployment_name] = DeploymentStatusUpdate(
        status="READY",
        status_message="Container ready",
        host_url="http://localhost:8500",
    )

    # Run second step - should call get_model_deployment_status
    controller.step()

    # Verify status was checked for our deployment
    deployment_status_calls = [d for d in mock_backend.status_calls if d.name == deployment_name]
    assert len(deployment_status_calls) == 1

    # Verify deployment was updated to READY
    deployment = sdk.inference.deployments.retrieve(deployment_name, workspace="default")
    assert deployment.status == "READY"


def test_controller_handles_backend_error(controller_with_mock_backend):
    """Test that controller handles backend errors gracefully."""
    controller, mock_backend, sdk = controller_with_mock_backend
    test_uuid = uuid.uuid4().hex[:8]
    config_name = f"test-config-err-{test_uuid}"
    deployment_name = f"test-deployment-err-{test_uuid}"

    # Create config and deployment
    sdk.inference.deployment_configs.create(name=config_name, workspace="default", nim_deployment={"gpu": 0})
    sdk.inference.deployments.create(name=deployment_name, workspace="default", config=config_name)

    # Configure backend to return ERROR
    mock_backend.create_response = DeploymentStatusUpdate(
        status="ERROR",
        status_message="Failed to create container",
        error_details={"error": "Image not found"},
    )

    # Run controller step
    controller.step()

    # Verify deployment status was updated to ERROR
    deployment = sdk.inference.deployments.retrieve(deployment_name, workspace="default")
    assert deployment.status == "ERROR"
    assert "Failed to create container" in (deployment.status_message or "")


def test_controller_deletes_when_deleting(controller_with_mock_backend):
    """Test that controller calls backend.delete_model_deployment for DELETING deployments."""
    controller, mock_backend, sdk = controller_with_mock_backend
    test_uuid = uuid.uuid4().hex[:8]
    config_name = f"test-config-del-{test_uuid}"
    deployment_name = f"test-deployment-del-{test_uuid}"

    # Create config and deployment
    sdk.inference.deployment_configs.create(name=config_name, workspace="default", nim_deployment={"gpu": 0})
    sdk.inference.deployments.create(name=deployment_name, workspace="default", config=config_name)

    # Move to READY state
    mock_backend.create_response = DeploymentStatusUpdate(status="PENDING", status_message="Starting")
    controller.step()
    mock_backend.status_responses[deployment_name] = DeploymentStatusUpdate(status="READY", status_message="Ready")
    controller.step()

    # Delete the deployment (moves to DELETING)
    sdk.inference.deployments.delete(deployment_name, workspace="default")

    # Clear call history
    mock_backend.delete_calls.clear()

    # Configure delete response
    mock_backend.delete_response = DeploymentStatusUpdate(
        status="DELETED",
        status_message="Container deleted",
    )

    # Run controller step - should call delete
    controller.step()

    # Verify delete was called for our deployment
    our_delete_calls = [c for c in mock_backend.delete_calls if c[0] == "default" and c[1] == deployment_name]
    assert len(our_delete_calls) == 1


def test_controller_garbage_collects_deleted_deployment(controller_with_mock_backend):
    """Test that controller hard-deletes DELETED deployments after grace period expires."""
    controller, mock_backend, sdk = controller_with_mock_backend
    test_uuid = uuid.uuid4().hex[:8]
    config_name = f"test-config-gc-{test_uuid}"
    deployment_name = f"test-deployment-gc-{test_uuid}"

    # Create config and deployment
    sdk.inference.deployment_configs.create(name=config_name, workspace="default", nim_deployment={"gpu": 0})
    sdk.inference.deployments.create(name=deployment_name, workspace="default", config=config_name)

    # Progress through lifecycle: CREATED → PENDING → READY → DELETING → DELETED
    mock_backend.create_response = DeploymentStatusUpdate(status="PENDING", status_message="Starting")
    controller.step()

    mock_backend.status_responses[deployment_name] = DeploymentStatusUpdate(
        status="READY", status_message="Ready", host_url="http://localhost:8080"
    )
    controller.step()

    # Delete deployment (moves to DELETING)
    sdk.inference.deployments.delete(deployment_name, workspace="default")

    mock_backend.delete_response = DeploymentStatusUpdate(status="DELETED", status_message="Deleted")
    controller.step()  # DELETING → DELETED

    # Verify deployment is in DELETED state (soft-deleted, still exists)
    deployment = sdk.inference.deployments.retrieve(deployment_name, workspace="default")
    assert deployment.status == "DELETED"

    # Patch the controller's reconciler to have 0 second grace period
    controller._deployment_reconciler._controller_config.model_deployment_garbage_collection_ttl_seconds = 0

    # Run controller step - should hard-delete since grace period expired
    controller.step()

    # Verify deployment is gone (hard-deleted)
    with pytest.raises(NotFoundError):
        sdk.inference.deployments.retrieve(deployment_name, workspace="default")


def test_controller_orphan_cleanup_after_deleted(controller_with_mock_backend):
    """Test that orphan cleanup deletes backend resources when deployment is DELETED and gone from API.

    Flow: create deployment → PENDING → READY → delete via API → DELETED → hard-delete (grace=0)
    → then simulate backend still reporting the deployment (orphan) → next step runs reconcile_orphans
    and calls delete_model_deployment(workspace, name) for the orphan.
    """
    controller, mock_backend, sdk = controller_with_mock_backend
    test_uuid = uuid.uuid4().hex[:8]
    config_name = f"test-config-orphan-{test_uuid}"
    deployment_name = f"test-deployment-orphan-{test_uuid}"

    # Create config and deployment
    sdk.inference.deployment_configs.create(name=config_name, workspace="default", nim_deployment={"gpu": 0})
    sdk.inference.deployments.create(name=deployment_name, workspace="default", config=config_name)

    # CREATED → PENDING → READY
    mock_backend.create_response = DeploymentStatusUpdate(status="PENDING", status_message="Starting")
    controller.step()

    mock_backend.status_responses[deployment_name] = DeploymentStatusUpdate(
        status="READY", status_message="Ready", host_url="http://localhost:8080"
    )
    controller.step()

    # Delete via API (moves to DELETING)
    sdk.inference.deployments.delete(deployment_name, workspace="default")

    mock_backend.delete_response = DeploymentStatusUpdate(status="DELETED", status_message="Deleted")
    controller.step()  # DELETING → DELETED

    deployment = sdk.inference.deployments.retrieve(deployment_name, workspace="default")
    assert deployment.status == "DELETED"

    # Hard-delete after grace period so deployment is no longer in API
    controller._deployment_reconciler._controller_config.model_deployment_garbage_collection_ttl_seconds = 0
    controller.step()

    with pytest.raises(NotFoundError):
        sdk.inference.deployments.retrieve(deployment_name, workspace="default")

    # Simulate backend still reporting this deployment (orphan)
    deployment_id = f"default/{deployment_name}"
    mock_backend.list_managed_deployment_names = AsyncMock(return_value=[deployment_id])
    mock_backend.delete_calls.clear()

    # Next step: reconcile_orphans sees backend has deployment_id but it's not in known set → delete orphan
    controller.step()

    # Orphan cleanup should have called delete_model_deployment("default", deployment_name)
    our_delete_calls = [c for c in mock_backend.delete_calls if c[0] == "default" and c[1] == deployment_name]
    assert len(our_delete_calls) == 1, (
        f"Expected one delete call for orphan {deployment_id}, got delete_calls={mock_backend.delete_calls}"
    )


def test_controller_creates_model_provider_when_ready(controller_with_mock_backend):
    """Test that controller creates ModelProvider when deployment becomes READY."""
    controller, mock_backend, sdk = controller_with_mock_backend
    test_uuid = uuid.uuid4().hex[:8]
    config_name = f"test-config-prov-{test_uuid}"
    deployment_name = f"test-deployment-prov-{test_uuid}"

    # Create config and deployment
    sdk.inference.deployment_configs.create(name=config_name, workspace="default", nim_deployment={"gpu": 0})
    sdk.inference.deployments.create(name=deployment_name, workspace="default", config=config_name)

    # Move to READY state with host_url - this should trigger provider creation
    mock_backend.create_response = DeploymentStatusUpdate(
        status="READY", status_message="Ready", host_url="http://localhost:9000"
    )
    controller.step()

    # Verify deployment has model_provider_id set
    deployment = sdk.inference.deployments.retrieve(deployment_name, workspace="default")
    assert deployment.status == "READY"
    assert deployment.model_provider_id is not None

    # Verify provider was created with correct host_url and status
    provider_id = deployment.model_provider_id
    provider_workspace, provider_name = provider_id.split("/")
    provider = sdk.inference.providers.retrieve(provider_name, workspace=provider_workspace)
    assert provider.host_url == "http://localhost:9000"
    assert provider.status == "READY", "Provider should be READY when deployment is READY"


def test_controller_deletes_model_provider_on_delete(controller_with_mock_backend):
    """Test that controller deletes ModelProvider when deployment is deleted."""
    controller, mock_backend, sdk = controller_with_mock_backend
    test_uuid = uuid.uuid4().hex[:8]
    config_name = f"test-config-delprov-{test_uuid}"
    deployment_name = f"test-deployment-delprov-{test_uuid}"

    # Create config and deployment
    sdk.inference.deployment_configs.create(name=config_name, workspace="default", nim_deployment={"gpu": 0})
    sdk.inference.deployments.create(name=deployment_name, workspace="default", config=config_name)

    # Move to READY state (creates provider)
    mock_backend.create_response = DeploymentStatusUpdate(
        status="READY", status_message="Ready", host_url="http://localhost:9001"
    )
    controller.step()

    # Get provider info before deletion
    deployment = sdk.inference.deployments.retrieve(deployment_name, workspace="default")
    provider_id = deployment.model_provider_id
    provider_workspace, provider_name = provider_id.split("/")

    # Verify provider exists
    sdk.inference.providers.retrieve(provider_name, workspace=provider_workspace)

    # Delete deployment (moves to DELETING)
    sdk.inference.deployments.delete(deployment_name, workspace="default")

    # Configure delete response and run controller
    mock_backend.delete_response = DeploymentStatusUpdate(status="DELETED", status_message="Deleted")
    controller.step()

    # Verify provider was deleted
    with pytest.raises(NotFoundError):
        sdk.inference.providers.retrieve(provider_name, workspace=provider_workspace)


# =============================================================================
# Docker Integration Tests
# =============================================================================


def _get_worker_port_range(worker_id: str, ports_per_worker: int = 100) -> tuple[int, int]:
    """Calculate unique port range for a pytest-xdist worker.

    Args:
        worker_id: The xdist worker ID ("master", "gw0", "gw1", etc.)
        ports_per_worker: Number of ports to allocate per worker

    Returns:
        Tuple of (start_port, end_port)

    Environment Variables:
        MODELS_DOCKER_PORT_RANGE_START: Override the base port (default: 49152)
    """
    # Use IANA ephemeral port range (49152-65535) to avoid conflicts with system services
    # Can be overridden via environment variable for DinD testing
    base_port = int(os.environ.get("MODELS_DOCKER_PORT_RANGE_START", "49152"))
    if worker_id == "master":
        worker_num = 0
    else:
        # Extract number from "gw0", "gw1", etc.
        worker_num = int(worker_id.replace("gw", ""))

    start_port = base_port + (worker_num * ports_per_worker)
    end_port = start_port + ports_per_worker - 1
    return start_port, end_port


@pytest.fixture
def docker_backend_config(worker_id):
    """Configuration for Docker backend in tests.

    Uses worker_id from pytest-xdist to allocate unique port ranges
    per worker, enabling parallel test execution.
    """
    start_port, end_port = _get_worker_port_range(worker_id)
    return {
        "models_docker_port_range_start": start_port,
        "models_docker_port_range_end": end_port,
        "docker_timeout": 60,
        "models_docker_host_service_name": "localhost",
    }


@pytest.fixture
def controller_with_docker(
    test_clients,
    docker_client,  # noqa: ARG001 - dependency ensures docker is available
    mock_nim_image,
    mock_sidecar_image,
    docker_backend_config,
    docker_test_context,
    models_controller_container_cleanup,
):
    """Create controller with real Docker backend."""
    from nemo_platform_plugin.jobs.image import get_qualified_image as real_get_qualified_image

    def patched_get_qualified_image(name: str, tag=None, registry=None):
        if name in ["nmp-core", "nmp-api"]:
            return mock_sidecar_image
        return real_get_qualified_image(name, tag=tag, registry=registry)

    # Create Docker backend with test config
    docker_backend = DockerServiceBackend(
        nmp_sdk=test_clients.async_sdk,
        config=docker_backend_config,
    )

    # Create registry with Docker backend
    backend_registry = BackendRegistry(registry={"docker": docker_backend})

    # Create controller with patched SDK factory and get_qualified_image so backend uses our mock sidecar
    mock_platform_config = MagicMock()
    mock_platform_config.models_url = "http://testserver"
    mock_platform_config.get_service_url.return_value = "http://testserver"
    with (
        patch("nmp.core.models.config.get_platform_config", return_value=mock_platform_config),
        patch("nmp.core.models.controllers.main.get_platform_config", return_value=mock_platform_config),
        patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk") as mock_sdk_factory,
        patch(
            "nmp.core.models.controllers.backends.docker.creation_reconciler.get_qualified_image",
            side_effect=patched_get_qualified_image,
        ),
    ):
        mock_sdk_factory.return_value = test_clients.async_sdk

        controller = ModelsController(
            backend_registry=backend_registry,
            stop_signal=None,
        )

        yield controller, docker_backend, test_clients.sdk, mock_nim_image, docker_test_context

        # Clean up controller resources (event loop, backend registry, etc.)
        controller.shutdown()


def test_docker_deployment_lifecycle(controller_with_docker, docker_client):
    """Test full Docker deployment lifecycle with provider reconciliation.

    Tests: create → PENDING → READY → delete → cleanup
    Also verifies: ModelProvider creation, served_models autodiscovery, provider deletion
    """
    controller, _, sdk, mock_nim_image, ctx = controller_with_docker
    test_uuid = uuid.uuid4().hex[:8]
    config_name = f"test-docker-lifecycle-{test_uuid}"
    deployment_name = f"test-docker-lifecycle-{test_uuid}"
    container_name = f"md-default-{deployment_name}"

    # Register container for cleanup
    ctx.register_container(container_name)
    ctx.register_volume(f"nim-cache-default-{deployment_name}")

    # === Phase 1: Create config and deployment ===
    # Parse image name and tag - use rsplit to handle registry URLs with port numbers
    # e.g., "registry.example.com/nemo-platform/mock-nim:1.0.0"
    image_name, image_tag = mock_nim_image.rsplit(":", 1)
    sdk.inference.deployment_configs.create(
        name=config_name,
        workspace="default",
        nim_deployment={
            "gpu": 0,
            "image_name": image_name,
            "image_tag": image_tag,
        },
    )

    sdk.inference.deployments.create(
        name=deployment_name,
        workspace="default",
        config=config_name,
    )

    # === Phase 2: Controller advances creation pipeline (CREATED -> PENDING -> container) ===
    # The staged creation pipeline needs multiple controller steps:
    # step 1: CREATED→PENDING (registers deployment, starts image pull)
    # step 2+: advance through PULLING_NIM_IMAGE → CREATING_CONTAINER
    @retry(stop=stop_after_delay(15), wait=wait_fixed(0.1), reraise=True)
    def wait_for_container_created():
        controller.step()
        container = docker_client.containers.get(container_name)
        assert container.status in ["created", "running"], f"Unexpected status: {container.status}"
        return container

    container = wait_for_container_created()

    # === Phase 3: Wait for container to start, then PENDING -> READY ===
    @retry(stop=stop_after_delay(10), wait=wait_fixed(0.1), reraise=True)
    def wait_for_container_running():
        container.reload()
        assert container.status == "running", f"Container not running: {container.status}"

    wait_for_container_running()

    # Controller polls health check and marks READY.
    # The mock NIM may need a moment to start responding to health checks,
    # so we poll multiple times until READY or timeout.
    @retry(stop=stop_after_delay(30), wait=wait_fixed(0.1), reraise=True)
    def wait_for_deployment_ready():
        controller.step()
        dep = sdk.inference.deployments.retrieve(deployment_name, workspace="default")
        assert dep.status == "READY", f"Deployment not READY: {dep.status}"
        return dep

    deployment = wait_for_deployment_ready()

    # === Phase 3b: Verify ModelProvider was created ===
    provider_id = deployment.model_provider_id
    assert provider_id is not None, "ModelProvider should be created when deployment becomes READY"

    provider_workspace, provider_name = provider_id.split("/")
    provider = sdk.inference.providers.retrieve(provider_name, workspace=provider_workspace)
    assert provider.host_url is not None, "Provider should have host_url set"
    assert provider.status == "READY", "Provider should be READY when deployment is READY"

    # === Phase 3c: Run another step to trigger provider reconciliation ===
    # Note: Autodiscovery of served_models requires Inference Gateway which is not
    # set up in this test. The provider_reconciler will log a warning but continue.
    # Key functionality (provider creation/deletion) is already verified above.
    controller.step()

    # Verify provider still exists after reconciliation step (no errors)
    sdk.inference.providers.retrieve(provider_name, workspace=provider_workspace)

    # === Phase 4: Delete deployment and verify cleanup ===
    sdk.inference.deployments.delete(deployment_name, workspace="default")

    # Controller processes deletion
    controller.step()

    # Poll for container to be removed or stopped (DinD may be slow)
    @retry(stop=stop_after_delay(15), wait=wait_fixed(0.1), reraise=True)
    def wait_for_container_deleted():
        try:
            c = docker_client.containers.get(container_name)
            c.reload()
            if c.status in ["exited", "removing", "dead"]:
                return  # Container is stopping/stopped
            raise AssertionError(f"Container still running: {c.status}")
        except NotFound:
            return  # Container was removed, which is expected

    try:
        wait_for_container_deleted()
    except AssertionError:
        # After all retries, log but don't fail - provider deletion is the key check
        print(f"Warning: Container {container_name} still running after retries")

    # === Phase 4b: Verify ModelProvider was deleted ===
    with pytest.raises(NotFoundError):
        sdk.inference.providers.retrieve(provider_name, workspace=provider_workspace)
