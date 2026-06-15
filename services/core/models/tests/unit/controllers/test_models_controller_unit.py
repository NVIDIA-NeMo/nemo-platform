# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ModelsController."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nmp.core.models.config import config as models_config
from nmp.core.models.controllers.context import ModelContext
from nmp.core.models.controllers.models_controller import NON_TERMINAL_STATES, ModelsController


class MockAsyncPaginator:
    """Mock async paginator to simulate SDK's paginated response."""

    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)


def test_controller_initialization(mock_sdk_class_patch, mock_get_config_patch, mock_backend_registry, assert_helpers):
    """Test that ModelsController initializes correctly."""
    # Create controller
    controller = ModelsController(backend_registry=mock_backend_registry)

    # Verify initialization
    assert_helpers.assert_controller_initialized(controller, mock_backend_registry)
    assert_helpers.assert_sdk_initialized_correctly(mock_sdk_class_patch)
    assert controller._provider_reconciler._controller_config is models_config.controller


def test_step_with_no_deployments(
    mock_sdk_class_patch, mock_get_config_patch, mock_asyncio_run_patch, mock_backend_registry, assert_helpers
):
    """Test step() when no deployments are found."""
    # Mock asyncio.run to return empty list
    mock_asyncio_run_patch.return_value = []

    controller = ModelsController(backend_registry=mock_backend_registry)

    # Run step
    controller.step()

    # Verify state
    assert_helpers.assert_controller_healthy(controller)
    assert_helpers.assert_asyncio_run_called_once(mock_asyncio_run_patch)


def test_step_with_deployments(
    mock_sdk_class_patch,
    mock_get_config_patch,
    mock_asyncio_run_patch,
    mock_backend_registry,
    sample_deployment,
    sample_deployment_ready,
    assert_helpers,
):
    """Test step() when deployments are found."""
    # Mock asyncio.run to return None (since async_controller_step doesn't return anything)
    mock_asyncio_run_patch.return_value = None

    controller = ModelsController(backend_registry=mock_backend_registry)

    # Run step
    controller.step()

    # Verify state
    assert_helpers.assert_controller_healthy(controller)
    assert_helpers.assert_asyncio_run_called_once(mock_asyncio_run_patch)


def test_step_with_exception(
    mock_sdk_class_patch, mock_get_config_patch, mock_asyncio_run_patch, mock_backend_registry, assert_helpers
):
    """Test step() when an exception occurs."""
    # Mock asyncio.run to raise exception
    mock_asyncio_run_patch.side_effect = Exception("Test error")

    controller = ModelsController(backend_registry=mock_backend_registry)

    # Run step and expect exception
    with pytest.raises(Exception, match="Test error"):
        controller.step()

    # Verify controller is not healthy
    assert_helpers.assert_controller_healthy(controller, is_healthy=False)


# SDK Call Tests


@pytest.mark.asyncio
async def test_get_non_terminal_deployments_calls_sdk(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry, sample_deployment
):
    """Test that retrieve_non_terminal_deployments calls SDK with correct statuses."""
    # Setup SDK mock responses - SDK returns AsyncPaginator for each call
    # Use MagicMock (not AsyncMock) because .list() returns an async iterator, not a coroutine
    mock_models_sdk.inference.deployments.list = MagicMock(
        side_effect=lambda **kwargs: MockAsyncPaginator([sample_deployment])
    )

    # Create controller and inject mock SDK
    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)

        # Call retrieve_non_terminal_deployments
        deployment_contexts = await controller.retrieve_non_terminal_deployments()

        # Verify SDK was called for each non-terminal status
        assert mock_models_sdk.inference.deployments.list.call_count == len(NON_TERMINAL_STATES)

        # Verify we got ModelContext objects back
        assert len(deployment_contexts) > 0
        for ctx in deployment_contexts:
            assert isinstance(ctx, ModelContext)
            assert ctx.model_deployment == sample_deployment


