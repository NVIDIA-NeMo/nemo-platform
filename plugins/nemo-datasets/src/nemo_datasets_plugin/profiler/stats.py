# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Per-column statistics and content probes.

Given a partition's features and its rows, :func:`measure_columns` measures each top-level column
according to its dtype: length quantiles for text, min/max/mean for numbers,
chat-shape signals for messages, and a bounded vocabulary where the column has one. The result is
sparse — a column with nothing worth measuring is omitted — and each column is isolated, so one the
detectors cannot handle costs only itself. Row values themselves are never stored here at all; a
small controlled vocabulary is added afterwards by :func:`quote_enumerations`, which gates on role.

The same pass reads each column's *content* — answer markers, embedded transcripts — as plain
per-column counts (:class:`ColumnProbes`). Those are measurements, not interpretations: what they
mean is classification's job, and keeping the looking here is what stops a content signal from being
reachable only through a correctly named column.

The measuring itself is done by a :class:`ColumnAccumulator` per column, chosen once on dtype. An
accumulator folds batches in and keeps no reference to them, so a column measured in pieces gives
the same answer as one measured whole — the property that lets a caller stop materialising a
partition before it can measure it. The base class is the entire measurement for a dtype with no
statistics of its own, because the probes run over every column whatever its type.

Every measurement is O(1) in rows and exact in what it counts, and nothing is retained: a column's
values are folded in and let go. The one estimate left is :class:`Quantiles`, which reads its
percentiles off bucketed counters rather than off the lengths themselves -- see
:class:`_LengthHistogram` for the bound that buys.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from nemo_datasets_plugin.profiler.schema import MAX_COLUMNS, SchemaFold
from nemo_platform_plugin.files.dataset_profile import (
    CategoricalStats,
    ColumnStats,
    Evidence,
    FeatureSchema,
    MessageStats,
    NumericStats,
    Quantiles,
    TextStats,
)

# A quotable enumeration holds at most this many distinct values.
_MAX_ENUM_VALUES = 32

# Where a column stops being a plausible controlled vocabulary, and so stops being worth counting.
# Three bounds because a count alone bounds cardinality but not bytes -- 1024 reasoning traces is
# 32 MB. `_MAX_VOCABULARY_VALUE_CHARS` is the one that matters most: it is a claim about what the
# column *is* rather than how big it is, so it settles a free-text column on the first value instead
# of after a thousand. Sized well above real vocabularies -- a `source` column spanning 500 datasets,
# a 200-class label set -- and far below anything that costs memory.
_MAX_VOCABULARY_VALUES = 1024
_MAX_VOCABULARY_VALUE_CHARS = 256
_MAX_VOCABULARY_BYTES = 64 * 1024
# What a non-string distinct value is charged against the byte bound. Ints and bools are small and
# uniform, so an exact size buys nothing the count bound does not already give.
_NON_STRING_VALUE_BYTES = 8

# Roles that are controlled vocabularies by construction, and so are safe to quote at any dataset
# size. Everything else -- prompts, completions, chosen/rejected, context, chat -- is free text no
# matter how few distinct values a small sample happens to show, and unroled columns are unknown,
# which is the same thing for this purpose. An allowlist, so an unrecognized column fails to silence
# rather than to exposure.
_QUOTABLE_ROLES = frozenset({"label", "provenance", "meta", "rank"})


@dataclass(frozen=True)
class ColumnMeasurements:
    """Everything one pass over a partition's columns produced.

    A named result rather than a tuple because the vocabularies joined it: they are not part of the
    stored profile, but :func:`quote_enumerations` needs them and can no longer go back to the rows
    for them.
    """

    stats: dict[str, ColumnStats]
    probes: dict[str, ColumnProbes]
    vocabularies: dict[str, set[Any]]  # name -> distinct values, only where the column stayed one
    errors: list[Evidence]


