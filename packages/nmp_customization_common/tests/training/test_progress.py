# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for JobsServiceProgressReporter's status_details handling.

Focused on carry-forward: the Jobs service REPLACES ``status_details``, so a
field lives only as long as the next report repeats it. The runner reports
checkpoint processing, completion and failure from a different process than the
training driver, and the driver states the schedule once and the checkpoint path
once. Without the carry-forward set, each of those is erased by the next update.
"""

from __future__ import annotations

from typing import Any

import pytest
from nmp.customization_common.training.progress import JobsServiceProgressReporter

SERIES: dict[str, list[dict[str, Any]]] = {
    "train_loss": [{"step": 10, "epoch": 1, "value": 0.5}],
    "train_reward": [{"step": 10, "epoch": 1, "value": 0.62}],
}
#: A blob a mid-run job would have stored: series plus the sticky facts.
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
    ``_fetch_status_details``, so the real fetch runs -- including its
    carry-forward cache side effect.
    """

    def __init__(self) -> None:
        self._job_ctx = _JobCtx()  # type: ignore[assignment] - duck-typed stand-in
        self._sdk = type("S", (), {"close": lambda self: None})()  # type: ignore[assignment]
        self._is_main_rank = True
        self._enabled = True
        self._max_steps = 0
        self._num_epochs = 0
        self._carried = {}


class _Task:
    def __init__(self, status_details: dict[str, Any]) -> None:
        self.status_details = status_details

    def data(self) -> "_Task":
        return self


class _Jobs:
    """A mini Jobs service: replace-on-write, readable back, counting fetches."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.stored: dict[str, Any] = {}
        self.fetches = 0
        self.persist = False

    def client(self) -> Any:
        harness = self

        class _Client:
            def update_job_step_task(self, **kwargs: Any) -> None:
                harness.sent.append(kwargs)
                if harness.persist:
                    harness.stored = dict(kwargs["body"].status_details or {})

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
# What carries forward
# --------------------------------------------------------------------------- #


def test_completion_carries_series_schedule_and_checkpoint(jobs: _Jobs) -> None:
    """The last write of a successful job must not blank what it took to get there."""
    _reporter(jobs, STORED).report_completed("Training completed")

    details = _details(jobs)
    assert details["metrics"] == SERIES
    assert details["max_steps"] == 30
    assert details["num_epochs"] == 3
    assert details["step"] == 10
    assert details["checkpoint_path"] == "/ckpt/step-10"
    assert details["phase"] == "completed", "the report's own phase still wins"


def test_failure_carries_the_same_set(jobs: _Jobs) -> None:
    """A failed run is exactly when the partial curve and last checkpoint matter."""
    _reporter(jobs, STORED).report_error("boom")

    details = _details(jobs)
    assert details["metrics"] == SERIES
    assert details["step"] == 10
    assert details["checkpoint_path"] == "/ckpt/step-10"


def test_intermediate_phase_carries_forward(jobs: _Jobs) -> None:
    """processing_checkpoint fires after the driver exits, before completion."""
    _reporter(jobs, STORED).report_running("processing_checkpoint")

    details = _details(jobs)
    assert details["metrics"] == SERIES
    assert details["max_steps"] == 30
    assert details["phase"] == "processing_checkpoint"


def test_per_step_observations_do_not_carry_forward(jobs: _Jobs) -> None:
    """A completed task must not advertise a stale current loss or learning rate.

    Nothing is lost: each of these is recoverable from its series in `metrics`.
    """
    _reporter(jobs, STORED).report_completed("Training completed")

    details = _details(jobs)
    assert "train_loss" not in details
    assert "lr" not in details


def test_caller_supplied_values_win(jobs: _Jobs) -> None:
    fresher = {"train_loss": [{"step": 20, "epoch": 2, "value": 0.1}]}
    _reporter(jobs, STORED).report_running("training", step=20, metrics=fresher, max_steps=99)

    details = _details(jobs)
    assert details["metrics"] == fresher
    assert details["step"] == 20
    assert details["max_steps"] == 99


def test_empty_stored_values_add_no_keys(jobs: _Jobs) -> None:
    """Before training starts there is nothing to carry; don't invent keys."""
    stored = {"metrics": {"train_loss": [], "val_loss": []}, "checkpoint_path": ""}
    _reporter(jobs, stored).report_running("compiling_config")

    details = _details(jobs)
    assert "metrics" not in details
    assert "checkpoint_path" not in details


# --------------------------------------------------------------------------- #
# Write-through cache: the per-step hot path must not pay for a round-trip
# --------------------------------------------------------------------------- #


