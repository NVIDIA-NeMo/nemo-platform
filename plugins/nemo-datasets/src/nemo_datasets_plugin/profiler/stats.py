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
        counts = _cardinality(present, exhaustive)
        if counts is not None and counts.distinct_count <= _MAX_ENUM_VALUES:
            categorical = counts  # a bounded string enumeration, not free text
    elif _is_numeric(feature.dtype):
        numbers = [float(value) for value in present if isinstance(value, (int, float)) and not isinstance(value, bool)]
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


def _text_quality(strings: list[str]) -> TextQuality:
    total_chars = 0
    whitespace = 0
    non_ascii = 0
    repetition_sum = 0.0
    for value in strings:
        total_chars += len(value)
        whitespace += sum(char.isspace() for char in value)
        non_ascii += sum(ord(char) > 127 for char in value)
        repetition_sum += _repetition_score(value)
    return TextQuality(
        whitespace_ratio=whitespace / total_chars if total_chars else 0.0,
        non_ascii_ratio=non_ascii / total_chars if total_chars else 0.0,
        repetition_score=repetition_sum / len(strings) if strings else 0.0,
    )


def _repetition_score(text: str) -> float:
    """Fraction of characters inside a run of the same character of length >= 4.

    A cheap corruption proxy: near zero for natural text, high for scraping junk and degenerate
    single-character loops (``"aaaaaa"``, long ``"------"`` separators).
    """
    if not text:
        return 0.0
    redundant = 0
    run = 1
    for index in range(1, len(text)):
        if text[index] == text[index - 1]:
            run += 1
        else:
            if run >= 4:
                redundant += run
            run = 1
    if run >= 4:
        redundant += run
    return redundant / len(text)


# --- messages ------------------------------------------------------------------------------------


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
            role = message.get("role")
            if role is not None and role not in roles_seen:
                roles_seen.append(role)
            total_content += _content_len(message.get("content"))
            if "tool_calls" in message or role == "tool":
                has_tool_calls = True
        content_chars.append(total_content)
        if messages and isinstance(messages[-1], dict) and messages[-1].get("role") == "assistant":
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
    roles = [m.get("role") for m in messages if isinstance(m, dict) and m.get("role") != "system"]
    return all(roles[i] != roles[i + 1] for i in range(len(roles) - 1))
