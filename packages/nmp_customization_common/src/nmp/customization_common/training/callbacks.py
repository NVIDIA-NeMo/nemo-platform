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
though -- a key that is sent replaces the stored value wholesale -- so a report
carrying ``metrics`` sends every series in full rather than a delta, and a report
with nothing new to say about the curves omits the key rather than sending a
partial copy.

Series naming
-------------
One rule, no exceptions: a metric is stored and reported as ``<phase>_<name>``,
where the backend supplies its framework's own ``<name>`` (``loss``, ``lr``,
``accuracy``) and the phase that produced it supplies the prefix. The same
namespaced name is used for the accumulated series and for the current-step
value in ``status_details``.

The prefix is load-bearing rather than cosmetic -- DPO reports ``accuracy`` in
both its train and validation dicts, so bare names would interleave two
different quantities into one series. It also makes the payload collision-proof:
nothing a ``<phase>_`` name can spell reaches ``phase``, ``step``, ``epoch`` or
``metrics``.

``train_loss`` and ``val_loss``, the two series Studio charts, are what this rule
produces for a metric named ``loss``. They are not special cases, and there are
none.

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

Those are client-side upload figures. The server pays twice over: ``JobDispatcher``
persists each report to the task and then again to the copy propagated up to the
job, so the write volume is double the numbers above.

Deliberately accepted for batch training jobs, on the understanding that a
backend bounds its own report count -- NeMo-RL's ``resolve_log_interval`` caps a
run for exactly this reason. A backend that instead reports every step of a long
run pays quadratically, and the answer to that is delta appends in the transport
rather than trimming the series here.

Backends subclass this and set :attr:`_default_backend`: unsloth stamps a
``backend`` field on each report (``"unsloth"``); automodel and NeMo-RL leave it
``None`` so no ``backend`` key is added (preserving their status-detail shape).
Callers may also pass ``backend`` per call (e.g. unsloth's HF trainer callback).
"""

import logging
import math
import numbers
from collections.abc import Mapping
from typing import Any, ClassVar, cast

from nmp.customization_common.training.progress import JobsServiceProgressReporter

logger = logging.getLogger(__name__)


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


def _namespace(phase: str, metrics: Mapping[str, object]) -> dict[str, float | int]:
    """The chartable subset of ``metrics``, keyed by ``<phase>_<name>``.

    The single naming rule. A backend passes its framework's own metric names --
    ``loss``, ``lr``, ``accuracy`` -- and the phase that produced them supplies
    the prefix, so the train and validation copies of one name cannot collide.
    ``train_loss`` and ``val_loss`` are what the rule produces for ``loss``, not
    exceptions carved out of it.

    Prefixing is also what makes the payload collision-proof: ``report_running``
    owns ``phase``, and this callback owns ``step``, ``epoch`` and ``metrics``,
    none of which a ``<phase>_`` name can reach.

    Values :func:`is_chartable` rejects are dropped silently, and dropped from
    the report as well as the series -- one bad metric should cost its own curve,
    never the whole report. A ``Histogram`` left in ``status_details`` makes the
    update fail to serialize, and ``update_task`` swallows that error, so every
    metric in the report is lost while the job goes on looking healthy.
    """
    return {f"{phase}_{name}": _coerce(value) for name, value in metrics.items() if is_chartable(value)}


def _coerce(value: object) -> float | int:
    """Narrow a chartable value to a JSON-serializable builtin.

    numpy scalars satisfy ``numbers.Real`` but are not serializable. Counts stay
    ``int`` rather than becoming ``64.0``.
    """
    real = cast(numbers.Real, value)
    return int(real) if isinstance(real, numbers.Integral) else float(real)


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

    def _report_metrics(
        self,
        phase: str,
        report_phase: str,
        step: int,
        epoch: int,
        metrics: Mapping[str, object],
        backend: str | None,
    ) -> None:
        """Record every metric as a point and report them as current values.

        The one path both ``report_train_step`` and ``report_validation`` take.
        ``phase`` namespaces the series (``train``/``val``); ``report_phase`` is
        what the Jobs service records as the task's phase.
        """
        namespaced = _namespace(phase, metrics)
        for name, value in namespaced.items():
            self._series.setdefault(name, []).append({"step": step, "epoch": epoch, "value": value})

        details: dict[str, object] = {
            "step": step,
            "epoch": epoch,
            **namespaced,
            "metrics": self._build_metrics_summary(),
        }
        resolved = self._resolve_backend(backend)
        if resolved is not None:
            details["backend"] = resolved
        self._reporter.report_running(phase=report_phase, **details)

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
        self, step: int, epoch: int, metrics: Mapping[str, object], *, backend: str | None = None
    ) -> None:
        """Report one training step.

        Hand over the framework's metric dict as-is, under its own names --
        ``loss``, ``lr``, ``grad_norm``, ``preference_loss``, whatever it
        produces. Each chartable entry becomes a ``train_<name>`` series *and* a
        ``train_<name>`` current value, so a consumer can read either the curve or
        the latest point.

        No metric is required and none is privileged: a step that produces no
        loss reports no ``train_loss``, and a name is stated only when it was
        observed, because a null charts as a real zero.

        Taken as a dict rather than ``**kwargs`` so that the metric namespace and
        this method's own parameters cannot collide. Backends forward whatever
        their framework emits, and a framework is free to call something ``step``.
        """
        self._report_metrics("train", "training", step, epoch, metrics, backend)

    def report_validation(
        self, step: int, epoch: int, metrics: Mapping[str, object], *, backend: str | None = None
    ) -> None:
        """Report one validation pass.

        The same rule under the ``val_`` prefix. An algorithm that validates on
        task metrics alone and reports no ``loss`` simply leaves ``val_loss``
        empty, which is why nothing here is required either.
        """
        self._report_metrics("val", "validation", step, epoch, metrics, backend)

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