def test_reports_carrying_metrics_never_fetch(jobs: _Jobs) -> None:
    """`metrics` marks an update as coming from the accumulating callback.

    Those are the per-step reports. They omit max_steps and checkpoint_path, so a
    naive implementation would read the blob back on every single training step.
    """
    reporter = _reporter(jobs, STORED)
    for step in range(1, 11):
        reporter.report_running("training", step=step, metrics=SERIES)

    assert jobs.fetches == 0


def test_a_stated_value_is_restated_without_a_fetch(jobs: _Jobs) -> None:
    """report_training_start states the schedule once; every later step needs it."""
    reporter = _reporter(jobs)
    reporter.report_running("training", step=0, max_steps=30, num_epochs=3, metrics=SERIES)
    reporter.report_running("training", step=1, metrics=SERIES)

    details = _details(jobs)
    assert details["max_steps"] == 30
    assert details["num_epochs"] == 3
    assert jobs.fetches == 0


def test_checkpoint_path_survives_the_next_training_step(jobs: _Jobs) -> None:
    """It was published by one report and wiped by the very next one."""
    reporter = _reporter(jobs)
    reporter.report_running("checkpoint_saved", step=10, checkpoint_path="/ckpt/step-10", metrics=SERIES)
    reporter.report_running("training", step=11, metrics=SERIES)

    assert _details(jobs)["checkpoint_path"] == "/ckpt/step-10"


def test_a_newer_checkpoint_supersedes_the_carried_one(jobs: _Jobs) -> None:
    reporter = _reporter(jobs)
    reporter.report_running("checkpoint_saved", step=10, checkpoint_path="/ckpt/step-10", metrics=SERIES)
    reporter.report_running("checkpoint_saved", step=20, checkpoint_path="/ckpt/step-20", metrics=SERIES)
    reporter.report_running("training", step=21, metrics=SERIES)

    assert _details(jobs)["checkpoint_path"] == "/ckpt/step-20"


def test_updates_without_metrics_read_the_blob_back(jobs: _Jobs) -> None:
    """The runner's reports come from a process that holds no state at all."""
    reporter = _reporter(jobs, STORED)
    reporter.report_running("processing_checkpoint")

    assert jobs.fetches == 1


def test_error_details_still_ride_along(jobs: _Jobs) -> None:
    """Carry-forward must not displace the error payload."""
    _reporter(jobs, STORED).report_error({"message": "oom", "code": "OOM"})

    assert jobs.sent[0]["body"].error_details == {"message": "oom", "code": "OOM"}


# --------------------------------------------------------------------------- #
# Resume seeding
# --------------------------------------------------------------------------- #


def test_fetch_current_metrics_returns_every_series(jobs: _Jobs) -> None:
    """A resumed job that only seeded train_loss would restart the other curves."""
    assert _reporter(jobs, STORED).fetch_current_metrics() == SERIES


def test_fetch_current_metrics_drops_non_list_values(jobs: _Jobs) -> None:
    """A malformed blob must not poison the accumulator."""
    stored = {"metrics": {"train_loss": [{"step": 1, "epoch": 1, "value": 1.0}], "junk": 3}}

    assert set(_reporter(jobs, stored).fetch_current_metrics()) == {"train_loss"}


def test_resume_seeding_also_seeds_the_carry_forward_cache(jobs: _Jobs) -> None:
    """The callback's construction-time fetch must double as the carry-forward seed.

    Otherwise a resumed run drops the previous run's checkpoint_path: its very
    first report already carries `metrics`, so it never reads the blob back.
    """
    reporter = _reporter(jobs, STORED)
    reporter.fetch_current_metrics()  # what TrainingProgressCallback.__init__ does
    fetches_after_seeding = jobs.fetches

    reporter.report_running("training", step=1, metrics=SERIES)

    assert _details(jobs)["checkpoint_path"] == "/ckpt/step-10"
    assert jobs.fetches == fetches_after_seeding, "no second round-trip"


# --------------------------------------------------------------------------- #
# Gating
# --------------------------------------------------------------------------- #


def test_disabled_reporter_sends_nothing(jobs: _Jobs) -> None:
    reporter = _reporter(jobs, STORED)
    reporter._enabled = False

    reporter.report_completed("Training completed")

    assert jobs.sent == []


def test_non_main_rank_sends_nothing(jobs: _Jobs) -> None:
    reporter = _reporter(jobs, STORED)
    reporter._is_main_rank = False

    reporter.report_completed("Training completed")

    assert jobs.sent == []
