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

    def fetch_current_metrics(self) -> dict[str, list[dict[str, Any]]] | None:
        return self._prior

    def configure_progress_tracking(self, max_steps: int, num_epochs: int) -> None:
        self.tracking = (max_steps, num_epochs)

    def report_running(self, phase: str, **details: Any) -> None:
        self.reports.append({"phase": phase, **details})

    def close(self) -> None:
        self.closed = True


class _UnreadableReporter(_RecordingReporter):
    """A reporter whose one read failed, as opposed to finding nothing stored."""

    def fetch_current_metrics(self) -> dict[str, list[dict[str, Any]]] | None:
        return None


@pytest.fixture
def reporter() -> _RecordingReporter:
    return _RecordingReporter()


def _make_callback(reporter: _RecordingReporter, **kwargs: Any) -> TrainingProgressCallback:
    """Build the callback over a duck-typed reporter, narrowing the type once here."""
    return TrainingProgressCallback(cast(JobsServiceProgressReporter, reporter), **kwargs)


def _train_steps(reporter: _RecordingReporter) -> list[int]:
    return [r["step"] for r in reporter.reports if r["phase"] == "training" and "step" in r]


def _val_steps(reporter: _RecordingReporter) -> list[int]:
    return [r["step"] for r in reporter.reports if r["phase"] == "validation"]


# --------------------------------------------------------------------------- #
# One naming rule, no exceptions
# --------------------------------------------------------------------------- #


def test_the_phase_supplies_the_prefix(reporter: _RecordingReporter) -> None:
    """Backends pass their framework's own names; the phase qualifies them."""
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
    assert reporter.reports[0]["train_phase"] == 1.0, "the metric is kept, under its qualified name"
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
    """step/epoch are progress, not metrics; they land with or without a curve.

    The series are left out rather than resent: nothing was added to them, the
    stored copy already matches, and the merge leaves an unmentioned key
    standing. Resending would pay the full payload for a report that changed
    nothing -- up to 413 KB by this module's own measurements.
    """
    _make_callback(reporter).report_train_step(step=7, epoch=2, metrics={})

    report = reporter.reports[-1]
    assert report["step"] == 7
    assert report["epoch"] == 2
    assert "metrics" not in report


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


# --------------------------------------------------------------------------- #
# Seeded points, and the run they came from
# --------------------------------------------------------------------------- #


def test_validation_and_training_at_the_same_step_both_land(reporter: _RecordingReporter) -> None:
    """NeMo-RL validates at step N before logging train N; both belong on the curves."""
    callback = _make_callback(reporter)
    callback.report_validation(step=10, epoch=1, metrics={"loss": 0.9})
    callback.report_train_step(step=10, epoch=1, metrics={"loss": 0.8})

    metrics = reporter.reports[-1]["metrics"]
    assert metrics["val_loss"] == [{"step": 10, "epoch": 1, "value": 0.9}]
    assert metrics["train_loss"] == [{"step": 10, "epoch": 1, "value": 0.8}]


def test_a_restart_appends_to_the_previous_runs_points() -> None:
    """Known issue, pinned so it cannot change without someone deciding to.

    A replaced pod -- a suspended and resumed Kubernetes Job, or a Volcano
    restart where an execution profile raises maxRetry above zero -- seeds itself
    from the old run's points and appends its own. This is the shape it takes
    when the backend does not resume: automodel and unsloth never do, and a
    NeMo-RL run that has not written a checkpoint yet has none to return to. The
    series then carries both runs end to end.

    The other shape is a NeMo-RL run that does resume -- dpo.setup() loads the
    latest checkpoint unconditionally -- and replays the steps it had already
    reported since that checkpoint, so its curve doubles back across that range
    instead of restarting. Not pinned here.

    Accepted rather than solved either way: telling the runs apart needs a run
    identifier on each point, and dropping the superseded ones is right for a
    replay and destructive for a restart. See the seeding note in callbacks.py.
    """
    prior = {"train_loss": [{"step": 50, "epoch": 1, "value": 1.0}]}
    reporter = _RecordingReporter(prior)
    _make_callback(reporter).report_train_step(step=1, epoch=1, metrics={"loss": 2.0})

    assert reporter.reports[-1]["metrics"]["train_loss"] == [
        {"step": 50, "epoch": 1, "value": 1.0},
        {"step": 1, "epoch": 1, "value": 2.0},
    ]