@pytest.mark.asyncio
async def test_get_non_terminal_deployments_handles_sdk_errors(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry
):
    """Test that retrieve_non_terminal_deployments handles SDK errors gracefully."""

    # Setup SDK mock to raise exception on first call, succeed on others
    def side_effect(**kwargs):
        filter_dict = kwargs.get("filter", {})
        status = filter_dict.get("status")
        if status == "CREATED":
            raise Exception("API Error")
        return MockAsyncPaginator([])

    # Use MagicMock (not AsyncMock) because .list() returns an async iterator, not a coroutine
    mock_models_sdk.inference.deployments.list = MagicMock(side_effect=side_effect)

    # Create controller and inject mock SDK
    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)

        # Call retrieve_non_terminal_deployments
        deployment_contexts = await controller.retrieve_non_terminal_deployments()

        # Verify it returns a list even with errors (errors are logged but not raised)
        assert isinstance(deployment_contexts, list)


@pytest.mark.asyncio
async def test_get_non_terminal_deployments_with_multiple_deployments(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry, sample_deployment, sample_deployment_ready
):
    """Test that retrieve_non_terminal_deployments processes multiple deployments."""
    # Add required fields for deployment fixture to work with ModelContext
    sample_deployment.config = None
    sample_deployment.config_version = None
    sample_deployment.model_provider_id = None

    sample_deployment_ready.config = None
    sample_deployment_ready.config_version = None
    sample_deployment_ready.model_provider_id = None

    # Setup SDK mock responses - return different deployments for each status
    def list_side_effect(**kwargs):
        filter_dict = kwargs.get("filter", {})
        status = filter_dict.get("status")
        if status == "CREATED":
            return MockAsyncPaginator([sample_deployment])
        elif status == "READY":
            return MockAsyncPaginator([sample_deployment_ready])
        return MockAsyncPaginator([])

    # Use MagicMock (not AsyncMock) because .list() returns an async iterator, not a coroutine
    mock_models_sdk.inference.deployments.list = MagicMock(side_effect=list_side_effect)

    # Create controller and inject mock SDK
    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)

        # Call retrieve_non_terminal_deployments
        deployment_contexts = await controller.retrieve_non_terminal_deployments()

        # Verify we got ModelContext objects for both deployments
        assert len(deployment_contexts) == 2

        # Extract deployments from contexts
        deployments = [ctx.model_deployment for ctx in deployment_contexts]
        assert sample_deployment in deployments
        assert sample_deployment_ready in deployments


@pytest.mark.asyncio
async def test_get_model_providers_calls_sdk(mock_get_config_patch, mock_models_sdk, mock_backend_registry):
    """Test that get_model_providers calls SDK to list providers."""
    # Setup SDK mock responses
    mock_provider = MagicMock()
    mock_provider.name = "test-provider"
    mock_provider.workspace = "test-ns"
    mock_provider.model_deployment_id = None

    # Use MagicMock (not AsyncMock) because .list() returns an async iterator, not a coroutine
    mock_models_sdk.inference.providers.list = MagicMock(return_value=MockAsyncPaginator([mock_provider]))

    # Create controller and inject mock SDK
    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)

        # Call get_model_providers
        provider_contexts = await controller.retrieve_model_providers()

        # Verify SDK was called
        mock_models_sdk.inference.providers.list.assert_called_once()

        # Verify we got ModelContext objects back
        assert provider_contexts is not None
        assert len(provider_contexts) == 1
        assert isinstance(provider_contexts[0], ModelContext)
        assert provider_contexts[0].model_provider == mock_provider


