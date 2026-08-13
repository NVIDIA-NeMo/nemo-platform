# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the shared TrainingProgressCallback.

Focused on the contract every backend depends on. There is one naming rule --
a metric is stored and reported as ``<phase>_<name>`` -- and no metric is
privileged, so most of this file is about proving the rule holds with no
exceptions hiding in it. The rest covers the transport: the Jobs service merges
``status_details`` key-wise but shallowly, so a report either resends a series in
full or leaves the key out, and states a scalar only when it observed one.
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
# One naming rule, no exceptions
# --------------------------------------------------------------------------- #


def test_the_phase_supplies_the_prefix(reporter: _RecordingReporter) -> None:
    """Backends pass their framework's own names; the phase namespaces them."""
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.5, "lr": 5e-06, "grad_norm": 1.9})
    callback.report_validation(step=1, epoch=1, metrics={"loss": 0.4, "accuracy": 0.9})

    metrics = reporter.reports[-1]["metrics"]
    assert metrics["train_loss"] == [{"step": 1, "epoch": 1, "value": 0.5}]
    assert metrics["train_lr"] == [{"step": 1, "epoch": 1, "value": 5e-06}]
    assert metrics["train_grad_norm"] == [{"step": 1, "epoch": 1, "value": 1.9}]
    assert metrics["val_loss"] == [{"step": 1, "epoch": 1, "value": 0.4}]
    assert metrics["val_accuracy"] == [{"step": 1, "epoch": 1, "value": 0.9}]


def test_train_loss_and_val_loss_fall_out_of_the_rule(reporter: _RecordingReporter) -> None:
    """The two names Studio charts are what `loss` produces, not special cases.

    They used to be carved out of the prefixing scheme because backends passed
    them pre-prefixed. Passing the framework's own `loss` regenerates both names
    from the ordinary rule, which is why nothing downstream had to change.
    """
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.5})
    callback.report_validation(step=1, epoch=1, metrics={"loss": 0.4})

    metrics = reporter.reports[-1]["metrics"]
    assert metrics["train_loss"] == [{"step": 1, "epoch": 1, "value": 0.5}]
    assert metrics["val_loss"] == [{"step": 1, "epoch": 1, "value": 0.4}]


def test_the_same_name_in_both_phases_stays_separate(reporter: _RecordingReporter) -> None:
    """DPO reports `accuracy` in both dicts; one series would interleave them."""
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.5, "accuracy": 0.18})
    callback.report_validation(step=1, epoch=1, metrics={"accuracy": 0.04})

    metrics = reporter.reports[-1]["metrics"]
    assert metrics["train_accuracy"] == [{"step": 1, "epoch": 1, "value": 0.18}]
    assert metrics["val_accuracy"] == [{"step": 1, "epoch": 1, "value": 0.04}]


def test_a_pre_prefixed_name_is_not_re_interpreted(reporter: _RecordingReporter) -> None:
    """A backend passing `val_loss` on a train step gets `train_val_loss`.

    The rule is mechanical: it never inspects the name for meaning, so a train
    step cannot reach the validation curve however its metric is spelled.
    """
    _make_callback(reporter).report_train_step(step=1, epoch=1, metrics={"loss": 0.5, "val_loss": 99.0})

    metrics = reporter.reports[-1]["metrics"]
    assert metrics["val_loss"] == []
    assert metrics["train_val_loss"] == [{"step": 1, "epoch": 1, "value": 99.0}]


def test_the_current_value_uses_the_series_name(reporter: _RecordingReporter) -> None:
    """One name per metric, whether you read the curve or the latest point."""
    _make_callback(reporter).report_train_step(step=1, epoch=1, metrics={"loss": 0.5, "lr": 5e-06, "reward": 0.62})

    report = reporter.reports[-1]
    assert report["train_loss"] == 0.5
    assert report["train_lr"] == 5e-06
    assert report["train_reward"] == 0.62
    assert "loss" not in report and "lr" not in report and "reward" not in report


