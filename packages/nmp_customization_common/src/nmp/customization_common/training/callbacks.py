# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Training progress callback shared by the customization backends.

Composes a :class:`nmp.customization_common.training.progress.JobsServiceProgressReporter`
and provides training-specific methods. Every numeric metric a backend reports is
accumulated as a time series and sent under a ``metrics`` key on the train and
validation reports, so any of them can be charted from job status alone.

The Jobs service merges ``status_details`` key-wise, so the stored series
survives every report that does not mention it: checkpoint, epoch-end and
training-start reports state only what they observed. The merge is shallow,
though -- a report that does send ``metrics`` replaces the stored value
wholesale, so every series goes out in full rather than as a delta.

Series naming
-------------
Series are namespaced by the phase that produced them: ``train_<name>`` and
``val_<name>``, which is what the long-standing ``train_loss``/``val_loss`` pair
already did. The prefix is load-bearing rather than cosmetic -- DPO reports
``accuracy`` in both its train and validation dicts, so unprefixed names would
interleave two different quantities into one series.

``train_loss`` and ``val_loss`` keep those exact names, so existing consumers
(the Studio loss chart) are unaffected.

Payload size
------------
Every series is resent in full on every train and validation report, so the
stored blob grows as ``series x reports`` and total upload as the square of it.
The driver of that cost is the number of *reports*, not training steps --
backends throttle reporting, so a 500-step run at ``log_interval=10``
accumulates 50 points per series, not 500.

Measured for a backend reporting ~22 series:

    500 steps, log_interval 10  ->   42 KB final blob,   1.1 MB uploaded
    500 steps, log_interval  1  ->  413 KB final blob, 101.3 MB uploaded

Deliberately accepted for batch training jobs. It does mean a backend that
reports every step of a long run pays quadratically, so if that becomes a real
configuration the transport should move to delta appends rather than the series
being trimmed here.

