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
from collections.abc import Collection
from typing import Any, Mapping, Optional, Self

from nemo_rl.utils.logger import LoggerInterface
from nmp.customization_common.service.context import NMPJobContext
from nmp.customization_common.training.callbacks import TrainingProgressCallback, is_chartable
from nmp.customization_common.training.reporting import (
    DEFAULT_MIN_REPORT_INTERVAL_SECONDS,
    DIAGNOSTIC_TIME_SERIES,
)
from nmp.rl.tasks.training.progress import JobsServiceProgressReporter

_logger = logging.getLogger(__name__)

# This logger no longer throttles. Bounding the report count is
# TrainingProgressCallback's job now, on both paths and for all three backends --
# NeMo-RL was the only one that did it, and the other two paid quadratically for
# the absence. What lived here (a per-run report budget, a train-step modulus, a
# validation-pass counter, and a pending/flush pair) moved there wholesale; the
# validation counter was also replaced rather than moved, because counting
# reports rather than distinct steps split a multi-dataloader pass across the
# admit/hold boundary and burned the budget N times faster with N dataloaders.
#
# What remains is an adapter: route by prefix, qualify validation metrics by
# dataloader, derive the epoch, and dedupe the rollout log.

#: What a preference-learning run is read on, beyond the shared diagnostics.
#: Together with :data:`DIAGNOSTIC_TIME_SERIES` these select fourteen of the twenty
#: metrics DPO reports (eleven on the train path, nine on validation); the six left
#: out are accounting counters -- ``num_valid_samples``, ``global_valid_seqs``,
#: ``global_valid_toks`` on both phases -- whose current value is all anyone reads.
#:
#: Patterns rather than literal names so each entry covers both phases and the whole
#: family. That is mostly load-bearing over in ``DIAGNOSTIC_TIME_SERIES``, whose
#: ``*_loss`` picks up ``train_sft_loss`` and ``val_preference_loss`` as well as the
#: two plain losses -- and picks them up for a second validation dataloader too,
#: whose names NeMo-RL qualifies with the dataset (``val_heldout_loss``).
DPO_TIME_SERIES_METRICS = (
    "*_accuracy",
    "*_rewards_chosen_mean",
    "*_rewards_rejected_mean",
)

#: GRPO's own read-on set. The DPO list is preference-learning shaped -- its one
#: reward entry, ``*_rewards_chosen_mean``, matches nothing GRPO emits -- so before
#: this a GRPO run stored four curves out of roughly eighty metrics, and the reward
#: was not among them. A policy-gradient run is read on reward first and on the
#: off-policy diagnostics second; those are the two things a stored history answers
#: and a current value cannot.
#:
#: Names carry ``/`` (``advantages/mean``), which ``*`` matches like any other
#: character, so a family is reachable with one entry.
#: Left out deliberately, as current values only: the ``/max /min /median /stddev``
#: siblings of every rollout family, the accounting counters
#: (``global_valid_toks``, ``num_valid_samples``, ``total_num_tokens``), and the
#: ratio-clipping bounds, which are read as "where is it now", not as a curve.
#:
#: Three more are left out for reasons particular to this service, since each looks
#: like an obvious inclusion:
#:
#: ``train_filtered_reward`` is unreachable, not merely inert. ``grpo.py`` sets
#: ``metrics["filtered_reward"]`` only under ``use_dynamic_sampling``, which
#: ``grpo_config.py`` hardcodes to False with no knob on ``GRPOTraining``.
#:
#: ``*total_reward/mean`` is the NeMo-Gym aggregator's reward, and on this service
#: it is the same number as ``train_reward`` -- both are the arithmetic mean of the
#: same ``full_result["reward"]`` values, because the three transforms that could
#: separate them (``reward_scaling``, ``reward_shaping``, ``use_dynamic_sampling``)
#: are all hardcoded off. Its validation half is worse than redundant: ``validate()``
#: reassigns ``additional_metrics_to_report`` per batch, so ``val_total_reward/mean``
#: is the *last batch only*, while ``val_accuracy`` below is the whole-pass mean of
#: the same quantity. If those three transforms are ever exposed, add it back --
#: that is exactly when raw-verifier and post-transform reward stop coinciding.
#:
#: ``*_rewards_chosen_mean``/``_rejected_mean`` are DPO's, and match nothing here.
GRPO_TIME_SERIES_METRICS = (
    # Reward: the mean over the step's batch, which is what the loss optimized.
    "train_reward",
    # GRPO's validation reward. `validate()` reports no loss at all, so this is the
    # only curve a validation pass contributes -- and it is the whole-pass mean,
    # unlike the per-batch rollout metrics beside it. Shares a spelling with DPO's
    # entry; both lists carry it because both algorithms report one.
    "*_accuracy",
    # Off-policy drift. `token_mult_prob_error` is the canonical rollout-vs-training
    # logprob mismatch signal (the loop plots a sample above 1.05); the KL pair is
    # how far the policy has walked from the reference.
    #
    # `kl_penalty` is a flat zero under the default `ref_policy_kl_penalty=0.0` --
    # the loss function only computes `kl` when the coefficient is nonzero. Kept
    # anyway, because the coefficient is a user-facing knob: a run with KL
    # regularization on wants the curve, and storing zeros for the runs that don't
    # is cheaper than having no history for the runs that do.
    "*_token_mult_prob_error",
    "*_gen_kl_error",
    "*_kl_penalty",
    # Advantage centering: should sit near zero, and drift means a broken baseline.
    "*advantages/mean",
    # Entropy collapse -- the failure that looks fine on the reward curve right up
    # until generations degenerate.
    "*_approx_entropy",
    # Length and termination behaviour, on both phases. `*_avg_length` is
    # validation's whole-pass mean; `*gen_tokens_per_sample/mean` is the train
    # rollout's. Truncation rising is usually why reward stopped moving.
    "*gen_tokens_per_sample/mean",
    "*_avg_length",
    "*_truncation_rate",
    # Multi-turn agent health for NeMo-Gym rollouts.
    "*turns_per_sample/mean",
)

