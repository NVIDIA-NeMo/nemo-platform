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

Payload size, and whose problem it is
-------------------------------------
Every series is resent in full on every train and validation report, so the
stored blob grows as ``series x reports`` and the cost as the square of it.

One report costs three writes, not one. The client sends it; ``JobDispatcher``
persists it to the task (``dispatcher.py:1217-1224``) and propagates a copy to the
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

**This class does not throttle, deliberately.** It records and sends whatever
the training library hands it, at whatever cadence the library logs. An earlier
version bounded the stored points per curve, thinning older points to stay
inside a budget; it was removed. The reasons are worth keeping, because the
temptation to put it back will recur:

- It bought less than it looked like. Every real customization job measured ran
  between 12 and 594 steps, and every Automodel contract fixture caps at 50. At
  that scale the cap never binds, and what it did bind it thinned.
- It cost full-resolution curves -- the thing a user actually wants -- to save
  a fraction of a megabyte.
- It was a workaround for someone else's design. The quadratic is entirely a
  property of ``status_details`` being a blob that is replaced wholesale and
  written three times. Capping points here made that cheaper to leave unfixed.
- The complexity was where the bugs were. Four data-loss defects were found in
  the throttling machinery and none in accumulation or reporting.

What remains true is the cost model above, and it is the Jobs service's to
solve: the curves want to live somewhere that appends rather than replaces.
Until they do, a long run is expensive, and that expense is now visible instead
of hidden behind a cap. Verified against a live platform: a 20,000-step run at
14 series stores an 11.9 MB blob and writes it in ~2s, well inside what the
entity store accepts.

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
import time
from collections.abc import Callable, Collection, Mapping
from fnmatch import fnmatchcase
from typing import Any, ClassVar, cast

from nmp.customization_common.training.progress import JobsServiceProgressReporter
from nmp.customization_common.training.reporting import ALL_METRICS, DEFAULT_MIN_REPORT_INTERVAL_SECONDS

logger = logging.getLogger(__name__)

__all__ = ["DatasetQualifier", "ReportRateLimiter", "TrainingProgressCallback", "is_chartable"]


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


class DatasetQualifier:
    """Fold a dataset's name into its metric names, past the first dataset seen.

    Both LLM backends validate over a *dict* of dataloaders and log once per
    entry, every call at the same step: NeMo-RL over ``val_dataloader.items()``,
    automodel over ``val_dataloaders``. Forwarded as-is, two datasets' ``loss``
    become two points at one step in a single ``val_loss`` series -- the
    collision the ``<phase>_`` rule exists to prevent, one level further down,
    and an invisible one because Studio keys its chart by step so one silently
    wins.

    The first dataset seen keeps the bare names, so ``val_loss`` stays
    ``val_loss`` on the ordinary single-dataset run; both frameworks name that
    dataloader too, so keying on "did a name arrive" would rename the common case
    and take Studio's curve with it. Iteration order over a dict is stable within
    a run and across a resume of the same config, so a dataset keeps whichever
    naming it started with.

    Shared because it was implemented for one backend and not the other, and the
    absence was silent: automodel's wrapper discarded the ``val_name`` its recipe
    passes, so every dataloader reported as ``val_loss``.
    """

    def __init__(self) -> None:
        self._primary: str | None = None

    def qualify(self, key: str, label: str, metrics: Mapping[str, Any]) -> dict[str, Any]:
        """Qualify ``metrics`` for the dataset identified by ``key``.

        ``key`` identifies the dataset (whatever the backend has to hand -- a
        prefix, a name); ``label`` is what gets folded into the metric names.
        They differ for NeMo-RL, whose key is the whole ``validation-<name>``
        prefix while only ``<name>`` belongs in the series.
        """
        if self._primary is None:
            self._primary = key
        if key == self._primary:
            return dict(metrics)
        return {f"{label}_{name}": value for name, value in metrics.items()}


