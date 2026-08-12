# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the RL TrainingProgressCallback's metric accumulation.

``JobsServiceProgressReporter.report_running`` REPLACES the task's ``status_details``
blob rather than merging into it, so a report that carries only the current step
erases everything before it. These tests pin the consequence: every report must carry
the full accumulated ``metrics`` payload, in the ``{step, epoch, value}`` shape Studio
reads as ``CustomizationMetricValue[]``.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from nmp.customization_common.training.progress import JobsServiceProgressReporter
from nmp.rl.tasks.training.backends.nemo_rl.callbacks import TrainingProgressCallback


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
# Accumulation
# --------------------------------------------------------------------------- #


def test_train_loss_accumulates_across_steps(reporter: _RecordingReporter) -> None:
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, loss=0.5)
    callback.report_train_step(step=2, epoch=1, loss=0.4)
    callback.report_train_step(step=3, epoch=1, loss=0.3)

    # The final report carries the whole curve, not just the last point.
    series = reporter.reports[-1]["metrics"]["train_loss"]
    assert series == [
        {"step": 1, "epoch": 1, "value": 0.5},
        {"step": 2, "epoch": 1, "value": 0.4},
        {"step": 3, "epoch": 1, "value": 0.3},
    ]


def test_every_report_carries_the_full_series(reporter: _RecordingReporter) -> None:
    """report_running replaces status_details, so an omission is a data loss."""
    callback = _make_callback(reporter)
    callback.report_training_start(max_steps=10, num_epochs=1)
    callback.report_train_step(step=1, epoch=1, loss=0.5)
    callback.report_validation(step=1, epoch=1, val_loss=0.45)
    callback.report_checkpoint_saved(step=1, epoch=1, checkpoint_path="/ckpt")

    for report in reporter.reports:
        assert "metrics" in report, report["phase"]
        assert "train_loss" in report["metrics"]
        assert "val_loss" in report["metrics"]


def test_val_loss_accumulates_separately(reporter: _RecordingReporter) -> None:
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, loss=0.5)
    callback.report_validation(step=1, epoch=1, val_loss=0.45)
    callback.report_validation(step=2, epoch=1, val_loss=0.40)

    metrics = reporter.reports[-1]["metrics"]
    assert len(metrics["train_loss"]) == 1
    assert metrics["val_loss"] == [
        {"step": 1, "epoch": 1, "value": 0.45},
        {"step": 2, "epoch": 1, "value": 0.40},
    ]


def test_series_are_copies_not_live_references(reporter: _RecordingReporter) -> None:
    """Each payload must snapshot the series; a shared list would mutate old reports."""
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, loss=0.5)
    first_payload = reporter.reports[-1]["metrics"]["train_loss"]
    callback.report_train_step(step=2, epoch=1, loss=0.4)

    assert len(first_payload) == 1


# --------------------------------------------------------------------------- #
# Resume seeding
# --------------------------------------------------------------------------- #


def test_prior_metrics_seed_the_series() -> None:
    """A resumed job continues the curve instead of restarting it."""
    prior = {
        "train_loss": [{"step": 1, "epoch": 1, "value": 0.9}],
        "val_loss": [{"step": 1, "epoch": 1, "value": 0.8}],
    }
    reporter = _RecordingReporter(prior)
    callback = _make_callback(reporter)
    callback.report_train_step(step=2, epoch=1, loss=0.5)

    series = reporter.reports[-1]["metrics"]["train_loss"]
    assert [entry["step"] for entry in series] == [1, 2]


def test_training_start_does_not_erase_seeded_metrics() -> None:
    """report_training_start fires before the first step; it must not blank the blob."""
    prior = {"train_loss": [{"step": 1, "epoch": 1, "value": 0.9}], "val_loss": []}
    reporter = _RecordingReporter(prior)
    callback = _make_callback(reporter)
    callback.report_training_start(max_steps=10, num_epochs=1)

    assert reporter.reports[0]["metrics"]["train_loss"] == prior["train_loss"]


# --------------------------------------------------------------------------- #
# Optional val_loss (GRPO)
# --------------------------------------------------------------------------- #


def test_validation_without_loss_omits_the_key(reporter: _RecordingReporter) -> None:
    """GRPO validates on accuracy; a null val_loss would chart as zero."""
    callback = _make_callback(reporter)
    callback.report_validation(step=1, epoch=1, val_loss=None, accuracy=0.75)

    report = reporter.reports[-1]
    assert "val_loss" not in report
    assert report["accuracy"] == 0.75
    assert report["phase"] == "validation"


def test_validation_without_loss_leaves_the_series_empty(reporter: _RecordingReporter) -> None:
    callback = _make_callback(reporter)
    callback.report_validation(step=1, epoch=1, val_loss=None, accuracy=0.75)

    assert reporter.reports[-1]["metrics"]["val_loss"] == []


def test_additional_metrics_ride_along_as_scalars(reporter: _RecordingReporter) -> None:
    """The wide RL metric set is current-step only; it must not enter the series."""
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, loss=0.5, reward=0.62, kl_penalty=0.008)

    report = reporter.reports[-1]
    assert report["reward"] == 0.62
    assert report["kl_penalty"] == 0.008
    assert report["metrics"]["train_loss"] == [{"step": 1, "epoch": 1, "value": 0.5}]


def test_close_delegates_to_the_reporter(reporter: _RecordingReporter) -> None:
    _make_callback(reporter).close()

    assert reporter.closed
