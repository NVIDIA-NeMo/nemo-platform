# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch

import httpx
from nemo_platform import ConflictError
from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.core.jobs.api.v2.jobs.schemas import PlatformJobStepWithContext
from nmp.core.jobs.controllers.backends.exceptions import ResourceAllocationError, SchedulingDeferred
from nmp.core.jobs.controllers.backends.registry import BackendRegistry
from nmp.core.jobs.controllers.backends.test import MockDockerCPUJobBackend
from nmp.core.jobs.controllers.scheduler import JobScheduler
from pytest import fixture


@fixture
def job_scheduler(backend_registry: BackendRegistry, mock_nmp_client) -> JobScheduler:
    return JobScheduler(backend_registry, mock_nmp_client)


def test_does_schedule_job(
    job_scheduler: JobScheduler,
    backend_registry: BackendRegistry,
    mock_nmp_client,
    test_step_pending: PlatformJobStepWithContext,
):
    # Mock the jobs list response
    mock_nmp_client.jobs.steps.list.return_value = [test_step_pending]

    # Get the test backend from the registry
    backend = backend_registry.get_backend(provider="cpu", profile="default")
    assert isinstance(backend, MockDockerCPUJobBackend)
    test_backend = backend

    # Run scheduler step
    job_scheduler.step()

    # Verify the NeMo Platform client was called with the correct filter
    # Note: MARK_INTERNAL_REQUEST_HEADERS are now set at SDK initialization, not per-request
    mock_nmp_client.jobs.steps.list.assert_called_once_with(
        workspace="-",
        name="-",
        filter={"status": ["created", "resuming"]},
        sort="created_at",
    )

    # Test backend should have received one schedule call for our test job
    assert len(test_backend.mock.schedule_calls) == 1
    assert test_backend.mock.schedule_calls[0]["step"].id == test_step_pending.id
    assert test_backend.mock.sync_calls == []


def test_scheduling_deferred_leaves_step_created(
    job_scheduler: JobScheduler,
    mock_nmp_client,
    test_step_pending: PlatformJobStepWithContext,
):
    mock_nmp_client.jobs.steps.list.return_value = [test_step_pending]

    with patch.object(job_scheduler, "schedule_step", side_effect=SchedulingDeferred("capacity full")):
        job_scheduler.step()

    mock_nmp_client.jobs.steps.update_status.assert_not_called()


def test_resource_allocation_error_marks_step_as_error(
    job_scheduler: JobScheduler,
    mock_nmp_client,
    test_step_pending: PlatformJobStepWithContext,
):
    """When ResourceAllocationError is raised (e.g. no GPUs), scheduler marks step as error with error_details."""
    mock_nmp_client.jobs.steps.list.return_value = [test_step_pending]
    error_message = "No GPUs available on this system. GPU jobs require a system with NVIDIA GPUs."

    with patch.object(job_scheduler, "schedule_step", side_effect=ResourceAllocationError(error_message)):
        job_scheduler.step()

    mock_nmp_client.jobs.steps.update_status.assert_called_once_with(
        test_step_pending.name,
        workspace=test_step_pending.workspace,
        job=test_step_pending.job,
        status=PlatformJobStatus.ERROR,
        status_details={"message": error_message},
        error_details={"message": error_message},
    )


def test_scheduler_logs_diagnostics_for_unexpected_schedule_error_in_debug_mode(
    job_scheduler: JobScheduler,
    mock_nmp_client,
    test_step_pending: PlatformJobStepWithContext,
):
    mock_nmp_client.jobs.steps.list.return_value = [test_step_pending]

    with (
        patch.object(job_scheduler, "schedule_step", side_effect=RuntimeError("boom")),
        patch("nmp.core.jobs.controllers.scheduler.logger.isEnabledFor", return_value=True),
        patch("nmp.core.jobs.controllers.scheduler.log_job_diagnostics_if_debug") as log_diagnostics,
    ):
        job_scheduler.step()

    log_diagnostics.assert_called_once_with(
        mock_nmp_client,
        test_step_pending,
        logger=job_scheduler._logger,
        context="unexpected scheduling error",
    )


def test_scheduler_does_not_mark_step_error_when_pending_update_conflicts_with_concurrent_advance(
    job_scheduler: JobScheduler,
    mock_nmp_client,
    test_step_pending: PlatformJobStepWithContext,
):
    mock_nmp_client.jobs.steps.list.return_value = [test_step_pending]

    request = httpx.Request(
        "PATCH", "http://localhost/apis/jobs/v2/workspaces/default/jobs/test-job-id/steps/test-step/status"
    )
    response = httpx.Response(
        409,
        request=request,
        json={
            "detail": (
                "Invalid status transition from PlatformJobStatus.ACTIVE to "
                "PlatformJobStatus.PENDING for step test-step-id"
            )
        },
    )
    conflict = ConflictError(
        "Error code: 409 - {'detail': 'Invalid status transition from PlatformJobStatus.ACTIVE "
        "to PlatformJobStatus.PENDING for step test-step-id'}",
        response=response,
        body=response.json(),
    )
    active_step = test_step_pending.model_copy(update={"status": PlatformJobStatus.ACTIVE})
    mock_nmp_client.jobs.steps.update_status.side_effect = [conflict]
    mock_nmp_client.jobs.steps.retrieve.return_value = active_step

    job_scheduler.step()

    mock_nmp_client.jobs.steps.update_status.assert_called_once_with(
        test_step_pending.name,
        workspace=test_step_pending.workspace,
        job=test_step_pending.job,
        status=PlatformJobStatus.PENDING,
    )
    mock_nmp_client.jobs.steps.retrieve.assert_called_once_with(
        test_step_pending.name,
        workspace=test_step_pending.workspace,
        job=test_step_pending.job,
    )


def test_scheduler_does_not_ignore_pending_update_conflict_when_step_remains_resuming(
    job_scheduler: JobScheduler,
    mock_nmp_client,
    test_step_pending: PlatformJobStepWithContext,
):
    resuming_step = test_step_pending.model_copy(update={"status": PlatformJobStatus.RESUMING})
    mock_nmp_client.jobs.steps.list.return_value = [resuming_step]

    request = httpx.Request(
        "PATCH", "http://localhost/apis/jobs/v2/workspaces/default/jobs/test-job-id/steps/test-step/status"
    )
    response = httpx.Response(
        409,
        request=request,
        json={
            "detail": (
                "Invalid status transition from PlatformJobStatus.RESUMING to "
                "PlatformJobStatus.PENDING for step test-step-id"
            )
        },
    )
    conflict = ConflictError(
        "Error code: 409 - {'detail': 'Invalid status transition from PlatformJobStatus.RESUMING "
        "to PlatformJobStatus.PENDING for step test-step-id'}",
        response=response,
        body=response.json(),
    )
    mock_nmp_client.jobs.steps.update_status.side_effect = [conflict, None]
    mock_nmp_client.jobs.steps.retrieve.return_value = resuming_step

    job_scheduler.step()

    assert mock_nmp_client.jobs.steps.update_status.call_count == 2
    error_call = mock_nmp_client.jobs.steps.update_status.call_args_list[1]
    assert error_call.kwargs["status"] == PlatformJobStatus.ERROR.value
    assert "409" in error_call.kwargs["status_details"]["message"]
    mock_nmp_client.jobs.steps.retrieve.assert_called_once_with(
        resuming_step.name,
        workspace=resuming_step.workspace,
        job=resuming_step.job,
    )
