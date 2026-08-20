# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for runner-owned controller thread health tracking."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from typing import cast

import pytest
from nmp.common.controller import ControllerManager, Loop
from nmp.platform_runner.controller_threads import start_controller_threads, start_sidecar_threads


class _HealthyLoop:
    name = ""
    is_healthy = True
    unhealthy_reason = None


@pytest.fixture(autouse=True)
def reset_controller_manager() -> Iterator[None]:
    ControllerManager._instance = None
    yield
    ControllerManager._instance = None


def test_controller_is_pending_until_run_func_registers_loop() -> None:
    manager = ControllerManager.get_instance()
    allow_registration = threading.Event()
    registered = threading.Event()
    stop_signal = threading.Event()

    def run(stop_signal: threading.Event) -> None:
        allow_registration.wait(timeout=2)
        manager.register("models_controller", cast(Loop, _HealthyLoop()))
        registered.set()
        stop_signal.wait(timeout=2)

    threads = start_controller_threads({"models": run}, stop_signal)
    try:
        assert manager.validate_all_healthy() == (False, {"models": False})

        allow_registration.set()
        assert registered.wait(timeout=2)
        assert manager.validate_all_healthy() == (True, {"models_controller": True})
    finally:
        stop_signal.set()
        for thread in threads:
            thread.join(timeout=2)


def test_controller_that_exits_without_shutdown_is_unhealthy(caplog: pytest.LogCaptureFixture) -> None:
    manager = ControllerManager.get_instance()
    stop_signal = threading.Event()

    with caplog.at_level(logging.ERROR, logger="nmp.platform_runner.controller_threads"):
        threads = start_controller_threads({"models": lambda _stop_signal: None}, stop_signal)
        for thread in threads:
            thread.join(timeout=2)

    assert manager.validate_all_healthy() == (False, {"models": False})
    assert "Controller 'models' exited unexpectedly" in caplog.text


def test_controller_thread_name_does_not_duplicate_prefix() -> None:
    stop_signal = threading.Event()

    threads = start_controller_threads({"controller-models": lambda _stop_signal: None}, stop_signal)
    for thread in threads:
        thread.join(timeout=2)

    assert threads[0].name == "controller-models"


def test_sidecar_failure_is_logged_without_affecting_controller_health(caplog: pytest.LogCaptureFixture) -> None:
    manager = ControllerManager.get_instance()
    stop_signal = threading.Event()

    def crash(_stop_signal: threading.Event) -> None:
        raise ValueError("optional configuration is missing")

    with caplog.at_level(logging.ERROR, logger="nmp.platform_runner.controller_threads"):
        threads = start_sidecar_threads({"adapters": crash}, stop_signal)
        for thread in threads:
            thread.join(timeout=2)

    assert manager.validate_all_healthy() == (True, {})
    assert "Sidecar 'adapters' crashed" in caplog.text
    assert threads[0].name == "sidecar-adapters"


def test_self_tracking_sidecar_is_pending_before_its_thread_runs_any_code() -> None:
    """Expose a self-tracking sidecar before its thread is scheduled."""
    manager = ControllerManager.get_instance()
    stop_signal = threading.Event()
    thread_may_proceed = threading.Event()

    def run(stop_signal: threading.Event) -> None:
        # Hold the thread before its own registration call.
        thread_may_proceed.wait(timeout=2)
        stop_signal.wait(timeout=2)

    threads = start_sidecar_threads({"auth-proxy": run}, stop_signal)
    try:
        all_healthy, status = manager.validate_all_healthy()
        assert all_healthy is False
        assert status.get("auth-proxy") is False
    finally:
        thread_may_proceed.set()
        stop_signal.set()
        for thread in threads:
            thread.join(timeout=2)
        manager.stop_tracking_controller("auth-proxy")