def test_a_malformed_stored_point_cannot_raise_into_the_training_loop() -> None:
    """The blob is read back from the server, so its shape is not guaranteed.

    report_train_step is called straight from NeMo-RL's log_metrics with nothing
    catching underneath, so a stored point that is not a {step, ...} dict has to
    be dropped rather than raise.
    """
    # Cast because the shape is the point: this is what a corrupted blob reads
    # back as, and no annotation describes it honestly.
    prior = cast(
        dict[str, list[dict[str, Any]]],
        {"train_loss": [{"step": 100, "epoch": 1, "value": 1.0}, "junk", {"epoch": 1}, {"step": "eight"}]},
    )
    reporter = _RecordingReporter(prior)
    _make_callback(reporter).report_train_step(step=110, epoch=1, metrics={"loss": 0.7})

    assert reporter.reports[-1]["metrics"]["train_loss"] == [
        {"step": 100, "epoch": 1, "value": 1.0},
        {"step": 110, "epoch": 1, "value": 0.7},
    ]


def test_a_report_that_changes_no_curve_omits_the_series(reporter: _RecordingReporter) -> None:
    """Nothing recorded means nothing to say: the stored copy already matches."""
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.5})
    callback.report_train_step(step=2, epoch=1, metrics={"grad_norm": float("nan")})

    assert "metrics" in reporter.reports[0]
    assert "metrics" not in reporter.reports[-1]


# --------------------------------------------------------------------------- #
# Training start states where the run actually starts
# --------------------------------------------------------------------------- #


def test_training_start_states_the_schedule_and_no_position(reporter: _RecordingReporter) -> None:
    """It fires before the first step, so it has no position to report yet."""
    _make_callback(reporter).report_training_start(max_steps=940, num_epochs=2)

    report = reporter.reports[-1]
    assert report["max_steps"] == 940
    assert report["num_epochs"] == 2
    assert "step" not in report


def test_training_start_does_not_reset_the_stored_progress() -> None:
    """report_running derives percentage_done from a stated step, and it merges.

    A literal 0 here wrote 0% over whatever progress the task had stored, and
    Studio rendered `2/2 (0%)` until the first train step landed -- many minutes
    later at log_interval=10. Stating nothing leaves the stored value standing.
    """
    prior = {"train_loss": [{"step": 470, "epoch": 2, "value": 0.5}]}
    reporter = _RecordingReporter(prior)

    _make_callback(reporter).report_training_start(max_steps=940, num_epochs=2)

    assert "step" not in reporter.reports[-1]
    assert "percentage_done" not in reporter.reports[-1]


# --------------------------------------------------------------------------- #
# A seed that could not be read is not a seed that found nothing
# --------------------------------------------------------------------------- #


def test_a_failed_seed_read_withholds_the_series() -> None:
    """The accumulator is known incomplete, and the merge replaces a sent key whole.

    Sending it would overwrite the stored history with the fraction of it this
    process happens to have. Omitting the key leaves the history standing, which
    costs this run's curves and is the recoverable half of the trade.
    """
    reporter = _UnreadableReporter()
    callback = _make_callback(reporter)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.5})
    callback.report_validation(step=1, epoch=1, metrics={"loss": 0.4})

    assert all("metrics" not in report for report in reporter.reports)


def test_a_failed_seed_read_still_reports_progress_and_current_values() -> None:
    """Only the accumulated curves are withheld; the scalars merge harmlessly."""
    reporter = _UnreadableReporter()
    _make_callback(reporter).report_train_step(step=7, epoch=2, metrics={"loss": 0.5, "lr": 5e-06})

    report = reporter.reports[-1]
    assert report["step"] == 7
    assert report["epoch"] == 2
    assert report["train_loss"] == 0.5
    assert report["train_lr"] == 5e-06


def test_an_empty_seed_read_still_reports_the_series(reporter: _RecordingReporter) -> None:
    """The other half of the distinction: nothing stored is safe to write over."""
    _make_callback(reporter).report_train_step(step=1, epoch=1, metrics={"loss": 0.5})

    assert reporter.reports[-1]["metrics"]["train_loss"] == [{"step": 1, "epoch": 1, "value": 0.5}]


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


