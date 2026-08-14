# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for NemoRLLogger's translation of NeMo-RL metrics into Jobs Service reports.

The metric dicts here mirror what NeMo-RL actually hands the logger, including the
non-scalar entries (``Histogram`` objects, tables, nested dicts) that share the dict
with the numbers, so they are exercised rather than sanitised away.

The logger forwards the dict whole and decides only *whether* and *when* to report:
which entries survive is the shared callback's business, covered by its own suite.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import types
from typing import Any

import pytest

# NeMo-RL is only installed inside the training image, so the LoggerInterface import
# at nemo_rl_logger module scope fails in a plain repo checkout. Stub just enough to
# import the module under test; when the real package IS present (the in-image smoke
# run) this is skipped and the genuine base class is used.
if importlib.util.find_spec("nemo_rl") is None:  # pragma: no cover - env dependent

    class LoggerInterface:  # minimal stand-in for the abstract base
        pass

    def _stub(name: str) -> types.ModuleType:
        """Build a stub module that survives a later importlib.util.find_spec.

        A bare ModuleType has ``__spec__ = None``, and find_spec consults
        sys.modules first -- so leaving it unset makes a later
        ``find_spec("nemo_rl")`` raise ValueError rather than return None. The
        stub outlives this module (nothing tears it down), so it must not booby
        trap whatever runs next in the session.
        """
        module = types.ModuleType(name)
        module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
        return module

    _logger_mod = _stub("nemo_rl.utils.logger")
    setattr(_logger_mod, "LoggerInterface", LoggerInterface)
    sys.modules.setdefault("nemo_rl", _stub("nemo_rl"))
    sys.modules.setdefault("nemo_rl.utils", _stub("nemo_rl.utils"))
    sys.modules.setdefault("nemo_rl.utils.logger", _logger_mod)

from nmp.rl.tasks.training.backends.nemo_rl import nemo_rl_logger  # noqa: E402
from nmp.rl.tasks.training.backends.nemo_rl.nemo_rl_logger import (  # noqa: E402
    _MAX_REPORTS_PER_RUN,
    NemoRLLogger,
    resolve_log_interval,
    resolve_steps_per_epoch,
)


class _RecordingCallback:
    """Stands in for TrainingProgressCallback, capturing what the logger forwards."""

    def __init__(self) -> None:
        self.train_steps: list[dict[str, Any]] = []
        self.validations: list[dict[str, Any]] = []
        self.training_starts: list[dict[str, Any]] = []
        self.closed = False

    def report_training_start(self, max_steps: int, num_epochs: int) -> None:
        self.training_starts.append({"max_steps": max_steps, "num_epochs": num_epochs})

    def report_train_step(self, step, epoch, metrics, *, backend=None):
        self.train_steps.append({"step": step, "epoch": epoch, "metrics": metrics})

    def report_validation(self, step, epoch, metrics, *, backend=None):
        self.validations.append({"step": step, "epoch": epoch, "metrics": metrics})

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def callback(monkeypatch: pytest.MonkeyPatch) -> _RecordingCallback:
    """Build a NemoRLLogger whose reporter/callback are inert local objects."""
    recorder = _RecordingCallback()
    monkeypatch.setattr(nemo_rl_logger, "JobsServiceProgressReporter", lambda *a, **k: object())
    monkeypatch.setattr(nemo_rl_logger, "TrainingProgressCallback", lambda _reporter: recorder)
    return recorder


def _make_logger(**kwargs: Any) -> NemoRLLogger:
    params: dict[str, Any] = {"steps_per_epoch": 10, "log_interval": 1}
    params.update(kwargs)
    return NemoRLLogger(**params)


def _driver_steps(max_steps: int) -> range:
    """The step sequence an N-step run actually produces.

    dpo.py logs `total_steps + 1` with total_steps 0-based and incremented after
    the log, so an N-step run emits 1..N -- not 0..N-1. Tests that use range(N)
    directly would validate the throttle against a convention no caller uses.
    """
    return range(1, max_steps + 1)


