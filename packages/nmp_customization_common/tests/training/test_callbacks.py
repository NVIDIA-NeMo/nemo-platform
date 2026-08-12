# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the shared TrainingProgressCallback.

Focused on the contract that every backend depends on: ``report_running`` REPLACES
the task's ``status_details``, so the accumulated series must ride on every report
or it is erased from stored status. Basic accumulation and resume-seeding are
covered by the per-backend suites; this file covers the shared surface itself.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import pytest
from nmp.customization_common.training.callbacks import TrainingProgressCallback
from nmp.customization_common.training.progress import JobsServiceProgressReporter


class _RecordingReporter:
    """Stands in for JobsServiceProgressReporter, capturing each report payload."""

    def __init__(self, prior: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._prior = prior or {"train_loss": [], "val_loss": []}
        self.reports: list[dict[str, Any]] = []
        self.tracking: tuple[int, int] | None = None
        self.closed = False

    def fetch_current_metrics(self) -> dict[str, list[dict[str, Any]]]:
        return self._prior

    def configure_progress_tracking(self, max_steps: int, num_epochs: int) -> None:
        self.tracking = (max_steps, num_epochs)

    def report_running(self, phase: str, **details: Any) -> None:
        self.reports.append({"phase": phase, **details})

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def reporter() -> _RecordingReporter:
    return _RecordingReporter()


def _make_callback(reporter: _RecordingReporter) -> TrainingProgressCallback:
    """Build the callback over a duck-typed reporter, narrowing the type once here."""
    return TrainingProgressCallback(cast(JobsServiceProgressReporter, reporter))


# --------------------------------------------------------------------------- #
# Every report path carries the series
# --------------------------------------------------------------------------- #


def test_every_report_path_carries_the_series(reporter: _RecordingReporter) -> None:
    """An omitted payload erases the curve from stored status_details."""
    callback = _make_callback(reporter)
    callback.report_training_start(max_steps=10, num_epochs=1)
    callback.report_train_step(step=1, epoch=1, loss=0.5)
    callback.report_validation(step=1, epoch=1, val_loss=0.45)
    callback.report_checkpoint_saved(step=1, epoch=1, checkpoint_path="/ckpt")
    callback.report_epoch_end(step=1, epoch=1)

    assert len(reporter.reports) == 5
    for report in reporter.reports:
        assert "metrics" in report, report["phase"]
        assert set(report["metrics"]) == {"train_loss", "val_loss"}


def test_training_start_does_not_erase_seeded_metrics() -> None:
    """report_training_start fires before the first step; it must not blank the blob."""
    prior = {"train_loss": [{"step": 1, "epoch": 1, "value": 0.9}], "val_loss": []}
    reporter = _RecordingReporter(prior)
    _make_callback(reporter).report_training_start(max_steps=10, num_epochs=1)

    assert reporter.reports[0]["metrics"]["train_loss"] == prior["train_loss"]


def test_series_are_snapshots_not_live_references(reporter: _RecordingReporter) -> None:
    """A shared list would retroactively mutate already-sent payloads."""
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, loss=0.5)
    first_payload = reporter.reports[-1]["metrics"]["train_loss"]
    callback.report_train_step(step=2, epoch=1, loss=0.4)

    assert len(first_payload) == 1


# --------------------------------------------------------------------------- #
# Optional val_loss
# --------------------------------------------------------------------------- #


def test_validation_without_loss_omits_the_key(reporter: _RecordingReporter) -> None:
    """GRPO validates on accuracy; a null val_loss would chart as a real zero."""
    _make_callback(reporter).report_validation(step=1, epoch=1, val_loss=None, accuracy=0.75)

    report = reporter.reports[-1]
    assert "val_loss" not in report
    assert report["accuracy"] == 0.75
    assert report["metrics"]["val_loss"] == []


def test_validation_with_loss_records_both_key_and_series(reporter: _RecordingReporter) -> None:
    _make_callback(reporter).report_validation(step=1, epoch=1, val_loss=0.25)

    report = reporter.reports[-1]
    assert report["val_loss"] == 0.25
    assert report["metrics"]["val_loss"] == [{"step": 1, "epoch": 1, "value": 0.25}]


# --------------------------------------------------------------------------- #
# additional_metrics
# --------------------------------------------------------------------------- #


def test_additional_train_metrics_ride_along_without_entering_the_series(
    reporter: _RecordingReporter,
) -> None:
    """The wide backend metric set is current-step only; series stay bounded."""
    _make_callback(reporter).report_train_step(step=1, epoch=1, loss=0.5, reward=0.62, kl_penalty=0.008)

    report = reporter.reports[-1]
    assert report["reward"] == 0.62
    assert report["kl_penalty"] == 0.008
    assert report["metrics"]["train_loss"] == [{"step": 1, "epoch": 1, "value": 0.5}]


def test_additional_validation_metrics_ride_along(reporter: _RecordingReporter) -> None:
    _make_callback(reporter).report_validation(step=1, epoch=1, val_loss=0.25, accuracy=0.9)

    assert reporter.reports[-1]["accuracy"] == 0.9


def test_additional_metrics_do_not_collide_with_backend_stamping(
    reporter: _RecordingReporter,
) -> None:
    """`backend` is keyword-only, so **additional_metrics can never capture it."""

    class _Stamped(TrainingProgressCallback):
        _default_backend: ClassVar[str | None] = "test-backend"

    callback = _Stamped(cast(JobsServiceProgressReporter, reporter))
    callback.report_train_step(step=1, epoch=1, loss=0.5, reward=0.62)

    report = reporter.reports[-1]
    assert report["backend"] == "test-backend"
    assert report["reward"] == 0.62


def test_close_delegates_to_the_reporter(reporter: _RecordingReporter) -> None:
    _make_callback(reporter).close()

    assert reporter.closed
