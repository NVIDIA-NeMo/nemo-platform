# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch

import httpx
from nemo_platform_plugin.client.errors import ConflictError, NemoTransportError
from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.core.jobs.api.v2.jobs.schemas import PlatformJobStepWithContext
from nmp.core.jobs.controllers.backends.exceptions import ResourceAllocationError, SchedulingDeferred
from nmp.core.jobs.controllers.backends.registry import BackendRegistry
from nmp.core.jobs.controllers.backends.test import MockDockerCPUJobBackend
from nmp.core.jobs.controllers.scheduler import JobScheduler
from pytest import fixture

from services.core.jobs.tests.controllers.client_mocks import data_response, paginated_response


def _conflict_error(detail: str) -> ConflictError:
    """Build a client ``ConflictError`` (HTTP 409) with the given detail message."""
    request = httpx.Request(
        "PATCH", "http://localhost/apis/jobs/v2/workspaces/default/jobs/test-job-id/steps/test-step/status"
    )
    response = httpx.Response(409, request=request, json={"detail": detail})
    return ConflictError(response)


@fixture
def job_scheduler(backend_registry: BackendRegistry, mock_nmp_client) -> JobScheduler:
    return JobScheduler(backend_registry, mock_nmp_client)


def test_does_schedule_job(
    job_scheduler: JobScheduler,
    backend_registry: BackendRegistry,
    mock_nmp_client,
    mock_jobs_client,
    test_step_pending: PlatformJobStepWithContext,
):
    # Mock the jobs list response
    mock_jobs_client.list_steps.return_value = paginated_response([test_step_pending])

    # Get the test backend from the registry
    backend = backend_registry.get_backend(provider="cpu", profile="default")
    assert isinstance(backend, MockDockerCPUJobBackend)
    test_backend = backend

    # Run scheduler step
    job_scheduler.step()

    # Verify the typed Jobs client was called with the correct deepObject filter.
    # The status list is encoded as ``filter[status]=created,resuming`` (comma form).
    mock_jobs_client.list_steps.assert_called_once_with(
        workspace="-",
        name="-",
        query_params={
            "filter[status]": "created,resuming",
            "sort": "created_at",
        },
    )

    # Test backend should have received one schedule call for our test job
    assert len(test_backend.mock.schedule_calls) == 1
    assert test_backend.mock.schedule_calls[0]["step"].id == test_step_pending.id
    assert test_backend.mock.sync_calls == []


def test_scheduling_deferred_leaves_step_created(
    job_scheduler: JobScheduler,
    mock_nmp_client,
    mock_jobs_client,
    test_step_pending: PlatformJobStepWithContext,
):
    mock_jobs_client.list_steps.return_value = paginated_response([test_step_pending])

    with patch.object(job_scheduler, "schedule_step", side_effect=SchedulingDeferred("capacity full")):
        job_scheduler.step()

    mock_jobs_client.update_job_step_status.assert_not_called()


def test_resource_allocation_error_marks_step_as_error(
    job_scheduler: JobScheduler,
    mock_nmp_client,
    mock_jobs_client,
    test_step_pending: PlatformJobStepWithContext,
):
    """When ResourceAllocationError is raised (e.g. no GPUs), scheduler marks step as error with error_details."""
    mock_jobs_client.list_steps.return_value = paginated_response([test_step_pending])
    error_message = "No GPUs available on this system. GPU jobs require a system with NVIDIA GPUs."

    with patch.object(job_scheduler, "schedule_step", side_effect=ResourceAllocationError(error_message)):
        job_scheduler.step()

    mock_jobs_client.update_job_step_status.assert_called_once()
    call = mock_jobs_client.update_job_step_status.call_args
    assert call.kwargs["name"] == test_step_pending.name
    assert call.kwargs["workspace"] == test_step_pending.workspace
    assert call.kwargs["job"] == test_step_pending.job
    body = call.kwargs["body"]
    assert body.status == PlatformJobStatus.ERROR
    assert body.status_details == {"message": error_message}
    assert body.error_details == {"message": error_message}


def test_scheduler_logs_diagnostics_for_unexpected_schedule_error_in_debug_mode(
    job_scheduler: JobScheduler,
    mock_nmp_client,
    mock_jobs_client,
    test_step_pending: PlatformJobStepWithContext,
):
    mock_jobs_client.list_steps.return_value = paginated_response([test_step_pending])

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
    mock_jobs_client,
    test_step_pending: PlatformJobStepWithContext,
):
    mock_jobs_client.list_steps.return_value = paginated_response([test_step_pending])

    conflict = _conflict_error(
        "Invalid status transition from PlatformJobStatus.ACTIVE to PlatformJobStatus.PENDING for step test-step-id"
    )
    active_step = test_step_pending.model_copy(update={"status": PlatformJobStatus.ACTIVE})
    mock_jobs_client.update_job_step_status.side_effect = [conflict]
    get_step_resp = active_step
    mock_jobs_client.get_job_step.return_value.data.return_value = get_step_resp

    job_scheduler.step()

    mock_jobs_client.update_job_step_status.assert_called_once()
    update_call = mock_jobs_client.update_job_step_status.call_args
    assert update_call.kwargs["name"] == test_step_pending.name
    assert update_call.kwargs["workspace"] == test_step_pending.workspace
    assert update_call.kwargs["job"] == test_step_pending.job
    assert update_call.kwargs["body"].status == PlatformJobStatus.PENDING

    mock_jobs_client.get_job_step.assert_called_once_with(
        name=test_step_pending.name,
        workspace=test_step_pending.workspace,
        job=test_step_pending.job,
    )


def test_scheduler_does_not_ignore_pending_update_conflict_when_step_remains_resuming(
    job_scheduler: JobScheduler,
    mock_nmp_client,
    mock_jobs_client,
    test_step_pending: PlatformJobStepWithContext,
):
    resuming_step = test_step_pending.model_copy(update={"status": PlatformJobStatus.RESUMING})
    mock_jobs_client.list_steps.return_value = paginated_response([resuming_step])

    conflict = _conflict_error(
        "Invalid status transition from PlatformJobStatus.RESUMING to PlatformJobStatus.PENDING for step test-step-id"
    )
    # First call (CREATED->PENDING) conflicts; the second call (marking ERROR) succeeds
    # and its response is chained with ``.data()`` by the scheduler.
    mock_jobs_client.update_job_step_status.side_effect = [conflict, data_response(None)]
    mock_jobs_client.get_job_step.return_value.data.return_value = resuming_step

    job_scheduler.step()

    assert mock_jobs_client.update_job_step_status.call_count == 2
    error_call = mock_jobs_client.update_job_step_status.call_args_list[1]
    error_body = error_call.kwargs["body"]
    assert error_body.status == PlatformJobStatus.ERROR
    assert "409" in error_body.status_details["message"]
    mock_jobs_client.get_job_step.assert_called_once_with(
        name=resuming_step.name,
        workspace=resuming_step.workspace,
        job=resuming_step.job,
    )


def test_scheduler_marks_itself_unhealthy_after_transport_failure(
    job_scheduler: JobScheduler,
    mock_jobs_client,
):
    mock_jobs_client.list_steps.return_value = paginated_response([])
    job_scheduler.step()
    assert job_scheduler.is_healthy

    request = httpx.Request("GET", "http://localhost/apis/jobs/v2/workspaces/-/jobs/-/steps")
    mock_jobs_client.list_steps.side_effect = NemoTransportError(
        httpx.ConnectError("Connection refused", request=request)
    )
    job_scheduler.step()

    assert not job_scheduler.is_healthy
