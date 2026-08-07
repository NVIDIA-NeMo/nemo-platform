# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Per-column statistics and content probes.

Given a partition's features and its rows, :func:`measure_columns` measures each top-level column
according to its dtype: length quantiles and corruption signals for text, min/max/mean for numbers,
chat-shape signals for messages, and a bounded vocabulary where the column has one. The result is
sparse — a column with nothing worth measuring is omitted — and each column is isolated, so one the
detectors cannot handle costs only itself. Row values themselves are never stored here at all; a
small controlled vocabulary is added afterwards by :func:`quote_enumerations`, which gates on role.

The same pass reads each column's *content* — answer markers, embedded transcripts — as plain
per-column counts (:class:`ColumnProbes`, also reachable alone via :func:`derive_probes`, which
classification uses when it was handed no probes). Those are measurements, not interpretations: what
they mean is classification's job, and keeping the looking here is what stops a content signal from
being reachable only through a correctly named column.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from nemo_platform_plugin.files.dataset_profile import (
    CategoricalStats,
    ColumnStats,
    Evidence,
    FeatureSchema,
    MessageStats,
    NumericStats,
    Quantiles,
    TextQuality,
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


def measure_columns(
    features: list[FeatureSchema], rows: list[dict[str, Any]]
) -> tuple[dict[str, ColumnStats], dict[str, ColumnProbes], list[Evidence]]:
    """Measure every top-level column: its statistics and its content probes, in one pass each.

    Each column is isolated. A value no detector anticipated -- a chat message whose ``role`` is a
    number, a float where a string was declared -- costs that column its measurements and nothing
    else, where previously it cost the partition every measurement it had. The failure is reported
    as an ``error`` evidence rather than left as a silent gap, because a column absent from ``stats``
    is otherwise indistinguishable from one that simply had nothing worth measuring.

    This is the narrow half of the two guards the profiler runs. The wide one still wraps the whole
    measure stage, and still catches anything structural -- schema derivation, classification -- that
    is not attributable to a single column.

    Statistics and probes are measured together because they read the same values, and extracting a
    column out of the rows costs more than either measurement. Neither fills in
    ``categorical.values``: that needs the roles, which classification has not assigned yet, so
    :func:`quote_enumerations` adds them afterwards.
    """
    stats: dict[str, ColumnStats] = {}
    probes: dict[str, ColumnProbes] = {}
    errors: list[Evidence] = []
    total = len(rows)
    for feature in features:
        # Parquet permits duplicate field names, and both maps are keyed by name. Measuring the
        # first and skipping the rest makes which one wins deterministic instead of "whichever came
        # last", and keeps stats and probes agreeing on the same one.
        if feature.name in probes:
            continue
        values = [row.get(feature.name) for row in rows]
        try:
            column = _column_stats(feature, values, total)
            probes[feature.name] = _column_probes(values)
        except Exception as exc:
            errors.append(
                Evidence(
                    kind="error",
                    detail=(
                        f"column {feature.name!r} ({feature.dtype}) could not be measured: {type(exc).__name__}: {exc}"
                    ),
                )
            )
            continue
        if column is not None:
            stats[feature.name] = column
    return stats, probes, errors


def quote_enumerations(
    features: list[FeatureSchema], stats: dict[str, ColumnStats], rows: list[dict[str, Any]]
) -> None:
    """Fill in ``categorical.values`` for columns whose role makes them a controlled vocabulary.

    Runs after classification, because it needs the roles it gates on, and mutates ``stats`` in place
    the way classification mutates ``features``. Deliberately fills in rather than redacting: skip
    this pass and no values are stored, where a redaction pass that got skipped would leak them.

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
        try:
            distinct = {value for row in rows if (value := row.get(feature.name)) is not None}
        except TypeError:
            continue  # unhashable values have no enumeration to quote
        column.categorical.values = sorted(str(value) for value in distinct)


def _column_stats(feature: FeatureSchema, values: list[Any], total: int) -> ColumnStats | None:
    present = [value for value in values if value is not None]
    null_rate = (total - len(present)) / total if total else 0.0

    text = numeric = messages = categorical = quality = None
    if feature.dtype == "string":
        strings = [value for value in present if isinstance(value, str)]
        if strings:
            text = TextStats(chars=_quantiles([len(value) for value in strings]))
            quality = _text_quality(strings)
        # Only while the column looks like a controlled vocabulary; see `_cardinality`. The values
        # themselves are row data and are added later, by role, never by size.
        categorical = _cardinality(present)
    elif feature.dtype == "bool":
        # The column that decides unpaired_preference deserves a measured class balance rather than
        # no stats at all.
        categorical = _cardinality(present)
    elif _is_numeric(feature.dtype):
        # Drop non-finite floats (NaN / +-inf): they serialize to JSON null and then fail to
        # re-validate against NumericStats' required floats, which would make the whole profile
        # unreadable on the next load.
        numbers = [
            float(value)
            for value in present
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        ]
        if numbers:
            numeric = NumericStats(min=min(numbers), max=max(numbers), mean=sum(numbers) / len(numbers))
        categorical = _cardinality(present)
    elif feature.dtype == "messages":
        messages = _message_stats([value for value in present if isinstance(value, list)])

    column = ColumnStats(
        null_rate=null_rate, text=text, numeric=numeric, messages=messages, categorical=categorical, quality=quality
    )
    if not any([text, numeric, messages, categorical, quality]) and null_rate == 0.0:
        return None  # nothing worth measuring
    return column


def _is_numeric(dtype: str) -> bool:
    return dtype.startswith(("int", "uint", "float"))


def _quantiles(values: list[int]) -> Quantiles:
    """Nearest-rank percentiles over the sample (n is small, so this stays exact)."""
    ordered = sorted(values)
    n = len(ordered)

    def at(percentile: int) -> int:
        if n == 0:
            return 0
        rank = math.ceil(percentile / 100 * n)
        return ordered[min(rank, n) - 1]

    return Quantiles(p50=at(50), p95=at(95), p99=at(99), max=ordered[-1] if ordered else 0)


def _cardinality(present: list[Any]) -> CategoricalStats | None:
    """The distinct-value count, for as long as the column looks like a controlled vocabulary.

    Returns None the moment it stops looking like one, discarding what it had accumulated. Counting
    distinct values exactly means *retaining* them, so on a free-text column this set grows to hold
    the column, to report that `response` had 9,954 distinct values in 10,000 rows -- which is "this
    is free text", which the role marker and the length quantiles already say for nothing.

    Today that costs little, because the rows are held anyway and the set stores pointers into them:
    measured at 2.6 MB beside 61.4 MB of resident rows. The bound is here for the pipeline this is
    becoming. Once a batch is folded and discarded, a distinct set is the *sole owner* of every value
    it kept, and the same two columns cost 46.8 MB against 0.163 MB for every other accumulator
    combined. Unbounded, this is the one thing that would make a streaming fold O(rows) again.

    Three bounds rather than one. A count alone bounds cardinality but not bytes, and 1024 reasoning
    traces is 32 MB. The middle bound is the one that does the real work: it asks what the column
    *is* rather than how many values it holds, in the same way the role gate on quoting does. A
    vocabulary member is short by nature, so a single 32 KB value settles the question on sight,
    which is why free-text columns exit here almost immediately instead of after 1024 values.

    The values themselves are still never returned here. They are row content, gated on role rather
    than on size, and :func:`quote_enumerations` adds them once classification has assigned one.
    """
    distinct: set[Any] = set()
    retained_bytes = 0
    for value in present:
        if isinstance(value, str) and len(value) > _MAX_VOCABULARY_VALUE_CHARS:
            return None
        try:
            if value in distinct:
                continue
            distinct.add(value)
        except TypeError:
            return None  # unhashable values (dicts / lists) have no cardinality signal
        retained_bytes += len(value) if isinstance(value, str) else _NON_STRING_VALUE_BYTES
        if len(distinct) > _MAX_VOCABULARY_VALUES or retained_bytes > _MAX_VOCABULARY_BYTES:
            return None
    return CategoricalStats(distinct_count=len(distinct))


# --- text quality --------------------------------------------------------------------------------


_WHITESPACE_RUN = re.compile(r"\s")
_NON_ASCII_RUN = re.compile(r"[^\x00-\x7f]")
# Any character repeated four or more times in a row. Scanning with the regex engine instead of a
# Python loop is what keeps this affordable: these three measurements used to run three interpreted
# passes over every character of every string and dominated total profiling time.
_REPEAT_RUN = re.compile(r"(.)\1{3,}", re.DOTALL)

# What `\s` matches within ASCII, in the order `str.count` will be asked for them.
_ASCII_WHITESPACE = " \t\n\r\f\v"

# Rows a column's quality ratios are measured over. These three are the only per-character work left
# in the profiler -- measured at 37x the cost of every content probe combined, and roughly fifteen
# times everything else in a column's measurement put together -- while every other statistic is
# O(1) per row. They are also ratios, which a sample of tens of thousands of rows pins down far past
# the precision anyone reads them to. Bounding them is what makes reading every row affordable.
_QUALITY_SAMPLE_ROWS = 50_000


def _quality_sample(strings: list[str]) -> list[str]:
    """The rows to measure quality over: all of them, or an evenly strided subset.

    Strided rather than random, because two runs over the same bytes must agree. Randomness is what
    ``SamplingInfo.seed`` existed to make reproducible, and that field was deleted on the grounds
    that the profiler makes no random choices and a seed would be theatre -- which should stay true.

    Strided rather than the head, because shards arrive sorted often enough that the first rows of a
    large column are not a sample of it. A stride costs the same, needs no state, and spreads the
    sample across the whole column.

    A stride can in principle alias against periodic data: a set with two rows per prompt, sampled
    at stride two, sees one phase of every pair. Measured on exactly that shape -- HelpSteer2 rates
    two responses per prompt -- the two phases agree to 0.35% on `whitespace_ratio` and differ by at
    most 8% on the other two, whose values there are 0.0003 and 0.0025. That is well inside the band
    these estimates already carry near zero, and does not buy a block-sampling scheme to avoid.
    """
    if len(strings) <= _QUALITY_SAMPLE_ROWS:
        return strings
    return strings[:: len(strings) // _QUALITY_SAMPLE_ROWS]


def _whitespace_count(text: str) -> int:
    """Whitespace characters, matching ``\\s`` exactly.

    The ASCII branch is not merely faster, it is the only one that may take the shortcut: within
    ASCII ``\\s`` is precisely :data:`_ASCII_WHITESPACE`, so counting those six literals in C is the
    same measurement. Outside it, ``\\s`` also matches U+00A0 and the rest of Unicode's spaces, which
    the literal count would silently miss -- so the regex is a correctness fallback, not a slow path
    kept for tidiness.
    """
    if text.isascii():
        return sum(text.count(char) for char in _ASCII_WHITESPACE)
    return _count_matches(_WHITESPACE_RUN, text)


def _non_ascii_count(text: str) -> int:
    """Characters outside ASCII. ``str.isascii`` settles the common case in C without a scan.

    Deliberately not ``len(text.encode()) - len(text)``, which is faster still and answers a
    different question: that counts *bytes* of encoding overhead, so a three-byte codepoint would
    contribute two where this contributes one.
    """
    if text.isascii():
        return 0
    return _count_matches(_NON_ASCII_RUN, text)


def _text_quality(strings: list[str]) -> TextQuality:
    sample = _quality_sample(strings)
    total_chars = 0
    whitespace = 0
    non_ascii = 0
    repetition_sum = 0.0
    for value in sample:
        total_chars += len(value)
        whitespace += _whitespace_count(value)
        non_ascii += _non_ascii_count(value)
        repetition_sum += _repetition_score(value)
    return TextQuality(
        whitespace_ratio=whitespace / total_chars if total_chars else 0.0,
        non_ascii_ratio=non_ascii / total_chars if total_chars else 0.0,
        # Every denominator is the sample's own, never the column's: each ratio is an estimate over
        # the rows that were actually scanned, which is what keeps it unbiased rather than diluted.
        repetition_score=repetition_sum / len(sample) if sample else 0.0,
    )


def _count_matches(pattern: re.Pattern[str], text: str) -> int:
    return sum(1 for _ in pattern.finditer(text))


def _repetition_score(text: str) -> float:
    """Fraction of characters inside a run of the same character of length >= 4.

    A cheap corruption proxy: near zero for natural text, high for scraping junk and degenerate
    single-character loops (``"aaaaaa"``, long ``"------"`` separators).
    """
    if not text:
        return 0.0
    redundant = sum(len(match.group(0)) for match in _REPEAT_RUN.finditer(text))
    return redundant / len(text)


# --- messages ------------------------------------------------------------------------------------

# Role strings that mean "the turn the model is trained to produce". Matching only the literal
# "assistant" made every chat dataset using another convention (ShareGPT's gpt, or bot/model) look
# like it ended on a user turn, which classification reads as a prompt-only dataset with no training
# target — a false negative over a large slice of public chat data.
_ASSISTANT_ROLES = {"assistant", "gpt", "bot", "model", "chatbot", "ai"}


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


def _message_stats(rows_messages: list[list]) -> MessageStats | None:
    if not rows_messages:
        return None
    turns: list[int] = []
    content_chars: list[int] = []
    roles_seen: list[str] = []
    ends_with_assistant = 0
    valid_alternation = 0
    has_tool_calls = False

    for messages in rows_messages:
        turns.append(len(messages))
        total_content = 0
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = _role_of(message)
            if role is not None:
                # Coerced to str because roles_seen is typed list[str] and a non-string role would
                # fail validation — aborting the whole profile from inside the one stage the pipeline
                # does not guard. Reported verbatim otherwise: the contract is explicit that an
                # unexpected role is the finding worth surfacing, not something to normalize away.
                role = role if isinstance(role, str) else str(role)
                if role not in roles_seen:
                    roles_seen.append(role)
            total_content += _content_len(_message_field(message, "content", "value"))
            # `.get` truthiness, not `in`: parquet materializes every declared struct field, so a
            # schema that merely declares tool_calls would otherwise report tool use on every row.
            if message.get("tool_calls") or role == "tool":
                has_tool_calls = True
        content_chars.append(total_content)
        if messages and isinstance(messages[-1], dict) and _is_assistant_role(_role_of(messages[-1])):
            ends_with_assistant += 1
        if _valid_alternation(messages):
            valid_alternation += 1

    n = len(rows_messages)
    return MessageStats(
        turns=_quantiles(turns),
        content_chars=_quantiles(content_chars),
        roles_seen=roles_seen,
        ends_with_assistant_rate=ends_with_assistant / n,
        valid_alternation_rate=valid_alternation / n,
        has_tool_calls=has_tool_calls,
    )


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


def derive_probes(features: list[FeatureSchema], rows: list[dict[str, Any]]) -> dict[str, ColumnProbes]:
    """Run the content probes over every top-level column, keyed by column name."""
    probes: dict[str, ColumnProbes] = {}
    for feature in features:
        # Duplicate parquet field names: first wins, matching `measure_columns` so both agree on which.
        if feature.name in probes:
            continue
        probes[feature.name] = _column_probes([row.get(feature.name) for row in rows])
    return probes


def _column_probes(values: list[Any]) -> ColumnProbes:
    texts = [text for value in values if (text := _probe_text(value)) is not None]
    return ColumnProbes(
        rows=len(values),
        non_empty=sum(1 for value in values if value not in (None, "", [], {})),
        texts=len(texts),
        extractable_answer=sum(1 for text in texts if _GSM8K_ANSWER.search(text) or _BOXED_ANSWER.search(text)),
        transcript_marker=sum(1 for text in texts if _TRANSCRIPT_MARKER.search(text)),
    )


def _probe_text(value: Any) -> str | None:
    """The text a probe reads from one cell: the string itself, or a chat column's final turn.

    The final turn is read through :func:`_message_field`, so ShareGPT's ``{from, value}`` spelling
    works like ``{role, content}``. Both are handled everywhere else in this module and in schema
    derivation; missing it here cost every ShareGPT-shaped dataset its verifiability.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and isinstance(value[-1], dict):
        content = _message_field(value[-1], "content", "value")
        if isinstance(content, str):
            return content
    return None