@pytest.mark.asyncio
async def test_async_controller_step_calls_reconcilers(mock_get_config_patch, mock_models_sdk, mock_backend_registry):
    """Test that async_controller_step calls both reconcilers."""
    # Setup SDK mocks
    mock_deployment = MagicMock()
    mock_deployment.status = "CREATED"
    mock_deployment.config = None
    mock_deployment.config_version = None
    mock_deployment.model_provider_id = None

    mock_provider = MagicMock()
    mock_provider.model_deployment_id = None

    # Mock SDK to return deployment only for CREATED status
    def list_deployments_side_effect(**kwargs):
        filter_dict = kwargs.get("filter", {})
        status = filter_dict.get("status")
        if status == "CREATED":
            return MockAsyncPaginator([mock_deployment])
        return MockAsyncPaginator([])

    # Use MagicMock (not AsyncMock) because .list() returns an async iterator, not a coroutine
    mock_models_sdk.inference.deployments.list = MagicMock(side_effect=list_deployments_side_effect)
    mock_models_sdk.inference.providers.list = MagicMock(return_value=MockAsyncPaginator([mock_provider]))

    # Create controller and inject mock SDK
    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)

        # Mock the reconciler methods to track calls
        controller._deployment_reconciler.reconcile_deployments = AsyncMock()
        controller._provider_reconciler.reconcile_model_providers = AsyncMock()

        # Call async_controller_step
        await controller.async_controller_step()

        # Verify both reconcilers were called
        controller._deployment_reconciler.reconcile_deployments.assert_called_once()
        controller._provider_reconciler.reconcile_model_providers.assert_called_once()

        # Verify they were called with ModelContext objects
        deployment_contexts = controller._deployment_reconciler.reconcile_deployments.call_args[0][0]
        assert len(deployment_contexts) == 1
        assert isinstance(deployment_contexts[0], ModelContext)
        assert deployment_contexts[0].model_deployment == mock_deployment

        provider_contexts = controller._provider_reconciler.reconcile_model_providers.call_args[0][0]
        assert len(provider_contexts) == 1
        assert isinstance(provider_contexts[0], ModelContext)
        assert provider_contexts[0].model_provider == mock_provider


@pytest.mark.asyncio
async def test_async_controller_step_runs_provider_reconciler_with_no_providers(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry
):
    """The provider reconciler still runs with an empty list so VM orphan cleanup can execute."""
    mock_models_sdk.inference.deployments.list = MagicMock(return_value=MockAsyncPaginator([]))
    mock_models_sdk.inference.providers.list = MagicMock(return_value=MockAsyncPaginator([]))

    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)

        controller._deployment_reconciler.reconcile_deployments = AsyncMock()
        controller._deployment_reconciler.reconcile_orphans = AsyncMock()
        controller._deployment_reconciler.gc_error_deployments = AsyncMock()
        controller._provider_reconciler.reconcile_model_providers = AsyncMock()

        await controller.async_controller_step()

        controller._provider_reconciler.reconcile_model_providers.assert_awaited_once_with([])


@pytest.mark.asyncio
async def test_async_controller_step_skips_provider_reconciler_when_provider_listing_fails(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry
):
    """A provider list failure must not look like a successful empty list to cleanup."""
    mock_models_sdk.inference.deployments.list = MagicMock(return_value=MockAsyncPaginator([]))
    mock_models_sdk.inference.providers.list = MagicMock(side_effect=RuntimeError("providers unavailable"))

    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)

        controller._deployment_reconciler.reconcile_deployments = AsyncMock()
        controller._deployment_reconciler.reconcile_orphans = AsyncMock()
        controller._deployment_reconciler.gc_error_deployments = AsyncMock()
        controller._provider_reconciler.reconcile_model_providers = AsyncMock()

        await controller.async_controller_step()

        controller._provider_reconciler.reconcile_model_providers.assert_not_called()


# =============================================================================
# Shutdown and Cancellation Tests
# =============================================================================


def test_step_handles_cancelled_error(
    mock_sdk_class_patch, mock_get_config_patch, mock_asyncio_run_patch, mock_backend_registry
):
    """Test that step() handles CancelledError gracefully without raising."""
    mock_asyncio_run_patch.side_effect = asyncio.CancelledError()

    controller = ModelsController(backend_registry=mock_backend_registry)

    # Should not raise -- CancelledError is expected during shutdown
    controller.step()

    # Controller should not be marked healthy (step didn't complete)
    assert controller._is_healthy is False


