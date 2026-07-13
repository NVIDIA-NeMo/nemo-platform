# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for per-column statistics."""

from nemo_datasets_plugin.profiler.stats import derive_stats
from nemo_platform_plugin.files.dataset_profile import FeatureSchema


def _feature(name, dtype):
    return FeatureSchema(name=name, dtype=dtype)


def _rows(name, values):
    return [{name: value} for value in values]


# --- text ----------------------------------------------------------------------------------------


def test_text_stats_length_quantiles_and_quality():
    values = ["a", "bb", "ccc", "dddd"]
    stats = derive_stats([_feature("t", "string")], _rows("t", values), exhaustive=False)["t"]
    assert stats.text.chars.max == 4
    assert stats.text.chars.p50 in {2, 3}  # nearest-rank over 4 values
    assert stats.quality is not None
    assert stats.quality.whitespace_ratio == 0.0


def test_text_quality_flags_repetition_and_non_ascii():
    stats = derive_stats([_feature("t", "string")], _rows("t", ["aaaaaaaa", "héllo wörld"]), exhaustive=False)["t"]
    assert stats.quality.repetition_score > 0.0  # the "aaaaaaaa" run
    assert stats.quality.non_ascii_ratio > 0.0  # accented characters


def test_free_text_string_has_no_categorical_but_low_cardinality_does():
    free_text = derive_stats([_feature("t", "string")], _rows("t", [f"unique-{i}" for i in range(50)]), exhaustive=True)
    assert free_text["t"].categorical is None  # too many distinct values to be an enumeration

    labels = derive_stats([_feature("c", "string")], _rows("c", ["yes", "no", "yes", "no"]), exhaustive=True)
    assert labels["c"].categorical.distinct_count == 2
    assert labels["c"].categorical.values == ["no", "yes"]  # proven enumeration under exhaustive read


# --- numeric -------------------------------------------------------------------------------------


def test_numeric_stats_and_cardinality():
    stats = derive_stats([_feature("n", "int64")], _rows("n", [0, 4, 2, 2, 3]), exhaustive=True)["n"]
    assert (stats.numeric.min, stats.numeric.max) == (0.0, 4.0)
    assert stats.numeric.mean == 2.2
    assert stats.categorical.distinct_count == 4  # {0, 2, 3, 4}


def test_numeric_cardinality_values_withheld_when_not_exhaustive():
    stats = derive_stats([_feature("n", "int64")], _rows("n", [1, 2, 3]), exhaustive=False)["n"]
    assert stats.categorical.distinct_count == 3
    assert stats.categorical.values is None  # a sample cannot prove the enumeration


# --- messages ------------------------------------------------------------------------------------


def test_message_stats_shape_signals():
    rows = [
        {"m": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello there"}]},
        {"m": [{"role": "user", "content": "again"}, {"role": "assistant", "content": "yes"}]},
    ]
    stats = derive_stats([_feature("m", "messages")], rows, exhaustive=False)["m"]
    assert stats.messages.turns.max == 2
    assert stats.messages.roles_seen == ["user", "assistant"]  # first-seen order
    assert stats.messages.ends_with_assistant_rate == 1.0
    assert stats.messages.valid_alternation_rate == 1.0
    assert stats.messages.has_tool_calls is False


def test_message_stats_detects_tool_calls_and_user_ending():
    rows = [{"m": [{"role": "user", "content": "run"}, {"role": "assistant", "tool_calls": [{"id": "1"}]}]}]
    stats = derive_stats([_feature("m", "messages")], rows, exhaustive=False)["m"]
    assert stats.messages.has_tool_calls is True
    assert stats.messages.ends_with_assistant_rate == 1.0  # last turn is the assistant tool call


def test_message_ends_with_user_turn_is_prompt_only_signal():
    rows = [{"m": [{"role": "user", "content": "solve"}]}]
    stats = derive_stats([_feature("m", "messages")], rows, exhaustive=False)["m"]
    assert stats.messages.ends_with_assistant_rate == 0.0


# --- sparsity and null rate ----------------------------------------------------------------------


def test_unmeasured_dtypes_are_omitted():
    features = [_feature("s", "struct"), _feature("j", "json")]
    rows = [{"s": {"a": 1}, "j": object()}]
    assert derive_stats(features, rows, exhaustive=False) == {}


def test_null_rate_is_reported():
    stats = derive_stats([_feature("t", "string")], _rows("t", ["a", None, "c", None]), exhaustive=False)["t"]
    assert stats.null_rate == 0.5