class RowFold:
    """The per-column accumulators for one partition, fed batch by batch.

    Each column is isolated. A value no detector anticipated -- a chat message whose ``role`` is a
    number, a float where a string was declared -- costs that column its measurements and nothing
    else, where previously it cost the partition every measurement it had. The failure is reported
    as an ``error`` evidence rather than left as a silent gap, because a column absent from ``stats``
    is otherwise indistinguishable from one that simply had nothing worth measuring. It is caught per
    column *per batch*, so a bad row in the middle of a file cannot take the rest of the file with it.

    This is the narrow half of the two guards the profiler runs. The wide one still wraps the whole
    measure stage, and still catches anything structural -- schema derivation, classification -- that
    is not attributable to a single column.

    Statistics and probes are folded together because they read the same values, and extracting a
    column out of a batch costs more than either measurement. Neither fills in
    ``categorical.values``: that needs the roles, which classification has not assigned yet, so
    :func:`quote_enumerations` adds them afterwards, from the vocabulary this kept.
    """

    def __init__(self, features: list[FeatureSchema]) -> None:
        self._accumulators: dict[str, ColumnAccumulator] = {}
        self._features: list[FeatureSchema] = []
        self._failed: dict[str, Evidence] = {}
        for feature in features:
            # Parquet permits duplicate field names, and every map here is keyed by name. Measuring
            # the first and skipping the rest makes which one wins deterministic instead of
            # "whichever came last", and keeps stats and probes agreeing on the same one.
            if feature.name in self._accumulators:
                continue
            self._accumulators[feature.name] = _accumulator_for(feature)
            self._features.append(feature)

    def update(self, rows: list[dict[str, Any]]) -> None:
        """Fold one batch of rows into every column's accumulator."""
        for feature in self._features:
            if feature.name in self._failed:
                continue
            try:
                self._accumulators[feature.name].update([row.get(feature.name) for row in rows])
            except Exception as exc:
                self._failed[feature.name] = Evidence(
                    kind="error",
                    detail=(
                        f"column {feature.name!r} ({feature.dtype}) could not be measured: {type(exc).__name__}: {exc}"
                    ),
                )

    def finalize(self) -> tuple[list[FeatureSchema], ColumnMeasurements]:
        """The schema that was measured, and the measurements.

        The features come back rather than being assumed from what was handed in, because they are
        not the same list: duplicate names were dropped in the constructor, so a caller holding its
        own copy would describe a column that no accumulator ever measured. Returning the same pair
        :meth:`InferredRowFold.finalize` does also spares the caller an ``isinstance`` to find out
        which of the two it is holding.
        """
        stats: dict[str, ColumnStats] = {}
        probes: dict[str, ColumnProbes] = {}
        vocabularies: dict[str, set[Any]] = {}
        errors: list[Evidence] = []
        for feature in self._features:
            failure = self._failed.get(feature.name)
            if failure is not None:
                errors.append(failure)
                continue
            accumulator = self._accumulators[feature.name]
            try:
                column, probe = accumulator.finalize()
            except Exception as exc:
                errors.append(
                    Evidence(
                        kind="error",
                        detail=(
                            f"column {feature.name!r} ({feature.dtype}) could not be summarised: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    )
                )
                continue
            probes[feature.name] = probe
            vocabulary = accumulator.vocabulary()
            if vocabulary is not None:
                vocabularies[feature.name] = vocabulary
            if column is not None:
                stats[feature.name] = column
        return self._features, ColumnMeasurements(stats=stats, probes=probes, vocabularies=vocabularies, errors=errors)


def measure_columns(features: list[FeatureSchema], rows: list[dict[str, Any]]) -> ColumnMeasurements:
    """Measure every top-level column over rows already in hand.

    The whole partition as a single batch. :class:`RowFold` is the same measurement taken as the
    rows arrive; this is the shape for a caller that has them all anyway.
    """
    fold = RowFold(features)
    fold.update(rows)
    _, measured = fold.finalize()
    return measured


def quote_enumerations(
    features: list[FeatureSchema], stats: dict[str, ColumnStats], vocabularies: dict[str, set[Any]]
) -> None:
    """Fill in ``categorical.values`` for columns whose role makes them a controlled vocabulary.

    Runs after classification, because it needs the roles it gates on, and mutates ``stats`` in place
    the way classification mutates ``features``. Deliberately fills in rather than redacting: skip
    this pass and no values are stored, where a redaction pass that got skipped would leak them.

    Reads what the accumulators already kept rather than going back to the rows. That second pass
    was the last thing tying the measure stage to a materialised partition, and it was re-deriving a
    set the vocabulary had built and thrown away.

    Cardinality is only the size bound. It cannot be the permission, because it inverts on small
    data -- in a three-row dataset every column holds under 32 distinct values, free text included,
    so an entire column of prompts was quotable. The role says what a column *is*, at any size.
    """
    for feature in features:
        if feature.semantic_role not in _QUOTABLE_ROLES:
            continue
        column = stats.get(feature.name)
        if column is None or column.categorical is None or column.categorical.distinct_count > _MAX_ENUM_VALUES:
            continue
        values = vocabularies.get(feature.name)
        if values is None:
            continue
        column.categorical.values = sorted(str(value) for value in values)


class ColumnAccumulator:
    """Measures one top-level column, over however many batches it is handed.

    ``update`` folds a batch in and keeps no reference to it; ``finalize`` turns what was folded into
    the stored blocks. Splitting a column across calls gives the same answer as one call with all of
    it, which is the property that lets the caller stop materialising a partition before measuring it.

    The base class is the whole measurement for a dtype with no statistics of its own — a struct, a
    list, anything the dispatch does not recognise — because the content probes run over every column
    regardless of type. Subclasses add their dtype's state by overriding ``_observe`` and ``_blocks``.
    """

    def __init__(self) -> None:
        self.rows = 0
        self._nulls = 0
        self._non_empty = 0
        self._texts = 0
        self._extractable_answer = 0
        self._transcript_marker = 0

    def update(self, values: list[Any]) -> None:
        """Fold one batch of this column's values in, one entry per row."""
        present: list[Any] = []
        for value in values:
            self.rows += 1
            if value is None:
                self._nulls += 1
            else:
                present.append(value)
                if value not in ("", [], {}):
                    self._non_empty += 1
            text = _probe_text(value)
            if text is not None:
                self._texts += 1
                if _GSM8K_ANSWER.search(text) or _BOXED_ANSWER.search(text):
                    self._extractable_answer += 1
                if _TRANSCRIPT_MARKER.search(text):
                    self._transcript_marker += 1
        self._observe(present)

    def finalize(self) -> tuple[ColumnStats | None, ColumnProbes]:
        """The column's stored measurements, and its probe counts.

        Stats are None when there was nothing worth measuring, which keeps the map sparse. Probes are
        always returned: a column of nothing is a finding classification is entitled to read.
        """
        blocks = self._blocks()
        null_rate = self._nulls / self.rows if self.rows else 0.0
        column = ColumnStats(null_rate=null_rate, **blocks)
        if not any(blocks.values()) and null_rate == 0.0:
            column = None
        return column, ColumnProbes(
            rows=self.rows,
            non_empty=self._non_empty,
            texts=self._texts,
            extractable_answer=self._extractable_answer,
            transcript_marker=self._transcript_marker,
        )

    def _observe(self, present: list[Any]) -> None:
        """Fold this batch's non-null values into the dtype's own state. The base column has none."""

    def _blocks(self) -> dict[str, Any]:
        """The dtype-specific ``ColumnStats`` blocks. The base column contributes none."""
        return {}

    def backfill_nulls(self, count: int) -> None:
        """Charge this column ``count`` rows in which it was absent.

        A column that first appears in the fiftieth batch was null for every row before it, which is
        exactly what a materialising reader computes with ``row.get(name)``. Counted rather than fed
        as values, so discovering a column late costs a pair of additions and not a pass.
        """
        self.rows += count
        self._nulls += count

    def vocabulary(self) -> set[Any] | None:
        """The distinct values, for a column that is a bounded vocabulary. None for one that is not,
        which is every dtype without a notion of cardinality."""
        return None


class _Vocabulary:
    """Distinct values, for as long as the column still looks like a controlled vocabulary.

    Stops the moment it stops looking like one and drops what it had, which is the whole point:
    counting distinct values exactly means *retaining* them, so on a free-text column this set grows
    to hold the column. Today that costs little, because the rows are held anyway and the set stores
    pointers into them -- 2.6 MB beside 61.4 MB of resident rows. It is the fold this is becoming
    that makes it matter: once a batch is folded and discarded, this set is the *sole owner* of every
    value it kept, and two text columns cost 46.8 MB against 0.163 MB for every other accumulator
    combined. Unbounded, it is the one thing that would make the fold O(rows) again.

    Three bounds rather than one. A count alone bounds cardinality but not bytes, and 1024 reasoning
    traces is 32 MB. The middle bound does the real work: it asks what the column *is* rather than
    how many values it holds, in the same way the role gate on quoting does. A vocabulary member is
    short by nature, so a single long value settles the question on sight, which is why free-text
    columns stop here almost immediately instead of after 1024 values.

    The values themselves are never handed out here. They are row content, gated on role rather than
    on size, and :func:`quote_enumerations` adds them once classification has assigned one.
    """

    def __init__(self) -> None:
        self._values: set[Any] = set()
        self._bytes = 0
        self._saturated = False

    def update(self, present: list[Any]) -> None:
        if self._saturated:
            return
        for value in present:
            if isinstance(value, str) and len(value) > _MAX_VOCABULARY_VALUE_CHARS:
                return self._saturate()
            try:
                if value in self._values:
                    continue
                self._values.add(value)
            except TypeError:
                return self._saturate()  # unhashable values (dicts / lists) have no cardinality signal
            self._bytes += len(value) if isinstance(value, str) else _NON_STRING_VALUE_BYTES
            if len(self._values) > _MAX_VOCABULARY_VALUES or self._bytes > _MAX_VOCABULARY_BYTES:
                return self._saturate()

    def _saturate(self) -> None:
        self._values = set()  # release what was held; holding it is the cost this bound exists to cap
        self._saturated = True

    def finalize(self) -> CategoricalStats | None:
        return None if self._saturated else CategoricalStats(distinct_count=len(self._values))

    def values(self) -> set[Any] | None:
        """What was kept, or None once the column stopped being a vocabulary.

        Handing this out is what lets :func:`quote_enumerations` fill in an enumeration without a
        second pass over the rows -- which it could only do while the rows were still there.
        """
        return None if self._saturated else self._values


class StringAccumulator(ColumnAccumulator):
    """A ``string`` column: length quantiles and a vocabulary if it has one."""

    def __init__(self) -> None:
        super().__init__()
        self._lengths = _LengthHistogram()
        self._vocabulary = _Vocabulary()
        self._strings = 0

    def _observe(self, present: list[Any]) -> None:
        for value in present:
            if isinstance(value, str):
                self._lengths.add(len(value))
                self._strings += 1
        self._vocabulary.update(present)

    def _blocks(self) -> dict[str, Any]:
        text = TextStats(chars=self._lengths.quantiles()) if self._strings else None
        return {"text": text, "categorical": self._vocabulary.finalize()}

    def vocabulary(self) -> set[Any] | None:
        return self._vocabulary.values()


class NumericAccumulator(ColumnAccumulator):
    """An ``int*`` / ``uint*`` / ``float*`` column: running extrema and mean, plus a vocabulary."""

    def __init__(self) -> None:
        super().__init__()
        self._min = math.inf
        self._max = -math.inf
        self._sum = 0.0
        self._count = 0
        self._vocabulary = _Vocabulary()

    def _observe(self, present: list[Any]) -> None:
        for value in present:
            # Non-finite floats (NaN / +-inf) are dropped: they serialize to JSON null and then fail
            # to re-validate against NumericStats' required floats, making the profile unreadable on
            # its next load. bool is an int in Python and is not a number here.
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                number = float(value)
                self._min = min(self._min, number)
                self._max = max(self._max, number)
                self._sum += number
                self._count += 1
        self._vocabulary.update(present)

    def _blocks(self) -> dict[str, Any]:
        numeric = None
        if self._count:
            numeric = NumericStats(min=self._min, max=self._max, mean=self._sum / self._count)
        return {"numeric": numeric, "categorical": self._vocabulary.finalize()}

    def vocabulary(self) -> set[Any] | None:
        return self._vocabulary.values()


class BoolAccumulator(ColumnAccumulator):
    """A ``bool`` column. The column that decides unpaired_preference deserves a measured class
    balance rather than no stats at all, and two values is a vocabulary by any reading."""

    def __init__(self) -> None:
        super().__init__()
        self._vocabulary = _Vocabulary()

    def _observe(self, present: list[Any]) -> None:
        self._vocabulary.update(present)

    def _blocks(self) -> dict[str, Any]:
        return {"categorical": self._vocabulary.finalize()}

    def vocabulary(self) -> set[Any] | None:
        return self._vocabulary.values()


class MessageAccumulator(ColumnAccumulator):
    """A ``messages`` column: turn and length distributions, the roles seen, and chat-shape rates."""

    def __init__(self) -> None:
        super().__init__()
        self._conversations = 0
        self._turns = _LengthHistogram()
        self._content_chars = _LengthHistogram()
        self._roles_seen: list[str] = []
        self._ends_with_assistant = 0
        self._valid_alternation = 0
        self._has_tool_calls = False

    def _observe(self, present: list[Any]) -> None:
        for messages in present:
            if not isinstance(messages, list):
                continue
            self._conversations += 1
            self._turns.add(len(messages))
            total_content = 0
            for message in messages:
                if not isinstance(message, dict):
                    continue
                role = _role_of(message)
                if role is not None:
                    # Coerced to str because roles_seen is typed list[str] and a non-string role
                    # would fail validation. Reported verbatim otherwise: the contract is explicit
                    # that an unexpected role is the finding worth surfacing, not something to
                    # normalize away.
                    role = role if isinstance(role, str) else str(role)
                    if role not in self._roles_seen and len(self._roles_seen) < _MAX_ROLES_SEEN:
                        self._roles_seen.append(role)
                total_content += _content_len(_message_field(message, "content", "value"))
                # `.get` truthiness, not `in`: parquet materializes every declared struct field, so a
                # schema that merely declares tool_calls would otherwise report tool use on every row.
                if message.get("tool_calls") or role == "tool":
                    self._has_tool_calls = True
            self._content_chars.add(total_content)
            if messages and isinstance(messages[-1], dict) and _is_assistant_role(_role_of(messages[-1])):
                self._ends_with_assistant += 1
            if _valid_alternation(messages):
                self._valid_alternation += 1

    def _blocks(self) -> dict[str, Any]:
        if not self._conversations:
            return {"messages": None}
        return {
            "messages": MessageStats(
                turns=self._turns.quantiles(),
                content_chars=self._content_chars.quantiles(),
                roles_seen=self._roles_seen,
                ends_with_assistant_rate=self._ends_with_assistant / self._conversations,
                valid_alternation_rate=self._valid_alternation / self._conversations,
                has_tool_calls=self._has_tool_calls,
            )
        }


def _accumulator_for(feature: FeatureSchema) -> ColumnAccumulator:
    """The accumulator that knows how to measure this column, dispatched once on its dtype."""
    if feature.dtype == "string":
        return StringAccumulator()
    if feature.dtype == "bool":
        return BoolAccumulator()
    if feature.dtype == "messages":
        return MessageAccumulator()
    if _is_numeric(feature.dtype):
        return NumericAccumulator()
    return ColumnAccumulator()


class DeferredAccumulator(ColumnAccumulator):
    """A column whose dtype is not known until the last row has gone by.

    An accumulator is normally chosen *by* dtype, which a declared schema gives up front. An inferred
    one does not: the observed types are unioned over the whole column and a disagreement widens to
    ``json``, so the choice cannot be made while the choosing still matters. Deferring it is the only
    resolution that neither reads the data twice nor decides from a prefix and hopes.

    So every shape is measured at once and the answer picked at the end. It costs no more per value
    than choosing would have -- a string only ever reaches the string state, an int only the numeric
    -- and the state it costs is four bounded structures per column rather than one. A column that
    resolves to a shape nothing measured, or to ``json``, simply has no blocks, which is what the
    dispatch would have produced for it anyway.
    """

    def __init__(self, name: str) -> None:
        super().__init__()
        self._schema = SchemaFold(name)
        self._string = StringAccumulator()
        self._numeric = NumericAccumulator()
        self._bool = BoolAccumulator()
        self._messages = MessageAccumulator()

    def _observe(self, present: list[Any]) -> None:
        self._schema.update(present)
        # Routed by python type. Where a dtype resolves to something measurable, every present value
        # is of that type by construction -- `_resolve_scalar` only returns `string` when the whole
        # column was strings -- so this sees exactly what the chosen accumulator would have seen.
        strings = [value for value in present if isinstance(value, str)]
        if strings:
            self._string._observe(strings)
        numbers = [value for value in present if isinstance(value, (int, float)) and not isinstance(value, bool)]
        if numbers:
            self._numeric._observe(numbers)
        bools = [value for value in present if isinstance(value, bool)]
        if bools:
            self._bool._observe(bools)
        lists = [value for value in present if isinstance(value, list)]
        if lists:
            self._messages._observe(lists)

    def feature(self) -> FeatureSchema:
        """The column's schema, as folded."""
        return self._schema.finalize()

    def _blocks(self) -> dict[str, Any]:
        dtype = self.feature().dtype
        if dtype == "string":
            return self._string._blocks()
        if dtype == "bool":
            return self._bool._blocks()
        if dtype == "messages":
            return self._messages._blocks()
        if _is_numeric(dtype):
            return self._numeric._blocks()
        return {}

    def vocabulary(self) -> set[Any] | None:
        dtype = self.feature().dtype
        if dtype == "string":
            return self._string.vocabulary()
        if dtype == "bool":
            return self._bool.vocabulary()
        if _is_numeric(dtype):
            return self._numeric.vocabulary()
        return None


class InferredRowFold:
    """A partition's columns, discovered as they appear and typed once they have all gone by.

    The counterpart to :class:`RowFold` for data that declares no schema. Columns are created on
    first sight and back-filled with the rows they were absent for, which is what makes the result
    identical to inferring the schema first and measuring second -- a row without the key genuinely
    holds a null for it.
    """

    def __init__(self) -> None:
        self._accumulators: dict[str, DeferredAccumulator] = {}
        self._order: list[str] = []
        self._failed: dict[str, Evidence] = {}
        self._rows_seen = 0

    def update(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            for name in row:
                if name in self._accumulators or len(self._accumulators) >= MAX_COLUMNS:
                    continue
                accumulator = DeferredAccumulator(name)
                accumulator.backfill_nulls(self._rows_seen)
                self._accumulators[name] = accumulator
                self._order.append(name)
        for name in self._order:
            if name in self._failed:
                continue
            try:
                self._accumulators[name].update([row.get(name) for row in rows])
            except Exception as exc:
                self._failed[name] = Evidence(
                    kind="error",
                    detail=f"column {name!r} could not be measured: {type(exc).__name__}: {exc}",
                )
        self._rows_seen += len(rows)

    def finalize(self) -> tuple[list[FeatureSchema], ColumnMeasurements]:
        features: list[FeatureSchema] = []
        stats: dict[str, ColumnStats] = {}
        probes: dict[str, ColumnProbes] = {}
        vocabularies: dict[str, set[Any]] = {}
        errors: list[Evidence] = []
        for name in self._order:
            failure = self._failed.get(name)
            if failure is not None:
                errors.append(failure)
                continue
            accumulator = self._accumulators[name]
            try:
                features.append(accumulator.feature())
                column, probe = accumulator.finalize()
            except Exception as exc:
                errors.append(
                    Evidence(
                        kind="error",
                        detail=f"column {name!r} could not be summarised: {type(exc).__name__}: {exc}",
                    )
                )
                continue
            probes[name] = probe
            vocabulary = accumulator.vocabulary()
            if vocabulary is not None:
                vocabularies[name] = vocabulary
            if column is not None:
                stats[name] = column
        return features, ColumnMeasurements(stats=stats, probes=probes, vocabularies=vocabularies, errors=errors)


def _is_numeric(dtype: str) -> bool:
    return dtype.startswith(("int", "uint", "float"))


# How finely a length distribution is recorded. Lengths below the slice count get a counter each and
# are exact; above it, each octave is cut into this many slices, so a bucket spans a fixed *relative*
# width of 1/32. Reporting a bucket's midpoint then puts every estimate within ~1.6% of the truth,
# whatever the value's magnitude and however many rows there are.
_HISTOGRAM_SLICE_BITS = 5
_HISTOGRAM_SLICES = 1 << _HISTOGRAM_SLICE_BITS


def _length_bucket(value: int) -> int:
    """The counter a length belongs to."""
    if value < _HISTOGRAM_SLICES:
        return value  # small lengths get a counter each, so they are recorded exactly
    shift = value.bit_length() - 1 - _HISTOGRAM_SLICE_BITS
    return (shift + 1) * _HISTOGRAM_SLICES + ((value >> shift) - _HISTOGRAM_SLICES)


def _bucket_bounds(bucket: int) -> tuple[int, int]:
    """The half-open range of lengths that land in ``bucket``. Inverse of :func:`_length_bucket`."""
    if bucket < _HISTOGRAM_SLICES:
        return bucket, bucket + 1
    index, slice_index = divmod(bucket, _HISTOGRAM_SLICES)
    shift = index - 1
    low = (_HISTOGRAM_SLICES + slice_index) << shift
    return low, low + (1 << shift)


class _LengthHistogram:
    """A per-row length distribution, held as counters rather than as the lengths themselves.

    This is what lets an accumulator stay O(1) in rows. Exact quantiles need every length kept and
    sorted, which is a list that grows with the dataset; a reservoir of sampled lengths bounds that,
    but buys the bound with an RNG -- and so with a seed back in the contract, and two runs over the
    same bytes disagreeing. Counting into fixed buckets bounds it with neither.

    The two put their error in different places. A reservoir sees *some* rows exactly, so its error
    is in which rows it happened to keep: probabilistic, and shrinking only with the sample size.
    This sees *every* row imprecisely, so its error is in how finely each value was recorded: a hard
    bound of half a bucket width, whatever the data does. Measured against exact quantiles on real
    shards, ~2%.

    Rounding the value is the cheap error to accept here, because the number is read to pick a
    sequence budget and gets rounded to a power of two by whoever reads it. ``max`` is kept exactly
    and separately: it is the one value here a reader may treat as a hard bound.
    """

    def __init__(self) -> None:
        self._counts: dict[int, int] = {}
        self._rows = 0
        self._max = 0

    def add(self, value: int) -> None:
        bucket = _length_bucket(value)
        self._counts[bucket] = self._counts.get(bucket, 0) + 1
        self._rows += 1
        if value > self._max:
            self._max = value

    def quantiles(self) -> Quantiles:
        return Quantiles(p50=self._at(50), p95=self._at(95), p99=self._at(99), max=self._max)

    def _at(self, percentile: int) -> int:
        """Nearest-rank percentile: the bucket the p-th row falls in, reported at its midpoint.

        The rank is exact -- every row was counted, none sampled -- so only the value is approximate.
        Midpoint rather than the bucket's low edge, which sits systematically under the truth and
        roughly doubles the average error.
        """
        if not self._rows:
            return 0
        target = math.ceil(percentile / 100 * self._rows)
        seen = 0
        for bucket in sorted(self._counts):
            seen += self._counts[bucket]
            if seen >= target:
                low, high = _bucket_bounds(bucket)
                # Never above `max`: a midpoint can overshoot the largest value actually present,
                # and a p99 above the maximum would be nonsense.
                return min((low + high) // 2, self._max)
        return self._max


# --- messages ------------------------------------------------------------------------------------

# Role strings that mean "the turn the model is trained to produce". Matching only the literal
# "assistant" made every chat dataset using another convention (`gpt`, `bot`, `model`) look
# like it ended on a user turn, which classification reads as a prompt-only dataset with no training
# target — a false negative over a large slice of public chat data.
_ASSISTANT_ROLES = {"assistant", "gpt", "bot", "model", "chatbot", "ai"}

# Distinct role strings a chat column may show before the list stops growing. It is fed straight from
# row content, so without a bound one malformed column could hold a string per message -- and since
# membership is checked against the list, that is quadratic as well as unbounded. The truncation
# costs nothing a reader would act on: the list exists to pick a chat template, and a column with
# more than this many roles is not a chat column, which the first few dozen already say.
_MAX_ROLES_SEEN = 64


def _message_field(message: dict, *names: str) -> Any:
    """The first present, non-null value among ``names``.

    Chat rows spell the same two fields either ``{role, content}`` or ``{from, value}``. Reading with
    a plain ``.get`` default is not enough: parquet materializes *every* declared struct field, so an
    absent field arrives as an explicit None rather than a missing key.
    """
    for name in names:
        value = message.get(name)
        if value is not None:
            return value
    return None


def _role_of(message: dict) -> Any:
    return _message_field(message, "role", "from")


def _is_assistant_role(role: Any) -> bool:
    return isinstance(role, str) and role.lower() in _ASSISTANT_ROLES


def _content_len(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):  # VLM content as a list of typed parts
        return sum(
            len(part["text"]) for part in content if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    return 0


def _valid_alternation(messages: list) -> bool:
    """True when user/assistant turns alternate (ignoring any leading system turns)."""
    roles = [_role_of(m) for m in messages if isinstance(m, dict) and _role_of(m) != "system"]
    return all(roles[i] != roles[i + 1] for i in range(len(roles) - 1))


# --- content probes ------------------------------------------------------------------------------

# Probes run over *every* column, not only role-assigned ones. Gating them on roles made a content
# signal reachable only through a recognized column name: a dataset whose answer column is called
# `a` instead of `answer` lost verifiability entirely, even though the markers were sitting in the
# data and the regex would have matched them. Classification reads these counts and decides what
# they mean; it no longer does the looking.
_TRANSCRIPT_MARKER = re.compile(r"\n\n(?:Human|Assistant|User):")
_GSM8K_ANSWER = re.compile(r"####\s*-?[\d.,/]+\s*$")
_BOXED_ANSWER = re.compile(r"\\boxed\{")


@dataclass(frozen=True)
class ColumnProbes:
    """What the content probes saw in one column across the sampled rows.

    Internal to the profiler rather than part of the stored contract: these are inputs to
    classification, and promoting them to durable per-column facts is a separate contract change.
    Counts, not rates — the caller divides, so a zero denominator stays visible instead of becoming
    a silent 0.0.
    """

    rows: int  # rows considered for this column
    non_empty: int  # value present and not "" / [] / {} — a usable target of any dtype
    texts: int  # rows that yielded text: a string, or a chat column's final turn
    extractable_answer: int  # of `texts`, how many carry `#### <number>` or `\boxed{`
    transcript_marker: int  # of `texts`, how many embed a Human:/Assistant: transcript


def _probe_text(value: Any) -> str | None:
    """The text a probe reads from one cell: the string itself, or a chat column's final turn.

    The final turn is read through :func:`_message_field`, so the ``{from, value}`` spelling works
    like ``{role, content}``. Both are handled everywhere else in this module and in schema
    derivation; missing it here cost every dataset spelled that way its verifiability.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and isinstance(value[-1], dict):
        content = _message_field(value[-1], "content", "value")
        if isinstance(content, str):
            return content
    return None
