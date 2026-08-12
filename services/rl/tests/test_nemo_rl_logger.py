# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for NemoRLLogger's translation of NeMo-RL metrics into Jobs Service reports.

The metric dicts here mirror what NeMo-RL actually hands the logger, including the
non-scalar entries (``Histogram``, ``Table``, nested dicts) that share the dict with
the numbers. Those are the reason ``has_metric_value`` type-checks rather than just
None-checks, so they are exercised rather than sanitised away.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import types
from typing import Any

import pytest

# NeMo-RL is only installed inside the training image, so the LoggerInterface import
# at nemo_rl_logger module scope fails in a plain repo checkout. Stub just enough to
# import the module under test; when the real package IS present (the in-image smoke
# run) this is skipped and the genuine base class is used.
if importlib.util.find_spec("nemo_rl") is None:  # pragma: no cover - env dependent
    _nemo_rl = types.ModuleType("nemo_rl")
    _utils = types.ModuleType("nemo_rl.utils")
    _logger_mod = types.ModuleType("nemo_rl.utils.logger")

    class LoggerInterface:  # minimal stand-in for the abstract base
        pass

    setattr(_logger_mod, "LoggerInterface", LoggerInterface)
    sys.modules.setdefault("nemo_rl", _nemo_rl)
    sys.modules.setdefault("nemo_rl.utils", _utils)
    sys.modules.setdefault("nemo_rl.utils.logger", _logger_mod)

from nmp.rl.tasks.training.backends.nemo_rl import nemo_rl_logger  # noqa: E402
from nmp.rl.tasks.training.backends.nemo_rl.nemo_rl_logger import (  # noqa: E402
    NemoRLLogger,
    has_metric_value,
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

    def report_train_step(self, step, epoch, loss, lr=None, grad_norm=None, **additional):
        self.train_steps.append(
            {"step": step, "epoch": epoch, "loss": loss, "lr": lr, "grad_norm": grad_norm, **additional}
        )

    def report_validation(self, step, epoch, val_loss=None, **additional):
        self.validations.append({"step": step, "epoch": epoch, "val_loss": val_loss, **additional})

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

    grpo.py and dpo.py both log `total_steps + 1` with total_steps 0-based and
    incremented after the log, so an N-step run emits 1..N -- not 0..N-1. Tests
    that use range(N) directly would validate the throttle against a convention
    no caller uses.
    """
    return range(1, max_steps + 1)


class _Histogram:
    """Stand-in for nemo_rl's wandb Histogram — non-numeric, and NaN-hostile."""


# Trimmed but faithful shape of GRPO's `train` dict: policy-loss metrics, the
# reward/advantage block, NeMo-Gym rollout metrics, and the non-scalars that ride
# along with them.
GRPO_TRAIN_METRICS: dict[str, Any] = {
    "loss": 0.31,
    "lr": 5e-6,
    "grad_norm": 1.7,
    "reward": 0.62,
    "total_reward/mean": 0.62,
    "total_reward/histogram": _Histogram(),
    "advantages/mean": 0.04,
    "advantages/min": -1.2,
    "advantages/max": 1.4,
    "kl_penalty": 0.008,
    "approx_entropy": 0.55,
    "token_mult_prob_error": 1.02,
    "truncation_rate": 0.125,
    "natural_termination_rate": 0.875,
    "turns_per_sample/mean": 2.5,
    "mean_gen_tokens_per_sample": 148.0,
    "num_valid_samples": 64,
    "global_valid_seqs": 64.0,
    "global_valid_toks": 9472.0,
    "generation_logger_metrics": {"inflight": [1, 2, 3]},
    "per_worker_token_counts": [{0: 100, 1: 120}],
    "ascii_tree_agent/full_result": object(),
}

# GRPO validation, verbatim in shape: no `loss` key anywhere.
GRPO_VALIDATION_METRICS: dict[str, Any] = {"accuracy": 0.75, "avg_length": 143.2}

DPO_TRAIN_METRICS: dict[str, Any] = {
    "loss": 0.5,
    "lr": 1e-5,
    "grad_norm": 0.9,
    "preference_loss": 0.42,
    "rewards_rejected_mean": -0.3,
    "num_valid_samples": 8,
    "global_valid_seqs": 8.0,
    "global_valid_toks": 1024.0,
}


# --------------------------------------------------------------------------- #
# has_metric_value
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value,expected",
    [
        (0.5, True),
        (0, True),
        (-1.5, True),
        (float("nan"), False),
        (None, False),
        # Non-scalars that genuinely appear in NeMo-RL metric dicts. Each of these
        # raises TypeError under a bare math.isnan, which is the regression guarded here.
        (_Histogram(), False),
        ({"inflight": [1, 2]}, False),
        ([1, 2, 3], False),
        ("0.5", False),
        # bool is an int subclass; charting a flag as 0/1 is not wanted.
        (True, False),
        (False, False),
    ],
)
def test_has_metric_value(value: Any, expected: bool) -> None:
    assert has_metric_value(value) is expected