def test_step_skips_when_stop_signal_set(
    mock_sdk_class_patch, mock_get_config_patch, mock_asyncio_run_patch, mock_backend_registry
):
    """Test that step() skips execution when stop signal is already set."""
    stop_signal = threading.Event()
    stop_signal.set()

    controller = ModelsController(backend_registry=mock_backend_registry, stop_signal=stop_signal)
    controller.step()

    # run_until_complete should NOT have been called
    mock_asyncio_run_patch.assert_not_called()


def test_cancel_step_no_op_when_no_task(mock_sdk_class_patch, mock_get_config_patch, mock_backend_registry):
    """Test that cancel_step() is a no-op when no step is running."""
    controller = ModelsController(backend_registry=mock_backend_registry)

    # Should not raise
    controller.cancel_step()
    assert controller._current_task is None


def test_cancel_step_no_op_when_loop_closed(mock_sdk_class_patch, mock_get_config_patch, mock_backend_registry):
    """Test that cancel_step() is a no-op when event loop is closed."""
    controller = ModelsController(backend_registry=mock_backend_registry)
    controller._loop.close()

    # Set a fake task to verify cancel is NOT called when loop is closed
    mock_task = MagicMock()
    mock_task.done.return_value = False
    controller._current_task = mock_task

    controller.cancel_step()
    mock_task.cancel.assert_not_called()


def test_cancel_step_schedules_task_cancellation(mock_sdk_class_patch, mock_get_config_patch, mock_backend_registry):
    """Test that cancel_step() schedules task.cancel() via call_soon_threadsafe."""
    controller = ModelsController(backend_registry=mock_backend_registry)

    # Create a mock task and attach it
    mock_task = MagicMock()
    mock_task.done.return_value = False
    controller._current_task = mock_task

    # Mock call_soon_threadsafe on the event loop
    controller._loop.call_soon_threadsafe = MagicMock()

    controller.cancel_step()

    controller._loop.call_soon_threadsafe.assert_called_once_with(mock_task.cancel)


def test_cancel_step_no_op_when_task_already_done(mock_sdk_class_patch, mock_get_config_patch, mock_backend_registry):
    """Test that cancel_step() is a no-op when the task is already done."""
    controller = ModelsController(backend_registry=mock_backend_registry)

    mock_task = MagicMock()
    mock_task.done.return_value = True
    controller._current_task = mock_task

    controller._loop.call_soon_threadsafe = MagicMock()

    controller.cancel_step()

    controller._loop.call_soon_threadsafe.assert_not_called()


def test_shutdown_closes_loop_and_backends(mock_sdk_class_patch, mock_get_config_patch, mock_backend_registry):
    """Test that shutdown() closes the event loop and shuts down all backends."""
    controller = ModelsController(backend_registry=mock_backend_registry)

    controller.shutdown()

    assert controller._loop.is_closed()
    mock_backend_registry.shutdown_all_backends.assert_called_once()


def test_shutdown_idempotent(mock_sdk_class_patch, mock_get_config_patch, mock_backend_registry):
    """Test that calling shutdown() twice does not raise."""
    controller = ModelsController(backend_registry=mock_backend_registry)

    controller.shutdown()
    controller.shutdown()  # Should not raise

    assert controller._loop.is_closed()
    # shutdown_all_backends called each time (backends should be idempotent)
    assert mock_backend_registry.shutdown_all_backends.call_count == 2


# =============================================================================
# _retrieve_model_entity_for_config tests (model_entity_id precedence)
# =============================================================================


@pytest.mark.asyncio
async def test_retrieve_model_entity_for_config_uses_model_entity_id_when_set(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry
):
    """When config.model_entity_id is set, it takes precedence over nim_deployment."""
    mock_entity = MagicMock()
    mock_entity.workspace = "my-ws"
    mock_entity.name = "my-model"
    mock_models_sdk.models.retrieve = AsyncMock(return_value=mock_entity)

    config = MagicMock()
    config.model_entity_id = "my-ws/my-model"
    config.model_spec = MagicMock()
    config.model_spec.model_namespace = "other-ns"
    config.model_spec.model_name = "other-model"
    config.model_spec.model_revision = None

    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)
        result = await controller._retrieve_model_entity_for_config(config)

    assert result is mock_entity
    mock_models_sdk.models.retrieve.assert_called_once_with(name="my-model", workspace="my-ws")


