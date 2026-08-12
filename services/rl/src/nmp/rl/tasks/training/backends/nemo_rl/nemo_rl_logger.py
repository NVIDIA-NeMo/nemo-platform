# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import logging
import math
import numbers
from typing import Any, Mapping, Optional

from nemo_rl.utils.logger import LoggerInterface
from nmp.customization_common.service.context import NMPJobContext
from nmp.rl.tasks.training.backends.nemo_rl.callbacks import TrainingProgressCallback
from nmp.rl.tasks.training.progress import JobsServiceProgressReporter

_logger = logging.getLogger(__name__)

# How many progress reports to aim for across one validation period. NeMo-RL has no
# notion of a reporting cadence, so it is derived from val_period.
_REPORTS_PER_VAL_PERIOD = 10

# Metric keys forwarded to Jobs Service, in addition to loss/lr/grad_norm.
#
# A union across algorithms: selection is by presence, so a DPO run simply has no
# GRPO keys and vice versa. GRPO's `train` dict is the merge of the policy-loss
# metrics, the reward/advantage block and NeMo-Gym's rollout metrics
# (nemo_rl/algorithms/grpo.py builds it, nemo_rl/experience/rollouts.py supplies
# the rollout half), so all three families are represented here.
_TRAIN_METRIC_KEYS = (
    # Shared
    "num_valid_samples",
    "global_valid_seqs",
    "global_valid_toks",
    # DPO
    "preference_loss",
    "rewards_rejected_mean",
    # GRPO: reward and advantages — the signal that says whether RL is working
    "reward",
    "total_reward/mean",
    "advantages/mean",
    "advantages/min",
    "advantages/max",
    # GRPO: policy-optimization health
    "kl_penalty",
    "approx_entropy",
    "token_mult_prob_error",
    # GRPO: rollout shape
    "truncation_rate",
    "natural_termination_rate",
    "turns_per_sample/mean",
    "mean_gen_tokens_per_sample",
)

# GRPO reports `accuracy`/`avg_length` here and no loss at all; DPO reports loss.
_VALIDATION_METRIC_KEYS = _TRAIN_METRIC_KEYS + ("accuracy", "avg_length")


def has_metric_value(metric: Any) -> bool:
    """Whether ``metric`` is a finite-enough scalar to forward to Jobs Service.

    The type check is load-bearing, not defensive. NeMo-RL's metric dicts carry
    non-scalars alongside the numbers: ``calculate_single_metric`` emits a
    ``<key>/histogram`` holding a ``Histogram`` object, NeMo-Gym adds a
    per-agent ``full_result`` ``Table``, and ``generation_logger_metrics`` is a
    nested dict. ``math.isnan`` raises ``TypeError`` on all of those, so a bare
    None-check would turn a widened key list into a crash mid-training.

    ``bool`` is rejected despite being an ``int`` subclass: no metric here is a
    flag, and silently charting one as 0/1 is worse than dropping it.
    """
    if isinstance(metric, bool) or not isinstance(metric, numbers.Real):
        return False
    return not math.isnan(float(metric))


