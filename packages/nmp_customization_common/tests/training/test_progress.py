# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for JobsServiceProgressReporter's status_details handling.

The Jobs service merges ``status_details`` key-wise rather than replacing the
blob (``JobDispatcher._update_status_details_object``, verified end-to-end
against a running platform), so a report only ever has to state what it
observed. These tests pin that: each report sends its own fields and nothing
else, and the only read the reporter makes is the one-shot resume seeding.
"""

from __future__ import annotations

from typing import Any

import pytest
from nmp.customization_common.training.progress import JobsServiceProgressReporter

SERIES: dict[str, list[dict[str, Any]]] = {
    "train_loss": [{"step": 10, "epoch": 1, "value": 0.5}],
    "train_reward": [{"step": 10, "epoch": 1, "value": 0.62}],
}
#: A blob a mid-run job would have stored, as read back on resume.
STORED: dict[str, Any] = {
    "phase": "training",
    "step": 10,
    "epoch": 1,
    "max_steps": 30,
    "num_epochs": 3,
    "train_loss": 0.5,
    "lr": 5e-06,
    "checkpoint_path": "/ckpt/step-10",
    "metrics": SERIES,
}


class _JobCtx:
    """The four identifiers update_task reads off the job context."""

    normalized_task = "training"
    workspace = "default"
    job_id = "job-1"
    step = "train"


class _Reporter(JobsServiceProgressReporter):
    """Reporter with the SDK and job context stubbed out.

    Bypasses ``__init__`` rather than mocking the SDK factory: what is under test
    is the status_details logic, and the real constructor calls ``get_task_sdk``,
    which wants credentials. Every attribute ``update_task`` touches is set here.

    The SDK client itself is patched (see the ``jobs`` fixture) rather than
    ``fetch_current_metrics``, so the real fetch runs.
    """

    def __init__(self) -> None:
        self._job_ctx = _JobCtx()  # type: ignore[assignment] - duck-typed stand-in
        self._sdk = type("S", (), {"close": lambda self: None})()  # type: ignore[assignment]
        self._is_main_rank = True
        self._enabled = True
        self._max_steps = 0
        self._num_epochs = 0


class _Task:
    def __init__(self, status_details: dict[str, Any]) -> None:
        self.status_details = status_details

    def data(self) -> "_Task":
        return self


class _Jobs:
    """A mini Jobs service: records writes, serves reads, counts fetches."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.stored: dict[str, Any] = {}
        self.fetches = 0

    def client(self) -> Any:
        harness = self

        class _Client:
            def update_job_step_task(self, **kwargs: Any) -> None:
                harness.sent.append(kwargs)

            def get_job_step_task(self, **kwargs: Any) -> _Task:
                harness.fetches += 1
                return _Task(harness.stored)

        return _Client()


@pytest.fixture
def jobs(monkeypatch: pytest.MonkeyPatch) -> _Jobs:
    """Patch the SDK client seam so update_task and the fetch both run for real."""
    harness = _Jobs()
    monkeypatch.setattr(
        "nmp.customization_common.training.progress.client_from_platform",
        lambda _sdk, _cls: harness.client(),
    )
    return harness


def _reporter(jobs: _Jobs, stored: dict[str, Any] | None = None) -> _Reporter:
    """A reporter over the harness, with the server pre-seeded if given."""
    if stored is not None:
        jobs.stored = stored
    return _Reporter()


def _details(jobs: _Jobs, index: int = -1) -> dict[str, Any]:
    assert jobs.sent, "expected at least one task update"
    return dict(jobs.sent[index]["body"].status_details or {})


# --------------------------------------------------------------------------- #
# A report states what it observed, and nothing else
# --------------------------------------------------------------------------- #


def test_a_report_sends_only_its_own_fields(jobs: _Jobs) -> None:
    """The server merges, so restating untouched fields would be pure upload."""
    _reporter(jobs, STORED).report_running("processing_checkpoint")

    assert _details(jobs) == {"phase": "processing_checkpoint"}


