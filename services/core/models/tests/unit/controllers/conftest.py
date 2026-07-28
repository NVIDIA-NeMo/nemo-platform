# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Test fixtures for Models Controller tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nmp.common.config import PlatformConfig


def platform_config(
    *,
    base_url: str = "http://localhost:8080",
    service_discovery: dict[str, str] | None = None,
    **kwargs,
) -> PlatformConfig:
    """Create a real PlatformConfig for testing."""
    if service_discovery is None:
        service_discovery = {
            "files": "http://files-service:8000",
            "models": "http://models-api:8000",
        }
    return PlatformConfig(  # type: ignore[abstract]
        base_url=base_url,
        service_discovery=service_discovery,
        **kwargs,
    )


@pytest.fixture
def mock_platform_config():
    """Create a platform config for testing (real PlatformConfig instance)."""
    return platform_config()


@pytest.fixture
def mock_get_config_patch(mock_platform_config):
    """Patch get_platform_config to return mock config.

    Patches in nmp.core.models.config (used when loading backends) and
    nmp.core.models.controllers.main (used in run() for server ready check).
    """
    with (
        patch(
            "nmp.core.models.config.get_platform_config",
            return_value=mock_platform_config,
        ),
        patch(
            "nmp.core.models.controllers.main.get_platform_config",
            return_value=mock_platform_config,
        ),
    ):
        yield


@pytest.fixture
def mock_sdk_class_patch():
    """Patch get_async_platform_sdk factory function."""
    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk") as mock:
        mock.return_value.close = AsyncMock()
        yield mock


@pytest.fixture
def mock_asyncio_run_patch():
    """Patch event loop run_until_complete for controller step tests."""
    # Create a mock event loop with run_until_complete method
    mock_loop = MagicMock()
    with patch("nmp.core.models.controllers.models_controller.asyncio.new_event_loop", return_value=mock_loop):
        yield mock_loop.run_until_complete


@pytest.fixture
def mock_models_sdk():
    """Create a mock AsyncNeMoPlatform SDK for testing."""
    mock_sdk = MagicMock()

    # Set up the nested structure for v2.inference.deployments
    mock_sdk.v2 = MagicMock()
    mock_sdk.v2.inference = MagicMock()
    mock_sdk.v2.inference.deployments = MagicMock()
    mock_sdk.v2.inference.deployments.list = MagicMock()

    return mock_sdk


@pytest.fixture
def mock_backend_registry():
    """Create a mock BackendRegistry for testing."""
    mock_registry = MagicMock()
    mock_backend = MagicMock()
    mock_registry.get_backend.return_value = mock_backend
    mock_registry.list_backends.return_value = ["docker"]
    return mock_registry


@pytest.fixture
def sample_deployment():
    """Create a sample ModelDeployment for testing."""
    deployment = MagicMock()
    deployment.workspace = "default"
    deployment.name = "test-deployment"
    deployment.entity_version = "v1"
    deployment.status = "PENDING"
    deployment.config = None
    deployment.config_version = None
    deployment.model_provider_id = None
    return deployment


@pytest.fixture
def sample_deployment_ready():
    """Create a sample ModelDeployment in READY state for testing."""
    deployment = MagicMock()
    deployment.workspace = "default"
    deployment.name = "ready-deployment"
    deployment.entity_version = "v1"
    deployment.status = "READY"
    deployment.config = None
    deployment.config_version = None
    deployment.model_provider_id = None
    return deployment


@pytest.fixture
def sample_deployment_unknown():
    """Create a sample ModelDeployment in UNKNOWN state for testing."""
    deployment = MagicMock()
    deployment.workspace = "test-ns"
    deployment.name = "unknown-deployment"
    deployment.entity_version = "v2"
    deployment.status = "UNKNOWN"
    return deployment


def _assert_controller_initialized(controller, mock_backend_registry):
    """Assert that controller is properly initialized with expected state."""
    assert controller._is_healthy is False
    assert controller._backend_registry == mock_backend_registry


def _assert_controller_has_required_attributes(controller):
    """Assert that controller has all required attributes."""
    assert hasattr(controller, "_is_healthy")
    assert hasattr(controller, "_backend_registry")
    assert hasattr(controller, "_models_sdk")


def _assert_controller_healthy(controller, is_healthy=True):
    """Assert controller health status."""
    assert controller.is_healthy is is_healthy


def _assert_sdk_initialized_correctly(mock_sdk_class_patch):
    """Assert that get_async_platform_sdk was called with correct args for Models API."""
    # Controller initializes ONE SDK for Models API (base_url is resolved from config inside the factory)
    assert mock_sdk_class_patch.call_count == 1
    call_kwargs = mock_sdk_class_patch.call_args.kwargs
    assert call_kwargs["as_service"] == "models"
    assert call_kwargs["internal"] is True
    assert "http_client" in call_kwargs


def _assert_asyncio_run_called_once(mock_asyncio_run_patch):
    """Assert that asyncio.run was called exactly once."""
    assert mock_asyncio_run_patch.call_count == 1


def _assert_sdk_list_called_for_all_statuses(mock_models_sdk, non_terminal_states_count):
    """Assert that SDK list method was called for each non-terminal status."""
    assert mock_models_sdk.inference.deployments.list.call_count == non_terminal_states_count


def _assert_deployments_count(deployments, expected_count):
    """Assert the number of deployments returned."""
    assert len(deployments) == expected_count


class AssertHelpers:
    """Container for assertion helper functions, accessible via fixture."""

    assert_controller_initialized = staticmethod(_assert_controller_initialized)
    assert_controller_has_required_attributes = staticmethod(_assert_controller_has_required_attributes)
    assert_controller_healthy = staticmethod(_assert_controller_healthy)
    assert_sdk_initialized_correctly = staticmethod(_assert_sdk_initialized_correctly)
    assert_asyncio_run_called_once = staticmethod(_assert_asyncio_run_called_once)
    assert_sdk_list_called_for_all_statuses = staticmethod(_assert_sdk_list_called_for_all_statuses)
    assert_deployments_count = staticmethod(_assert_deployments_count)


@pytest.fixture
def assert_helpers():
    """Fixture providing access to assertion helper functions.

    Usage:
        def test_something(assert_helpers):
            assert_helpers.assert_controller_healthy(controller)
    """
    return AssertHelpers


class AsyncPaginator:
    """Async iterator standing in for the SDK's paginated list() responses."""

    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


_ENTITY_FIELDS = ("model_providers", "fileset", "api_endpoint", "backend_format")


def make_entity(workspace: str, name: str, **attrs):
    """Model Entity stand-in addressable by ModelEntityCache.

    ``model_copy`` mirrors the real model in carrying every field across, which the
    cache relies on when overlaying staged changes onto a snapshot.
    """
    fields = {field: attrs.get(field) for field in _ENTITY_FIELDS}
    entity = MagicMock()
    entity.workspace = workspace
    entity.name = name
    for field, value in fields.items():
        setattr(entity, field, value)

    def _copy(update):
        return make_entity(workspace, name, **{**fields, **update})

    entity.model_copy = MagicMock(side_effect=_copy)
    return entity


async def seed_entity_cache(mock_models_sdk, entity_cache, entities=()):
    """Load the cache from the mock SDK so lookups resolve to ``entities``."""
    mock_models_sdk.models.list = MagicMock(return_value=AsyncPaginator(list(entities)))
    await entity_cache.refresh()
