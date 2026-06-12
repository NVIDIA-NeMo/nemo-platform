# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for Models service integration tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Generator, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform.types.inference.model_deployment import ModelDeployment
from nemo_platform.types.inference.model_deployment_config import ModelDeploymentConfig
from nemo_platform.types.models.model_entity import ModelEntity
from nmp.common.secrets.encryption import get_base64_encoded_random_bytes
from nmp.core.files.app.backends.huggingface import HuggingfaceStorageImpl
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate, ServiceBackend
from nmp.core.models.controllers.backends.registry import BackendRegistry
from nmp.core.models.controllers.models_controller import ModelsController
from nmp.core.models.service import ModelsService
from nmp.core.secrets.config import SecretsServiceConfig
from nmp.testing import ClientContext, create_test_client
from nmp.testing.blockbuster import blockbuster_fixture
from nmp.testing.docker import (
    MOCK_NIM_IMAGE_TAG,
    MOCK_SIDECAR_IMAGE_TAG,
    DockerTestContext,
    cleanup_model_deployment_containers,
    create_docker_client,
    ensure_mock_nim_image,
    ensure_mock_sidecar_image,
    get_worker_port_range,
)

import docker

blockbuster = blockbuster_fixture(autouse=True)


@pytest.fixture
def no_hf_network(monkeypatch):
    """Disable live HuggingFace API calls; keep fileset create/update paths local."""

    async def _validate_noop(self):
        return None

    async def _resolve_passthrough(self):
        return self.config

    monkeypatch.setattr(HuggingfaceStorageImpl, "validate_storage", _validate_noop)
    monkeypatch.setattr(HuggingfaceStorageImpl, "resolve_config", _resolve_passthrough)


# =============================================================================
# Constants
# =============================================================================

DEFAULT_WORKSPACE = "default"
MOCK_NIM_IMAGE_NAME = f"mock-nim-models:{MOCK_NIM_IMAGE_TAG}"
MOCK_SIDECAR_IMAGE_NAME = f"mock-sidecar-models:{MOCK_SIDECAR_IMAGE_TAG}"


# =============================================================================
# Shared Test Helpers
# =============================================================================


@pytest.fixture
def create_secret() -> Callable:
    """Factory fixture for creating secrets in the test server."""

    def _create(client_context: ClientContext, name: str, workspace: str = "default") -> None:
        response = client_context.test_client.post(
            f"/apis/secrets/v2/workspaces/{workspace}/secrets",
            json={"name": name, "value": "test-token"},
        )
        assert response.status_code == 201, f"Failed to create secret: {response.status_code} {response.text}"

    return _create


@pytest.fixture
def secrets_service_config() -> SecretsServiceConfig:
    """Create encryption config required by SecretsService."""
    return SecretsServiceConfig(
        encryption={
            "current_provider": "test",
            "providers": {
                "secret_key": {
                    "test": {"value": get_base64_encoded_random_bytes(32)},
                },
            },
        },
    )


# =============================================================================
# Mock Backend for Backend-Agnostic Tests
# =============================================================================


class MockServiceBackend(ServiceBackend):
    """Mock backend that returns controlled responses for testing."""

    def __init__(
        self,
        nmp_sdk: AsyncNeMoPlatform,
        config: dict[str, Any],
    ) -> None:
        """Initialize mock backend without calling parent init."""
        self._nmp_sdk = nmp_sdk
        self._config = config

        # Track method calls for assertions
        self.create_calls: list[tuple[ModelDeployment, ModelDeploymentConfig, Optional[ModelEntity]]] = []
        self.update_calls: list[tuple[ModelDeployment, ModelDeploymentConfig, Optional[ModelEntity]]] = []
        self.status_calls: list[ModelDeployment] = []
        self.delete_calls: list[tuple[str, str]] = []  # (workspace, name)

        # Configure responses (can be overridden per-test)
        # Note: host_url is None by default to avoid port conflicts in parallel tests.
        # Tests that need a specific host_url should set it explicitly in status_responses.
        self.create_response = DeploymentStatusUpdate(
            status="PENDING",
            status_message="Container created and starting",
            host_url=None,
        )
        # Per-deployment status responses - keyed by deployment name
        # If a deployment name is not in this dict, falls back to default_status_response
        self.status_responses: dict[str, DeploymentStatusUpdate] = {}
        self.default_status_response = DeploymentStatusUpdate(
            status="READY",
            status_message="Container is ready",
            host_url=None,
        )
        self.delete_response = DeploymentStatusUpdate(
            status="DELETED",
            status_message="Container deleted",
        )

    def init(self) -> None:
        """No-op init for mock backend."""
        pass

    def shutdown(self) -> None:
        """No-op shutdown for mock backend."""
        pass

    async def create_model_deployment(
        self,
        deployment: ModelDeployment,
        config: ModelDeploymentConfig,
        model_entity: Optional[ModelEntity] = None,
    ) -> DeploymentStatusUpdate:
        """Record call and return configured response."""
        self.create_calls.append((deployment, config, model_entity))
        return self.create_response

    async def update_model_deployment(
        self,
        deployment: ModelDeployment,
        config: ModelDeploymentConfig,
        model_entity: Optional[ModelEntity] = None,
    ) -> DeploymentStatusUpdate:
        """Record call and return configured response."""
        self.update_calls.append((deployment, config, model_entity))
        return self.create_response  # Update returns same as create

    async def get_model_deployment_status(self, deployment: ModelDeployment) -> DeploymentStatusUpdate:
        """Record call and return configured response.

        Uses per-deployment responses from status_responses dict if available,
        otherwise falls back to default_status_response.
        """
        self.status_calls.append(deployment)
        return self.status_responses.get(deployment.name, self.default_status_response)

    async def delete_model_deployment(self, workspace: str, name: str) -> DeploymentStatusUpdate:
        """Record call and return configured response."""
        self.delete_calls.append((workspace, name))
        return self.delete_response

    async def list_managed_deployment_names(self) -> list[str]:
        """Return empty list; mock has no managed deployments."""
        return []


