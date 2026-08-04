# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for per-column statistics."""

from nemo_datasets_plugin.profiler.stats import derive_probes, derive_stats
from nemo_platform_plugin.files.dataset_profile import ColumnStats, FeatureSchema


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


def test_string_cardinality_counts_always_but_withholds_free_text_values():
    # distinct_count is the id-like signal and is always safe to store; only the values themselves
    # are row data, and only a small proven enumeration may be kept.
    free_text = derive_stats([_feature("t", "string")], _rows("t", [f"unique-{i}" for i in range(50)]), exhaustive=True)
    assert free_text["t"].categorical.distinct_count == 50  # ~= row count -> id-like
    assert free_text["t"].categorical.values is None  # too many distinct values to be an enumeration

    labels = derive_stats([_feature("c", "string")], _rows("c", ["yes", "no", "yes", "no"]), exhaustive=True)
    assert labels["c"].categorical.distinct_count == 2
    assert labels["c"].categorical.values == ["no", "yes"]  # proven enumeration under exhaustive read


def test_bool_column_gets_a_measured_class_balance():
    stats = derive_stats([_feature("label", "bool")], _rows("label", [True, False, True]), exhaustive=True)
    assert stats["label"].categorical.distinct_count == 2
    assert stats["label"].categorical.values == ["False", "True"]


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


def test_numeric_stats_ignore_non_finite_values():
    # NaN / +-inf poison min/max/mean and serialize to JSON null, which then fails to re-validate
    # against NumericStats' required floats -- making the whole profile unreadable. Drop them.
    values = [1.0, float("nan"), 3.0, float("inf"), float("-inf"), 5.0]
    stats = derive_stats([_feature("n", "float64")], _rows("n", values), exhaustive=True)["n"]
    assert (stats.numeric.min, stats.numeric.max, stats.numeric.mean) == (1.0, 5.0, 3.0)
    ColumnStats.model_validate_json(stats.model_dump_json())  # round-trips: no NaN/inf leaked into JSON


def test_numeric_all_non_finite_yields_no_numeric_summary():
    stats = derive_stats([_feature("n", "float64")], _rows("n", [float("nan"), float("inf")]), exhaustive=True)
    assert stats.get("n") is None or stats["n"].numeric is None


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


def test_message_stats_read_sharegpt_from_value():
    rows = [{"m": [{"from": "human", "value": "hi"}, {"from": "gpt", "value": "hello there"}]}]
    stats = derive_stats([_feature("m", "messages")], rows, exhaustive=False)["m"]
    assert stats.messages.roles_seen == ["human", "gpt"]  # verbatim, not normalized
    assert stats.messages.content_chars.max == len("hi") + len("hello there")
    assert stats.messages.ends_with_assistant_rate == 1.0  # "gpt" is the responder turn


def test_assistant_equivalent_roles_count_as_the_training_target():
    # Matching only the literal "assistant" made every other convention look prompt-only.
    for responder in ("assistant", "gpt", "bot", "model", "AI"):
        rows = [{"m": [{"role": "user", "content": "q"}, {"role": responder, "content": "a"}]}]
        stats = derive_stats([_feature("m", "messages")], rows, exhaustive=False)["m"]
        assert stats.messages.ends_with_assistant_rate == 1.0, responder


def test_non_string_role_does_not_break_measurement():
    # roles_seen is typed list[str]; a numeric role used to raise a ValidationError from inside the
    # one stage the pipeline did not guard, aborting the whole profile.
    rows = [{"m": [{"role": 1, "content": "hi"}]}]
    stats = derive_stats([_feature("m", "messages")], rows, exhaustive=False)["m"]
    assert stats.messages.roles_seen == ["1"]


def test_declared_but_unset_tool_calls_is_not_tool_use():
    # parquet materializes every declared struct field, so `"tool_calls" in message` reported tool
    # use for any schema that merely declares the field.
    rows = [{"m": [{"role": "user", "content": "hi", "tool_calls": None}]}]
    stats = derive_stats([_feature("m", "messages")], rows, exhaustive=False)["m"]
    assert stats.messages.has_tool_calls is False


def test_message_content_parts_tolerate_non_string_text():
    # A VLM-style content part whose "text" key is present but not a string must not crash measurement.
    rows = [{"m": [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": None}]}]}]
    stats = derive_stats([_feature("m", "messages")], rows, exhaustive=False)["m"]
    assert stats.messages.content_chars.max == 0  # no measurable text, and no crash


# --- sparsity and null rate ----------------------------------------------------------------------


def test_unmeasured_dtypes_are_omitted():
    features = [_feature("s", "struct"), _feature("j", "json")]
    rows = [{"s": {"a": 1}, "j": object()}]
    assert derive_stats(features, rows, exhaustive=False) == {}


def test_null_rate_is_reported():
    stats = derive_stats([_feature("t", "string")], _rows("t", ["a", None, "c", None]), exhaustive=False)["t"]
    assert stats.null_rate == 0.5


# --- content probes ------------------------------------------------------------------------------


def test_probes_are_measured_for_every_column_not_just_named_ones():
    # The whole point of measuring probes here rather than in classify: a column whose name the
    # alias table does not know still gets its content read.
    features = [_feature("q", "string"), _feature("a", "string")]
    rows = [{"q": "what is 2+2?", "a": "add them #### 4"}, {"q": "and 3+3?", "a": "no final answer"}]
    probes = derive_probes(features, rows)

    assert set(probes) == {"q", "a"}
    assert probes["a"].texts == 2
    assert probes["a"].extractable_answer == 1
    assert probes["q"].extractable_answer == 0


def test_probes_read_the_final_turn_of_a_chat_column():
    rows = [{"m": [{"role": "user", "content": "q"}, {"role": "assistant", "content": "steps #### 7"}]}]
    probes = derive_probes([_feature("m", "messages")], rows)
    assert probes["m"].texts == 1
    assert probes["m"].extractable_answer == 1


def test_probes_read_the_sharegpt_message_spelling():
    # {from, value} is handled in schema derivation and message stats; reading only {role, content}
    # here cost every ShareGPT-shaped dataset its verifiability.
    rows = [{"m": [{"from": "human", "value": "q"}, {"from": "gpt", "value": "steps #### 7"}]}]
    probes = derive_probes([_feature("m", "messages")], rows)
    assert probes["m"].texts == 1
    assert probes["m"].extractable_answer == 1


def test_probes_count_non_empty_across_container_dtypes():
    # `non_empty` is what a ground_truth column's coverage is measured from, and a verification
    # target is just as often a list or struct as a string.
    features = [_feature("gt", "list")]
    rows = [{"gt": [{"in": "1"}]}, {"gt": []}, {"gt": None}]
    probes = derive_probes(features, rows)
    assert probes["gt"].rows == 3
    assert probes["gt"].non_empty == 1


def test_probes_detect_embedded_transcripts():
    rows = [{"c": "\n\nHuman: hi\n\nAssistant: hello"}, {"c": "plain prose"}]
    probes = derive_probes([_feature("c", "string")], rows)
    assert probes["c"].transcript_marker == 1
