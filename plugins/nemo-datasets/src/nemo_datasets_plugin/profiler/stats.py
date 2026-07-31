# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Per-column statistics.

Given a partition's features and its sampled rows, measure each top-level column according to its
dtype: length quantiles and corruption signals for text, min/max/mean for numbers, chat-shape
signals for messages, and cardinality for both. The result is sparse — a column with nothing worth
measuring is omitted. Row values themselves are never stored, except a proven small enumeration
under ``categorical.values`` when the read was exhaustive.
"""

from __future__ import annotations

import math
import re
from typing import Any

from nemo_platform_plugin.files.dataset_profile import (
    CategoricalStats,
    ColumnStats,
    FeatureSchema,
    MessageStats,
    NumericStats,
    Quantiles,
    TextQuality,
    TextStats,
)

# A proven enumeration is only stored when the read was exhaustive and this small.
_MAX_ENUM_VALUES = 32


def derive_stats(
    features: list[FeatureSchema], rows: list[dict[str, Any]], *, exhaustive: bool
) -> dict[str, ColumnStats]:
    """Measure each top-level column. Keys are a subset of the feature names (sparse)."""
    total = len(rows)
    stats: dict[str, ColumnStats] = {}
    for feature in features:
        # Parquet permits duplicate field names, and stats is keyed by name. Measuring the first and
        # skipping the rest makes which one wins deterministic instead of "whichever came last".
        if feature.name in stats:
            continue
        column = _column_stats(feature, [row.get(feature.name) for row in rows], total, exhaustive)
        if column is not None:
            stats[feature.name] = column
    return stats


def _column_stats(feature: FeatureSchema, values: list[Any], total: int, exhaustive: bool) -> ColumnStats | None:
    present = [value for value in values if value is not None]
    null_rate = (total - len(present)) / total if total else 0.0

    text = numeric = messages = categorical = quality = None
    if feature.dtype == "string":
        strings = [value for value in present if isinstance(value, str)]
        if strings:
            text = TextStats(chars=_quantiles([len(value) for value in strings]))
            quality = _text_quality(strings)
        # distinct_count is always safe to store and is the id-like signal (~= rows_scanned) the
        # contract documents; only the values themselves are row data, and _cardinality already gates
        # those on an exhaustive read. Withholding the count for high-cardinality strings dropped the
        # signal precisely where it carries the most information.
        categorical = _cardinality(present, exhaustive)
    elif feature.dtype == "bool":
        # The column that decides unpaired_preference deserves a measured class balance rather than
        # no stats at all.
        categorical = _cardinality(present, exhaustive)
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
        categorical = _cardinality(present, exhaustive)
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


def _cardinality(present: list[Any], exhaustive: bool) -> CategoricalStats | None:
    try:
        distinct = set(present)
    except TypeError:
        return None  # unhashable values (dicts / lists) have no cardinality signal
    values = None
    if exhaustive and len(distinct) <= _MAX_ENUM_VALUES:
        values = sorted(str(value) for value in distinct)
    return CategoricalStats(distinct_count=len(distinct), values=values)


# --- text quality --------------------------------------------------------------------------------


_WHITESPACE_RUN = re.compile(r"\s")
_NON_ASCII_RUN = re.compile(r"[^\x00-\x7f]")
# Any character repeated four or more times in a row. Scanning with the regex engine instead of a
# Python loop is what keeps this affordable: these three measurements used to run three interpreted
# passes over every character of every string and dominated total profiling time.
_REPEAT_RUN = re.compile(r"(.)\1{3,}", re.DOTALL)


def _text_quality(strings: list[str]) -> TextQuality:
    total_chars = 0
    whitespace = 0
    non_ascii = 0
    repetition_sum = 0.0
    for value in strings:
        total_chars += len(value)
        # str.count-style scanning in C rather than a per-character generator in Python.
        whitespace += _count_matches(_WHITESPACE_RUN, value)
        non_ascii += _count_matches(_NON_ASCII_RUN, value)
        repetition_sum += _repetition_score(value)
    return TextQuality(
        whitespace_ratio=whitespace / total_chars if total_chars else 0.0,
        non_ascii_ratio=non_ascii / total_chars if total_chars else 0.0,
        repetition_score=repetition_sum / len(strings) if strings else 0.0,
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