class _Histogram:
    """Stand-in for a non-numeric metric value — NaN-hostile, like the real thing."""


# A DPO `train` dict: the scalars, plus the non-scalars that ride along with them
# in a real NeMo-RL metric dict.
TRAIN_METRICS: dict[str, Any] = {
    "loss": 0.5,
    "lr": 1e-5,
    "grad_norm": 0.9,
    "preference_loss": 0.42,
    "rewards_rejected_mean": -0.3,
    "num_valid_samples": 8,
    "global_valid_seqs": 8.0,
    "global_valid_toks": 1024.0,
    "some/histogram": _Histogram(),
    "generation_logger_metrics": {"inflight": [1, 2, 3]},
    "per_worker_token_counts": [{0: 100, 1: 120}],
}

VALIDATION_METRICS: dict[str, Any] = {"loss": 0.25, "num_valid_samples": 8}

# GRPO/PPO log this under `prefix="train"` at the same step as TRAIN_METRICS,
# from the rollout rather than the training step. Generation stats only: no loss.
ROLLOUT_METRICS: dict[str, Any] = {
    "total_turns": 64,
    "avg_turns_per_sample": 1.0,
    "mean_gen_tokens_per_sample": 412.5,
    "truncation_rate": 0.02,
}

# What GRPO's validate() returns. It scores on rewards, so there is no loss in it.
REWARD_VALIDATION_METRICS: dict[str, Any] = {"accuracy": 0.61, "avg_length": 412.5}


# --------------------------------------------------------------------------- #
# Module stub hygiene
# --------------------------------------------------------------------------- #


def test_module_stub_does_not_break_find_spec() -> None:
    """The stub installed at import time outlives this module; it must be inert.

    find_spec consults sys.modules first and raises on a `__spec__` of None, so a
    bare ModuleType here would turn an unrelated later `find_spec("nemo_rl")`
    into a ValueError -- the same kind of cross-suite leak this file's sibling
    test_dpo_config had to be rewritten around.
    """
    assert importlib.util.find_spec("nemo_rl") is not None


# --------------------------------------------------------------------------- #
# Train metrics
# --------------------------------------------------------------------------- #


def test_the_metric_dict_is_forwarded_whole(callback: _RecordingCallback) -> None:
    """No allow-list: a metric NeMo-RL adds charts without a change here.

    The old list silently dropped anything never added to it -- DPO's `accuracy`,
    `sft_loss` and `rewards_chosen_mean` among them. Deciding which entries are
    chartable is the callback's job, not a second gate doing a weaker version of
    the same check.
    """
    _make_logger().log_metrics(TRAIN_METRICS, step=0, prefix="train")

    assert callback.train_steps[0]["metrics"] == TRAIN_METRICS


def test_the_forwarded_dict_is_a_copy(callback: _RecordingCallback) -> None:
    """NeMo-RL reuses its metric dict across steps; a reference would alias it."""
    metrics = dict(TRAIN_METRICS)
    _make_logger().log_metrics(metrics, step=0, prefix="train")
    metrics["loss"] = 99.0

    assert callback.train_steps[0]["metrics"]["loss"] == 0.5


def test_train_call_without_a_loss_is_ignored(callback: _RecordingCallback) -> None:
    """A `train` log without a loss is a partial, mid-step call rather than a step."""
    rollout_only = {k: v for k, v in TRAIN_METRICS.items() if k != "loss"}
    _make_logger().log_metrics(rollout_only, step=0, prefix="train")

    assert callback.train_steps == []


def test_the_rollout_log_does_not_produce_a_second_train_report(callback: _RecordingCallback) -> None:
    """GRPO and PPO log twice under `prefix="train"` at one step.

    grpo.py logs `rollout_metrics` and then the training `metrics`, both at
    `total_steps + 1`. Only the second has a loss, which is why the branch keys
    on one: without it the step reports twice -- each resending every series --
    and a throttled step ends up pending as the rollout half, losing the loss.
    """
    logger = _make_logger()
    logger.log_metrics(ROLLOUT_METRICS, step=1, prefix="train")
    logger.log_metrics(TRAIN_METRICS, step=1, prefix="train")

    assert len(callback.train_steps) == 1
    assert callback.train_steps[0]["metrics"]["loss"] == 0.5


