# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
import threading
import time

from nemo_platform import APIError, APIStatusError, NeMoPlatform
from nemo_platform.types.jobs import PlatformJobStepWithContext
from nemo_platform.types.jobs.platform_job_steps_list_filter_param import PlatformJobStepsListFilterParam
from nemo_platform.types.shared.platform_job_status import PlatformJobStatus as SDKPlatformJobStatus
from nmp.common.controller import Controller
from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.common.observability import scoped_app_ctx, start_span_with_ctx
from nmp.core.jobs.app.ctx import JobBackendContext, JobContext
from nmp.core.jobs.controllers.backends import extract_provider_profile
from nmp.core.jobs.controllers.backends.registry import BackendRegistry
from nmp.core.jobs.controllers.diagnostics import log_job_diagnostics_if_debug
from opentelemetry import metrics, trace

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)
logger = logging.getLogger(__name__)


class JobReconciler(Controller):
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

        self._step_reconciliation_total = meter.create_counter(
            name="nmp.jobs.reconciler.step.reconciliation.total",
            description="Total number of job reconciliation attempts",
        )
        self._step_reconciliation_errors = meter.create_counter(
            name="nmp.jobs.reconciler.step.reconciliation.errors",
            description="Number of job reconciliation errors",
        )

    @property
    def is_healthy(self) -> bool:
        return self._is_healthy

    def step(self):
        # Check stop signal before making any API calls
        if self._stop_signal and self._stop_signal.is_set():
            logger.debug("Stop signal received, skipping reconciliation step")
            return

        fetch_started_at = time.monotonic()
        with tracer.start_as_current_span("jobs_reconciler/fetch_steps_for_reconciliation"):
            try:
                statuses: list[SDKPlatformJobStatus] = [
                    PlatformJobStatus.PENDING.value,
                    PlatformJobStatus.ACTIVE.value,
                    PlatformJobStatus.CANCELLING.value,
                    PlatformJobStatus.PAUSING.value,
                ]
                steps_to_reconcile = self.get_steps_for_reconciliation(statuses)
                self._is_healthy = True
            except APIError:
                self._is_healthy = False
                logger.exception("Could not fetch job steps for reconciliation", exc_info=True)
                return

        if len(steps_to_reconcile) > 0:
            logger.info(f"Got {len(steps_to_reconcile)} job steps to reconcile")
        else:
            logger.debug("No job steps to reconcile")
        logger.debug(
            "Reconciler fetched job steps",
            extra={"count": len(steps_to_reconcile), "duration_seconds": time.monotonic() - fetch_started_at},
        )
        for step in steps_to_reconcile:
            with start_span_with_ctx(
                tracer,
                "jobs_reconciler/reconcile_job_step",
                JobContext(id=step.job, step_name=step.name),
            ):
                try:
                    provider, profile = extract_provider_profile(step)
                    backend = self._backend_registry.get_backend(provider=provider, profile=profile)
                    self._step_reconciliation_total.add(1)
                    with scoped_app_ctx(
                        JobBackendContext(provider=provider, profile=profile, name=str(backend)),
                    ):
                        sync_started_at = time.monotonic()
                        job_update = backend.sync(step)
                        logger.debug(
                            "Reconciler backend sync completed",
                            extra={
                                "job": step.job,
                                "step": step.name,
                                "workspace": step.workspace,
                                "provider": provider,
                                "profile": profile,
                                "from_status": step.status,
                                "to_status": job_update.status,
                                "duration_seconds": time.monotonic() - sync_started_at,
                            },
                        )
                        logger.info(f"Updating job step status from '{step.status}' to '{job_update.status}'")
                        if (
                            job_update.status == PlatformJobStatus.ERROR.value
                            and step.status != PlatformJobStatus.ERROR
                        ):
                            log_job_diagnostics_if_debug(
                                self._nmp_sdk,
                                step,
                                logger=self._logger,
                                context="step transitioned to error during reconciliation",
                            )
                        self._update_step_status_with_timing(
                            step=step,
                            provider=provider,
                            profile=profile,
                            status=job_update.status,
                            status_details=job_update.status_details,
                            error_details=job_update.error_details,
                        )
                except APIStatusError as e:
                    # In cases when attempting to update job step status results in a conflict (409),
                    # log a warning and continue processing other steps.
                    if e.status_code == 409:
                        logger.warning(f"Conflict updating job step': {str(e)}")
                        self._step_reconciliation_errors.add(
                            1,
                            attributes={
                                "error_type": "api_status_conflict",
                            },
                        )
                    else:
                        logger.error(f"Could not reconcile job step': {str(e)}")
                        self._step_reconciliation_errors.add(
                            1,
                            attributes={
                                "error_type": "api_status_error",
                            },
                        )
                except Exception:
                    logger.exception("Unexpected error when reconciling job step")
                    log_job_diagnostics_if_debug(
                        self._nmp_sdk,
                        step,
                        logger=self._logger,
                        context="unexpected reconciliation error",
                    )
                    self._step_reconciliation_errors.add(
                        1,
                        attributes={
                            "error_type": "unknown",
                        },
                    )

        # Perform any necessary cleanup steps for expired jobs
        logger.debug("Running job cleanup for expired job steps")
        for backend in self._backend_registry.get_all_backends():
            with tracer.start_as_current_span("jobs_reconciler/cleanup_backend_steps"):
                try:
                    backend.cleanup_steps()
                except Exception:
                    logger.exception("Could not complete cleanup steps for backend", exc_info=True)

    def _update_step_status_with_timing(
        self,
        *,
        step: PlatformJobStepWithContext,
        provider: str,
        profile: str,
        status: str,
        status_details: dict | None = None,
        error_details: dict | None = None,
    ):
        started_at = time.monotonic()
        try:
            response = self._nmp_sdk.jobs.steps.update_status(
                step.name,
                workspace=step.workspace,
                job=step.job,
                status=status,
                status_details=status_details,  # type: ignore
                error_details=error_details,  # type: ignore
            )
        except Exception:
            logger.warning(
                "Reconciler step status update failed",
                extra={
                    "job": step.job,
                    "step": step.name,
                    "workspace": step.workspace,
                    "provider": provider,
                    "profile": profile,
                    "from_status": step.status,
                    "to_status": status,
                    "duration_seconds": time.monotonic() - started_at,
                },
            )
            raise
        logger.debug(
            "Reconciler step status update succeeded",
            extra={
                "job": step.job,
                "step": step.name,
                "workspace": step.workspace,
                "provider": provider,
                "profile": profile,
                "from_status": step.status,
                "to_status": status,
                "duration_seconds": time.monotonic() - started_at,
            },
        )
        return response

    def get_steps_for_reconciliation(self, statuses: list[SDKPlatformJobStatus]) -> list[PlatformJobStepWithContext]:
        """
        Return the list of steps to reconcile.
        """
        # Iterate through all pages to get all steps
        steps = []
        filter_params: PlatformJobStepsListFilterParam = {"status": statuses}
        for step in self._nmp_sdk.jobs.steps.list(
            name="-",  # Use "-" to indicate all jobs
            workspace="-",  # Cross-workspace query
            filter=filter_params,
            sort="updated_at",
        ):
            steps.append(step)
        return steps