@pytest.mark.asyncio
async def test_retrieve_model_entity_for_config_uses_model_entity_id_with_revision(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry
):
    """When config.model_entity_id includes @revision, revision is passed to retrieve."""
    mock_entity = MagicMock()
    mock_models_sdk.models.retrieve = AsyncMock(return_value=mock_entity)

    config = MagicMock()
    config.model_entity_id = "my-ws/my-model@v2"
    config.model_spec = MagicMock()

    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)
        result = await controller._retrieve_model_entity_for_config(config)

    assert result is mock_entity
    mock_models_sdk.models.retrieve.assert_called_once_with(name="my-model@v2", workspace="my-ws")
    call_kw = mock_models_sdk.models.retrieve.call_args[1]
    assert call_kw["name"] == "my-model@v2"
    assert call_kw["workspace"] == "my-ws"


@pytest.mark.asyncio
async def test_retrieve_model_entity_for_config_falls_back_to_nim_deployment_when_no_model_entity_id(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry
):
    """When config.model_entity_id is not set, entity is derived from nim_deployment."""
    mock_entity = MagicMock()
    mock_models_sdk.models.retrieve = AsyncMock(return_value=mock_entity)

    config = MagicMock()
    config.model_entity_id = None
    config.model_spec = MagicMock()
    config.model_spec.model_namespace = "nim-ns"
    config.model_spec.model_name = "nim-model"
    config.model_spec.model_revision = "v1"

    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)
        result = await controller._retrieve_model_entity_for_config(config)

    assert result is mock_entity
    mock_models_sdk.models.retrieve.assert_called_once_with(name="nim-model@v1", workspace="nim-ns")


@pytest.mark.asyncio
async def test_retrieve_model_entity_for_config_returns_none_when_no_nim_deployment_and_no_model_entity_id(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry
):
    """When neither model_entity_id nor nim_deployment has model info, returns None."""
    config = MagicMock()
    config.model_entity_id = None
    config.model_spec = None

    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)
        result = await controller._retrieve_model_entity_for_config(config)

    assert result is None
    mock_models_sdk.models.retrieve.assert_not_called()


@pytest.mark.asyncio
async def test_retrieve_model_entity_for_config_invalid_model_entity_id_falls_back_to_nim_deployment(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry
):
    """When model_entity_id is set but unparseable (e.g. no slash), fall back to nim_deployment."""
    mock_entity = MagicMock()
    mock_models_sdk.models.retrieve = AsyncMock(return_value=mock_entity)

    config = MagicMock()
    config.model_entity_id = "bogus"
    config.model_spec = MagicMock()
    config.model_spec.model_namespace = "fallback-ns"
    config.model_spec.model_name = "fallback-model"
    config.model_spec.model_revision = None

    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)
        result = await controller._retrieve_model_entity_for_config(config)

    assert result is mock_entity
    mock_models_sdk.models.retrieve.assert_called_once_with(name="fallback-model", workspace="fallback-ns")


# =============================================================================
# ERROR Deployment GC Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_retrieve_error_deployments_calls_sdk(mock_get_config_patch, mock_models_sdk, mock_backend_registry):
    """Test that retrieve_error_deployments calls SDK with ERROR filter."""
    mock_deployment = MagicMock()
    mock_deployment.status = "ERROR"

    mock_models_sdk.inference.deployments.list = MagicMock(return_value=MockAsyncPaginator([mock_deployment]))

    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)
        result = await controller.retrieve_error_deployments()

    assert len(result) == 1
    assert result[0] == mock_deployment

    mock_models_sdk.inference.deployments.list.assert_called_once_with(
        workspace="-",
        filter={"status": "ERROR"},
        all_versions=True,
        page_size=1000,
    )