# --------------------------------------------------------------------------- #
# The reporting cadence
#
# Moved here from services/rl/tests/test_nemo_rl_logger.py, which is where this
# was implemented for one backend while the other two reported every step. The
# invariants are that backend's; the coverage is now everyone's.
# --------------------------------------------------------------------------- #


def test_the_cadence_follows_the_run_length(reporter: _RecordingReporter) -> None:
    """One input, and it is not the validation cadence.

    How often someone wants the curve and the progress bar to move is unrelated
    to how often the run validates. The two were coupled once, and the coupling
    ran backwards: validating less often -- what you do when validation is
    expensive -- made the training curve coarser.
    """
    callback = _make_callback(reporter, max_points=10)
    callback.report_training_start(max_steps=100, num_epochs=1)
    for step in range(1, 101):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})

    assert _train_steps(reporter) == [1, 11, 21, 31, 41, 51, 61, 71, 81, 91]


def test_a_long_run_draws_a_usable_curve_and_no_more(reporter: _RecordingReporter) -> None:
    """The point of the whole exercise, at the scale where it matters.

    20,000 steps used to mean 20,000 reports for two of the three backends, each
    resending every accumulated series in full and each one blocking the training
    loop for longer than the last.
    """
    callback = _make_callback(reporter, max_points=200)
    callback.report_training_start(max_steps=20_000, num_epochs=1)
    for step in range(1, 20_001):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})

    reported = _train_steps(reporter)
    assert len(reported) == 200
    assert len(reporter.reports[-1]["metrics"]["train_loss"]) == 200


def test_a_run_shorter_than_the_budget_reports_every_step(reporter: _RecordingReporter) -> None:
    """Nothing is thinned that did not need thinning."""
    callback = _make_callback(reporter, max_points=200)
    callback.report_training_start(max_steps=50, num_epochs=1)
    for step in range(1, 51):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})

    assert _train_steps(reporter) == list(range(1, 51))


def test_the_first_arrival_is_always_admitted(reporter: _RecordingReporter) -> None:
    """A curve should start at the beginning of the run, not one interval into it."""
    callback = _make_callback(reporter, max_points=2)
    callback.report_training_start(max_steps=1_000, num_epochs=1)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.5})

    assert _train_steps(reporter) == [1]


def test_reporting_before_the_schedule_is_stated_is_not_withheld(reporter: _RecordingReporter) -> None:
    """A backend that never states a run length reports everything, not nothing.

    The interval is unknown until report_training_start, and the safe reading of
    an unknown run length is that it is short. Getting this backwards would mean
    a backend that forgot to announce its schedule reported once and then went
    silent, which is indistinguishable from a hung run.
    """
    callback = _make_callback(reporter, max_points=200)
    for step in range(1, 6):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})

    assert _train_steps(reporter) == [1, 2, 3, 4, 5]


def test_an_unstated_run_length_is_still_bounded(reporter: _RecordingReporter) -> None:
    """Admitting everything is the *starting* position, not the standing one.

    With no schedule to seed an interval from, decimation is the only thing
    holding the budget -- so it has to be able to hold it alone. The cadence
    coarsens as the curve fills rather than being right from step one, which is
    the documented cost of not knowing the run length.
    """
    callback = _make_callback(reporter, max_points=20)
    for step in range(1, 1_001):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})

    stored = reporter.reports[-1]["metrics"]["train_loss"]
    assert len(stored) <= 20
    assert len(_train_steps(reporter)) < 100, "and the report count is bounded too, not just the curve"