def test_has_metric_value_does_not_raise_on_any_grpo_metric() -> None:
    """Every value in a real GRPO dict must be classifiable without raising."""
    for key, value in GRPO_TRAIN_METRICS.items():
        assert isinstance(has_metric_value(value), bool), key


def test_has_metric_value_accepts_numpy_scalars() -> None:
    np = pytest.importorskip("numpy")
    assert has_metric_value(np.float32(0.5)) is True
    assert has_metric_value(np.float64(0.5)) is True
    assert has_metric_value(np.int64(3)) is True
    assert has_metric_value(np.float32("nan")) is False


# --------------------------------------------------------------------------- #
# GRPO train metrics
# --------------------------------------------------------------------------- #


def test_grpo_train_step_forwards_reward_and_rollout_metrics(callback: _RecordingCallback) -> None:
    """The reward signal is the point of GRPO; it must reach Jobs Service."""
    _make_logger().log_metrics(GRPO_TRAIN_METRICS, step=0, prefix="train")

    assert len(callback.train_steps) == 1
    reported = callback.train_steps[0]
    assert reported["loss"] == 0.31
    assert reported["reward"] == 0.62
    assert reported["total_reward/mean"] == 0.62
    assert reported["advantages/mean"] == 0.04
    assert reported["kl_penalty"] == 0.008
    assert reported["approx_entropy"] == 0.55
    assert reported["truncation_rate"] == 0.125
    assert reported["turns_per_sample/mean"] == 2.5


def test_grpo_train_step_drops_non_scalar_metrics(callback: _RecordingCallback) -> None:
    """Histograms/Tables/nested dicts must not be forwarded, and must not raise."""
    _make_logger().log_metrics(GRPO_TRAIN_METRICS, step=0, prefix="train")

    reported = callback.train_steps[0]
    for key in (
        "total_reward/histogram",
        "generation_logger_metrics",
        "per_worker_token_counts",
        "ascii_tree_agent/full_result",
    ):
        assert key not in reported


def test_rollout_only_train_call_is_ignored(callback: _RecordingCallback) -> None:
    """GRPO logs `train` twice per step; the mid-step call has no loss and is a partial."""
    rollout_only = {k: v for k, v in GRPO_TRAIN_METRICS.items() if k != "loss"}
    _make_logger().log_metrics(rollout_only, step=0, prefix="train")

    assert callback.train_steps == []


def test_dpo_train_metrics_still_forwarded(callback: _RecordingCallback) -> None:
    """Widening the key list for GRPO must not drop DPO's existing metrics."""
    _make_logger().log_metrics(DPO_TRAIN_METRICS, step=0, prefix="train")

    reported = callback.train_steps[0]
    assert reported["loss"] == 0.5
    assert reported["preference_loss"] == 0.42
    assert reported["rewards_rejected_mean"] == -0.3
    assert reported["global_valid_toks"] == 1024.0


def test_log_interval_throttles_train_reports(callback: _RecordingCallback) -> None:
    logger = _make_logger(log_interval=5)
    for step in _driver_steps(10):
        logger.log_metrics(GRPO_TRAIN_METRICS, step=step, prefix="train")

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
        logger.log_metrics(GRPO_TRAIN_METRICS, step=step, prefix="train")

    assert [r["step"] for r in callback.train_steps] == [10, 20]

    logger.close()

    assert [r["step"] for r in callback.train_steps] == [10, 20, 23]


def test_close_does_not_duplicate_an_already_reported_step(callback: _RecordingCallback) -> None:
    logger = _make_logger(log_interval=10)
    for step in _driver_steps(20):
        logger.log_metrics(GRPO_TRAIN_METRICS, step=step, prefix="train")

    logger.close()

    assert [r["step"] for r in callback.train_steps] == [10, 20]


def test_flushed_step_carries_the_full_metric_payload(callback: _RecordingCallback) -> None:
    logger = _make_logger(log_interval=10)
    logger.log_metrics(GRPO_TRAIN_METRICS, step=1, prefix="train")
    logger.close()

    flushed = callback.train_steps[-1]
    assert flushed["step"] == 1
    assert flushed["reward"] == 0.62
    assert flushed["loss"] == 0.31


def test_double_close_flushes_once(callback: _RecordingCallback) -> None:
    logger = _make_logger(log_interval=10)
    logger.log_metrics(GRPO_TRAIN_METRICS, step=1, prefix="train")

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
    logger.log_metrics(GRPO_TRAIN_METRICS, step=1, prefix="train")

    logger.finish()

    assert [r["step"] for r in callback.train_steps] == [1]
    assert callback.closed