@pytest.mark.asyncio
async def test_retrieve_error_deployments_handles_sdk_error(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry
):
    """Test that retrieve_error_deployments returns empty list on SDK error."""
    mock_models_sdk.inference.deployments.list = MagicMock(side_effect=Exception("API Error"))

    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)
        result = await controller.retrieve_error_deployments()

    assert result == []


@pytest.mark.asyncio
async def test_async_controller_step_calls_gc(mock_get_config_patch, mock_models_sdk, mock_backend_registry):
    """Test that async_controller_step invokes gc_error_deployments."""
    mock_error_deployment = MagicMock()
    mock_error_deployment.status = "ERROR"

    mock_provider = MagicMock()
    mock_provider.model_deployment_id = None

    call_count = 0

    def list_side_effect(**kwargs):
        nonlocal call_count
        filter_dict = kwargs.get("filter", {})
        status = filter_dict.get("status")
        if status == "ERROR":
            return MockAsyncPaginator([mock_error_deployment])
        return MockAsyncPaginator([])

    mock_models_sdk.inference.deployments.list = MagicMock(side_effect=list_side_effect)
    mock_models_sdk.inference.providers.list = MagicMock(return_value=MockAsyncPaginator([mock_provider]))

    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)

        controller._deployment_reconciler.reconcile_deployments = AsyncMock()
        controller._deployment_reconciler.reconcile_orphans = AsyncMock()
        controller._deployment_reconciler.gc_error_deployments = AsyncMock()
        controller._provider_reconciler.reconcile_model_providers = AsyncMock()

        await controller.async_controller_step()

        controller._deployment_reconciler.gc_error_deployments.assert_called_once()
        gc_args = controller._deployment_reconciler.gc_error_deployments.call_args[0][0]
        assert len(gc_args) == 1
        assert gc_args[0] == mock_error_deployment


@pytest.mark.asyncio
async def test_async_controller_step_skips_gc_when_no_error_deployments(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry
):
    """Test that gc_error_deployments is not called when there are no ERROR deployments."""
    mock_provider = MagicMock()
    mock_provider.model_deployment_id = None

    mock_models_sdk.inference.deployments.list = MagicMock(return_value=MockAsyncPaginator([]))
    mock_models_sdk.inference.providers.list = MagicMock(return_value=MockAsyncPaginator([mock_provider]))

    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry)

        controller._deployment_reconciler.reconcile_deployments = AsyncMock()
        controller._deployment_reconciler.reconcile_orphans = AsyncMock()
        controller._deployment_reconciler.gc_error_deployments = AsyncMock()
        controller._provider_reconciler.reconcile_model_providers = AsyncMock()

        await controller.async_controller_step()

        controller._deployment_reconciler.gc_error_deployments.assert_not_called()


@pytest.mark.asyncio
async def test_async_controller_step_stop_signal_skips_gc(
    mock_get_config_patch, mock_models_sdk, mock_backend_registry
):
    """Test that GC is skipped when stop signal is set before GC runs."""
    stop_signal = threading.Event()

    mock_models_sdk.inference.deployments.list = MagicMock(return_value=MockAsyncPaginator([]))
    mock_models_sdk.inference.providers.list = MagicMock(return_value=MockAsyncPaginator([]))

    with patch("nmp.core.models.controllers.models_controller.get_async_platform_sdk", return_value=mock_models_sdk):
        controller = ModelsController(backend_registry=mock_backend_registry, stop_signal=stop_signal)

        controller._deployment_reconciler.reconcile_deployments = AsyncMock()
        controller._deployment_reconciler.reconcile_orphans = AsyncMock()
        controller._deployment_reconciler.gc_error_deployments = AsyncMock()
        controller._provider_reconciler.reconcile_model_providers = AsyncMock()

        async def set_stop_and_reconcile(*args, **kwargs):
            stop_signal.set()

        controller._deployment_reconciler.reconcile_orphans = AsyncMock(side_effect=set_stop_and_reconcile)

        await controller.async_controller_step()

        controller._deployment_reconciler.gc_error_deployments.assert_not_called()
        controller._provider_reconciler.reconcile_model_providers.assert_not_called()