def _clean_patterns(patterns: Collection[str] | None) -> tuple[str, ...]:
    """Normalise a configured pattern list into something safe to match against.

    Every value here has come off a config file, and on the NeMo-RL path it
    reaches us straight out of a YAML with no schema in between. Matching runs
    inline in a training step, so anything unusable has to be handled now rather
    than raise from inside :func:`fnmatch.fnmatchcase` and take the run with it:
    a ``None`` in the list used to surface as ``TypeError: object of type
    'NoneType' has no len()`` out of ``report_train_step``.

    A bare string is the other trap, and the quieter one. ``str`` satisfies
    ``Collection[str]`` as a collection of its *characters*, so
    ``time_series_metrics: train_loss`` in YAML became the ten patterns ``t``,
    ``r``, ``a``, ... which match nothing at all -- a run that records no history
    and reports no error. There is only one thing it can have meant, so it is
    read as a single pattern.

    An empty result from a non-empty input means every entry was unusable, which
    is a broken config rather than a request for no history; that falls back to
    recording everything, on the principle that a misconfiguration should cost
    noise rather than data. An input that was *already* empty is left alone --
    ``[]`` legitimately means "no series at all".
    """
    if patterns is None:
        return ALL_METRICS
    if isinstance(patterns, str):
        return (patterns,)

    try:
        given = tuple(patterns)
    except TypeError:
        logger.warning(f"progress_reporting.time_series_metrics is not a list ({patterns!r}); recording every metric.")
        return ALL_METRICS

    usable = tuple(pattern for pattern in given if isinstance(pattern, str))
    unusable = [pattern for pattern in given if not isinstance(pattern, str)]
    if unusable:
        logger.warning(
            f"Ignoring {len(unusable)} non-string entr{'y' if len(unusable) == 1 else 'ies'} in "
            f"progress_reporting.time_series_metrics: {unusable!r}."
        )
    if given and not usable:
        logger.warning("No usable entry in progress_reporting.time_series_metrics; recording every metric.")
        return ALL_METRICS
    return usable


