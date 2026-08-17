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
qualified name is used for the accumulated series and for the current-step
value in ``status_details``.

The prefix is load-bearing rather than cosmetic -- DPO reports ``accuracy`` in
both its train and validation dicts, so bare names would interleave two
different quantities into one series. It also makes the payload collision-proof:
nothing a ``<phase>_`` name can spell reaches ``phase``, ``step``, ``epoch`` or
``metrics``.

``train_loss`` and ``val_loss``, the two series Studio charts, are what this rule
produces for a metric named ``loss``. They are not special cases, and there are
none.

Payload size, and the gate that bounds it
-----------------------------------------
Every series is resent in full on every train and validation report, so the
stored blob grows as ``series x reports`` and the cost as the square of it. The
driver is the number of *reports*, not training steps, which is why this class
throttles: see :class:`_PathGate` and :meth:`TrainingProgressCallback._report_metrics`.

One report costs three writes, not one. The client sends it; ``JobDispatcher``
persists it to the task (``dispatcher.py:1217-1223``) and propagates a copy to the
job attempt (``:1240-1242`` -> ``:1018-1019``). Both of those go through
``EntityClient.update``, which PUTs the entity's whole ``data`` blob -- so the two
server-side writes carry the entire accumulated ``metrics`` **whether or not the
report mentioned it**. A report that omits the series is therefore not a cheap
report; it is a report that saves only its own share of one leg out of three.

Measured against a live platform, driving this callback with each backend's real
metric dict. A point serialises to ~43 bytes:

                     series   blob/report   latency/report
    NeMo-RL DPO        20      0.86 KB x R    46ms + 0.31ms/KB
    Automodel          12      0.52 KB x R    46ms + 0.31ms/KB
    unsloth             4      0.17 KB x R    46ms + 0.31ms/KB

That latency is the third cost and the one a user feels: ``update_task`` is a
synchronous call made from the backend's logging hook, on the training thread,
between one optimizer step and the next. It grows with the blob, so an unbounded
run does not merely upload quadratically -- it *stalls training* quadratically.
Measured: 600 unthrottled reports at 11 series spent 52 seconds blocked inside
the loop, the last fifty averaging 2.4x the latency of the first fifty.

Bounding the point count is what keeps all three finite. It leaves one ceiling
standing: each admitted report still resends every series in full, so the answer
to *that* is moving the curves out of ``status_details`` -- not trimming further
here. Delta appends alone would fix only the client leg.

Seeding, and what it inherits
----------------------------
The accumulator lives in this process, so a new process taking over a task
would report from empty and -- the merge being wholesale per key -- replace
whatever the task had already stored. It therefore seeds itself from the
server, which is behaviour that predates the per-metric series: the reporter
has always read back the stored curves.

Known issue: a series can end up holding points from more than one run, which
contradict each other. If a task's pod is replaced -- the Jobs service can
suspend and resume a Kubernetes Job, and the Volcano backend restarts on
``PodFailed`` when an execution profile raises ``maxRetry`` above its default
of zero -- the new process seeds itself from the old one's points and then
appends its own. It takes one of two shapes, according to whether the backend
resumes from a checkpoint.

Automodel and unsloth never do, and neither does a NeMo-RL run that has not
written a checkpoint yet to return to: ``save_period`` is ``val_period``, which
is ``steps_per_epoch``, so a single-epoch run saves only on its last step.
Training restarts at step one and the series carries both runs end to end.

NeMo-RL otherwise does resume. ``dpo.setup()`` loads the latest checkpoint
unconditionally and the loop continues from the step recorded in it. Reporting
runs ahead of checkpointing -- the train cadence is set by run length, the save
cadence by ``val_period`` -- so the steps between that checkpoint and the
interruption had already been recorded, and the replayed points are appended
after the ones they supersede. The curve doubles back on itself across that
range rather than restarting.

Either way, consumers see the last value written at a given step, and a tail
from the abandoned attempt beyond wherever the new run has reached.

