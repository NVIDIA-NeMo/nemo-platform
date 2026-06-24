# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, call, patch

from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.core.jobs.api.v2.jobs.schemas import PlatformJobStepWithContext
from nmp.core.jobs.controllers.backends import JobUpdate
from nmp.core.jobs.controllers.backends.registry import BackendRegistry
from nmp.core.jobs.controllers.backends.test import MockDockerCPUJobBackend
from nmp.core.jobs.controllers.reconciler import JobReconciler


def test_job_reconciler_syncs_active_job(
    backend_registry: BackendRegistry,
    test_step_active: PlatformJobStepWithContext,
):
    mock_client = MagicMock()

    # Set up the nested structure that tests expect
    mock_client.jobs = MagicMock()
    mock_client.jobs.list = MagicMock()
    mock_client.jobs.update_status = MagicMock()
    mock_client.jobs.steps = MagicMock()
    mock_client.jobs.steps.list = MagicMock()
    mock_client.jobs.steps.update_status = MagicMock()
    job_reconciler = JobReconciler(backend_registry, mock_client)

    # Mock the jobs list response
    mock_client.jobs.steps.list.return_value = [test_step_active]

    # Get the test backend from the registry
    test_backend = job_reconciler._backend_registry.get_backend(provider="cpu", profile="default")
    assert isinstance(test_backend, MockDockerCPUJobBackend)

    # Run reconciler step
    job_reconciler.step()

    # Verify the NeMo Platform client was called with the correct filter for active steps and pending steps
    # Note: MARK_INTERNAL_REQUEST_HEADERS are now set at SDK initialization, not per-request
    assert mock_client.jobs.steps.list.mock_calls == [
        call(
            workspace="-",
            name="-",
            filter={"status": ["pending", "active", "cancelling", "pausing"]},
            sort="updated_at",
        ),
    ]

    # Test backend should have received one sync call for our test job
    assert len(test_backend.mock.sync_calls) == 1
    assert test_backend.mock.sync_calls[0]["step"].id == test_step_active.id

    # Verify the status update was called with the correct job ID and status
    mock_client.jobs.steps.update_status.assert_called_with(
        "test-step",
        workspace="default",
        job="test-job-id",
        status="completed",
        error_details=None,
        status_details=None,
    )


def test_job_reconciler_logs_diagnostics_for_error_transition_in_debug_mode(
    backend_registry: BackendRegistry,
    test_step_active: PlatformJobStepWithContext,
):
    mock_client = MagicMock()
    mock_client.jobs = MagicMock()
    mock_client.jobs.steps = MagicMock()
    mock_client.jobs.steps.list.return_value = [test_step_active]

    job_reconciler = JobReconciler(backend_registry, mock_client)
    test_backend = job_reconciler._backend_registry.get_backend(provider="cpu", profile="default")
    assert isinstance(test_backend, MockDockerCPUJobBackend)

    with (
        patch.object(test_backend, "sync", return_value=JobUpdate(status=PlatformJobStatus.ERROR.value)),
        patch("nmp.core.jobs.controllers.reconciler.log_job_diagnostics_if_debug") as log_diagnostics,
    ):
        job_reconciler.step()

    log_diagnostics.assert_called_once_with(
        mock_client,
        test_step_active,
        logger=job_reconciler._logger,
        context="step transitioned to error during reconciliation",
    )
