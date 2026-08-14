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
from typing import Any, Mapping, Optional, Self

from nemo_rl.utils.logger import LoggerInterface
from nmp.customization_common.service.context import NMPJobContext
from nmp.customization_common.training.callbacks import TrainingProgressCallback, is_chartable
from nmp.rl.tasks.training.progress import JobsServiceProgressReporter

_logger = logging.getLogger(__name__)

# Progress reports for one run, per reporting path. Reporting is throttled to
# whatever cadence lands about this many across the run, so a curve has the same
# resolution whether the run is 300 steps or 30,000. Roughly the number of points a
# chart a few hundred pixels wide can draw distinctly, and past which the extra
# points cost more than they show.
#
# It is also what bounds the cost, which is why it is a ceiling and not a target.
# Every report resends every accumulated series in full and the Jobs service stores
# the blob twice, so upload grows as the square of the report count -- see the
# payload note in nmp.customization_common.training.callbacks. Capping the count is
# what keeps that finite; the resolution argument is what makes 200 the right
# number rather than merely a small one.
#
# Per path, so a run making full use of both is bounded by twice this. That is a
# bound either way; what matters is that no path is unbounded, and applying one
# budget across two cadences that fire independently would mean whichever ran
# first starved the other.
_MAX_REPORTS_PER_RUN = 200

# NeMo-RL's metric dicts are forwarded whole. There is no allow-list: the
# callback keeps the finite scalars and drops everything else, so a metric
# NeMo-RL adds charts itself instead of waiting on a change here. That is what
# the old list cost -- DPO's `accuracy`, `sft_loss` and `rewards_chosen_mean`
# were dropped silently for never having been added to it.
#
# The callback's filter is load-bearing, not defensive: `calculate_single_metric`
# emits a `<key>/histogram` holding a `Histogram`, NeMo-Gym adds a per-agent
# `full_result` `Table`, and `generation_logger_metrics` is a nested dict. Each
# one rides in the same dict as the scalars.