#: What each driver passes as its ``default_time_series_metrics``: the shared
#: diagnostic set plus its own algorithm's.
#:
#: One list per algorithm rather than a union of all of them, because
#: ``TrainingProgressCallback.close()`` warns about patterns that matched no metric,
#: and that warning exists to catch a user's typo -- most often an unqualified name
#: like ``loss``, which selects nothing. A union makes it fire on every healthy run
#: (a DPO run would name every GRPO pattern and vice versa), and a warning that
#: always fires cannot distinguish the typo it was built for. The union also made
#: each algorithm carry the other's payload for nothing.
#:
#: Adding an algorithm means adding its tuple and passing it from its driver. There
#: is deliberately no combined constant to fall back on: a new driver that forgets
#: gets :data:`DIAGNOSTIC_TIME_SERIES` and loses its own metrics' history, which is
#: recoverable and visible in the log, rather than silently inheriting two other
#: algorithms' patterns.
DPO_DEFAULT_TIME_SERIES_METRICS = DIAGNOSTIC_TIME_SERIES + DPO_TIME_SERIES_METRICS
GRPO_DEFAULT_TIME_SERIES_METRICS = DIAGNOSTIC_TIME_SERIES + GRPO_TIME_SERIES_METRICS

# NeMo-RL's metric dicts are forwarded whole. There is no allow-list on *reporting*: the
# callback keeps the finite scalars and drops everything else, so a metric
# NeMo-RL adds charts itself instead of waiting on a change here. That is what
# the old list cost -- DPO's `accuracy`, `sft_loss` and `rewards_chosen_mean`
# were dropped silently for never having been added to it.
#
# The callback's filter is load-bearing, not defensive: `calculate_single_metric`
# emits a `<key>/histogram` holding a `Histogram`, NeMo-Gym adds a per-agent
# `full_result` `Table`, and `generation_logger_metrics` is a nested dict. Each
# one rides in the same dict as the scalars.


