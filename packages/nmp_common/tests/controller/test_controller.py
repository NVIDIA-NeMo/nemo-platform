# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the control loop liveness model."""

import threading
import time
from datetime import datetime, timedelta, timezone

from nmp.common.controller import (
    Controller,
    Heartbeat,
    HeartbeatMixin,
    Loop,
    TimedLoopWaiter,
    TrackLastExecutionTime,
)


class _PlainController(Controller):
    """Controller that reports no progress beyond entering step()."""

    def __init__(self) -> None:
        self.steps = 0

    def step(self):
        self.steps += 1


class _ItemController(HeartbeatMixin, Controller):
    """Controller that reports progress as it works through a batch."""

    def __init__(self, items: int, seconds_per_item: float = 0.0) -> None:
        self.items = items
        self.seconds_per_item = seconds_per_item
        self.processed = 0

    def step(self):
        for _ in range(self.items):
            if self.seconds_per_item:
                time.sleep(self.seconds_per_item)
            self.processed += 1
            self.emit_heartbeat()


def test_heartbeat_beat_advances_last():
    heartbeat = Heartbeat()
    before = heartbeat.last()
    heartbeat.beat()
    assert heartbeat.last() >= before


def test_wrapper_shares_its_heartbeat_with_a_reporting_controller():
    controller = _ItemController(items=0)
    wrapper = TrackLastExecutionTime(controller)

    # Backdate so a beat from the controller is observable.
    wrapper._heartbeat._last = datetime.now(timezone.utc) - timedelta(seconds=60)
    stale = wrapper.last_execution_time()

    controller.emit_heartbeat()

    assert wrapper.last_execution_time() > stale


def test_emit_heartbeat_before_attach_is_a_noop():
    controller = _ItemController(items=0)
    # Never wrapped, so no heartbeat is attached.
    controller.emit_heartbeat()


def test_controller_without_the_mixin_still_tracks_step_entry():
    controller = _PlainController()
    wrapper = TrackLastExecutionTime(controller)

    wrapper._heartbeat._last = datetime.now(timezone.utc) - timedelta(seconds=60)
    stale = wrapper.last_execution_time()

    wrapper.step()

    assert controller.steps == 1
    assert wrapper.last_execution_time() > stale


def _run_loop_until(loop: Loop, predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not reached before timeout")


def test_loop_stays_healthy_while_a_long_step_reports_progress():
    """A step far exceeding its interval stays healthy as long as it progresses."""
    stop_signal = threading.Event()
    # Interval 0.05s allows 0.15s without progress; the step runs ~0.5s total but
    # reports progress every ~0.01s.
    controller = _ItemController(items=50, seconds_per_item=0.01)
    wrapper = TrackLastExecutionTime(controller)
    loop = Loop(TimedLoopWaiter(0.05, stop_signal=stop_signal), wrapper, stop_signal=stop_signal)
    loop.name = "progressing"

    loop.start()
    try:
        _run_loop_until(loop, lambda: controller.processed > 25)
        # Well past 3x the interval into a single step, yet still healthy.
        assert loop.is_healthy
        assert loop.unhealthy_reason is None
    finally:
        stop_signal.set()
        loop.join(timeout=5)


def test_loop_goes_unhealthy_when_a_step_reports_no_progress():
    """A step that blocks without reporting progress is still detected."""
    stop_signal = threading.Event()
    started = threading.Event()
    release = threading.Event()

    class _StuckController(HeartbeatMixin, Controller):
        def step(self):
            started.set()
            release.wait(timeout=5)

    wrapper = TrackLastExecutionTime(_StuckController())
    loop = Loop(TimedLoopWaiter(0.05, stop_signal=stop_signal), wrapper, stop_signal=stop_signal)
    loop.name = "stuck"

    loop.start()
    try:
        assert started.wait(timeout=5)
        _run_loop_until(loop, lambda: not loop.is_healthy)
        assert loop.unhealthy_reason is not None
        assert "no progress" in loop.unhealthy_reason
    finally:
        release.set()
        stop_signal.set()
        loop.join(timeout=5)


def test_loop_reports_reason_when_thread_is_not_alive():
    stop_signal = threading.Event()
    wrapper = TrackLastExecutionTime(_PlainController())
    loop = Loop(TimedLoopWaiter(0.05, stop_signal=stop_signal), wrapper, stop_signal=stop_signal)
    loop.name = "never-started"

    assert not loop.is_healthy
    assert loop.unhealthy_reason == "loop thread is not alive"


def test_loop_reports_reason_when_controller_declares_itself_unhealthy():
    stop_signal = threading.Event()

    class _SelfUnhealthy(HeartbeatMixin, Controller):
        def step(self):
            self.emit_heartbeat()

        @property
        def is_healthy(self) -> bool:
            return False

    wrapper = TrackLastExecutionTime(_SelfUnhealthy())
    loop = Loop(TimedLoopWaiter(0.05, stop_signal=stop_signal), wrapper, stop_signal=stop_signal)
    loop.name = "self-unhealthy"

    loop.start()
    try:
        _run_loop_until(loop, lambda: not loop.is_healthy)
        assert loop.unhealthy_reason == "controller reported itself unhealthy"
    finally:
        stop_signal.set()
        loop.join(timeout=5)