class ReportRateLimiter:
    """Decides when a metric report may go on the wire.

    Points are never at stake here. Every metric a backend reports is recorded
    into the accumulator the moment it arrives; this only decides how often that
    accumulator is *sent*, and a report it withholds loses nothing because its
    points ship with the next one. That is the whole difference from the
    point-capping this replaced, which discarded data to stay inside a budget and
    needed decimation, seed reconstruction and per-dataloader bookkeeping to do
    it.

    What it buys is real but bounded, and worth stating so nobody expects more:
    on a 594-step run over half an hour it takes 594 requests down to 180 and the
    time blocked inside the training loop from 36s to 11s. It does *not* bound a
    long run. The cost of one request grows with the accumulated blob, so an
    11-hour run still spends tens of minutes reporting however this is tuned --
    and no rate limit can fix that, because the payload is what is growing. That
    ceiling belongs to the transport; see the payload note in the module
    docstring.

    ``monotonic`` rather than wall-clock time: a training process outlives NTP
    corrections, and a clock stepping backwards would stall reporting until it
    caught up.
    """

    def __init__(
        self,
        min_interval_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        #: Negative is meaningless and would make every check pass; clamp rather
        #: than raise, since this arrives from a job config and a reporting knob
        #: must not be able to stop a run from starting.
        self._min_interval = max(float(min_interval_seconds), 0.0)
        self._clock = clock
        self._last_sent: float | None = None

    def allow_request(self) -> bool:
        """Whether to send now, recording the send if so.

        The first call always allows: a curve should start at the beginning of
        the run rather than one interval into it, and the progress bar should
        move as soon as there is something to say.
        """
        now = self._clock()
        if self._last_sent is not None and now - self._last_sent < self._min_interval:
            return False
        self._last_sent = now
        return True


class TrainingProgressCallback:
    """Report training progress to the Jobs service."""

    #: Backend name stamped on each report when a per-call ``backend`` isn't given.
    #: ``None`` means no ``backend`` field is added.
    _default_backend: ClassVar[str | None] = None

    def __init__(
        self,
        reporter: JobsServiceProgressReporter,
        *,
        time_series_metrics: Collection[str] | None = None,
        min_report_interval_seconds: float = DEFAULT_MIN_REPORT_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        """Build the callback over ``reporter``.

        Args:
            reporter: Transport to the Jobs service.
            time_series_metrics: Qualified metric names or glob patterns to
                accumulate, or None for all of them.
            min_report_interval_seconds: Least time between metric reports going
                on the wire. 0 sends every one. Points are recorded regardless.
            clock: Monotonic time source, injectable so the limiter can be tested
                without sleeping.
        """
        self._reporter = reporter
        self._limiter = ReportRateLimiter(min_report_interval_seconds, clock)
        #: The most recent report the limiter withheld, replayed by ``close()``
        #: so a run ends on its real final values rather than on whenever the
        #: limiter last let one through.
        self._pending_metrics: tuple[str, int, int, dict[str, float | int], str | None] | None = None
        #: Whether any point has been recorded since the last send, which is what
        #: decides whether the next report needs to carry the series at all.
        self._unsent_points = False
        #: Normalised to patterns so there is one code path: None becomes "*",
        #: which is what it already meant. An empty list stays empty and records
        #: nothing, which is a different and equally legitimate request. See
        #: :func:`_clean_patterns` for what else has to be normalised out.
        self._time_series_metrics: tuple[str, ...] = _clean_patterns(time_series_metrics)
        #: Names already reported as current-value-only, so the explanation is
        #: logged once per name rather than once per step.
        self._excluded_seen: set[str] = set()
        #: Every qualified name this run has reported, matched or not. Distinct
        #: from ``_excluded_seen``, and the distinction matters: "did any metric
        #: arrive" is what decides whether an unmatched pattern is worth warning
        #: about, and asking ``_excluded_seen`` instead answered "did any metric
        #: arrive *and fail to match*" -- false exactly when every metric matched
        #: something, which is the common case a typo has to be caught in.
        self._metrics_seen: set[str] = set()
        #: Patterns that have selected at least one metric, so close() can name
        #: the ones that never did.
        self._patterns_matched: set[str] = set()
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
        for all three backends. ``phase`` qualifies the series names
        (``train``/``val``); ``report_phase`` is what the Jobs service records as
        the task's phase.

        Every report a backend makes is *recorded*; the rate limiter decides only
        which of them are *sent*. Nothing is discarded either way -- a withheld
        report's points are already on their curves and ship with the next
        request -- which is what separates this from the point cap it replaced.

        The payload is built at send time rather than at record time, so a
        withheld report costs a dict of scalars rather than a copy of every
        series. On a long run most reports are withheld.
        """
        qualified = _qualify_metric_names(phase, metrics)
        recorded = self._time_series_subset(qualified)
        for name, value in recorded.items():
            self._series.setdefault(name, []).append({"step": step, "epoch": epoch, "value": value})
        if recorded:
            self._unsent_points = True

        pending = (report_phase, step, epoch, qualified, backend)
        if self._limiter.allow_request():
            self._send_metrics(pending)
        else:
            # Superseded wholesale, and safely: the only thing a dropped pending
            # report loses is its own scalars, and the newer one that replaced it
            # carries fresher ones. The points it recorded are not in here.
            self._pending_metrics = pending

    def _send_metrics(self, pending: tuple[str, int, int, dict[str, float | int], str | None]) -> None:
        """Build and send one metric report, clearing what it supersedes."""
        report_phase, step, epoch, qualified, backend = pending
        details: dict[str, object] = {
            "step": step,
            "epoch": epoch,
            **qualified,
        }
        # Sent in full or not at all, so a report with no new point has nothing
        # to say about the curves: the stored copy already matches, and the merge
        # leaves a key that is not mentioned standing.
        #
        # Keyed on whether anything has been recorded *since the last send*, not
        # on what this particular report added. Under a rate limit those differ:
        # the report that happens to pass the limiter may itself be all
        # current-value-only while several withheld before it added points, and
        # asking only about this one would strand them until the next.
        if not self._seed_unavailable and self._unsent_points:
            details["metrics"] = self._build_metrics_summary()
        self._pending_metrics = None
        self._unsent_points = False
        self._send(report_phase, details, backend)

    def _time_series_subset(self, qualified: dict[str, float | int]) -> dict[str, float | int]:
        """The entries of ``qualified`` that get a stored series, not just a value.

        The one bound on the payload this class still applies, and the one that
        is a data-modelling choice rather than a workaround: a backend reporting
        twenty metrics spends most of the blob on histories nobody reads. Throughput and
        accounting counters -- ``tps``, ``mem``, ``num_label_tokens``,
        ``global_valid_toks`` -- are worth a number on a status page and not two
        hundred stored points each.

        Leaving a metric out costs its history, never its visibility: every
        chartable metric is still reported as a current value on every admitted
        report. That is the distinction that makes this safe where the old
        report-time allow-list was not -- that one dropped metrics outright, and
        DPO's ``accuracy``, ``sft_loss`` and ``rewards_chosen_mean`` went missing
        for a release because nobody had added them to it. Here the same omission
        costs a chart, and says so in the log.

        Patterns match the **qualified** name, the one that appears in
        ``status_details``, so what a user writes is what they read back. Globs
        via :func:`fnmatch.fnmatchcase` -- ``fnmatchcase`` and not ``fnmatch``,
        which applies ``os.path.normcase`` and would therefore match
        case-insensitively on some platforms and not others.

        Matching the qualified name is what makes NeMo-RL's second validation set
        expressible: its logger folds the dataloader name in, so that set's loss
        arrives as ``val_heldout_loss``, which no unqualified spelling could
        reach and which ``*_loss`` covers without knowing the dataset's name.
        """
        keep: dict[str, float | int] = {}
        dropped: list[str] = []
        self._metrics_seen.update(qualified)
        for name, value in qualified.items():
            matched = [p for p in self._time_series_metrics if fnmatchcase(name, p)]
            if matched:
                keep[name] = value
                self._patterns_matched.update(matched)
            else:
                dropped.append(name)

        unseen = sorted(set(dropped) - self._excluded_seen)
        if unseen:
            self._excluded_seen.update(unseen)
            logger.info(
                "Reporting as current values only, with no stored history: %s. Recording a series "
                "for anything matching: %s. Add a name or pattern to "
                "progress_reporting.time_series_metrics to record one of these too.",
                ", ".join(unseen),
                ", ".join(self._time_series_metrics) or "(nothing)",
            )
        return keep

    def _warn_on_patterns_that_matched_nothing(self) -> None:
        """Say so when a configured pattern never matched a metric that arrived.

        The failure this catches is a misspelling, and the likeliest one is an
        unqualified name: ``loss`` selects nothing, because the metric is
        ``train_loss``. Without this the run reports no history for it and looks
        exactly like a run that was configured not to.

        Left to ``close()`` rather than checked up front, because a name that has
        not arrived yet is not yet wrong -- backends omit metrics on some steps,
        and validation names do not appear until the first pass.

        Gated on whether *any* metric arrived, not on whether any was excluded.
        Those differ precisely when every metric that arrived matched something,
        which is the ordinary case and therefore the one a typo has to be caught
        in: ``["*_loss", "val_accuarcy"]`` against a run that reports only a loss
        has nothing excluded, and the misspelling used to pass in silence.
        """
        unmatched = [p for p in self._time_series_metrics if p not in self._patterns_matched]
        if not unmatched or not self._metrics_seen:
            # No metric arrived at all: every pattern trivially matched nothing,
            # and the run reporting nothing is the larger problem to look at.
            return
        logger.warning(
            "These progress_reporting.time_series_metrics entries matched no metric this run: %s. "
            "Names are qualified by phase, so 'loss' matches nothing and 'train_loss', 'val_loss' "
            "or '*_loss' is meant. Metrics this run reported: %s.",
            ", ".join(unmatched),
            ", ".join(sorted(self._metrics_seen)),
        )

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
        """
        self._reporter.configure_progress_tracking(max_steps, num_epochs)
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

    def close(self) -> None:
        """Flush whatever the gates withheld, then clean up resources.

        Idempotent: NeMo-RL reaches this from a driver ``finally``, from the
        composite logger's ``finish()`` and from ``__del__``, and a second flush
        would append the final step twice.
        """
        if self._closed:
            return
        self._closed = True
        if self._pending_metrics is not None:
            # Load-bearing for data, not only for freshness: the points recorded
            # since the last send exist nowhere but this process until something
            # carries them.
            try:
                self._send_metrics(self._pending_metrics)
            except Exception as exc:  # pragma: no cover - defensive, shutdown path
                logger.warning(f"Failed to send the final metric report: {exc}")
        self._warn_on_patterns_that_matched_nothing()
        self._reporter.close()
