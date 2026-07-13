# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
import threading
import time
import traceback
from typing import TypedDict, cast, get_args

import nemo_platform
from nemo_platform import APIStatusError, NeMoPlatform
from nemo_platform.types import PlatformJobStatus as SDKPlatformJobStatus
from nemo_platform.types.jobs import PlatformJobStepWithContext
from nemo_platform.types.jobs.platform_job_steps_list_filter_param import PlatformJobStepsListFilterParam
from nmp.common.controller import Controller
from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.common.observability import start_span_with_ctx
from nmp.core.jobs.app.ctx import JobBackendContext, JobContext
from nmp.core.jobs.controllers.backends import JobUpdate, extract_provider_profile
from nmp.core.jobs.controllers.backends.exceptions import ResourceAllocationError, SchedulingDeferred
from nmp.core.jobs.controllers.backends.registry import BackendRegistry
from nmp.core.jobs.controllers.diagnostics import log_job_diagnostics_if_debug
from opentelemetry import metrics, trace

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)
logger = logging.getLogger(__name__)

DEFAULT_PROFILE = "default"
DEFAULT_PROVIDER = "cpu"
SDK_PLATFORM_JOB_STATUSES = frozenset(get_args(SDKPlatformJobStatus))


class StepStatusDetailParams(TypedDict, total=False):
    status_details: dict[str, object]
    error_details: dict[str, object]


def as_sdk_platform_job_status(status: str) -> SDKPlatformJobStatus:
    if status not in SDK_PLATFORM_JOB_STATUSES:
        raise ValueError(f"Unsupported platform job status: {status}")
    return cast(SDKPlatformJobStatus, status)