# --------------------------------------------------------------------------- #
# Elapsed steps, not a modulus
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("framework_interval", [1, 3, 7, 10])
def test_a_framework_that_reports_on_its_own_cadence_still_gets_a_full_curve(
    framework_interval: int,
) -> None:
    """The bug a modulus gate would have, and the reason this one counts elapsed steps.

    unsloth's on_log is gated by HuggingFace at `logging_steps` before it reaches
    us, so composing a second modulus yields their LCM rather than the finer of
    the two. At logging_steps=3 against a target interval of 100, `step % 100`
    admits only multiples of 300 -- a third of the points asked for -- and at 7,
    an eighth. The default of 1 divides everything, which is exactly why a
    modulus passes every test one would write by default and then mangles the
    curve for anyone who touches the knob.
    """
    reporter = _RecordingReporter()
    callback = _make_callback(reporter, max_points=200)
    callback.report_training_start(max_steps=20_000, num_epochs=1)
    for step in range(framework_interval, 20_001, framework_interval):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})

    # Never over budget, and never the LCM collapse: >= 190 of the 200 asked for.
    assert 190 <= len(_train_steps(reporter)) <= 200


def test_a_framework_coarser_than_the_target_gets_everything_it_has(reporter: _RecordingReporter) -> None:
    """The gate subsamples what it is handed; it cannot manufacture points.

    Degrading to "admit everything" is the honest failure for a framework whose
    own cadence is coarser than ours -- a modulus would instead drop most of the
    few points that exist.
    """
    callback = _make_callback(reporter, max_points=200)
    callback.report_training_start(max_steps=20_000, num_epochs=1)
    for step in range(500, 20_001, 500):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})

    assert len(_train_steps(reporter)) == 40, "only 40 points exist, and all 40 land"


# --------------------------------------------------------------------------- #
# Each path carries its own budget
# --------------------------------------------------------------------------- #


def test_the_two_paths_are_gated_independently(reporter: _RecordingReporter) -> None:
    """One budget across two cadences means whichever fires first starves the other."""
    callback = _make_callback(reporter, max_points=10)
    callback.report_training_start(max_steps=100, num_epochs=1)
    for step in range(1, 101):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})
        if step % 10 == 0:
            callback.report_validation(step=step, epoch=1, metrics={"loss": 0.4})

    assert len(_train_steps(reporter)) == 10
    assert _val_steps(reporter) == [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]


def test_capping_only_the_train_side_would_bound_nothing(reporter: _RecordingReporter) -> None:
    """`val_check_interval=1` is reachable, and it validates on every step.

    The train reports were held to 200 while validation reported all 20,000 --
    each one resending every accumulated series in full, which is what makes one
    uncapped path enough to leave the total quadratic.
    """
    callback = _make_callback(reporter, max_points=200)
    callback.report_training_start(max_steps=20_000, num_epochs=1)
    for step in range(1, 20_001):
        callback.report_validation(step=step, epoch=1, metrics={"loss": 0.4})

    assert len(_val_steps(reporter)) == 200


def test_every_report_at_one_validation_step_gets_the_same_decision(reporter: _RecordingReporter) -> None:
    """validate() logs once per dataloader, all at a single step.

    An ordinal counter -- which is what this replaces -- would admit dataset A
    and hold dataset B at one step, leaving the two curves disagreeing about
    which steps exist, and would burn the budget N times faster with N
    dataloaders.
    """
    callback = _make_callback(reporter, max_points=5)
    callback.report_training_start(max_steps=1_000, num_epochs=1)
    for step in (10, 20, 30, 210, 220):
        for dataset in ("", "heldout_"):
            callback.report_validation(step=step, epoch=1, metrics={f"{dataset}loss": 0.4})

    landed = _val_steps(reporter)
    for step in set(landed):
        assert landed.count(step) == 2, f"step {step} admitted one dataloader but not the other"


# --------------------------------------------------------------------------- #
# The decimation backstop
# --------------------------------------------------------------------------- #


def test_a_curve_never_outgrows_the_budget_even_on_a_wrong_run_length(
    reporter: _RecordingReporter,
) -> None:
    """The guarantee stops depending on an input we do not control.

    A run that overshoots the length it declared -- or a backend added later
    whose schedule nobody audited -- costs a resolution step-down rather than an
    unbounded series.
    """
    callback = _make_callback(reporter, max_points=20)
    callback.report_training_start(max_steps=100, num_epochs=1)  # off by 20x
    for step in range(1, 2_001):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})

    stored = reporter.reports[-1]["metrics"]["train_loss"]
    assert len(stored) <= 20
    assert len(stored) >= 10, "a step-down, not a collapse"