def resolve_log_interval(max_steps: int) -> int:
    """Steps between progress reports: enough steps for ``_MAX_REPORTS_PER_RUN``.

    Run length is the only input. The cadence used to be derived from
    ``val_period`` as well, targeting ~10 reports per validation period, and that
    term decided the interval on nearly every real configuration. It had no
    bearing on the question: how often someone wants the curve and the progress
    bar to move is unrelated to how often the run validates.

    Its effect was to hold the report count at ten per epoch at every scale.
    ``compute_val_check_interval`` returns ``steps_per_epoch`` when the user sets
    no ``val_check_interval``, so on the default path ``val_period`` *was* the
    epoch: a 20,000-step run drew its loss curve from ten points. The coupling
    was inverted, too -- validating less often, which is what you do when
    validation is expensive, made the training curve coarser.

    ``report_running`` derives ``percentage_done`` from the step a train report
    states, so this sets the granularity of the progress bar as well as of the
    chart. Ten reports across an eleven-hour run is ten movements of the bar.
    """
    return max((max(max_steps, 0) + _MAX_REPORTS_PER_RUN - 1) // _MAX_REPORTS_PER_RUN, 1)


def resolve_val_report_interval(val_period: int | None, max_steps: int) -> int:
    """Validation passes between validation reports.

    The same bound as :func:`resolve_log_interval`, applied to the other report
    path. A validation report costs exactly what a train report costs -- every
    series resent in full, stored twice by the Jobs service -- so capping only
    the train side bounds nothing: ``val_check_interval=1`` is reachable through
    ``compute_val_check_interval``, and it produces one validation pass per step.
    A 20k-step run then made 200 train reports and 20,000 validation ones.

    Returns 1 for any ordinary cadence, so nothing in the existing regime moves:
    validating every 100 steps over 20k steps is 200 passes, which is already the
    cap. Only a cadence that would exceed it thins the passes out.
    """
    period = max(val_period or 0, 1)
    passes = max(max_steps, 0) // period
    return max((passes + _MAX_REPORTS_PER_RUN - 1) // _MAX_REPORTS_PER_RUN, 1)


def _val_dataset_name(prefix: str) -> str:
    """The dataloader name NeMo-RL suffixed onto a validation prefix.

    ``validation`` carries none; ``validation-0`` and ``validation/nemo_gym``
    name their dataloader, the separator depending on the caller.
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
        log_interval: int = 10,
        max_steps: int | None = None,
        num_epochs: int | None = None,
        val_report_interval: int = 1,
    ):
        """Initialize the NemoRL logger.

        Args:
            steps_per_epoch: Number of steps per epoch (required for accurate epoch calculation).
            job_ctx: NeMo Platform job context for progress reporting (defaults to environment variables).
            log_interval: Number of steps between progress updates.
            max_steps: Total number of training steps (optional, used for progress reporting).
            num_epochs: Total number of epochs (optional, used for progress reporting).
            val_report_interval: Validation passes between validation reports. 1 reports
                every pass, which is what any ordinary validation cadence resolves to.

        Raises:
            ValueError: If ``steps_per_epoch``, ``log_interval`` or
                ``val_report_interval`` is < 1. All three are used as
                divisors/moduli in ``log_metrics`` (epoch derivation and the two
                throttles), so non-positive values are rejected up front to fail
                fast instead of raising ZeroDivisionError mid-training.
        """
        if steps_per_epoch < 1:
            raise ValueError(f"steps_per_epoch must be >= 1, got {steps_per_epoch}")
        if log_interval < 1:
            raise ValueError(f"log_interval must be >= 1, got {log_interval}")
        if val_report_interval < 1:
            raise ValueError(f"val_report_interval must be >= 1, got {val_report_interval}")

        self._job_ctx = job_ctx or NMPJobContext.from_env()
        self._log_interval = log_interval
        self._val_report_interval = val_report_interval
        self._max_steps = max_steps
        self._num_epochs = num_epochs
        self._steps_per_epoch = steps_per_epoch

        self._callback = TrainingProgressCallback(JobsServiceProgressReporter(self._job_ctx))

        self._closed = False

        # Validation passes seen so far, which is what the validation throttle
        # counts against: passes arrive on their own cadence, so a step-based
        # modulus would skip whole passes rather than thin them evenly.
        self._val_passes = 0

        # The prefix whose metrics keep the bare names; see _namespace_validation.
        self._primary_val_prefix: str | None = None

        # Reports built but withheld by a throttle, at most one of each kind.
        # Flushed on close() so a run's final train step and final validation pass
        # are reported even when neither lands on its interval -- otherwise the
        # last recorded values are stale.
        self._pending: dict[str, dict[str, Any]] = {}

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
    ) -> Self:
        """Build a logger from a NeMo-RL training schedule.

        The arithmetic lives here rather than in each driver, which is where DPO
        derived its own ``log_interval`` from ``val_period`` and where any further
        algorithm would have copied it. One place to call, and one place to fix.

        Args:
            steps_per_epoch: Authoritative value when the algorithm config carries
                one (DPO does); otherwise derived from max_steps and num_epochs.
            val_period: Steps between validation passes. Sets the cadence of the
                validation reports only; the train cadence is run length alone.
        """
        return cls(
            steps_per_epoch=resolve_steps_per_epoch(max_steps, num_epochs, steps_per_epoch),
            job_ctx=job_ctx,
            log_interval=resolve_log_interval(max_steps),
            val_report_interval=resolve_val_report_interval(val_period, max_steps),
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
            report = {"step": step, "epoch": epoch, "metrics": dict(metrics)}
            # Throttled to log_interval to reduce output. A withheld step is held as
            # pending rather than dropped, so close() can flush the last one.
            if step % self._log_interval == 0:
                self._send("train", report)
            else:
                self._pending["train"] = report

        # Validation reports whatever the pass produced. There is one validation
        # log per pass per dataloader and no rollout twin to tell apart, so
        # requiring a `loss` here bought nothing and cost whole passes: GRPO
        # validates on `accuracy` and `avg_length` and reports no loss at all, so
        # every validation it ran went unrecorded. The gate is only against a
        # hollow report -- a pass whose metrics are all histograms says nothing.
        elif prefix and prefix.startswith("validation"):
            if any(is_chartable(value) for value in metrics.values()):
                self._val_passes += 1
                report = {
                    "step": step,
                    "epoch": epoch,
                    "metrics": self._namespace_validation(prefix, metrics),
                }
                if self._val_passes % self._val_report_interval == 0:
                    self._send("validation", report)
                else:
                    self._pending["validation"] = report

        _logger.debug(f"log_metrics: step={step}, prefix={prefix}, metrics={metrics}")

    def _namespace_validation(self, prefix: str, metrics: Mapping[str, Any]) -> dict[str, Any]:
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
        dataset keeps whichever namespace it started in.
        """
        if self._primary_val_prefix is None:
            self._primary_val_prefix = prefix
        if prefix == self._primary_val_prefix:
            return dict(metrics)
        dataset = _val_dataset_name(prefix) or prefix
        return {f"{dataset}_{name}": value for name, value in metrics.items()}

    def _send(self, kind: str, report: dict[str, Any]) -> None:
        """Report one built payload, retiring anything withheld of that kind."""
        if kind == "train":
            self._callback.report_train_step(**report)
        else:
            self._callback.report_validation(**report)
        self._pending.pop(kind, None)

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
        """Flush any withheld final step, then clean up resources."""
        if self._closed:
            return
        self._closed = True
        self._flush_pending()
        _logger.info("NemoRLLogger closing")
        self._callback.close()

    def _flush_pending(self) -> None:
        """Report whatever the throttles withheld, oldest step first.

        Step order so a series' points are appended in the order they were
        produced, rather than in whichever order the kinds happen to iterate.

        Reachable from ``__del__``, so failures must not propagate; the reporter
        already swallows and logs transport errors, and this guards the rest.
        """
        pending, self._pending = self._pending, {}
        for kind, report in sorted(pending.items(), key=lambda item: item[1]["step"]):
            try:
                self._send(kind, report)
            except Exception as exc:  # pragma: no cover - defensive, shutdown path
                _logger.warning(f"Failed to flush final {kind} report: {exc}")

    def __del__(self):
        """Cleanup when the logger is destroyed."""
        try:
            if hasattr(self, "_closed") and not self._closed:
                self.close()
        except Exception:
            # Silently ignore errors during interpreter shutdown
            pass