def test_reserved_names_cannot_be_reached_by_a_metric(reporter: _RecordingReporter) -> None:
    """Prefixing removes the collision class outright rather than filtering it.

    `phase` is report_running's own parameter and used to raise TypeError into
    the training loop; `step`, `epoch` and `metrics` are this callback's own keys
    and used to need splat ordering to avoid being shadowed.
    """
    callback = _make_callback(reporter)
    collide = {"phase": 1.0, "step": 2.0, "epoch": 3.0, "metrics": 4.0, "loss": 0.5}
    callback.report_train_step(step=10, epoch=1, metrics=collide)
    callback.report_validation(step=10, epoch=1, metrics=collide)

    for report in reporter.reports:
        assert report["step"] == 10, "the real step survives"
        assert report["epoch"] == 1
        assert isinstance(report["metrics"], dict), "the series payload survives"
    assert [r["phase"] for r in reporter.reports] == ["training", "validation"]
    assert reporter.reports[0]["train_phase"] == 1.0, "the metric is kept, under its namespaced name"
    assert reporter.reports[0]["train_step"] == 2.0


# --------------------------------------------------------------------------- #
# Nothing is required
# --------------------------------------------------------------------------- #


def test_a_step_without_a_loss_reports_the_rest(reporter: _RecordingReporter) -> None:
    """No metric is privileged, so none of them is mandatory either."""
    _make_callback(reporter).report_train_step(step=1, epoch=1, metrics={"reward": 0.62})

    report = reporter.reports[-1]
    assert report["train_reward"] == 0.62
    assert report["metrics"]["train_loss"] == []


def test_validation_without_a_loss_leaves_the_curve_empty(reporter: _RecordingReporter) -> None:
    """An algorithm may validate on task metrics alone; a null charts as zero."""
    _make_callback(reporter).report_validation(step=1, epoch=1, metrics={"accuracy": 0.75})

    report = reporter.reports[-1]
    assert "val_loss" not in report
    assert report["val_accuracy"] == 0.75
    assert report["metrics"]["val_loss"] == []


def test_an_empty_metric_dict_still_reports_progress(reporter: _RecordingReporter) -> None:
    """step/epoch are progress, not metrics; they land with or without a curve."""
    _make_callback(reporter).report_train_step(step=7, epoch=2, metrics={})

    report = reporter.reports[-1]
    assert report["step"] == 7
    assert report["epoch"] == 2
    assert report["metrics"] == {"train_loss": [], "val_loss": []}


# --------------------------------------------------------------------------- #
# What cannot be charted is dropped from both places
# --------------------------------------------------------------------------- #


def test_unchartable_metrics_are_dropped_from_the_series(reporter: _RecordingReporter) -> None:
    """Histograms and tables ride in the same dict as the scalars upstream."""
    _make_callback(reporter).report_train_step(
        step=1,
        epoch=1,
        metrics={"loss": 0.5, "histogram": object(), "nested": {"a": 1}, "flag": True, "missing": float("nan")},
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
    _make_callback(reporter).report_train_step(step=1, epoch=1, metrics={"hist": object(), "reward": 0.62})

    report = reporter.reports[-1]
    assert "hist" not in report and "train_hist" not in report
    assert report["train_reward"] == 0.62, "a well-behaved metric in the same report still lands"


def test_non_finite_scalars_are_omitted(reporter: _RecordingReporter) -> None:
    """A NaN grad_norm is routine on a skipped step; the SDK sends it as null."""
    _make_callback(reporter).report_train_step(
        step=1, epoch=1, metrics={"loss": 0.5, "lr": float("inf"), "grad_norm": float("nan"), "absent": None}
    )

    report = reporter.reports[-1]
    assert "train_lr" not in report
    assert "train_grad_norm" not in report
    assert "train_absent" not in report
    assert report["train_loss"] == 0.5


def test_counts_stay_integers(reporter: _RecordingReporter) -> None:
    """`num_valid_samples: 8` should not chart as 8.0."""
    _make_callback(reporter).report_train_step(step=1, epoch=1, metrics={"num_valid_samples": 8})

    assert reporter.reports[-1]["train_num_valid_samples"] == 8


def test_numpy_scalars_are_coerced(reporter: _RecordingReporter) -> None:
    """numpy satisfies numbers.Real but is not JSON-serializable."""
    np = pytest.importorskip("numpy")
    _make_callback(reporter).report_train_step(step=1, epoch=1, metrics={"loss": np.float32(0.5), "count": np.int64(3)})

    report = reporter.reports[-1]
    assert type(report["train_loss"]) is float
    assert type(report["train_count"]) is int


class _Histogram:
    """Stand-in for a non-numeric metric value -- NaN-hostile, like the real thing."""

    def __float__(self) -> float:
        raise TypeError("Histogram is not a scalar")


@pytest.mark.parametrize(
    "value,expected",
    [
        (0.5, True),
        (0, True),
        (-1.5, True),
        (float("nan"), False),
        (float("inf"), False),
        (float("-inf"), False),
        (None, False),
        # Non-scalars that genuinely appear in NeMo-RL metric dicts. Each raises
        # TypeError under a bare math.isfinite, which is the regression guarded here.
        (_Histogram(), False),
        ({"inflight": [1, 2]}, False),
        ([1, 2, 3], False),
        ("0.5", False),
        # bool is an int subclass; charting a flag as 0/1 is not wanted.
        (True, False),
        (False, False),
        # float() overflows here; the predicate must classify, never propagate.
        (10**400, False),
    ],
)
def test_is_chartable(value: Any, expected: bool) -> None:
    assert is_chartable(value) is expected


def test_is_chartable_accepts_numpy_scalars() -> None:
    np = pytest.importorskip("numpy")
    assert is_chartable(np.float32(0.5)) is True
    assert is_chartable(np.float64(0.5)) is True
    assert is_chartable(np.int64(3)) is True
    assert is_chartable(np.float32("nan")) is False


# --------------------------------------------------------------------------- #
# Which reports carry the series
# --------------------------------------------------------------------------- #


def test_step_reports_carry_the_series(reporter: _RecordingReporter) -> None:
    """The reports that move a curve send every curve, since the merge is shallow."""
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.5})
    callback.report_validation(step=1, epoch=1, metrics={"loss": 0.45})

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
    callback.report_train_step(step=2, epoch=1, metrics={"loss": 0.8})
    assert reporter.reports[-1]["metrics"]["train_loss"] == [
        {"step": 1, "epoch": 1, "value": 0.9},
        {"step": 2, "epoch": 1, "value": 0.8},
    ]