def _val_dataset_name(prefix: str) -> str:
    """The dataloader name NeMo-RL suffixed onto a validation prefix.

    Most algorithms log a bare ``validation``. DPO and RM iterate a dict of
    validation dataloaders and log ``f"validation-{name}"`` per entry, keyed by
    dataset -- ``validation-default``, ``validation-HelpSteer3``. Those two forms
    are all any current call site emits.

    ``/`` is stripped as well because it is NeMo-RL's other prefix separator
    (``timing/validation``). Nothing composes a validation prefix with it today;
    stripping it costs nothing if something starts.
    """
    return prefix[len("validation") :].lstrip("-/")


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
        max_steps: int | None = None,
        num_epochs: int | None = None,
        time_series_metrics: Collection[str] | None = None,
        min_report_interval_seconds: float | None = None,
        default_time_series_metrics: Collection[str] = DIAGNOSTIC_TIME_SERIES,
    ):
        """Initialize the NemoRL logger.

        Args:
            steps_per_epoch: Number of steps per epoch (required for accurate epoch calculation).
            job_ctx: NeMo Platform job context for progress reporting (defaults to environment variables).
            max_steps: Total number of training steps (optional, used for progress reporting).
            num_epochs: Total number of epochs (optional, used for progress reporting).
            time_series_metrics: Qualified metric names or glob patterns to
                record as a series, from the job config. None takes
                ``default_time_series_metrics`` -- absent means "the algorithm's
                default", not "everything"; ``["*"]`` is how a caller asks for
                every metric. An empty list means no series at all and is
                honoured as written, which is why the substitution tests
                ``is None`` rather than truthiness.
            default_time_series_metrics: What an unstated ``time_series_metrics``
                falls back to. The driver supplies its algorithm's list
                (:data:`GRPO_DEFAULT_TIME_SERIES_METRICS`,
                :data:`DPO_DEFAULT_TIME_SERIES_METRICS`); the default here is the
                algorithm-agnostic diagnostic set, so a driver that forgets loses
                its own metrics' history rather than inheriting another
                algorithm's patterns.

        Raises:
            ValueError: If ``steps_per_epoch`` is < 1. It divides in
                ``log_metrics`` to derive the epoch, so a non-positive value is
                rejected up front to fail fast instead of raising
                ZeroDivisionError mid-training.
        """
        if steps_per_epoch < 1:
            raise ValueError(f"steps_per_epoch must be >= 1, got {steps_per_epoch}")

        self._job_ctx = job_ctx or NMPJobContext.from_env()
        self._max_steps = max_steps
        self._num_epochs = num_epochs
        self._steps_per_epoch = steps_per_epoch

        self._callback = TrainingProgressCallback(
            JobsServiceProgressReporter(self._job_ctx),
            time_series_metrics=(default_time_series_metrics if time_series_metrics is None else time_series_metrics),
            min_report_interval_seconds=(
                DEFAULT_MIN_REPORT_INTERVAL_SECONDS
                if min_report_interval_seconds is None
                else min_report_interval_seconds
            ),
        )

        self._closed = False

        # The prefix whose metrics keep the bare names; see _qualify_by_dataset.
        self._primary_val_prefix: str | None = None

        _logger.info(
            f"Initialized NemoRLLogger with jobs_url={self._job_ctx.jobs_url}, "
            f"max_steps={max_steps}, num_epochs={num_epochs}, steps_per_epoch={steps_per_epoch}"
        )

    @classmethod
    def for_schedule(
        cls,
        *,
        max_steps: int,
        num_epochs: int | None,
        val_period: int | None = None,
        steps_per_epoch: int | None = None,
        time_series_metrics: Collection[str] | None = None,
        min_report_interval_seconds: float | None = None,
        default_time_series_metrics: Collection[str] = DIAGNOSTIC_TIME_SERIES,
        job_ctx: NMPJobContext | None = None,
    ) -> Self:
        """Build a logger from a NeMo-RL training schedule.

        Args:
            steps_per_epoch: Authoritative value when the algorithm config carries
                one (DPO does); otherwise derived from max_steps and num_epochs.
            time_series_metrics: Names or patterns from the job config. None takes
                ``default_time_series_metrics``.
            default_time_series_metrics: The calling driver's algorithm list --
                :data:`GRPO_DEFAULT_TIME_SERIES_METRICS` or
                :data:`DPO_DEFAULT_TIME_SERIES_METRICS`.
            val_period: Accepted and unused. It used to set the validation report
                cadence, and before that the training one; both now follow from
                run length in the shared callback. Kept in the signature so the
                drivers that pass it keep working, and because the next algorithm
                wired up will pass it too.
        """
        return cls(
            steps_per_epoch=resolve_steps_per_epoch(max_steps, num_epochs, steps_per_epoch),
            job_ctx=job_ctx,
            max_steps=max_steps,
            num_epochs=num_epochs,
            time_series_metrics=time_series_metrics,
            min_report_interval_seconds=min_report_interval_seconds,
            default_time_series_metrics=default_time_series_metrics,
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
        # `step` arrives 1-indexed and is used as-is. The caller passes
        # `total_steps + 1`, where total_steps is 0-based and incremented *after*
        # logging (nemo_rl/algorithms/dpo.py), so it is already the
        # 1-indexed step number. Incrementing again put the last step of an
        # N-step run at N+1 and shifted the whole series one to the right of the
        # axis Studio draws it against.
        #
        # Step 0 does arrive, from the validate-at-start path only; it belongs to
        # epoch 1, hence the clamp rather than a bare `step - 1`.
        epoch = (max(step - 1, 0) // self._steps_per_epoch) + 1

        # `loss` gates the train branch as a discriminator, not as a requirement.
        # GRPO and PPO log twice under `prefix="train"` at one step -- rollout
        # stats first, then the training metrics, both at `total_steps + 1`
        # (grpo.py) -- and only the second carries a loss. Keying on it is what
        # keeps one step from producing two reports, and what keeps the rollout
        # log from displacing a pending report that has the loss in it.
        if prefix == "train" and is_chartable(metrics.get("loss")):
            self._callback.report_train_step(step=step, epoch=epoch, metrics=dict(metrics))

        # Validation reports whatever the pass produced. There is one validation
        # log per pass per dataloader and no rollout twin to tell apart, so
        # requiring a `loss` here bought nothing and cost whole passes: GRPO
        # validates on `accuracy` and `avg_length` and reports no loss at all, so
        # every validation it ran went unrecorded. The gate is only against a
        # hollow report -- a pass whose metrics are all histograms says nothing.
        elif prefix and prefix.startswith("validation"):
            if any(is_chartable(value) for value in metrics.values()):
                self._callback.report_validation(
                    step=step,
                    epoch=epoch,
                    metrics=self._qualify_by_dataset(prefix, metrics),
                )

        _logger.debug(f"log_metrics: step={step}, prefix={prefix}, metrics={metrics}")

    def _qualify_by_dataset(self, prefix: str, metrics: Mapping[str, Any]) -> dict[str, Any]:
        """Fold the dataloader name into each metric name, past the first set.

        ``validate()`` loops over ``val_dataloader.items()`` and logs once per
        dataset, every call at the same step under ``f"validation-{name}"``.
        Forwarded as-is, two datasets' ``loss`` interleave as two points at one
        step in a single ``val_loss`` series -- the collision the ``<phase>_``
        rule exists to prevent, one level further down. Automodel's
        ``val_dataloaders`` loop has the same shape.

        The first prefix seen keeps the bare names, so ``val_loss`` stays
        ``val_loss`` on the ordinary single-dataset run. NeMo-RL names that
        dataloader too, so keying on "did a name arrive" would rename the common
        case and take Studio's curve with it. Iteration order over the dataloader
        dict is stable within a run and across a resume of the same config, so a
        dataset keeps whichever naming it started with.
        """
        if self._primary_val_prefix is None:
            self._primary_val_prefix = prefix
        if prefix == self._primary_val_prefix:
            return dict(metrics)
        dataset = _val_dataset_name(prefix) or prefix
        return {f"{dataset}_{name}": value for name, value in metrics.items()}

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
        driver also calls ``close()`` directly, because ``dpo_train`` never
        invokes ``finish()`` either -- only the single-controller path does.
        """
        self.close()

    def close(self) -> None:
        """Clean up resources, flushing whatever the callback's gates withheld.

        The flush itself lives in ``TrainingProgressCallback.close()`` now, and is
        idempotent there as well as here -- this is reachable from the driver's
        ``finally``, from ``finish()`` and from ``__del__``.
        """
        if self._closed:
            return
        self._closed = True
        _logger.info("NemoRLLogger closing")
        self._callback.close()

    def __del__(self):
        """Cleanup when the logger is destroyed."""
        try:
            if hasattr(self, "_closed") and not self._closed:
                self.close()
        except Exception:
            # Silently ignore errors during interpreter shutdown
            pass
