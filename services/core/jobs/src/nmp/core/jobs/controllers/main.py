# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
import signal
import threading
import time

from nmp.common.config import get_platform_config
from nmp.common.controller import ControllerManager, Loop, TimedLoopWaiter, TrackLastExecutionTime
from nmp.common.sdk_factory import get_platform_sdk
from nmp.common.service.api.health import wait_for_service_ready
from nmp.core.jobs.config import config as jobs_config
from nmp.core.jobs.config import profiles
from nmp.core.jobs.controllers.backends.registry import BackendRegistry
from nmp.core.jobs.controllers.reconciler import JobReconciler
from nmp.core.jobs.controllers.scheduler import JobScheduler

stop_signal = threading.Event()
logger = logging.getLogger(__name__)


def _sync_advertised_profiles_to_registry(backend_registry: BackendRegistry) -> None:
    """Keep GET /v2/execution-profiles aligned with backends that actually registered.

    ``profiles`` is built at import time; ``BackendRegistry.from_config`` may later
    skip unavailable Docker backends. The jobs API imports the same list object, so we
    replace its contents in place (``clear`` + ``extend``) rather than rebinding the
    name — that way local standalone stops advertising executors that never registered.
    """
    registered = backend_registry.registered_profile_keys()
    kept = []
    for profile in profiles:
        if (profile.provider, profile.profile) in registered:
            kept.append(profile)

    skipped = len(profiles) - len(kept)
    if skipped:
        logger.warning(
            "Removed %s execution profile(s) that failed backend registration so advertised "
            "profiles match the jobs controller registry.",
            skipped,
        )
        profiles.clear()
        profiles.extend(kept)


def handle_sighup(signum, frame):
    stop_signal.set()


def run(parent_stop_signal: threading.Event | None = None):
    # Create logger after configuration is set up
    logger.info("Starting jobs controller")

    # Use provided stop signal or create our own
    if parent_stop_signal is None:
        # Register the handler for SIGINT and SIGTERM only if running standalone
        signal.signal(signal.SIGINT, handle_sighup)
        signal.signal(signal.SIGTERM, handle_sighup)
        local_stop_signal = stop_signal
    else:
        local_stop_signal = parent_stop_signal

    # Initialize components
    # Use service principal for controller - runs in background thread without user context
    nmp_sdk = get_platform_sdk(as_service="jobs", internal=True)
    logger.debug("Platform SDK initialized successfully.")

    backend_registry = BackendRegistry.from_config(nmp_sdk=nmp_sdk, profiles=profiles)
    _sync_advertised_profiles_to_registry(backend_registry)
    logger.info("Executor backends registry initialized successfully.")

    # Wait for the jobs service to be ready before starting control loops (polls /status so we can start once jobs is ready)
    platform_config = get_platform_config()
    if not wait_for_service_ready(platform_config, "jobs", local_stop_signal):
        if local_stop_signal.is_set():
            logger.info("Shutdown requested before server became ready")
            return
        logger.warning("Server did not become ready in time, starting loops anyway")

    # Job scheduling loop
    job_scheduler = JobScheduler(backend_registry, nmp_sdk, stop_signal=local_stop_signal)
    job_scheduler_monitored = TrackLastExecutionTime(job_scheduler)
    job_scheduler_loop = Loop(
        TimedLoopWaiter(jobs_config.schedule_interval_seconds, stop_signal=local_stop_signal),
        job_scheduler_monitored,
        stop_signal=local_stop_signal,
    )

    # Job reconciler loop
    job_reconciler = JobReconciler(backend_registry, nmp_sdk, stop_signal=local_stop_signal)
    job_reconciler_monitored = TrackLastExecutionTime(job_reconciler)
    job_reconciler_loop = Loop(
        TimedLoopWaiter(jobs_config.reconcile_interval_seconds, stop_signal=local_stop_signal),
        job_reconciler_monitored,
        shutdown_func=backend_registry.shutdown_all_backends,
        stop_signal=local_stop_signal,
    )

    # Register loops with ControllerManager
    controller_manager = ControllerManager.get_instance()
    controller_manager.register("job_scheduler", job_scheduler_loop)
    controller_manager.register("job_reconciler", job_reconciler_loop)

    # Start control loops
    job_scheduler_loop.start()
    job_reconciler_loop.start()
    logger.info("Jobs controller started successfully")

    # Main loop
    while not local_stop_signal.is_set():
        time.sleep(1)

    logger.info("Shutting down control loops...")
    job_scheduler_loop.stop()
    job_reconciler_loop.stop()

    for loop in [job_scheduler_loop, job_reconciler_loop]:
        loop.join()

    logger.info("All jobs control loops have been shut down.")