Backends subclass this and set :attr:`_default_backend`: unsloth stamps a
``backend`` field on each report (``"unsloth"``); automodel and NeMo-RL leave it
``None`` so no ``backend`` key is added (preserving their status-detail shape).
Callers may also pass ``backend`` per call (e.g. unsloth's HF trainer callback).
"""

import logging
import math
import numbers
from typing import Any, ClassVar, cast

from nmp.customization_common.training.progress import JobsServiceProgressReporter

logger = logging.getLogger(__name__)

#: ``(phase, name)`` pairs that keep the bare name instead of taking a phase
#: prefix, because they predate the prefixing scheme and are read by name
#: downstream.
#:
#: Keyed on the phase as well as the name, not the name alone: a backend that
#: reports ``val_loss`` among a *train* step's metrics would otherwise append it
#: to the validation loss curve, which is exactly the cross-phase interleaving
#: the prefix exists to prevent. Such a metric becomes ``train_val_loss``.
_UNPREFIXED = frozenset({("train", "train_loss"), ("val", "val_loss")})

#: Names a backend metric may not use, because ``report_running`` takes ``phase``
#: as its own parameter -- a collision is a TypeError out of the training loop
#: rather than the silent shadowing that splat order gives the other names.
_RESERVED = frozenset({"phase"})


def is_chartable(value: Any) -> bool:
    """Whether ``value`` is a finite scalar that can enter a metric series.

    Backends hand us whatever their framework produced, which is not always a
    number: NeMo-RL's metric dicts interleave ``Histogram`` objects, tables and
    nested dicts with the scalars, and ``math.isfinite`` raises ``TypeError`` on
    all of those rather than returning False.

    NaN and both infinities are rejected: neither is a value a chart can place on
    an axis, and a single infinity flattens every real point in the series
    against it. The SDK coerces both to ``null`` on the wire, so letting one
    through costs a hole in the curve rather than a malformed blob.

    ``bool`` is rejected despite being an ``int`` subclass: no metric here is a
    flag, and silently charting one as 0/1 is worse than dropping it.
    """
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        # An unbounded Python int overflows float(). The contract here is that
        # any value a backend hands us gets classified without raising, so an
        # absurd counter loses its series rather than the run losing reporting.
        return False


def _forwardable(additional_metrics: dict[str, object]) -> dict[str, object]:
    """The subset of ``additional_metrics`` that may ride along in status_details.

    Keeps one invariant: a metric appears as a current-step scalar exactly when
    it also entered a series. Both drops are silent, for the same reason -- one
    bad metric should cost its own curve, never the whole report:

    - Values :func:`is_chartable` rejects. ``_record`` already skipped these, but
      they were still splatted into the payload, where a ``Histogram`` makes the
      whole update fail to serialize. ``update_task`` swallows that error, so
      every metric in the report is lost while the job goes on looking healthy.
    - :data:`_RESERVED` names, which collide with ``report_running``'s own
      parameters and raise ``TypeError`` into the training loop.
    """
    return {name: value for name, value in additional_metrics.items() if name not in _RESERVED and is_chartable(value)}


class TrainingProgressCallback:
    """Report training progress to the Jobs service."""

    #: Backend name stamped on each report when a per-call ``backend`` isn't given.
    #: ``None`` means no ``backend`` field is added.
    _default_backend: ClassVar[str | None] = None

    def __init__(self, reporter: JobsServiceProgressReporter):
        self._reporter = reporter

        #: series name -> [{step, epoch, value}], seeded from the server so a
        #: resumed job continues its curves instead of restarting them.
        self._series: dict[str, list[dict[str, float | int]]] = dict(reporter.fetch_current_metrics())
        if any(self._series.values()):
            logger.info(
                "Seeded %d metric series from server (%d points): %s",
                len(self._series),
                sum(len(points) for points in self._series.values()),
                ", ".join(sorted(self._series)),
            )

    def _resolve_backend(self, backend: str | None) -> str | None:
        return backend if backend is not None else self._default_backend

    def _record(self, phase: str, name: str, step: int, epoch: int, value: object) -> None:
        """Append one point to the ``<phase>_<name>`` series, if it is chartable.

        Silently drops non-numeric values rather than raising: a backend adding a
        metric that turns out to be a histogram should lose that one series, not
        fail the training run's progress reporting.
        """
        if not is_chartable(value):
            return
        # Coerce to a built-in: numpy scalars satisfy numbers.Real but are not
        # JSON-serializable. Counts stay ints rather than becoming 64.0.
        real = cast(numbers.Real, value)
        numeric: float | int = int(real) if isinstance(real, numbers.Integral) else float(real)
        series = name if (phase, name) in _UNPREFIXED else f"{phase}_{name}"
        self._series.setdefault(series, []).append({"step": step, "epoch": epoch, "value": numeric})

    def _build_metrics_summary(self) -> dict[str, list[dict[str, float | int]]]:
        """Build the accumulated metrics payload for inclusion in status_details.

        ``train_loss``/``val_loss`` are always present, even when empty, so the
        shape stays stable for consumers that index them directly. Lists are
        copied: the payload must not mutate after it is handed over.
        """
        summary: dict[str, list[dict[str, float | int]]] = {"train_loss": [], "val_loss": []}
        summary.update({name: list(points) for name, points in self._series.items()})
        return summary

    def report_training_start(self, max_steps: int, num_epochs: int, *, backend: str | None = None) -> None:
        """Report that training has started with schedule information.

        Carries no ``metrics``: it fires before the first step, so it has nothing
        to add to the curves, and sending the empty accumulator would replace a
        resumed job's stored series with two empty lists.
        """
        self._reporter.configure_progress_tracking(max_steps, num_epochs)
        details: dict[str, object] = {
            "step": 0,
            "max_steps": max_steps,
            "num_epochs": num_epochs,
        }
        resolved = self._resolve_backend(backend)
        if resolved is not None:
            details["backend"] = resolved
        self._reporter.report_running(phase="training", **details)

    def report_train_step(
        self,
        step: int,
        epoch: int,
        loss: float,
        lr: float | None = None,
        grad_norm: float | None = None,
        *,
        backend: str | None = None,
        **additional_metrics: object,
    ) -> None:
        """Report training step with metrics.

        ``additional_metrics`` are backend-specific (DPO's ``preference_loss``,
        ``rewards_rejected_mean``, ...). Each numeric one accumulates into
        its own ``train_<name>`` series *and* rides along as a current-step
        scalar, so consumers can read either the curve or the latest value.

        Every scalar is stated only when it was actually observed, matching
        ``val_loss``: an absent ``lr`` or a NaN ``grad_norm`` reaches the server
        as a null, which a chart reads as a real zero.
        """
        forwardable = _forwardable(additional_metrics)
        self._record("train", "train_loss", step, epoch, loss)
        self._record("train", "lr", step, epoch, lr)
        self._record("train", "grad_norm", step, epoch, grad_norm)
        for name, value in forwardable.items():
            self._record("train", name, step, epoch, value)
        # `**forwardable` is splatted first, matching report_validation, so a
        # backend metric cannot shadow the accumulated series or the step's own loss.
        # `step`/`epoch`/`lr`/`grad_norm` are named parameters and so already safe.
        details: dict[str, object] = {
            **forwardable,
            "step": step,
            "epoch": epoch,
            "metrics": self._build_metrics_summary(),
        }
        for name, value in (("train_loss", loss), ("lr", lr), ("grad_norm", grad_norm)):
            if is_chartable(value):
                details[name] = value
        resolved = self._resolve_backend(backend)
        if resolved is not None:
            details["backend"] = resolved
        self._reporter.report_running(phase="training", **details)

    def report_validation(
        self,
        step: int,
        epoch: int,
        val_loss: float | None = None,
        *,
        backend: str | None = None,
        **additional_metrics: object,
    ) -> None:
        """Report validation results.

        ``val_loss`` is optional because not every algorithm produces one -- an
        algorithm may validate purely on task metrics and report no loss at all.
        The key is omitted rather than sent as null, which would chart as a real
        zero, and the ``val_loss`` series simply stays empty for such runs.
        """
        forwardable = _forwardable(additional_metrics)
        details: dict[str, object] = {
            "step": step,
            "epoch": epoch,
            **forwardable,
        }
        for name, value in forwardable.items():
            self._record("val", name, step, epoch, value)
        if is_chartable(val_loss):
            self._record("val", "val_loss", step, epoch, val_loss)
            details["val_loss"] = val_loss
        details["metrics"] = self._build_metrics_summary()

        resolved = self._resolve_backend(backend)
        if resolved is not None:
            details["backend"] = resolved
        self._reporter.report_running(phase="validation", **details)

    def report_checkpoint_saved(
        self,
        step: int,
        epoch: int,
        checkpoint_path: str | None = None,
        *,
        backend: str | None = None,
    ) -> None:
        """Report that a checkpoint was saved.

        The ``checkpoint_path`` key is omitted when the backend has no path to
        state -- both automodel and unsloth pass ``None`` when their framework
        doesn't hand one back. Sending it as null would not merely say nothing:
        the server merges key-wise, so an explicit null overwrites the last known
        checkpoint, while omitting the key leaves it standing.
        """
        details: dict[str, object] = {
            "step": step,
            "epoch": epoch,
        }
        if checkpoint_path:
            details["checkpoint_path"] = checkpoint_path
        resolved = self._resolve_backend(backend)
        if resolved is not None:
            details["backend"] = resolved
        self._reporter.report_running(phase="checkpoint_saved", **details)

    def report_epoch_end(self, step: int, epoch: int, *, backend: str | None = None) -> None:
        """Report that an epoch has completed."""
        details: dict[str, object] = {
            "step": step,
            "epoch": epoch,
        }
        resolved = self._resolve_backend(backend)
        if resolved is not None:
            details["backend"] = resolved
        self._reporter.report_running(phase="epoch_end", **details)

    def close(self) -> None:
        """Clean up resources."""
        self._reporter.close()