def test_finish_is_reachable_through_the_composite_dispatch(callback: _RecordingCallback) -> None:
    """Mirrors Logger.finish()'s exact lookup, so a rename here fails loudly."""
    logger = _make_logger(log_interval=10)
    logger.log_metrics(GRPO_TRAIN_METRICS, step=1, prefix="train")

    finish = getattr(logger, "finish", None)
    assert callable(finish)
    finish()

    assert [r["step"] for r in callback.train_steps] == [1]


def test_finish_then_close_flushes_once(callback: _RecordingCallback) -> None:
    """Both the composite and the driver may call in; the step reports once."""
    logger = _make_logger(log_interval=10)
    logger.log_metrics(GRPO_TRAIN_METRICS, step=1, prefix="train")

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
    "val_period,expected",
    [
        (100, 10),
        (10, 1),
        (5, 1),  # floors to 0 -> clamped
        (1, 1),
        (0, 1),
        (None, 1),  # GRPO's val_period is Optional
    ],
)
def test_resolve_log_interval(val_period: int | None, expected: int) -> None:
    assert resolve_log_interval(val_period) == expected


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
    """Both drivers now share this path; DPO used to derive a different interval."""
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
        logger.log_metrics(GRPO_TRAIN_METRICS, step=step, prefix="train")

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
    _make_logger().log_metrics(GRPO_VALIDATION_METRICS, step=0, prefix="validation")

    reported = callback.validations[0]
    assert reported["step"] == 0
    assert reported["epoch"] == 1


# --------------------------------------------------------------------------- #
# Validation — the branch GRPO never reached
# --------------------------------------------------------------------------- #


def test_grpo_validation_is_reported_without_a_loss(callback: _RecordingCallback) -> None:
    """GRPO validates on accuracy/avg_length and reports no loss.

    Gating this branch on `loss` silently dropped every GRPO validation report.
    """
    _make_logger().log_metrics(GRPO_VALIDATION_METRICS, step=10, prefix="validation")

    assert len(callback.validations) == 1
    reported = callback.validations[0]
    assert reported["val_loss"] is None
    assert reported["accuracy"] == 0.75
    assert reported["avg_length"] == 143.2
    assert reported["step"] == 10
    assert reported["epoch"] == 1


def test_dpo_validation_still_reports_loss(callback: _RecordingCallback) -> None:
    _make_logger().log_metrics({"loss": 0.25, "num_valid_samples": 8}, step=10, prefix="validation")

    reported = callback.validations[0]
    assert reported["val_loss"] == 0.25
    assert reported["num_valid_samples"] == 8


def test_validation_with_nothing_usable_is_not_reported(callback: _RecordingCallback) -> None:
    """An empty or all-non-scalar dict must not produce a hollow report."""
    _make_logger().log_metrics({}, step=9, prefix="validation")
    _make_logger().log_metrics({"histogram/x": _Histogram()}, step=9, prefix="validation")

    assert callback.validations == []


def test_best_validation_loss_tracks_minimum(callback: _RecordingCallback) -> None:
    logger = _make_logger()
    logger.log_metrics({"loss": 0.5}, step=10, prefix="validation")
    logger.log_metrics({"loss": 0.2}, step=20, prefix="validation")
    logger.log_metrics({"loss": 0.7}, step=30, prefix="validation")

    assert logger._best_metric_value == 0.2
    assert logger._best_epoch == 2


def test_grpo_validation_leaves_best_loss_untouched(callback: _RecordingCallback) -> None:
    """No loss means no best-loss update — and no crash comparing None."""
    logger = _make_logger()
    logger.log_metrics(GRPO_VALIDATION_METRICS, step=10, prefix="validation")

    assert math.isinf(logger._best_metric_value)
    assert logger._best_epoch is None


@pytest.mark.parametrize("prefix", ["validation", "validation-0", "validation/nemo_gym"])
def test_all_validation_prefixes_are_handled(callback: _RecordingCallback, prefix: str) -> None:
    """NeMo-RL suffixes the prefix per dataloader; all must route to validation."""
    _make_logger().log_metrics(GRPO_VALIDATION_METRICS, step=9, prefix=prefix)

    assert len(callback.validations) == 1


# --------------------------------------------------------------------------- #
# Prefixes we intentionally ignore
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("prefix", ["timing/train", "timing/validation", "timing/setup", "performance", "refit", ""])
def test_unhandled_prefixes_produce_no_reports(callback: _RecordingCallback, prefix: str) -> None:
    _make_logger().log_metrics({"loss": 0.1, "total_step_time": 12.0}, step=0, prefix=prefix)

    assert callback.train_steps == []
    assert callback.validations == []