class JobScheduler(Controller):
    def __init__(
        self,
        backend_registry: BackendRegistry,
        nmp_sdk: NeMoPlatform,
        stop_signal: threading.Event | None = None,
    ) -> None:
        self._backend_registry = backend_registry
        self._nmp_sdk = nmp_sdk
        self._stop_signal = stop_signal
        self._is_healthy = False
        self._logger = logger

        self._step_scheduled_total = meter.create_counter(
            name="nmp.jobs.scheduler.step.scheduled.total",
            description="Total number of job scheduling attempts",
        )
        self._step_scheduling_errors = meter.create_counter(
            name="nmp.jobs.scheduler.step.scheduling.errors",
            description="Number of job scheduling errors",
        )

    @property
    def is_healthy(self) -> bool:
        return self._is_healthy

    def step(self):
        # Check stop signal before making any API calls
        if self._stop_signal and self._stop_signal.is_set():
            logger.debug("Stop signal received, skipping scheduling step")
            return

        steps = []
        fetch_started_at = time.monotonic()
        with tracer.start_as_current_span("jobs_scheduler/fetch_steps_for_scheduling"):
            try:
                steps = self.get_steps_for_scheduling()
                self._is_healthy = True
            except nemo_platform.APIError:
                self._is_healthy = False
                logger.exception("Could not fetch job steps for scheduling", exc_info=True)
                return

        if len(steps) > 0:
            logger.info(f"Got {len(steps)} job steps to schedule")
        else:
            logger.debug("No job steps to schedule")
        logger.debug(
            "Scheduler fetched job steps",
            extra={"count": len(steps), "duration_seconds": time.monotonic() - fetch_started_at},
        )
        for step in steps:
            with start_span_with_ctx(
                tracer, "jobs_scheduler/schedule_step", JobContext(id=step.job, step_name=step.name)
            ):
                try:
                    schedule_started_at = time.monotonic()
                    update = self.schedule_step(step)
                    logger.debug(
                        "Scheduled job step",
                        extra={
                            "job": step.job,
                            "step": step.name,
                            "workspace": step.workspace,
                            "duration_seconds": time.monotonic() - schedule_started_at,
                            "status": update.status,
                        },
                    )
                    try:
                        self._update_step_status_with_timing(
                            step=step,
                            phase="schedule",
                            status=update.status,
                            status_details=update.status_details,
                            error_details=update.error_details,
                        )
                    except APIStatusError as e:
                        # Stopgap for a scheduler/reconciler race: by the time the scheduler persists
                        # CREATED -> PENDING, another controller pass may already have advanced the
                        # step to ACTIVE (or later). In that case, treating the stale PENDING write
                        # as fatal incorrectly marks a healthy job as ERROR. The real fix is to
                        # properly serialize step state transitions so stale controller writes do not
                        # happen in the first place.
                        if self._should_ignore_conflicting_pending_update(step, update, e):
                            logger.info(
                                "Ignoring stale pending update for job step that already advanced",
                                extra={
                                    "job": step.job,
                                    "step": step.name,
                                    "workspace": step.workspace,
                                },
                            )
                            continue
                        raise

                except ResourceAllocationError as e:
                    logger.info(
                        f"Could not schedule job '{step.job}' step '{step.name}' due to resource constraints: {e.message}. Marking step as error."
                    )
                    log_job_diagnostics_if_debug(
                        self._nmp_sdk,
                        step,
                        logger=self._logger,
                        context="resource allocation error during scheduling",
                    )
                    self._step_scheduling_errors.add(1, attributes={"error_type": "resource_allocation"})
                    self._update_step_status_with_timing(
                        step=step,
                        phase="resource_allocation_error",
                        status=PlatformJobStatus.ERROR.value,
                        status_details={"message": e.message},
                        error_details={"message": e.message},
                    )
                except SchedulingDeferred as e:
                    logger.debug(
                        "Scheduling deferred for job step",
                        extra={
                            "job": step.job,
                            "step": step.name,
                            "workspace": step.workspace,
                            "reason": e.message,
                        },
                    )
                except Exception as e:
                    logger.exception("Could not schedule job step", exc_info=True)
                    log_job_diagnostics_if_debug(
                        self._nmp_sdk,
                        step,
                        logger=self._logger,
                        context="unexpected scheduling error",
                    )
                    self._step_scheduling_errors.add(1, attributes={"error_type": "unknown"})
                    self._update_step_status_with_timing(
                        step=step,
                        phase="unexpected_error",
                        status=PlatformJobStatus.ERROR.value,
                        status_details={"message": str(e)},
                        error_details={"message": str(e), "error": traceback.format_exc()},
                    )

    def _update_step_status_with_timing(
        self,
        *,
        step: PlatformJobStepWithContext,
        phase: str,
        status: str,
        status_details: dict[str, object] | None = None,
        error_details: dict[str, object] | None = None,
    ):
        started_at = time.monotonic()
        detail_params: StepStatusDetailParams = {}
        if status_details is not None:
            detail_params["status_details"] = status_details
        if error_details is not None:
            detail_params["error_details"] = error_details
        try:
            response = self._nmp_sdk.jobs.steps.update_status(
                step.name,
                workspace=step.workspace,
                job=step.job,
                status=as_sdk_platform_job_status(status),
                **detail_params,
            )
        except Exception:
            logger.warning(
                "Scheduler step status update failed",
                extra={
                    "job": step.job,
                    "step": step.name,
                    "workspace": step.workspace,
                    "phase": phase,
                    "from_status": step.status,
                    "to_status": status,
                    "duration_seconds": time.monotonic() - started_at,
                },
            )
            raise
        logger.debug(
            "Scheduler step status update succeeded",
            extra={
                "job": step.job,
                "step": step.name,
                "workspace": step.workspace,
                "phase": phase,
                "from_status": step.status,
                "to_status": status,
                "duration_seconds": time.monotonic() - started_at,
            },
        )
        return response

    def get_steps_for_scheduling(self) -> list[PlatformJobStepWithContext]:
        """
        Return the oldest set of steps to schedule. We using the
        set of pending steps as our queue for what to schedule next.
        """
        # Iterate through all pages to get all steps
        steps = []
        filter_params: PlatformJobStepsListFilterParam = {
            "status": [PlatformJobStatus.CREATED.value, PlatformJobStatus.RESUMING.value]
        }
        for step in self._nmp_sdk.jobs.steps.list(
            name="-",  # Use "-" to indicate all jobs
            workspace="-",  # Cross-workspace query
            filter=filter_params,
            sort="created_at",
        ):
            steps.append(step)
        return steps

    def schedule_step(self, step: PlatformJobStepWithContext) -> JobUpdate:
        provider, profile = extract_provider_profile(step)
        backend = self._backend_registry.get_backend(profile=profile, provider=provider)
        self._step_scheduled_total.add(1, attributes={"provider": provider, "profile": profile})
        with start_span_with_ctx(
            tracer,
            "job_scheduler/schedule_step_with_backend",
            JobBackendContext(provider=provider, profile=profile, name=str(backend)),
        ):
            assert step.step_spec is not None
            return backend.schedule(step.step_spec.executor, step)

    def _should_ignore_conflicting_pending_update(
        self,
        step: PlatformJobStepWithContext,
        update: JobUpdate,
        error: APIStatusError,
    ) -> bool:
        if error.status_code != 409 or update.status != PlatformJobStatus.PENDING.value:
            return False

        current_step = self._nmp_sdk.jobs.steps.retrieve(
            step.name,
            workspace=step.workspace,
            job=step.job,
        )
        original_status = PlatformJobStatus(step.status)
        current_status = PlatformJobStatus(current_step.status)
        return current_status != original_status and original_status.can_transition_to(current_status)