def test_every_train_scalar_is_forwarded(callback: _RecordingCallback) -> None:
    """Including the ones the old allow-list had no entry for."""
    _make_logger().log_metrics(TRAIN_METRICS, step=0, prefix="train")

    reported = callback.train_steps[0]["metrics"]
    assert reported["loss"] == 0.5
    assert reported["preference_loss"] == 0.42
    assert reported["rewards_rejected_mean"] == -0.3
    assert reported["global_valid_toks"] == 1024.0


def test_log_interval_throttles_train_reports(callback: _RecordingCallback) -> None:
    logger = _make_logger(log_interval=5)
    for step in _driver_steps(10):
        logger.log_metrics(TRAIN_METRICS, step=step, prefix="train")

    assert [r["step"] for r in callback.train_steps] == [5, 10]


# --------------------------------------------------------------------------- #
# Final-step flush
# --------------------------------------------------------------------------- #


def test_close_flushes_the_withheld_final_step(callback: _RecordingCallback) -> None:
    """When max_steps is not a multiple of log_interval the last step is throttled out.

    Without a flush the run's last recorded loss is stale — for 23 steps at an
    interval of 10 it would be step 20's, and steps 21-23 would never be seen.
    """
    logger = _make_logger(log_interval=10)
    for step in _driver_steps(23):
        logger.log_metrics(TRAIN_METRICS, step=step, prefix="train")

    assert [r["step"] for r in callback.train_steps] == [10, 20]

    logger.close()

    assert [r["step"] for r in callback.train_steps] == [10, 20, 23]


def test_close_does_not_duplicate_an_already_reported_step(callback: _RecordingCallback) -> None:
    logger = _make_logger(log_interval=10)
    for step in _driver_steps(20):
        logger.log_metrics(TRAIN_METRICS, step=step, prefix="train")

    logger.close()

    assert [r["step"] for r in callback.train_steps] == [10, 20]


def test_flushed_step_carries_the_full_metric_payload(callback: _RecordingCallback) -> None:
    logger = _make_logger(log_interval=10)
    logger.log_metrics(TRAIN_METRICS, step=1, prefix="train")
    logger.close()

    flushed = callback.train_steps[-1]
    assert flushed["step"] == 1
    assert flushed["metrics"]["loss"] == 0.5
    assert flushed["metrics"]["preference_loss"] == 0.42


def test_double_close_flushes_once(callback: _RecordingCallback) -> None:
    logger = _make_logger(log_interval=10)
    logger.log_metrics(TRAIN_METRICS, step=1, prefix="train")

    logger.close()
    logger.close()

    assert len(callback.train_steps) == 1


def test_finish_flushes_like_close(callback: _RecordingCallback) -> None:
    """`finish` is the name NeMo-RL's composite Logger actually dispatches.

    nemo_rl.utils.logger.Logger has no close(); its teardown fan-out is
    `getattr(logger, "finish", None)`. Without this alias the composite skips us
    entirely and the withheld final step is never flushed.
    """
    logger = _make_logger(log_interval=10)
    logger.log_metrics(TRAIN_METRICS, step=1, prefix="train")

    logger.finish()

    assert [r["step"] for r in callback.train_steps] == [1]
    assert callback.closed


def test_finish_is_reachable_through_the_composite_dispatch(callback: _RecordingCallback) -> None:
    """Mirrors Logger.finish()'s exact lookup, so a rename here fails loudly."""
    logger = _make_logger(log_interval=10)
    logger.log_metrics(TRAIN_METRICS, step=1, prefix="train")

    finish = getattr(logger, "finish", None)
    assert callable(finish)
    finish()

    assert [r["step"] for r in callback.train_steps] == [1]


def test_finish_then_close_flushes_once(callback: _RecordingCallback) -> None:
    """Both the composite and the driver may call in; the step reports once."""
    logger = _make_logger(log_interval=10)
    logger.log_metrics(TRAIN_METRICS, step=1, prefix="train")

    logger.finish()
    logger.close()

    assert len(callback.train_steps) == 1