def test_series_survive_a_resume_beyond_the_loss_curves() -> None:
    """A resumed job must continue every curve, not just train_loss."""
    prior = {
        "train_loss": [{"step": 1, "epoch": 1, "value": 0.9}],
        "train_reward": [{"step": 1, "epoch": 1, "value": 0.2}],
    }
    reporter = _RecordingReporter(prior)
    _make_callback(reporter).report_train_step(step=2, epoch=1, metrics={"loss": 0.8, "reward": 0.3})

    assert reporter.reports[-1]["metrics"]["train_reward"] == [
        {"step": 1, "epoch": 1, "value": 0.2},
        {"step": 2, "epoch": 1, "value": 0.3},
    ]


def test_series_are_snapshots_not_live_references(reporter: _RecordingReporter) -> None:
    """A shared list would retroactively mutate already-sent payloads."""
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.5})
    first_payload = reporter.reports[-1]["metrics"]["train_loss"]
    callback.report_train_step(step=2, epoch=1, metrics={"loss": 0.4})

    assert len(first_payload) == 1


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
# Backend stamping
# --------------------------------------------------------------------------- #


def test_the_default_backend_is_stamped_on_every_report(reporter: _RecordingReporter) -> None:
    class _Stamped(TrainingProgressCallback):
        _default_backend: ClassVar[str | None] = "test-backend"

    callback = _Stamped(cast(JobsServiceProgressReporter, reporter))
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.5, "reward": 0.62})

    report = reporter.reports[-1]
    assert report["backend"] == "test-backend"
    assert report["train_reward"] == 0.62


def test_no_backend_field_when_the_default_is_unset(reporter: _RecordingReporter) -> None:
    """automodel and NeMo-RL both depend on this: their reports carry no `backend`.

    Neither subclasses this class, so the absence of the key is a property of the
    default here rather than of anything on their side. unsloth opts in.
    """
    callback = _make_callback(reporter)
    callback.report_training_start(max_steps=10, num_epochs=1)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.5})
    callback.report_validation(step=1, epoch=1, metrics={"loss": 0.4})
    callback.report_checkpoint_saved(step=1, epoch=1, checkpoint_path="/ckpt")
    callback.report_epoch_end(step=1, epoch=1)

    assert reporter.reports, "expected reports to assert against"
    assert all("backend" not in report for report in reporter.reports)


def test_a_per_call_backend_overrides_the_default(reporter: _RecordingReporter) -> None:
    """unsloth's HF trainer callback passes it per call."""
    _make_callback(reporter).report_train_step(step=1, epoch=1, metrics={"loss": 0.5}, backend="unsloth")

    assert reporter.reports[-1]["backend"] == "unsloth"


def test_close_delegates_to_the_reporter(reporter: _RecordingReporter) -> None:
    _make_callback(reporter).close()

    assert reporter.closed