# =============================================================================
# Integration Test Fixtures
# =============================================================================


@pytest.fixture
def test_clients() -> Generator[ClientContext, None, None]:
    """Create all client types sharing the same app for controller tests.

    The controller needs an async SDK, but we also need the sync SDK/test client
    to create test data. ClientContext provides all of these sharing one app.
    """
    with create_test_client(ModelsService, client_type=ClientContext) as clients:
        yield clients


@pytest.fixture
def mock_backend(test_clients: ClientContext) -> MockServiceBackend:
    """Create a mock backend for testing."""
    return MockServiceBackend(
        nmp_sdk=test_clients.async_sdk,
        config={},
    )


@pytest.fixture
def mock_backend_registry(mock_backend: MockServiceBackend) -> BackendRegistry:
    """Create a backend registry with the mock backend."""
    return BackendRegistry(registry={"mock": mock_backend})


@pytest.fixture
def controller_with_mock_backend(
    test_clients: ClientContext, mock_backend_registry: BackendRegistry
) -> Generator[tuple[ModelsController, MockServiceBackend, NeMoPlatform], None, None]:
    """Create a ModelsController wired to use the test SDK and mock backend.

    Note: The ProviderReconciler's autodiscovery is mocked to avoid issues when
    running tests in parallel. Without this mock, the reconciler would try to
    call through the IGW proxy (which isn't available in models-only tests) and
    would also iterate over providers from other tests running in the same worker.

    Yields:
        Tuple of (controller, mock_backend, sync_sdk) for testing
    """
    mock_backend = mock_backend_registry.get_backend()

    # Create controller with mock backend registry
    # We need to patch the SDK factory and platform config (used in config and main modules)
    mock_platform_config = MagicMock()
    mock_platform_config.models_url = "http://testserver"
    mock_platform_config.get_service_url.return_value = "http://testserver"
    with (
        patch("nmp.core.models.config.get_platform_config", return_value=mock_platform_config),
        patch("nmp.core.models.controllers.main.get_platform_config", return_value=mock_platform_config),
        patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk") as mock_sdk_factory,
    ):
        mock_sdk_factory.return_value = test_clients.async_sdk

        controller = ModelsController(
            backend_registry=mock_backend_registry,
            stop_signal=None,
        )

        # Mock the provider reconciler to avoid issues in parallel test execution.
        # The reconciler tries to call through the IGW proxy for autodiscovery,
        # which isn't available in models-only tests.
        controller._provider_reconciler.reconcile_model_providers = AsyncMock(return_value=None)

        yield controller, mock_backend, test_clients.sdk

        # Clean up controller resources (event loop, backend registry, etc.)
        controller.shutdown()


# =============================================================================
# Docker Test Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def docker_client() -> Generator[docker.DockerClient, None, None]:
    """Create a Docker client for tests."""
    client = create_docker_client()
    yield client


@pytest.fixture(scope="module")
def mock_nim_image(docker_client: docker.DockerClient) -> Generator[str, None, None]:
    """Build or retrieve the nginx-based mock NIM image."""
    yield ensure_mock_nim_image(docker_client, MOCK_NIM_IMAGE_NAME)


@pytest.fixture(scope="module")
def mock_sidecar_image(docker_client: docker.DockerClient) -> Generator[str, None, None]:
    """Build or retrieve the mock sidecar image with a unique name per service.

    Avoids concurrent-build races across workers. The backend's get_qualified_image
    is patched in controller fixtures to return this name for 'nmp-core'.
    """
    yield ensure_mock_sidecar_image(docker_client, MOCK_SIDECAR_IMAGE_NAME)


@pytest.fixture
def docker_test_context(
    docker_client: docker.DockerClient, request: pytest.FixtureRequest
) -> Generator[DockerTestContext, None, None]:
    """Create a Docker test context with automatic cleanup and diagnostics."""
    ctx = DockerTestContext(docker_client=docker_client)

    yield ctx

    # Check if test failed and print diagnostics
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        ctx.print_diagnostics()

    # Always cleanup
    ctx.cleanup()


@pytest.fixture
def models_controller_container_cleanup(docker_client: docker.DockerClient) -> Generator[None, None, None]:
    """Teardown: remove all containers with label nmp.nvidia.com/managed-by=models-controller.

    Ensures failed tests (e.g. stuck in PENDING) don't leave NIM/sidecar containers.
    Request this via controller_with_docker; no per-test try/finally needed.
    """
    yield
    cleanup_model_deployment_containers(docker_client)


@pytest.fixture
def docker_backend_config(worker_id: str, mock_sidecar_image: str) -> dict[str, Any]:
    """Configuration for Docker backend in tests.

    Uses worker_id from pytest-xdist to allocate unique port ranges per worker.
    Depends on mock_sidecar_image so the image get_qualified_image('nmp-core')
    exists before any test runs.
    """
    start_port, end_port = get_worker_port_range(worker_id)
    return {
        "models_docker_port_range_start": start_port,
        "models_docker_port_range_end": end_port,
        "docker_timeout": 60,
        "models_docker_host_service_name": "localhost",
    }


# =============================================================================
# Pytest Hooks
# =============================================================================


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, None, None]:
    """Store test results on the item for fixture access."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)