def test_close_with_nothing_pending_reports_nothing(callback: _RecordingCallback) -> None:
    _make_logger().close()

    assert callback.train_steps == []


# --------------------------------------------------------------------------- #
# Schedule resolution — one formula for both drivers
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "val_period,max_steps,expected",
    [
        # Driven by val_period: ~10 reports across one validation period.
        (100, 200, 10),
        (10, 200, 1),
        (5, 200, 1),  # floors to 0 -> clamped
        (1, 200, 1),
        (0, 200, 1),
        (None, 200, 1),  # val_period is Optional
        # Driven by the run-length cap, once val_period has stopped bounding
        # anything. This is the regime a small val_check_interval lands in.
        (5, 2_000, 10),
        (5, 20_000, 100),
        (None, 20_000, 100),
        # Whichever floor is coarser wins; here it is val_period's.
        (10_000, 20_000, 1_000),
        # A run shorter than the cap is never throttled past its own length.
        (0, 1, 1),
    ],
)
def test_resolve_log_interval(val_period: int | None, max_steps: int, expected: int) -> None:
    assert resolve_log_interval(val_period, max_steps) == expected


def test_the_run_length_cap_bounds_the_report_count(callback: _RecordingCallback) -> None:
    """val_period alone does not bound reporting, and the report is what costs.

    `val_check_interval=5` is an ordinary request, and it floors the
    reports-per-validation-period term to zero -- so before the cap this run
    reported all 20,000 steps. Each report resends every series in full, so that
    is quadratic in upload and in stored-blob writes, not linear.
    """
    max_steps = 20_000
    logger = NemoRLLogger.for_schedule(max_steps=max_steps, num_epochs=1, val_period=5)
    for step in _driver_steps(max_steps):
        logger.log_metrics(TRAIN_METRICS, step=step, prefix="train")

    assert len(callback.train_steps) <= _MAX_REPORTS_PER_RUN
    assert len(callback.train_steps) >= _MAX_REPORTS_PER_RUN // 2, "still a usable curve, not a throttle to nothing"


@pytest.mark.parametrize(
    "max_steps,num_epochs,explicit,expected",
    [
        (100, 4, None, 25),
        (100, None, None, 100),
        (100, 0, None, 100),  # guard against a zero divisor
        (3, 10, None, 1),  # floors to 0 -> clamped
        (100, 4, 40, 40),  # explicit wins (DPO carries steps_per_epoch)
        (100, 4, 0, 25),  # ...unless it is unusable
    ],
)
def test_resolve_steps_per_epoch(max_steps: int, num_epochs: int | None, explicit: int | None, expected: int) -> None:
    assert resolve_steps_per_epoch(max_steps, num_epochs, explicit) == expected


def test_for_schedule_builds_a_consistent_logger(callback: _RecordingCallback) -> None:
    """DPO's own formula produced 11 here, via a `+1` that skewed every value."""
    logger = NemoRLLogger.for_schedule(max_steps=100, num_epochs=4, val_period=100)

    assert logger._log_interval == 10
    assert logger._steps_per_epoch == 25
    assert logger._max_steps == 100


# --------------------------------------------------------------------------- #
# Step and epoch arithmetic
# --------------------------------------------------------------------------- #


def test_step_is_reported_as_the_caller_numbered_it(callback: _RecordingCallback) -> None:
    """The caller's step is already 1-indexed; re-incrementing shifted the curve."""
    logger = _make_logger(max_steps=23)
    for step in _driver_steps(23):
        logger.log_metrics(TRAIN_METRICS, step=step, prefix="train")

    reported = [r["step"] for r in callback.train_steps]
    assert reported[0] == 1, "an N-step run starts at 1"
    assert reported[-1] == 23, "...and ends at N, not N+1"


