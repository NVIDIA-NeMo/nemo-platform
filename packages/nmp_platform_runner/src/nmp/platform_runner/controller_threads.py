# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Thread lifecycle helpers for runner-owned controllers and sidecars."""

from __future__ import annotations

import logging
import threading

from nmp.common.controller import ControllerManager
from nmp.platform_runner.loader import ControllerRunFunc

logger = logging.getLogger(__name__)


def start_controller_threads(
    controller_run_funcs: dict[str, ControllerRunFunc],
    stop_signal: threading.Event,
) -> list[threading.Thread]:
    """Start controllers while making pre-registration failures observable."""
    manager = ControllerManager.get_instance()
    threads = []

    for name, run_func in controller_run_funcs.items():
        manager.expect_controller(name)

        def run_tracked_controller(
            run_func: ControllerRunFunc = run_func,
            name: str = name,
        ) -> None:
            with manager.controller_registration_context(name):
                try:
                    run_func(stop_signal)
                except Exception:
                    manager.mark_controller_failed(name)
                    logger.exception("Controller %s crashed", name)
                    return

                if not stop_signal.is_set():
                    manager.mark_controller_failed(name)
                    logger.error("Controller %s exited unexpectedly", name)

        thread = threading.Thread(target=run_tracked_controller, name=f"controller-{name}", daemon=True)
        thread.start()
        threads.append(thread)

    return threads
