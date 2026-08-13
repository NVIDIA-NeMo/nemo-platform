# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the shared TrainingProgressCallback.

Focused on the contract every backend depends on. The Jobs service merges
``status_details`` key-wise but does so shallowly, so a report either resends a
series in full or leaves the key out entirely -- and a report states a scalar
only when it actually observed one, because a null charts as a real zero. Basic
accumulation and resume-seeding are covered by the per-backend suites; this file
covers the shared surface itself.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import pytest
from nmp.customization_common.training.callbacks import TrainingProgressCallback, is_chartable
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
# Which reports carry the series
# --------------------------------------------------------------------------- #


def test_step_reports_carry_the_series(reporter: _RecordingReporter) -> None:
    """The reports that move a curve send every curve, since the merge is shallow."""
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, loss=0.5)
    callback.report_validation(step=1, epoch=1, val_loss=0.45)

    assert len(reporter.reports) == 2
    for report in reporter.reports:
        assert "metrics" in report, report["phase"]
        assert set(report["metrics"]) == {"train_loss", "val_loss"}


def test_non_step_reports_omit_the_series(reporter: _RecordingReporter) -> None:
    """The server merges, so a report with nothing to add leaves the stored curve alone.

    Sending it anyway is pure upload on every checkpoint, and at training start
    it is worse than useless: the accumulator is empty there, and a shallow merge
    would replace a resumed job's stored series with two empty lists.
    """
    callback = _make_callback(reporter)
    callback.report_training_start(max_steps=10, num_epochs=1)
    callback.report_checkpoint_saved(step=1, epoch=1, checkpoint_path="/ckpt")
    callback.report_epoch_end(step=1, epoch=1)

    assert len(reporter.reports) == 3
    for report in reporter.reports:
        assert "metrics" not in report, report["phase"]


def test_training_start_does_not_resend_seeded_metrics() -> None:
    """It fires before the first step, so it has nothing to say about the curves."""
    prior = {"train_loss": [{"step": 1, "epoch": 1, "value": 0.9}], "val_loss": []}
    reporter = _RecordingReporter(prior)
    callback = _make_callback(reporter)
    callback.report_training_start(max_steps=10, num_epochs=1)

    assert "metrics" not in reporter.reports[0]

    # ...and the seeded series is still there for the first step that does report.
    callback.report_train_step(step=2, epoch=1, loss=0.8)
    assert reporter.reports[-1]["metrics"]["train_loss"] == [
        {"step": 1, "epoch": 1, "value": 0.9},
        {"step": 2, "epoch": 1, "value": 0.8},
    ]


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
# Optional checkpoint_path
# --------------------------------------------------------------------------- #


def test_checkpoint_report_without_a_path_omits_the_key(reporter: _RecordingReporter) -> None:
    """A null would overwrite the last known checkpoint instead of leaving it.

    The server merges key-wise, so omitting the key leaves the stored path
    standing while an explicit null replaces it. automodel and unsloth both pass
    None when their framework hands back no path.
    """
    _make_callback(reporter).report_checkpoint_saved(step=1, epoch=1)

    assert "checkpoint_path" not in reporter.reports[-1]


def test_checkpoint_report_with_a_path_states_it(reporter: _RecordingReporter) -> None:
    _make_callback(reporter).report_checkpoint_saved(step=1, epoch=1, checkpoint_path="/ckpt")

    assert reporter.reports[-1]["checkpoint_path"] == "/ckpt"


# --------------------------------------------------------------------------- #
# additional_metrics
# --------------------------------------------------------------------------- #


def test_additional_train_metrics_become_series_and_ride_along(
    reporter: _RecordingReporter,
) -> None:
    """Each backend metric is both a curve and a current-step scalar."""
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, loss=0.5, reward=0.62, kl_penalty=0.008)
    callback.report_train_step(step=2, epoch=1, loss=0.4, reward=0.71, kl_penalty=0.009)

    report = reporter.reports[-1]
    assert report["reward"] == 0.71, "latest value still rides along at the top level"
    assert report["metrics"]["train_reward"] == [
        {"step": 1, "epoch": 1, "value": 0.62},
        {"step": 2, "epoch": 1, "value": 0.71},
    ]
    assert report["metrics"]["train_kl_penalty"] == [
        {"step": 1, "epoch": 1, "value": 0.008},
        {"step": 2, "epoch": 1, "value": 0.009},
    ]