def test_decimation_keeps_the_leading_edge(reporter: _RecordingReporter) -> None:
    """A curve may lose resolution; it must never lose its most recent point."""
    callback = _make_callback(reporter, max_points=4)
    for step in range(1, 12):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": float(step)})

    stored = reporter.reports[-1]["metrics"]["train_loss"]
    assert stored[-1]["step"] == _train_steps(reporter)[-1]


def test_decimation_thins_every_curve_on_the_path(reporter: _RecordingReporter) -> None:
    """Not just the loss: the budget is per curve, and they all cost the same."""
    callback = _make_callback(reporter, max_points=4)
    for step in range(1, 12):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5, "lr": 1e-5})

    metrics = reporter.reports[-1]["metrics"]
    assert len(metrics["train_loss"]) <= 4
    assert len(metrics["train_lr"]) <= 4


# --------------------------------------------------------------------------- #
# Never lose the tail
# --------------------------------------------------------------------------- #


def test_close_flushes_the_withheld_final_step(reporter: _RecordingReporter) -> None:
    """The last step rarely lands on an interval, and it is the one worth having.

    Without a flush a run ends on whatever the cadence last happened to catch,
    so the final loss a reader sees is stale by up to a full interval.
    """
    callback = _make_callback(reporter, max_points=10)
    callback.report_training_start(max_steps=100, num_epochs=1)
    for step in range(1, 24):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})

    assert _train_steps(reporter) == [1, 11, 21]

    callback.close()

    assert _train_steps(reporter) == [1, 11, 21, 23]


def test_close_flushes_the_withheld_final_validation(reporter: _RecordingReporter) -> None:
    callback = _make_callback(reporter, max_points=2)
    callback.report_training_start(max_steps=100, num_epochs=1)
    for step in (10, 20, 30):
        callback.report_validation(step=step, epoch=1, metrics={"loss": 0.4})

    assert _val_steps(reporter) == [10]

    callback.close()

    assert _val_steps(reporter) == [10, 30]


def test_close_does_not_duplicate_an_already_reported_step(reporter: _RecordingReporter) -> None:
    """A report that landed retires whatever the gate was holding."""
    callback = _make_callback(reporter, max_points=10)
    callback.report_training_start(max_steps=100, num_epochs=1)
    for step in range(1, 22):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})

    assert _train_steps(reporter) == [1, 11, 21]

    callback.close()

    assert _train_steps(reporter) == [1, 11, 21]


def test_a_flushed_step_carries_its_full_payload(reporter: _RecordingReporter) -> None:
    """It is a real report, not a marker: the curves and the scalars both land."""
    callback = _make_callback(reporter, max_points=2)
    callback.report_training_start(max_steps=1_000, num_epochs=1)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.9})
    callback.report_train_step(step=2, epoch=1, metrics={"loss": 0.5, "lr": 1e-5})

    callback.close()

    flushed = reporter.reports[-1]
    assert flushed["step"] == 2
    assert flushed["train_loss"] == 0.5
    assert flushed["train_lr"] == 1e-5
    assert flushed["metrics"]["train_loss"][-1] == {"step": 2, "epoch": 1, "value": 0.5}


def test_pending_reports_flush_in_step_order(reporter: _RecordingReporter) -> None:
    """A consumer reads a report behind the last one as a rewind."""
    callback = _make_callback(reporter, max_points=2)
    callback.report_training_start(max_steps=1_000, num_epochs=1)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.5})
    callback.report_validation(step=2, epoch=1, metrics={"loss": 0.4})
    callback.report_train_step(step=18, epoch=1, metrics={"loss": 0.5})
    callback.report_validation(step=19, epoch=1, metrics={"loss": 0.4})

    callback.close()

    flushed = [(r["phase"], r["step"]) for r in reporter.reports[-2:]]
    assert flushed == [("training", 18), ("validation", 19)]


def test_a_double_close_flushes_once(reporter: _RecordingReporter) -> None:
    """Reachable from a driver finally, from finish() and from __del__."""
    callback = _make_callback(reporter, max_points=2)
    callback.report_training_start(max_steps=1_000, num_epochs=1)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.9})
    callback.report_train_step(step=2, epoch=1, metrics={"loss": 0.5})

    callback.close()
    callback.close()

    assert _train_steps(reporter) == [1, 2]


