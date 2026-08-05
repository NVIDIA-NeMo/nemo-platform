# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from nemo_platform_ext.cli.core import waiters
from nemo_platform_ext.cli.telemetry.events import TaskStatusEnum

WAITERS_MODULE = "nemo_platform_ext.cli.core.waiters"
EMIT_TARGET = "nemo_platform_ext.cli.telemetry.emit.emit_event"


class _DummyLive:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __enter__(self) -> _DummyLive:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def update(self, *args: object) -> None:
        pass

    def stop(self) -> None:
        pass

    def start(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _quiet_rich_output() -> Iterator[None]:
    with (
        patch(f"{WAITERS_MODULE}.Live", _DummyLive),
        patch(f"{WAITERS_MODULE}.console.print"),
    ):
        yield


@pytest.fixture
def frozen_time() -> Iterator[MagicMock]:
    with patch(f"{WAITERS_MODULE}.time.time", return_value=0) as time:
        yield time


@pytest.fixture
def waiter_pause() -> Iterator[MagicMock]:
    with patch(f"{WAITERS_MODULE}._pause") as pause:
        yield pause


def _completed_status() -> SimpleNamespace:
    return SimpleNamespace(
        status="completed",
        steps=[
            SimpleNamespace(name="audit-job"),
            SimpleNamespace(name="evaluate"),
            SimpleNamespace(name="evaluate-suite"),
            SimpleNamespace(name="customer-project-step"),
        ],
        status_details={"input_tokens": 512, "output_tokens": 2048, "model": "nemotron-super-49b"},
    )


def test_completed_emits_single_job_run_event(frozen_time: MagicMock) -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = _completed_status()

    with patch(EMIT_TARGET) as emit_event:
        assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default", resource_label="customization") is True

    emit_event.assert_called_once()
    event = emit_event.call_args.args[0]
    assert event.job_type == "customization"
    assert event.task_status is TaskStatusEnum.COMPLETED
    assert event.input_tokens == 512
    assert event.output_tokens == 2048
    assert event.model == "defined"
    assert event.plugins == []
    assert "customer-project-step" not in event.job_type


def test_static_step_name_is_not_emitted_as_job_type(frozen_time: MagicMock) -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(
        status="completed", steps=[SimpleNamespace(name="audit-job")], status_details={}
    )

    with patch(EMIT_TARGET) as emit_event:
        assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default", resource_label="audit") is True

    event = emit_event.call_args.args[0]
    assert event.job_type == "audit"
    assert event.plugins == []


def test_job_type_falls_back_to_resource_label_without_steps(frozen_time: MagicMock) -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(status="completed", steps=[], status_details={})

    with patch(EMIT_TARGET) as emit_event:
        assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default", resource_label="customization") is True

    event = emit_event.call_args.args[0]
    assert event.job_type == "customization"
    assert event.plugins == []


def test_unsafe_resource_label_falls_back_to_custom(frozen_time: MagicMock) -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(
        status="completed",
        steps=[SimpleNamespace(name="private-customer-step")],
        status_details={},
    )

    with patch(EMIT_TARGET) as emit_event:
        assert (
            waiters.wait_for_platform_job(jobs, "job-a", workspace="default", resource_label="customer alpha project")
            is True
        )

    event = emit_event.call_args.args[0]
    assert event.job_type == "custom"
    assert event.plugins == []


def test_status_details_defaults_when_absent(frozen_time: MagicMock) -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(status="completed", steps=[], status_details={})

    with patch(EMIT_TARGET) as emit_event:
        assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default") is True

    event = emit_event.call_args.args[0]
    assert event.input_tokens == -1
    assert event.output_tokens == -1
    assert event.model == "undefined"
    assert event.plugins == []


def test_null_status_details_still_emits(frozen_time: MagicMock) -> None:
    """Explicit nulls must not drop the event; a real 0 token count must survive."""
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(
        status="completed",
        steps=[],
        status_details={"model": None, "input_tokens": 0, "output_tokens": None},
    )

    with patch(EMIT_TARGET) as emit_event:
        assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default") is True

    emit_event.assert_called_once()
    event = emit_event.call_args.args[0]
    assert event.model == "undefined"
    assert event.input_tokens == 0
    assert event.output_tokens == -1


def test_non_string_model_details_still_emit_safe_bucket(frozen_time: MagicMock) -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(
        status="completed",
        steps=[],
        status_details={"model": {"name": "private-model"}, "input_tokens": 7, "output_tokens": 9},
    )

    with patch(EMIT_TARGET) as emit_event:
        assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default") is True

    emit_event.assert_called_once()
    event = emit_event.call_args.args[0]
    assert event.model == "defined"
    assert event.input_tokens == 7
    assert event.output_tokens == 9


def test_duration_uses_job_created_at_when_available() -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(
        status="completed",
        steps=[],
        status_details={},
        created_at=datetime.fromtimestamp(90.0, tz=timezone.utc),
    )

    with (
        patch(f"{WAITERS_MODULE}.time.time", side_effect=[100.0, 100.0, 100.0, 130.0]),
        patch(EMIT_TARGET) as emit_event,
    ):
        assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default") is True

    event = emit_event.call_args.args[0]
    assert event.duration_sec == 40.0


def test_error_status_maps_to_error(frozen_time: MagicMock) -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(status="error", steps=[], status_details={})

    with patch(EMIT_TARGET) as emit_event:
        assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default") is False

    emit_event.assert_called_once()
    assert emit_event.call_args.args[0].task_status is TaskStatusEnum.ERROR


def test_cancelled_status_maps_to_canceled(frozen_time: MagicMock) -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(status="cancelled", steps=[], status_details={})

    with patch(EMIT_TARGET) as emit_event:
        assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default") is False

    emit_event.assert_called_once()
    assert emit_event.call_args.args[0].task_status is TaskStatusEnum.CANCELED


def test_timeout_emits_nothing_and_does_not_crash(waiter_pause: MagicMock) -> None:
    jobs = MagicMock()
    jobs.get_status.return_value = SimpleNamespace(status="running", steps=[], status_details={})

    with patch(EMIT_TARGET) as emit_event:
        assert waiters.wait_for_platform_job(jobs, "job-a", workspace="default", timeout=5, poll_interval=10) is False

    emit_event.assert_not_called()