def resolve_log_interval(val_period: int | None) -> int:
    """Steps between progress reports, targeting ~10 reports per validation period."""
    return max((val_period or 0) // _REPORTS_PER_VAL_PERIOD, 1)


def resolve_steps_per_epoch(max_steps: int, num_epochs: int | None, explicit: int | None = None) -> int:
    """Steps per epoch, preferring an explicit value from the algorithm config."""
    if explicit is not None and explicit >= 1:
        return explicit
    return max(max_steps // max(num_epochs or 1, 1), 1)


class NemoRLLogger(LoggerInterface):
    """
    NemoRLLogger is a logger implementation that reports training updates to Jobs Service.

    It implements the LoggerInterface from nemo_rl.utils.logger to provide a consistent
    logging interface while maintaining compatibility with the Jobs Service.

    This implementation uses TrainingProgressCallback with JobsServiceProgressReporter
    to report progress via the NeMo Platform SDK.
    """

    def __init__(
        self,
        steps_per_epoch: int,
        job_ctx: NMPJobContext | None = None,
        log_interval: int = 10,
        max_steps: int | None = None,
        num_epochs: int | None = None,
    ):
        """Initialize the NemoRL logger.

        Args:
            steps_per_epoch: Number of steps per epoch (required for accurate epoch calculation).
            job_ctx: NeMo Platform job context for progress reporting (defaults to environment variables).
            log_interval: Number of steps between progress updates.
            max_steps: Total number of training steps (optional, used for progress reporting).
            num_epochs: Total number of epochs (optional, used for progress reporting).

        Raises:
            ValueError: If ``steps_per_epoch`` or ``log_interval`` is < 1. Both are
                used as divisors/moduli in ``log_metrics`` (epoch derivation and
                log-interval throttling), so non-positive values are rejected up
                front to fail fast instead of raising ZeroDivisionError mid-training.
        """
        if steps_per_epoch < 1:
            raise ValueError(f"steps_per_epoch must be >= 1, got {steps_per_epoch}")
        if log_interval < 1:
            raise ValueError(f"log_interval must be >= 1, got {log_interval}")

        self._job_ctx = job_ctx or NMPJobContext.from_env()
        self._log_interval = log_interval
        self._max_steps = max_steps
        self._num_epochs = num_epochs
        self._steps_per_epoch = steps_per_epoch

        # Create the callback for progress reporting
        self._reporter = JobsServiceProgressReporter(self._job_ctx)
        self._callback = TrainingProgressCallback(self._reporter)

        # Track best metrics for monitoring
        self._best_metric_value = float("inf")
        self._best_epoch: int | None = None
        self._closed = False

        # Last train step built but withheld by the log_interval throttle. Flushed on
        # close() so the final step is reported even when max_steps is not a multiple
        # of log_interval -- otherwise the run's last recorded loss is stale.
        self._pending_train_report: dict[str, Any] | None = None

        _logger.info(
            f"Initialized NemoRLLogger with jobs_url={self._job_ctx.jobs_url}, "
            f"log_interval={log_interval}, max_steps={max_steps}, num_epochs={num_epochs}, "
            f"steps_per_epoch={steps_per_epoch}"
        )

    @classmethod
    def for_schedule(
        cls,
        *,
        max_steps: int,
        num_epochs: int | None,
        val_period: int | None,
        steps_per_epoch: int | None = None,
        job_ctx: NMPJobContext | None = None,
    ) -> "NemoRLLogger":
        """Build a logger from a NeMo-RL training schedule.

        The DPO and GRPO drivers previously derived ``log_interval`` and
        ``steps_per_epoch`` with different formulas for the same intent -- at
        ``val_period=100`` one produced 11 and the other 10 -- so the arithmetic
        lives here instead of being restated per algorithm.

        Args:
            steps_per_epoch: Authoritative value when the algorithm config carries
                one (DPO does); otherwise derived from max_steps and num_epochs.
        """
        return cls(
            steps_per_epoch=resolve_steps_per_epoch(max_steps, num_epochs, steps_per_epoch),
            job_ctx=job_ctx,
            log_interval=resolve_log_interval(val_period),
            max_steps=max_steps,
            num_epochs=num_epochs,
        )

    def log_metrics(
        self,
        metrics: dict[str, Any],
        step: int,
        prefix: Optional[str] = "",
        step_metric: Optional[str] = None,
        step_finished: bool = False,
    ) -> None:
        """Log metrics to NeMo Customizer.

        Args:
            metrics: Dict of metrics to log
            step: Global step value
            prefix: Optional prefix for metric names (e.g. "train", "validation", "timing/train")
            step_metric: Optional step metric name (ignored in this implementation)
            step_finished: Whether the step is finished (part of NeMo-RL's LoggerInterface; ignored here)
        """
        # `step` arrives 1-indexed and is used as-is. Both callers pass
        # `total_steps + 1`, where total_steps is 0-based and incremented *after*
        # logging (nemo_rl/algorithms/grpo.py, .../dpo.py), so it is already the
        # 1-indexed step number. Incrementing again put the last step of an
        # N-step run at N+1 and shifted the whole series one to the right of the
        # axis Studio draws it against.
        #
        # Step 0 does arrive, from the validate-at-start path only; it belongs to
        # epoch 1, hence the clamp rather than a bare `step - 1`.
        epoch = (max(step - 1, 0) // self._steps_per_epoch) + 1

        # Handle training loss.
        #
        # The loss gate also de-duplicates: GRPO logs under `train` twice per step —
        # once mid-step with the rollout metrics alone (no loss), then again with the
        # full merged dict. Requiring loss keeps the second, complete one.
        if prefix == "train" and has_metric_value(metrics.get("loss")):
            report = {
                "step": step,
                "epoch": epoch,
                "loss": metrics["loss"],
                "lr": metrics.get("lr"),
                "grad_norm": metrics.get("grad_norm"),
                **self._select_metrics(metrics, _TRAIN_METRIC_KEYS),
            }
            # Throttled to log_interval to reduce output. A withheld step is held as
            # pending rather than dropped, so close() can flush the last one.
            if step % self._log_interval == 0:
                self._callback.report_train_step(**report)
                self._pending_train_report = None
            else:
                self._pending_train_report = report

        # Handle validation metrics.
        #
        # `val_loss` is optional because GRPO has none: its validation dict is
        # {accuracy, avg_length}. Gating on loss here dropped every GRPO validation
        # report silently, so instead report whenever anything usable came through.
        elif prefix and prefix.startswith("validation"):
            raw_val_loss = metrics.get("loss")
            val_loss = raw_val_loss if has_metric_value(raw_val_loss) else None
            additional_metrics = self._select_metrics(metrics, _VALIDATION_METRIC_KEYS)

            if val_loss is not None or additional_metrics:
                self._callback.report_validation(
                    step=step,
                    epoch=epoch,
                    val_loss=val_loss,
                    **additional_metrics,
                )
                # Track best validation loss
                if val_loss is not None and val_loss < self._best_metric_value:
                    self._best_metric_value = val_loss
                    self._best_epoch = epoch

        _logger.debug(f"log_metrics: step={step}, prefix={prefix}, metrics={metrics}")

    @staticmethod
    def _select_metrics(metrics: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        """Pick the whitelisted keys that carry a forwardable scalar."""
        return {key: metrics[key] for key in keys if has_metric_value(metrics.get(key))}

    def log_hyperparams(self, params: Mapping[str, Any]) -> None:
        """Log hyperparameters and report training start.

        Args:
            params: Dictionary of hyperparameters to log
        """
        # Extract max_steps and num_epochs from params if not already set
        max_steps = self._max_steps or params.get("max_steps", 0)
        num_epochs = self._num_epochs or params.get("num_epochs", 1)

        # Update internal tracking if extracted from params
        if not self._max_steps and max_steps:
            self._max_steps = max_steps
        if not self._num_epochs and num_epochs:
            self._num_epochs = num_epochs

        self._callback.report_training_start(max_steps=max_steps, num_epochs=num_epochs)
        _logger.debug(f"log_hyperparams: max_steps={max_steps}, num_epochs={num_epochs}")

    def log_histogram(self, histogram: list[Any], step: int, name: str) -> None:
        """No-op: required by NeMo-RL's LoggerInterface.

        Jobs Service progress reporting has no histogram concept, so there is
        nothing to forward. Implemented only to satisfy the abstract base class.
        """
        return None

    def log_plot(self, figure: Any, step: int, name: str) -> None:
        """No-op: required by NeMo-RL's LoggerInterface.

        ``figure`` is a ``matplotlib.figure.Figure``; typed ``Any`` so we don't
        import matplotlib. Jobs Service has no figure/plot concept, so this is a
        no-op implemented only to satisfy the abstract base class.
        """
        return None

    def finish(self) -> None:
        """Alias for :meth:`close` under the name NeMo-RL's composite fans out.

        ``nemo_rl.utils.logger.Logger`` has no ``close()`` at all; its only
        teardown hook is ``finish()``, dispatched via
        ``getattr(logger, "finish", None)``. Without this method the composite
        silently skips us and the withheld final step is never flushed. The
        drivers also call ``close()`` directly, because ``grpo_train``/
        ``dpo_train`` never invoke ``finish()`` either -- only the
        single-controller path does.
        """
        self.close()

    def close(self) -> None:
        """Flush any withheld final step, then clean up resources."""
        if self._closed:
            return
        self._closed = True
        self._flush_pending_train_report()
        _logger.info("NemoRLLogger closing")
        self._callback.close()

    def _flush_pending_train_report(self) -> None:
        """Report the last step if the log_interval throttle withheld it.

        Reachable from ``__del__``, so failures must not propagate; the reporter
        already swallows and logs transport errors, and this guards the rest.
        """
        if self._pending_train_report is None:
            return
        report, self._pending_train_report = self._pending_train_report, None
        try:
            self._callback.report_train_step(**report)
        except Exception as exc:  # pragma: no cover - defensive, shutdown path
            _logger.warning(f"Failed to flush final train step: {exc}")

    def __del__(self):
        """Cleanup when the logger is destroyed."""
        try:
            if hasattr(self, "_closed") and not self._closed:
                self.close()
        except Exception:
            # Silently ignore errors during interpreter shutdown
            pass