def test_close_with_nothing_withheld_reports_nothing(reporter: _RecordingReporter) -> None:
    _make_callback(reporter).close()

    assert reporter.reports == []


def test_the_flushed_tail_does_not_cost_the_curve_half_its_resolution() -> None:
    """Found by measuring a real run against a live platform, not by reading this.

    A run whose length divides evenly lands exactly `max_points` admissions and
    then flushes one more, and decimating on that last append halves the finished
    curve. A 600-step run at a budget of 200 reported 200 points and stored 101,
    at a spacing of 5 to 6 rather than 3 -- and the same holds at 20,000 steps,
    so it was the nominal path rather than an edge of it.
    """
    reporter = _RecordingReporter()
    callback = _make_callback(reporter, max_points=200)
    callback.report_training_start(max_steps=600, num_epochs=1)
    for step in range(1, 601):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})
    callback.close()

    stored = reporter.reports[-1]["metrics"]["train_loss"]
    assert len(stored) == 201, "the budget, plus the tail that is never dropped"
    assert stored[-1]["step"] == 600
    spacings = {stored[i + 1]["step"] - stored[i]["step"] for i in range(len(stored) - 2)}
    assert spacings == {3}, "and the cadence asked for, held to the end"


def test_a_resumed_process_is_not_misled_by_the_flushed_tail() -> None:
    """The last gap in a stored curve is systematically unrepresentative.

    Every run ends by flushing the step its gate withheld, which lands hard
    against its predecessor -- so a curve ending `..., 19901, 20000` was
    reporting every hundred steps and reads, off that final pair alone, as
    every one. A process taking the task over would then report all 20,000.
    """
    prior = {
        "train_loss": [{"step": s, "epoch": 1, "value": 0.5} for s in (1, 101, 201, 301, 400)],
    }
    reporter = _RecordingReporter(prior)
    callback = _make_callback(reporter, max_points=200)

    callback.report_train_step(step=450, epoch=1, metrics={"loss": 0.4})
    assert _train_steps(reporter) == [], "the 99-step gap is the cadence, not the 99th"

    callback.report_train_step(step=500, epoch=1, metrics={"loss": 0.4})
    assert _train_steps(reporter) == [500]


# --------------------------------------------------------------------------- #
# The gate's state is whatever the seeded series says it is
# --------------------------------------------------------------------------- #


def test_a_resumed_process_continues_the_cadence_it_inherited() -> None:
    """Otherwise it restarts at full resolution and blows the budget on the tail.

    The interval in force is recoverable from the spacing of the stored points,
    which is what lets a decimated curve survive a restart: the halved series
    records its doubled interval in its own steps.
    """
    prior = {"train_loss": [{"step": 100, "epoch": 1, "value": 0.9}, {"step": 200, "epoch": 1, "value": 0.8}]}
    reporter = _RecordingReporter(prior)
    callback = _make_callback(reporter, max_points=200)

    callback.report_train_step(step=250, epoch=1, metrics={"loss": 0.7})
    assert _train_steps(reporter) == [], "half an interval in, and held"

    callback.report_train_step(step=300, epoch=1, metrics={"loss": 0.6})
    assert _train_steps(reporter) == [300]


def test_the_seeded_cadence_is_never_relaxed_by_the_schedule() -> None:
    """A short declared run must not undo a coarser cadence already in force.

    Dropping back would re-admit at the finer rate for the remainder, which is
    exactly what decimation had already decided against.
    """
    prior = {"train_loss": [{"step": 100, "epoch": 1, "value": 0.9}, {"step": 200, "epoch": 1, "value": 0.8}]}
    reporter = _RecordingReporter(prior)
    callback = _make_callback(reporter, max_points=200)
    callback.report_training_start(max_steps=200, num_epochs=1)  # would seed interval 1

    callback.report_train_step(step=210, epoch=1, metrics={"loss": 0.7})

    assert _train_steps(reporter) == []


def test_the_anchor_is_the_series_that_has_been_there_from_the_start() -> None:
    """A metric that only starts appearing mid-run understates both position and cadence."""
    prior = {
        "train_loss": [{"step": s, "epoch": 1, "value": 0.5} for s in (100, 200, 300)],
        "train_reward": [{"step": 300, "epoch": 1, "value": 0.2}],
    }
    reporter = _RecordingReporter(prior)
    callback = _make_callback(reporter, max_points=200)

    callback.report_train_step(step=350, epoch=1, metrics={"loss": 0.4})
    assert _train_steps(reporter) == [], "interval 100 read off train_loss, not 0 off train_reward"