def test_lr_and_grad_norm_accumulate(reporter: _RecordingReporter) -> None:
    """Both are curves people read; neither is an `additional_metric`."""
    _make_callback(reporter).report_train_step(step=1, epoch=1, loss=0.5, lr=5e-06, grad_norm=1.9)

    metrics = reporter.reports[-1]["metrics"]
    assert metrics["train_lr"] == [{"step": 1, "epoch": 1, "value": 5e-06}]
    assert metrics["train_grad_norm"] == [{"step": 1, "epoch": 1, "value": 1.9}]


def test_absent_lr_and_grad_norm_create_no_series(reporter: _RecordingReporter) -> None:
    """A backend that reports neither should not get two empty keys."""
    _make_callback(reporter).report_train_step(step=1, epoch=1, loss=0.5)

    metrics = reporter.reports[-1]["metrics"]
    assert "train_lr" not in metrics
    assert "train_grad_norm" not in metrics


def test_additional_validation_metrics_become_series_and_ride_along(reporter: _RecordingReporter) -> None:
    _make_callback(reporter).report_validation(step=1, epoch=1, val_loss=0.25, accuracy=0.9)

    report = reporter.reports[-1]
    assert report["accuracy"] == 0.9
    assert report["metrics"]["val_accuracy"] == [{"step": 1, "epoch": 1, "value": 0.9}]


def test_train_and_validation_metrics_of_the_same_name_stay_separate(
    reporter: _RecordingReporter,
) -> None:
    """GRPO reports `truncation_rate` in both dicts; one series would interleave them."""
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, loss=0.5, truncation_rate=0.18)
    callback.report_validation(step=1, epoch=1, truncation_rate=0.04)

    metrics = reporter.reports[-1]["metrics"]
    assert metrics["train_truncation_rate"] == [{"step": 1, "epoch": 1, "value": 0.18}]
    assert metrics["val_truncation_rate"] == [{"step": 1, "epoch": 1, "value": 0.04}]


def test_non_numeric_metrics_are_dropped_from_the_series(reporter: _RecordingReporter) -> None:
    """Histograms and tables ride in the same dict as the scalars upstream."""
    _make_callback(reporter).report_train_step(
        step=1, epoch=1, loss=0.5, histogram=object(), nested={"a": 1}, flag=True, missing=float("nan")
    )

    metrics = reporter.reports[-1]["metrics"]
    assert set(metrics) == {"train_loss", "val_loss"}


def test_a_dropped_metric_costs_only_itself(reporter: _RecordingReporter) -> None:
    """It must not ride along in the payload either, or the whole report dies.

    A `Histogram` in status_details makes the SDK update fail to serialize, and
    `update_task` swallows that error -- so every metric in the report is lost
    while the job goes on looking healthy. Verified against a live platform
    before this filter existed: the step never landed.
    """
    _make_callback(reporter).report_train_step(step=1, epoch=1, loss=0.5, hist=object(), reward=0.62)

    report = reporter.reports[-1]
    assert "hist" not in report
    assert report["reward"] == 0.62, "a well-behaved metric in the same report still lands"


def test_a_metric_named_phase_does_not_break_the_report(reporter: _RecordingReporter) -> None:
    """`phase` is report_running's own parameter; a collision is a TypeError.

    Splat order silently shadows the other reserved names. This one raised
    straight out of the training loop, so it is filtered rather than shadowed.
    """
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, loss=0.5, phase=1.0)
    callback.report_validation(step=1, epoch=1, val_loss=0.4, phase=1.0)

    assert [r["phase"] for r in reporter.reports] == ["training", "validation"]


def test_a_train_step_metric_named_val_loss_stays_out_of_the_val_curve(
    reporter: _RecordingReporter,
) -> None:
    """The legacy bare names are exempt from prefixing per phase, not per name.

    Matching on the name alone put a training-side number in the series Studio
    draws as the validation loss.
    """
    _make_callback(reporter).report_train_step(step=1, epoch=1, loss=0.5, val_loss=99.0)

    metrics = reporter.reports[-1]["metrics"]
    assert metrics["val_loss"] == []
    assert metrics["train_val_loss"] == [{"step": 1, "epoch": 1, "value": 99.0}]


def test_the_legacy_names_still_go_unprefixed_in_their_own_phase(reporter: _RecordingReporter) -> None:
    """The Studio loss chart reads `train_loss`/`val_loss` by those exact names."""
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, loss=0.5)
    callback.report_validation(step=1, epoch=1, val_loss=0.4)

    metrics = reporter.reports[-1]["metrics"]
    assert metrics["train_loss"] == [{"step": 1, "epoch": 1, "value": 0.5}]
    assert metrics["val_loss"] == [{"step": 1, "epoch": 1, "value": 0.4}]


