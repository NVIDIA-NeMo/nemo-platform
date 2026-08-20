# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Thread lifecycle helpers for runner-owned controllers and sidecars."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable

from nmp.common.controller import ControllerManager
from nmp.platform_runner.loader import ControllerRunFunc
from nmp.platform_runner.registry import SELF_TRACKING_SIDECARS

logger = logging.getLogger(__name__)

# Covers auth-proxy's Uvicorn and health-loop shutdown budgets.
RUNNER_JOIN_TIMEOUT_SECONDS = 16.0


def start_controller_threads(
    controller_run_funcs: dict[str, ControllerRunFunc],
    stop_signal: threading.Event,
) -> list[threading.Thread]:
    """Start controllers while making pre-registration failures observable."""
    return _start_runner_threads(controller_run_funcs, stop_signal, track_controller_health=True)


def start_sidecar_threads(
    sidecar_run_funcs: dict[str, ControllerRunFunc],
    stop_signal: threading.Event,
) -> list[threading.Thread]:
    """Start sidecars without requiring them to register controller health."""
    return _start_runner_threads(sidecar_run_funcs, stop_signal, track_controller_health=False)


def _start_runner_threads(
    run_funcs: dict[str, ControllerRunFunc],
    stop_signal: threading.Event,
    *,
    track_controller_health: bool,
) -> list[threading.Thread]:
    manager = ControllerManager.get_instance()
    threads = []
    kind, thread_prefix = ("Controller", "controller") if track_controller_health else ("Sidecar", "sidecar")

    for name, run_func in run_funcs.items():
        # Pre-register self-tracking sidecars before their thread is scheduled.
        if track_controller_health or name in SELF_TRACKING_SIDECARS:
            manager.await_controller_registration(name)

        def run_tracked(
            run_func: ControllerRunFunc = run_func,
            name: str = name,
        ) -> None:
            with manager.controller_registration_context(name):
                try:
                    run_func(stop_signal)
                except Exception:
                    if track_controller_health:
                        manager.mark_controller_failed(name)
                    logger.exception("%s '%s' crashed", kind, name)
                    return

                if not stop_signal.is_set():
                    if track_controller_health:
                        manager.mark_controller_failed(name)
                    logger.error("%s '%s' exited unexpectedly", kind, name)

        thread_name = name if name.startswith(f"{thread_prefix}-") else f"{thread_prefix}-{name}"
        thread = threading.Thread(target=run_tracked, name=thread_name, daemon=True)
        thread.start()
        threads.append(thread)

    return threads


def join_and_untrack_runner_threads(
    threads: list[threading.Thread],
    thread_by_name: dict[str, threading.Thread],
    names: Iterable[str],
    *,
    join_timeout: float,
) -> None:
    """Join threads within one shared deadline and untrack those that stop.

    Live threads remain unhealthy. Self-tracking sidecars are omitted from
    ``names`` because they own resource threads that are not visible here.
    """
    deadline = time.monotonic() + join_timeout
    pending = list(threads)
    while pending and time.monotonic() < deadline:
        pending = [thread for thread in pending if thread.is_alive()]
        if pending:
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
    for thread in threads:
        if thread.is_alive():
            logger.warning("Runner thread %s did not finish in time", thread.name)

    manager = ControllerManager.get_instance()
    for name in names:
        thread = thread_by_name.get(name)
        if thread is not None and thread.is_alive():
            logger.warning("Leaving health tracking in place for %r; its thread did not finish in time", name)
            continue
        manager.stop_tracking_controller(name)