@pytest.mark.parametrize(
    "step,expected_epoch",
    [
        (0, 1),  # validate-at-start, before any training
        (1, 1),
        (10, 1),  # last step of epoch 1 at steps_per_epoch=10
        (11, 2),  # first of epoch 2
        (20, 2),
        (21, 3),
    ],
)
def test_epoch_boundaries(callback: _RecordingCallback, step: int, expected_epoch: int) -> None:
    """Epoch flips on the step after a full epoch, not the last step of one."""
    _make_logger().log_metrics({"loss": 0.5}, step=step, prefix="train")

    assert callback.train_steps[0]["epoch"] == expected_epoch


def test_validate_at_start_reports_step_zero(callback: _RecordingCallback) -> None:
    """Both algorithms run an optional validation pass at step 0 before training."""
    _make_logger().log_metrics({"loss": 0.5}, step=0, prefix="validation")

    reported = callback.validations[0]
    assert reported["step"] == 0
    assert reported["epoch"] == 1


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def test_validation_forwards_the_dict_whole(callback: _RecordingCallback) -> None:
    """`loss` is forwarded under its own name; the phase prefix makes it val_loss."""
    _make_logger().log_metrics(VALIDATION_METRICS, step=10, prefix="validation")

    reported = callback.validations[0]["metrics"]
    assert reported["loss"] == 0.25
    assert reported["num_valid_samples"] == 8


def test_validation_with_nothing_usable_is_not_reported(callback: _RecordingCallback) -> None:
    """An empty or all-non-scalar dict must not produce a hollow report."""
    _make_logger().log_metrics({}, step=9, prefix="validation")
    _make_logger().log_metrics({"histogram/x": _Histogram()}, step=9, prefix="validation")

    assert callback.validations == []


def test_a_validation_pass_without_a_loss_is_still_reported(callback: _RecordingCallback) -> None:
    """No metric is privileged, so a loss is not what makes a pass worth recording.

    GRPO scores validation on rewards: its validate() returns `accuracy` and
    `avg_length` and no loss at all. Gating on one dropped every validation pass
    it ran -- not the loss curve, the whole pass.
    """
    _make_logger().log_metrics(REWARD_VALIDATION_METRICS, step=10, prefix="validation")

    assert callback.validations[0]["metrics"] == REWARD_VALIDATION_METRICS


def test_a_loss_free_validation_leaves_the_best_metric_alone(callback: _RecordingCallback) -> None:
    """Best-so-far tracks the validation loss, so a pass without one says nothing."""
    logger = _make_logger()
    logger.log_metrics({"loss": 0.4}, step=10, prefix="validation")
    logger.log_metrics(REWARD_VALIDATION_METRICS, step=20, prefix="validation")

    assert len(callback.validations) == 2
    assert logger._best_metric_value == 0.4
    assert logger._best_epoch == 1


def test_best_validation_loss_tracks_minimum(callback: _RecordingCallback) -> None:
    logger = _make_logger()
    logger.log_metrics({"loss": 0.5}, step=10, prefix="validation")
    logger.log_metrics({"loss": 0.2}, step=20, prefix="validation")
    logger.log_metrics({"loss": 0.7}, step=30, prefix="validation")

    assert logger._best_metric_value == 0.2
    assert logger._best_epoch == 2


@pytest.mark.parametrize("prefix", ["validation", "validation-0", "validation/nemo_gym"])
def test_all_validation_prefixes_are_handled(callback: _RecordingCallback, prefix: str) -> None:
    """NeMo-RL suffixes the prefix per dataloader; all must route to validation."""
    _make_logger().log_metrics(VALIDATION_METRICS, step=9, prefix=prefix)

    assert len(callback.validations) == 1


# --------------------------------------------------------------------------- #
# Prefixes we intentionally ignore
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("prefix", ["timing/train", "timing/validation", "timing/setup", "performance", "refit", ""])
def test_unhandled_prefixes_produce_no_reports(callback: _RecordingCallback, prefix: str) -> None:
    _make_logger().log_metrics({"loss": 0.1, "total_step_time": 12.0}, step=0, prefix=prefix)

    assert callback.train_steps == []
    assert callback.validations == []