def test_completion_sends_only_its_own_fields(jobs: _Jobs) -> None:
    """The stored series, schedule and checkpoint path survive on the server."""
    _reporter(jobs, STORED).report_completed("Training completed")

    assert _details(jobs) == {"message": "Training completed", "phase": "completed"}
    assert jobs.sent[-1]["body"].status == "completed"


def test_percentage_done_is_derived_from_a_stated_step(jobs: _Jobs) -> None:
    reporter = _reporter(jobs)
    reporter.configure_progress_tracking(max_steps=40, num_epochs=1)
    reporter.report_running("training", step=10, metrics=SERIES)

    assert _details(jobs)["percentage_done"] == 25


def test_percentage_done_is_clamped(jobs: _Jobs) -> None:
    """A resumed or over-run job can report past max_steps."""
    reporter = _reporter(jobs)
    reporter.configure_progress_tracking(max_steps=10, num_epochs=1)
    reporter.report_running("training", step=99, metrics=SERIES)

    assert _details(jobs)["percentage_done"] == 100


def test_error_details_still_ride_along(jobs: _Jobs) -> None:
    _reporter(jobs, STORED).report_error({"message": "oom", "code": "OOM"})

    assert jobs.sent[0]["body"].error_details == {"message": "oom", "code": "OOM"}


# --------------------------------------------------------------------------- #
# Reads: exactly one, for resume seeding
# --------------------------------------------------------------------------- #


def test_no_report_reads_the_blob_back(jobs: _Jobs) -> None:
    """Writes are fire-and-forget. A read per report was the old carry-forward tax."""
    reporter = _reporter(jobs, STORED)
    for step in range(1, 11):
        reporter.report_running("training", step=step, metrics=SERIES)
    reporter.report_running("processing_checkpoint")
    reporter.report_completed("Training completed")
    reporter.report_error("boom")

    assert jobs.fetches == 0


def test_fetch_current_metrics_returns_every_series(jobs: _Jobs) -> None:
    """A resumed job that only seeded train_loss would restart the other curves."""
    assert _reporter(jobs, STORED).fetch_current_metrics() == SERIES


def test_fetch_current_metrics_drops_non_list_values(jobs: _Jobs) -> None:
    """A malformed blob must not poison the accumulator."""
    stored = {"metrics": {"train_loss": [{"step": 1, "epoch": 1, "value": 1.0}], "junk": 3}}

    assert set(_reporter(jobs, stored).fetch_current_metrics()) == {"train_loss"}


def test_fetch_current_metrics_copies_the_point_lists(jobs: _Jobs) -> None:
    """The caller appends to what it gets back; it must not alias the response."""
    seeded = _reporter(jobs, STORED).fetch_current_metrics()
    seeded["train_loss"].append({"step": 20, "epoch": 2, "value": 0.4})

    assert len(SERIES["train_loss"]) == 1


def test_fetch_current_metrics_survives_an_unseeded_task(jobs: _Jobs) -> None:
    """First run: the task has no stored details, which is not an error."""
    assert _reporter(jobs, {}).fetch_current_metrics() == {}


# --------------------------------------------------------------------------- #
# Gating
# --------------------------------------------------------------------------- #


def test_disabled_reporter_sends_nothing(jobs: _Jobs) -> None:
    reporter = _reporter(jobs, STORED)
    reporter._enabled = False

    reporter.report_completed("Training completed")

    assert jobs.sent == []


def test_disabled_reporter_does_not_fetch(jobs: _Jobs) -> None:
    reporter = _reporter(jobs, STORED)
    reporter._enabled = False

    assert reporter.fetch_current_metrics() == {}
    assert jobs.fetches == 0


def test_non_main_rank_sends_nothing(jobs: _Jobs) -> None:
    reporter = _reporter(jobs, STORED)
    reporter._is_main_rank = False

    reporter.report_completed("Training completed")

    assert jobs.sent == []