def test_a_from_scratch_restart_reports_from_its_first_step() -> None:
    """The elapsed check alone would withhold the whole first half of a restarted run.

    automodel and unsloth never resume from a checkpoint, so a replaced pod seeds
    itself from the previous attempt's points and starts again at step one.
    Reporting nothing until it caught up would be a far worse failure than the
    duplicated series the seeding note already documents.
    """
    prior = {"train_loss": [{"step": s, "epoch": 1, "value": 0.5} for s in (100, 200, 500)]}
    reporter = _RecordingReporter(prior)
    callback = _make_callback(reporter, max_points=200)
    callback.report_training_start(max_steps=20_000, num_epochs=1)

    callback.report_train_step(step=1, epoch=1, metrics={"loss": 2.0})

    assert _train_steps(reporter) == [1]


def test_a_restarted_run_is_gated_again_from_where_it_restarted(reporter: _RecordingReporter) -> None:
    """Admitting the backwards step must not disable the gate for the rest of the run."""
    prior = {"train_loss": [{"step": 500, "epoch": 1, "value": 0.5}]}
    reporter = _RecordingReporter(prior)
    callback = _make_callback(reporter, max_points=10)
    callback.report_training_start(max_steps=100, num_epochs=1)

    for step in range(1, 32):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})

    assert _train_steps(reporter) == [1, 11, 21, 31]


def test_a_failed_seed_read_does_not_disable_the_gate() -> None:
    """Those reports omit `metrics`, which makes them look free. They are not.

    Two of the three writes a report costs carry the whole stored blob whatever
    the payload says, so withholding the series saves a fraction of one leg out
    of three and none of the latency.
    """
    reporter = _UnreadableReporter()
    callback = _make_callback(reporter, max_points=10)
    callback.report_training_start(max_steps=100, num_epochs=1)
    for step in range(1, 101):
        callback.report_train_step(step=step, epoch=1, metrics={"loss": 0.5})

    assert len(_train_steps(reporter)) == 10


# --------------------------------------------------------------------------- #
# What a withheld report costs
# --------------------------------------------------------------------------- #


def test_a_withheld_report_is_not_sent_at_all(reporter: _RecordingReporter) -> None:
    """Not the curves, and not the current values either.

    Splitting the two -- scalars often, curves rarely -- does not help while the
    curves live in status_details: the two server-side writes carry the whole
    blob regardless of what the report said, so a scalar-only report costs
    almost exactly what a full one costs.
    """
    callback = _make_callback(reporter, max_points=2)
    callback.report_training_start(max_steps=1_000, num_epochs=1)
    callback.report_train_step(step=1, epoch=1, metrics={"loss": 0.9})
    callback.report_train_step(step=2, epoch=1, metrics={"loss": 0.5})

    assert _train_steps(reporter) == [1]


def test_the_reports_that_are_never_gated(reporter: _RecordingReporter) -> None:
    """Checkpoints and epoch ends are events, not samples of a curve.

    They also carry the only record of where a checkpoint landed, so a gate that
    dropped one would lose it rather than thin it.
    """
    callback = _make_callback(reporter, max_points=1)
    callback.report_training_start(max_steps=1_000, num_epochs=1)
    for step in (1, 2, 3):
        callback.report_checkpoint_saved(step=step, epoch=1, checkpoint_path=f"/ckpt/{step}")
        callback.report_epoch_end(step=step, epoch=1)

    assert len([r for r in reporter.reports if r["phase"] == "checkpoint_saved"]) == 3
    assert len([r for r in reporter.reports if r["phase"] == "epoch_end"]) == 3


@pytest.mark.parametrize("max_points", [0, -1])
def test_a_budget_below_one_is_rejected(reporter: _RecordingReporter, max_points: int) -> None:
    """A curve with no points on it reads downstream as a run that never reported."""
    with pytest.raises(ValueError, match="max_points"):
        _make_callback(reporter, max_points=max_points)