Left alone deliberately, and the two shapes are why. The clean fix is to
identify which run a point came from so both can be kept and told apart, but
Studio's loss chart keys a Map by step, so it would need to filter or overlay
by run before any of it were visible. Detecting the restart here and dropping
the superseded points is the other option, and it is right for one shape and
not the other: a replayed range is work that was rolled back and is no loss,
while a from-scratch restart's points are a failed attempt's entire history,
gone permanently to keep one series single-valued. Telling those two apart is
the work, and not a trade to make in passing.

Backends subclass this and set :attr:`_default_backend`: unsloth stamps a
``backend`` field on each report (``"unsloth"``); automodel and NeMo-RL leave it
``None`` so no ``backend`` key is added (preserving their status-detail shape).
Callers may also pass ``backend`` per call (e.g. unsloth's HF trainer callback).
"""

import logging
import math
import numbers
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, cast

from nmp.customization_common.training.progress import JobsServiceProgressReporter
from nmp.customization_common.training.reporting import DEFAULT_MAX_POINTS

logger = logging.getLogger(__name__)

__all__ = ["DEFAULT_MAX_POINTS", "TrainingProgressCallback", "is_chartable"]

#: The two reporting paths, which are also the series-name prefixes the phase
#: supplies. Kept as constants because the gate keys on both meanings.
TRAIN_PHASE = "train"
VAL_PHASE = "val"


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


def _qualify_metric_names(phase: str, metrics: Mapping[str, object]) -> dict[str, float | int]:
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


def _point_step(point: object) -> float | int | None:
    """The step a stored series point records, or ``None`` if it records none.

    Defensive because the accumulator is seeded from whatever the server had
    stored: a malformed blob must cost the points it corrupted, never raise out
    of a report and into the training loop.
    """
    if not isinstance(point, dict):
        return None
    step = point.get("step")
    return step if isinstance(step, (int, float)) else None


@dataclass
class _PathGate:
    """Admission state for one reporting path, and whatever it withheld.

    Two paths report on independent cadences, so each carries its own budget --
    applying one across both would mean whichever fired first starved the other.

    Elapsed steps, never a modulus
    ------------------------------
    ``step % interval == 0`` is only correct when the caller sees every step.
    This class cannot assume that: unsloth's ``on_log`` is gated by HuggingFace at
    ``TrainingArguments.logging_steps`` before it ever reaches us. Compose two
    moduli and you get their LCM rather than the finer of the two -- at
    ``logging_steps=3`` and a target interval of 100, a modulus admits only
    multiples of 300 and draws a third of the points asked for. The default of 1
    divides everything, so a modulus passes every test one would naturally write
    and then mangles the curve for anyone who touches the knob.

    Elapsed steps degrade to "admit everything" when the framework is coarser
    than the target, which is the honest failure, and are behaviour-preserving
    over a contiguous step sequence.
    """

    #: Steps that must elapse between admissions. 1 until the run length is
    #: known, so a backend that never states a schedule reports everything
    #: rather than nothing.
    interval: int = 1

    #: Step of the last admitted report, or None before the first.
    last_admitted: float | int | None = None

    #: The most recent (step, decision) pair. ``validate()`` logs once per
    #: dataloader at one step -- NeMo-RL over ``val_dataloader.items()``,
    #: automodel over ``val_dataloaders`` -- and every one of those must get the
    #: same answer, or one dataset lands at a step where its neighbour was held.
    #: An ordinal counter would also burn the budget N times faster with N
    #: dataloaders, which is the bug this replaces.
    decision: tuple[float | int, bool] | None = field(default=None, repr=False)

    #: The last report this gate withheld, replayed by ``close()`` so a run's
    #: final step is never lost to a throttle. At most one: a newer held report
    #: supersedes an older one, since only the latest is still current.
    pending: dict[str, Any] | None = field(default=None, repr=False)

    def admit(self, step: float | int) -> bool:
        """Whether to record and send a report at ``step``.

        The first arrival is always admitted, so a curve starts at the beginning
        of the run rather than one full interval into it.

        A step at or behind the last admitted one is also admitted, and resets
        the gate to it. That is the from-scratch restart: a replaced pod seeds
        itself from the previous attempt's points and starts again at step one,
        and an elapsed check alone would then withhold every report until the run
        caught up to where the old one stopped. Reporting nothing for the first
        half of a restarted run is a worse failure than the duplicated series the
        seeding note above already documents.
        """
        if self.decision is not None and self.decision[0] == step:
            return self.decision[1]

        admitted = (
            self.last_admitted is None or step <= self.last_admitted or step - self.last_admitted >= self.interval
        )
        self.decision = (step, admitted)
        if admitted:
            self.last_admitted = step
        return admitted


class TrainingProgressCallback:
    """Report training progress to the Jobs service."""

    #: Backend name stamped on each report when a per-call ``backend`` isn't given.
    #: ``None`` means no ``backend`` field is added.
    _default_backend: ClassVar[str | None] = None

    def __init__(
        self,
        reporter: JobsServiceProgressReporter,
        *,
        max_points: int = DEFAULT_MAX_POINTS,
        curves: Collection[str] | None = None,
    ):
        """Build the callback over ``reporter``.

        Args:
            reporter: Transport to the Jobs service.
            max_points: Points kept on each metric curve, per path. Rejected
                below 1 up front rather than producing a curve with no points on
                it, which reads downstream as a run that never reported.
            curves: Metric names to accumulate, unqualified by phase, or None to
                accumulate every metric that arrives. The two bounds multiply --
                the stored blob is ``curves x max_points`` -- so this is the
                larger lever of the two on a backend that reports many metrics.
        """
        if max_points < 1:
            raise ValueError(f"max_points must be >= 1, got {max_points}")

        self._reporter = reporter
        self._max_points = max_points
        #: None means "everything"; a frozenset means exactly these names.
        self._curves: frozenset[str] | None = None if curves is None else frozenset(curves)
        #: Names already reported as current-value-only, so the explanation is
        #: logged once per name rather than once per step.
        self._excluded_seen: set[str] = set()
        self._closed = False

        seeded = reporter.fetch_current_metrics()

        #: True when the seed read failed outright, as opposed to finding nothing
        #: stored. The accumulator is then known to be incomplete, and because
        #: the server replaces a sent key wholesale, reporting it would overwrite
        #: the very history that could not be read. So the ``metrics`` key is
        #: withheld for the life of the process: this run's curves stall, which
        #: is recoverable, rather than every previous run's being destroyed,
        #: which is not. Current values and progress still report normally.
        self._seed_unavailable = seeded is None
        if self._seed_unavailable:
            logger.warning(
                "Could not read the stored metric series; this run will report progress and current "
                "values but will not update the accumulated curves, to avoid overwriting them."
            )

        #: series name -> [{step, epoch, value}], seeded from the server so a
        #: process taking over a task continues its curves instead of replacing
        #: them, which is what an empty accumulator would do. A seeded point that
        #: records no step is dropped here: nothing can place it on a curve, so
        #: carrying it only defers the problem to whoever reads it.
        self._series: dict[str, list[dict[str, float | int]]] = {
            name: [point for point in points if _point_step(point) is not None]
            for name, points in (seeded or {}).items()
        }

        if any(self._series.values()):
            logger.info(
                "Seeded %d metric series from server (%d points): %s",
                len(self._series),
                sum(len(points) for points in self._series.values()),
                ", ".join(sorted(self._series)),
            )

        #: One gate per reporting path, reconstructed from the seeded series so a
        #: process taking over a task continues the cadence it inherited instead
        #: of restarting at full resolution and blowing the budget on the tail of
        #: a run. See :meth:`_seed_gate` -- the seed *is* the state, so resume
        #: needs no protocol of its own.
        self._gates: dict[str, _PathGate] = {phase: self._seed_gate(phase) for phase in (TRAIN_PHASE, VAL_PHASE)}

    def _seed_gate(self, phase: str) -> _PathGate:
        """Rebuild one path's gate from the series already stored for it.

        Both pieces of state fall out of the accumulator: the last admitted step
        is the last point's, and the interval in force is the curve's own average
        spacing. Reading the interval back out of the spacing is what makes
        decimation survive a restart -- a halved curve records its doubled
        interval in its own points, so the new process does not snap back to the
        seeded cadence and re-admit at twice the intended rate.

        The *average* gap rather than the last one, because the last one is
        systematically unrepresentative: every run ends by flushing the step its
        gate withheld, which lands hard against its predecessor. A curve ending
        ``..., 19901, 20000`` was reporting every hundred steps and would read as
        every one. Averaging also survives the seeded points being a decimated
        curve, which is the case this has to get right.
        """
        points = self._anchor(phase)
        gate = _PathGate()
        if not points:
            return gate

        gate.last_admitted = _point_step(points[-1])
        if len(points) > 1:
            span = cast(float, _point_step(points[-1])) - cast(float, _point_step(points[0]))
            gate.interval = max(int(span // (len(points) - 1)), 1)
        return gate

    def _anchor(self, phase: str) -> list[dict[str, float | int]]:
        """The longest series on ``phase``, which is the one present from step one.

        A metric that only starts appearing mid-run has fewer points and a
        different first step, so it would understate both the position and the
        cadence. Ties break by name so every process reading the same blob picks
        the same anchor.
        """
        prefix = f"{phase}_"
        candidates = [(len(points), name, points) for name, points in self._series.items() if name.startswith(prefix)]
        return max(candidates, default=(0, "", []))[2]

    def _decimate(self, phase: str) -> None:
        """Halve any curve on ``phase`` that has outgrown ``max_points``.

        The backstop behind the interval seeded from ``max_steps``, and expected
        never to fire on a configuration we ship: it costs a resolution step-down
        where a wrong run length would otherwise cost an unbounded series. What it
        buys is that the guarantee stops depending on an input we do not control --
        a run that overshoots its stated length, or a backend added later whose
        schedule nobody audited.

        Every other point goes, counting back from the end so the most recent one
        is always kept: a curve may lose resolution, never its leading edge.
        Rewriting the stored series is free, the Jobs merge being wholesale per
        key -- a shorter list simply replaces the longer one.
        """
        prefix = f"{phase}_"
        trimmed = False
        for name, points in self._series.items():
            if name.startswith(prefix) and len(points) > self._max_points:
                self._series[name] = points[(len(points) - 1) % 2 :: 2]
                trimmed = True
        if trimmed:
            gate = self._gates[phase]
            gate.interval *= 2
            logger.info(
                "Halved the %s curves to stay within %d points; reporting every %d steps from here.",
                phase,
                self._max_points,
                gate.interval,
            )

    def _resolve_backend(self, backend: str | None) -> str | None:
        return backend if backend is not None else self._default_backend

    def _send(self, phase: str, details: dict[str, object], backend: str | None) -> None:
        """Stamp the backend field, if there is one, and hand the report over.

        The tail every report shares, in one place because a change to it that
        missed a copy would be close to invisible: ``_default_backend`` is
        ``None`` for two of the three backends, so only unsloth's payload would
        have shown the difference.
        """
        resolved = self._resolve_backend(backend)
        if resolved is not None:
            details["backend"] = resolved
        self._reporter.report_running(phase=phase, **details)

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

        The one path both ``report_train_step`` and ``report_validation`` take,
        for all three backends, which is why the gate lives here rather than in
        each of them. ``phase`` qualifies the series names (``train``/``val``);
        ``report_phase`` is what the Jobs service records as the task's phase.

        The append and the send are gated as one unit, deliberately. Accumulating
        every step and merely sending less often would leave the series growing
        without bound while each send carried all of it -- upload becomes
        ``reports x points`` with points unbounded, which is strictly worse than
        no throttle at all.

        A held report's values are therefore discarded rather than delayed, and
        that includes the current-value scalars, so ``percentage_done`` moves at
        the gated cadence too. Splitting the two -- scalars often, curves rarely --
        does not help while the curves live in ``status_details``: the two
        server-side writes carry the whole blob regardless of what the report
        said, so a scalar-only report costs almost exactly what a full one costs.
        Measured at 108 bytes of payload against a 282 KB stored series: 111ms,
        against 58ms at 46 KB stored. The payload was identical; only the blob it
        did not send had grown.
        """
        qualified = _qualify_metric_names(phase, metrics)
        recorded = self._curve_subset(phase, qualified)
        gate = self._gates[phase]
        if not gate.admit(step):
            gate.pending = {
                "phase": phase,
                "report_phase": report_phase,
                "step": step,
                "epoch": epoch,
                "qualified": qualified,
                "recorded": recorded,
                "backend": backend,
            }
            return
        self._record_and_send(phase, report_phase, step, epoch, qualified, recorded, backend)

    def _curve_subset(self, phase: str, qualified: dict[str, float | int]) -> dict[str, float | int]:
        """The entries of ``qualified`` that get a stored series, not just a value.

        The other bound on the payload, and on most backends the larger one: it
        is ``curves x max_points`` that is stored, and a backend reporting twenty
        metrics spends most of that on curves nobody reads. Throughput and
        accounting counters -- ``tps``, ``mem``, ``num_label_tokens``,
        ``global_valid_toks`` -- are worth a number on a status page and not two
        hundred stored points each.

        Excluding a metric costs its history, never its visibility: every
        chartable metric is still reported as a current value on every admitted
        report. That is the distinction that makes this safe where the old
        report-time allow-list was not -- that one dropped metrics outright, and
        DPO's ``accuracy``, ``sft_loss`` and ``rewards_chosen_mean`` went missing
        for a release because nobody had added them to it. Here the same omission
        costs a chart, and says so in the log.

        Names are matched unqualified, so ``loss`` covers ``train_loss`` and
        ``val_loss`` both. One consequence worth knowing: NeMo-RL's logger folds
        the dataloader name into the metric names of every validation set past
        the first, so a second validation set's ``loss`` arrives as
        ``<dataset>_loss`` and needs that spelling in ``curves`` to be charted.
        The first set -- the only one any config we compile produces -- keeps the
        bare names.
        """
        if self._curves is None:
            return qualified

        bare = len(phase) + 1
        keep = {name: value for name, value in qualified.items() if name[bare:] in self._curves}

        dropped = sorted({name[bare:] for name in qualified} - self._curves - self._excluded_seen)
        if dropped:
            self._excluded_seen.update(dropped)
            logger.info(
                "Reporting as current values only, with no stored curve: %s. Charting: %s. "
                "Add a name to progress_reporting.curves to chart it too.",
                ", ".join(dropped),
                ", ".join(sorted(self._curves)) or "(nothing)",
            )
        return keep

    def _record_and_send(
        self,
        phase: str,
        report_phase: str,
        step: int,
        epoch: int,
        qualified: dict[str, float | int],
        recorded: dict[str, float | int],
        backend: str | None,
        decimate: bool = True,
    ) -> None:
        """Append an admitted report's points and put it on the wire.

        ``qualified`` is every chartable metric and becomes the current values;
        ``recorded`` is the subset that also gets a stored point. They are the
        same dict unless ``curves`` narrows it.

        ``decimate`` is False only for the tail flushed by ``close()``. A run
        whose length divides evenly lands exactly ``max_points`` admissions and
        then flushes one more, and decimating on that last append would halve the
        finished curve -- a 20,000-step run at a budget of 200 would store 101
        points, having reported 200, purely because its final step did not fall on
        an interval. Since nothing follows the flush, letting the curve close one
        point over budget costs a single point and keeps the resolution that was
        asked for.
        """
        for name, value in recorded.items():
            self._series.setdefault(name, []).append({"step": step, "epoch": epoch, "value": value})
        if recorded and decimate:
            self._decimate(phase)

        details: dict[str, object] = {
            "step": step,
            "epoch": epoch,
            **qualified,
        }
        # Sent in full or not at all, so a report that added no point has nothing
        # to say about the curves: the stored copy already matches, and the merge
        # leaves a key that is not mentioned standing. A report whose metrics are
        # all current-value-only lands here too, and correctly says nothing.
        if not self._seed_unavailable and recorded:
            details["metrics"] = self._build_metrics_summary()
        # Both retired here rather than by the caller, so that a flushed report
        # leaves the same state an admitted one does: anything the gate was
        # holding is now stale, superseded by a report that actually landed, and
        # this step is the one the next elapsed check measures from.
        gate = self._gates[phase]
        gate.pending = None
        gate.last_admitted = step
        self._send(report_phase, details, backend)

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
        to add to the curves, and sending the empty accumulator would replace the
        stored series with two empty lists.

        Carries no ``step`` either, for the same reason one level along.
        ``report_running`` turns a stated step into ``percentage_done``, and the
        merge is wholesale per key, so a literal 0 here overwrites whatever
        progress the task had stored -- in a field harder to spot than the series,
        because the epoch beside it is not restated and goes on reading
        correctly. Nothing has happened yet that this could truthfully report, so
        it says nothing and lets the first train step state the position.

        It is also where the reporting cadence is set, which is why it matters
        that all three backends call it before their first metric report --
        NeMo-RL via ``log_hyperparams``, automodel from the recipe wrapper,
        unsloth from ``on_train_begin``.
        """
        self._reporter.configure_progress_tracking(max_steps, num_epochs)
        self._configure_cadence(max_steps)
        details: dict[str, object] = {
            "max_steps": max_steps,
            "num_epochs": num_epochs,
        }
        self._send("training", details, backend)

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

        Taken as a dict rather than ``**kwargs`` so that the metric names and this
        method's own parameters cannot collide. Backends forward whatever their
        framework emits, and a framework is free to call something ``step``.
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
        self._send("checkpoint_saved", details, backend)

    def report_epoch_end(self, step: int, epoch: int, *, backend: str | None = None) -> None:
        """Report that an epoch has completed."""
        details: dict[str, object] = {
            "step": step,
            "epoch": epoch,
        }
        self._send("epoch_end", details, backend)

    def _configure_cadence(self, max_steps: int) -> None:
        """Set each path's interval from the run length.

        ``ceil(max_steps / max_points)`` on the train path, which is the whole
        input: how often someone wants the curve and the progress bar to move is
        unrelated to how often the run validates.

        The validation path gets the same seed rather than a pass count of its
        own. It is deliberately a lower bound and not an estimate -- validation
        passes are always at least a step apart, so a run whose passes are rarer
        than this simply reports all of them, and one that validates every step
        is thinned to the same budget as training. Nothing here needs the
        validation cadence plumbed through to be correct; stating it would only
        let the seed start closer to the answer, and ``_decimate`` closes the gap
        either way.

        Raised, never lowered: a gate seeded from stored points is already
        reporting at a cadence a previous process settled on, possibly after
        decimation, and dropping back to a finer one would re-admit at twice the
        intended rate for the rest of the run.
        """
        seeded = max((max(max_steps, 0) + self._max_points - 1) // self._max_points, 1)
        for gate in self._gates.values():
            gate.interval = max(gate.interval, seeded)

    def close(self) -> None:
        """Flush whatever the gates withheld, then clean up resources.

        Idempotent: NeMo-RL reaches this from a driver ``finally``, from the
        composite logger's ``finish()`` and from ``__del__``, and a second flush
        would append the final step twice.
        """
        if self._closed:
            return
        self._closed = True
        self._flush_pending()
        self._reporter.close()

    def _flush_pending(self) -> None:
        """Report the last step each gate held back, oldest first.

        Without this a throttled run ends on stale values: the final train step
        and the final validation pass rarely land on an interval, so the last
        thing a reader sees is whenever the cadence last happened to fire.

        Step order so points are appended in the order they were produced, rather
        than in whichever order the paths happen to iterate.

        Reachable from a shutdown path, so failures are logged rather than
        propagated -- the reporter already swallows transport errors, and this
        guards the rest.
        """
        held = sorted(
            (gate.pending for gate in self._gates.values() if gate.pending is not None),
            key=lambda report: report["step"],
        )
        for report in held:
            gate = self._gates[report["phase"]]
            gate.pending = None
            # Defensive against a double flush: a report admitted after this one
            # was held would already have retired it, so this can only fire if
            # something replayed the flush.
            if gate.last_admitted is not None and report["step"] <= gate.last_admitted:
                continue
            try:
                self._record_and_send(
                    report["phase"],
                    report["report_phase"],
                    report["step"],
                    report["epoch"],
                    report["qualified"],
                    report["recorded"],
                    report["backend"],
                    decimate=False,
                )
            except Exception as exc:  # pragma: no cover - defensive, shutdown path
                logger.warning(f"Failed to flush the final {report['phase']} report: {exc}")