# --------------------------------------------------------------------------- #
# A scalar is stated only when it was observed
# --------------------------------------------------------------------------- #


def test_absent_lr_and_grad_norm_are_omitted_not_nulled(reporter: _RecordingReporter) -> None:
    """A null charts as a real zero -- the same reason val_loss is omitted."""
    _make_callback(reporter).report_train_step(step=1, epoch=1, loss=0.5)

    report = reporter.reports[-1]
    assert "lr" not in report
    assert "grad_norm" not in report


def test_non_finite_scalars_are_omitted(reporter: _RecordingReporter) -> None:
    """A NaN grad_norm is routine on a skipped step; the SDK sends it as null."""
    _make_callback(reporter).report_train_step(step=1, epoch=1, loss=0.5, lr=float("inf"), grad_norm=float("nan"))

    report = reporter.reports[-1]
    assert "lr" not in report
    assert "grad_norm" not in report
    assert report["train_loss"] == 0.5


def test_a_non_finite_val_loss_is_omitted(reporter: _RecordingReporter) -> None:
    _make_callback(reporter).report_validation(step=1, epoch=1, val_loss=float("nan"))

    report = reporter.reports[-1]
    assert "val_loss" not in report
    assert report["metrics"]["val_loss"] == []


def test_is_chartable_classifies_an_unbounded_int_without_raising() -> None:
    """float() overflows on a big enough int; the predicate must not propagate it."""
    assert is_chartable(10**400) is False


def test_infinite_metrics_are_dropped_from_the_series(reporter: _RecordingReporter) -> None:
    """A diverged run's inf is not a chart value, and `Infinity` is not valid JSON."""
    _make_callback(reporter).report_train_step(
        step=1, epoch=1, loss=0.5, diverged=float("inf"), collapsed=float("-inf")
    )

    metrics = reporter.reports[-1]["metrics"]
    assert set(metrics) == {"train_loss", "val_loss"}


def test_series_survive_a_resume_beyond_the_loss_curves() -> None:
    """A resumed job must continue every curve, not just train_loss."""
    prior = {
        "train_loss": [{"step": 1, "epoch": 1, "value": 0.9}],
        "train_reward": [{"step": 1, "epoch": 1, "value": 0.2}],
    }
    reporter = _RecordingReporter(prior)
    _make_callback(reporter).report_train_step(step=2, epoch=1, loss=0.8, reward=0.3)

    assert reporter.reports[-1]["metrics"]["train_reward"] == [
        {"step": 1, "epoch": 1, "value": 0.2},
        {"step": 2, "epoch": 1, "value": 0.3},
    ]


def test_additional_metrics_cannot_shadow_the_series(reporter: _RecordingReporter) -> None:
    """`metrics` is not a parameter, so only splat order stops a silent override.

    `step`/`epoch`/`lr`/`grad_norm`/`backend` are named parameters -- passing one
    is a TypeError at the call site. `metrics` and `train_loss` would just win.
    """
    _make_callback(reporter).report_train_step(step=1, epoch=1, loss=0.5, metrics="clobbered")

    report = reporter.reports[-1]
    assert report["metrics"]["train_loss"] == [{"step": 1, "epoch": 1, "value": 0.5}]


def test_additional_metrics_cannot_shadow_the_step_loss(reporter: _RecordingReporter) -> None:
    _make_callback(reporter).report_train_step(step=1, epoch=1, loss=0.5, train_loss="clobbered")

    assert reporter.reports[-1]["train_loss"] == 0.5


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


def test_no_backend_field_when_the_default_is_unset(reporter: _RecordingReporter) -> None:
    """automodel and NeMo-RL both depend on this: their reports carry no `backend`.

    Neither subclasses this class, so the absence of the key is a property of the
    default here rather than of anything on their side. unsloth opts in.
    """
    callback = _make_callback(reporter)
    callback.report_training_start(max_steps=10, num_epochs=1)
    callback.report_train_step(step=1, epoch=1, loss=0.5)
    callback.report_validation(step=1, epoch=1, val_loss=0.4)
    callback.report_checkpoint_saved(step=1, epoch=1, checkpoint_path="/ckpt")
    callback.report_epoch_end(step=1, epoch=1)

    assert reporter.reports, "expected reports to assert against"
    assert all("backend" not in report for report in reporter.reports)


def test_close_delegates_to_the_reporter(reporter: _RecordingReporter) -> None:
    _make_callback(reporter).close()

    assert reporter.closed
