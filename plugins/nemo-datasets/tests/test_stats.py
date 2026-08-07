# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for per-column statistics."""

import pytest
from nemo_datasets_plugin.profiler import stats as stats_module
from nemo_datasets_plugin.profiler.stats import (
    _MAX_VOCABULARY_BYTES,
    _MAX_VOCABULARY_VALUE_CHARS,
    _MAX_VOCABULARY_VALUES,
    _NON_ASCII_RUN,
    _QUALITY_SAMPLE_ROWS,
    _WHITESPACE_RUN,
    _non_ascii_count,
    _quality_sample,
    _whitespace_count,
    derive_probes,
    measure_columns,
    quote_enumerations,
)
from nemo_platform_plugin.files.dataset_profile import ColumnStats, FeatureSchema


def _stats(features, rows):
    """Statistics only. Asserts nothing failed: these tests measure values, not the guard, and a
    swallowed exception would surface here as a confusing KeyError instead of its own message."""
    measured, _, errors = measure_columns(features, rows)
    assert not errors, errors
    return measured


def _feature(name, dtype):
    return FeatureSchema(name=name, dtype=dtype)


def _rows(name, values):
    return [{name: value} for value in values]


# --- text ----------------------------------------------------------------------------------------


def test_text_stats_length_quantiles_and_quality():
    values = ["a", "bb", "ccc", "dddd"]
    stats = _stats([_feature("t", "string")], _rows("t", values))["t"]
    assert stats.text.chars.max == 4
    assert stats.text.chars.p50 in {2, 3}  # nearest-rank over 4 values
    assert stats.quality is not None
    assert stats.quality.whitespace_ratio == 0.0


def test_text_quality_flags_repetition_and_non_ascii():
    stats = _stats([_feature("t", "string")], _rows("t", ["aaaaaaaa", "héllo wörld"]))["t"]
    assert stats.quality.repetition_score > 0.0  # the "aaaaaaaa" run
    assert stats.quality.non_ascii_ratio > 0.0  # accented characters


def test_one_bad_column_costs_only_itself(monkeypatch):
    # The narrow guard. A value no detector anticipated used to cost the partition every measurement
    # it had; it now costs its own column, and says so rather than leaving a silent gap.
    real_accumulator_for = stats_module._accumulator_for

    class Boom(stats_module.ColumnAccumulator):
        def _observe(self, present):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        stats_module,
        "_accumulator_for",
        lambda feature: Boom() if feature.name == "bad" else real_accumulator_for(feature),
    )

    features = [_feature("good", "string"), _feature("bad", "string")]
    measured, probes, errors = measure_columns(features, [{"good": "x", "bad": "y"}])

    assert "good" in measured and "bad" not in measured
    assert "good" in probes and "bad" not in probes  # probes go with the column that failed
    assert [e.kind for e in errors] == ["error"]
    assert "'bad'" in errors[0].detail and "RuntimeError" in errors[0].detail


# One column per dtype the dispatch knows, each carrying the awkward cases: nulls, empties, a
# non-finite float, a value long enough to saturate a vocabulary, both chat spellings.
_DTYPE_VALUES = {
    "string": ["a prompt #### 42", "héllo wörld", "", "aaaaaaaa", None, "x" * 300, "yes", "yes"],
    "int64": [1, 2, 2, None, 3, -5],
    "float64": [1.5, float("nan"), 2.5, None, float("inf"), 0.0],
    "bool": [True, False, True, None],
    "messages": [
        [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "there"}],
        [{"from": "human", "value": "q"}, {"from": "gpt", "value": "\\boxed{4}"}],
        [{"role": "user", "content": "x", "tool_calls": [{"n": 1}]}],
        None,
        [],
    ],
    "struct": [{"a": 1}, None, {"b": 2}],
}


@pytest.mark.parametrize("dtype", sorted(_DTYPE_VALUES))
@pytest.mark.parametrize("chunks", [1, 2, 3, 7])
def test_an_accumulator_folds_rather_than_buffers(dtype, chunks):
    # The property the fold rests on: a column split across calls has to measure the same as one
    # handed over whole. Without it, batching would quietly change the numbers -- and the batch size
    # is an implementation detail no reader of the profile could see.
    values = _DTYPE_VALUES[dtype] * 5
    feature = _feature("c", dtype)

    whole = stats_module._accumulator_for(feature)
    whole.update(values)

    in_pieces = stats_module._accumulator_for(feature)
    step = max(1, -(-len(values) // chunks))
    for start in range(0, len(values), step):
        in_pieces.update(values[start : start + step])

    assert in_pieces.finalize() == whole.finalize()


def test_the_typed_accumulators_probe_exactly_as_the_bare_one_does():
    # Probe counting lives on the base class, so every dtype gets it for free. If a subclass ever
    # shadows that, a chat column would quietly stop contributing verifiability evidence.
    features = [_feature(dtype, dtype) for dtype in sorted(_DTYPE_VALUES)]
    rows = [dict(zip(sorted(_DTYPE_VALUES), values)) for values in zip(*_DTYPE_VALUES.values())]

    _, probes, errors = measure_columns(features, rows)

    assert errors == []
    assert probes == derive_probes(features, rows)  # derive_probes goes through the base class


def test_measure_columns_measures_every_dtype_the_dispatch_knows():
    features = [
        _feature("text", "string"),
        _feature("count", "int64"),
        _feature("score", "float64"),
        _feature("flag", "bool"),
        _feature("chat", "messages"),
        _feature("meta", "struct"),
        _feature("missing", "string"),
    ]
    rows = [
        {
            "text": "a prompt ending in #### 42",
            "count": i,
            "score": i / 3,
            "flag": i % 2 == 0,
            "chat": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "there"}],
            "meta": {"src": "x"},
            "missing": None,
        }
        for i in range(5)
    ]
    measured, probes, errors = measure_columns(features, rows)

    assert errors == []
    assert measured["text"].text is not None and measured["text"].quality is not None
    assert measured["count"].numeric.min == 0.0
    assert measured["count"].categorical.distinct_count == 5
    assert measured["score"].numeric.mean == pytest.approx(sum(i / 3 for i in range(5)) / 5)
    assert measured["flag"].categorical.distinct_count == 2
    assert measured["chat"].messages.roles_seen == ["user", "assistant"]
    assert "meta" not in measured  # a struct with no nulls has nothing worth measuring
    assert measured["missing"].null_rate == 1.0  # all-null, kept for the null rate alone
    assert set(probes) == {feature.name for feature in features}  # every column, typed or not


def test_a_column_with_nothing_to_measure_is_not_reported_as_an_error():
    # Absence from `stats` is the normal sparse case. Only a *failure* earns an error, or the two
    # would be indistinguishable and the guard would cry wolf on every well-formed struct column.
    measured, probes, errors = measure_columns([_feature("s", "struct")], [{"s": {"a": 1}}])
    assert measured == {} and errors == []
    assert "s" in probes


@pytest.mark.parametrize(
    "text",
    [
        "",
        "plain ascii",
        "tabs\tand\nnewlines\r\f\v",
        "café naïve",  # non-ascii letters, ascii spaces
        "a b",  # NO-BREAK SPACE: \s matches it, counting six ascii literals would not
        "　  ",  # ideographic space, line separator, paragraph separator
        "\U0001f600 emoji beyond the BMP",  # 4-byte codepoint: byte overhead != character count
        "mixed   café\tend",
    ],
)
def test_quality_fast_paths_are_the_same_measurement_as_the_regexes(text):
    # The whole risk in this change. `str.count` over six ascii literals is not `\s`, and
    # `len(encode) - len` is not a character count -- either would be faster while quietly
    # measuring something else. The fast path is only allowed where it is provably identical.
    assert _whitespace_count(text) == sum(1 for _ in _WHITESPACE_RUN.finditer(text))
    assert _non_ascii_count(text) == sum(1 for _ in _NON_ASCII_RUN.finditer(text))


def test_quality_sample_is_bounded_strided_and_deterministic():
    under = [f"r{i}" for i in range(_QUALITY_SAMPLE_ROWS)]
    assert _quality_sample(under) is under  # nothing to sample: measured in full

    over = [f"r{i}" for i in range(_QUALITY_SAMPLE_ROWS * 3)]
    sample = _quality_sample(over)
    assert len(sample) <= _QUALITY_SAMPLE_ROWS + 1
    assert _quality_sample(over) == sample  # no RNG, so no seed to record and no run-to-run drift
    # Spans the column rather than its head: the last sampled row is near the end.
    assert over.index(sample[-1]) >= len(over) - 3


def test_quality_is_measured_across_the_column_not_its_head(monkeypatch):
    # Corruption confined to the second half. A head sample would report a clean column; a stride
    # sees it. This is why the sample is strided and not simply the first N rows.
    monkeypatch.setattr(stats_module, "_QUALITY_SAMPLE_ROWS", 4)
    values = ["ordinary sentence"] * 8 + ["aaaaaaaaaaaa"] * 8
    quality = _stats([_feature("t", "string")], _rows("t", values))["t"].quality
    assert quality.repetition_score > 0.4


def test_a_column_under_the_bound_is_measured_exactly(monkeypatch):
    monkeypatch.setattr(stats_module, "_QUALITY_SAMPLE_ROWS", 100)
    values = ["ordinary sentence"] * 9 + ["aaaaaaaaaaaa"]
    quality = _stats([_feature("t", "string")], _rows("t", values))["t"].quality
    assert quality.repetition_score == pytest.approx(0.1)  # exactly one corrupt row in ten


def test_cardinality_is_counted_while_the_column_is_a_vocabulary():
    labels = _stats([_feature("c", "string")], _rows("c", ["yes", "no", "yes", "no"]))
    assert labels["c"].categorical.distinct_count == 2

    # Still counted well past the point where every value is distinct: it is size, not repetition,
    # that decides whether a column is a vocabulary.
    many = _stats([_feature("t", "string")], _rows("t", [f"unique-{i}" for i in range(50)]))
    assert many["t"].categorical.distinct_count == 50


def test_cardinality_stops_at_too_many_values():
    over = _stats([_feature("t", "string")], _rows("t", [f"v{i}" for i in range(_MAX_VOCABULARY_VALUES + 1)]))
    assert over["t"].categorical is None  # absence is the claim: not a vocabulary
    assert over["t"].text is not None  # ...but the column is still measured

    at_cap = _stats([_feature("t", "string")], _rows("t", [f"v{i}" for i in range(_MAX_VOCABULARY_VALUES)]))
    assert at_cap["t"].categorical.distinct_count == _MAX_VOCABULARY_VALUES


def test_one_long_value_settles_it_without_counting():
    # The rule that does the real work: a vocabulary member is short by nature, so a single long
    # value proves the column is not one -- on sight, rather than after a thousand of them.
    values = ["yes", "no", "x" * (_MAX_VOCABULARY_VALUE_CHARS + 1)]
    assert _stats([_feature("t", "string")], _rows("t", values))["t"].categorical is None

    still_short = ["yes", "no", "x" * _MAX_VOCABULARY_VALUE_CHARS]
    assert _stats([_feature("t", "string")], _rows("t", still_short))["t"].categorical.distinct_count == 3


def test_cardinality_stops_on_total_bytes_before_the_count():
    # Values individually short enough and few enough, but heavy in aggregate. Without this bound
    # the other two would admit 1024 x 256 chars -- four times the byte budget.
    values = [f"{i:04d}" + "x" * 200 for i in range(_MAX_VOCABULARY_BYTES // 200)]
    assert len(values) < _MAX_VOCABULARY_VALUES  # the count bound is not what stops this
    assert _stats([_feature("t", "string")], _rows("t", values))["t"].categorical is None


def test_derive_stats_never_quotes_values():
    # Quoting needs a role, and roles are not assigned when stats are measured. Filling them in
    # afterwards rather than redacting means a skipped pass stores nothing instead of leaking.
    stats = _stats([_feature("c", "string")], _rows("c", ["yes", "no"]))
    assert stats["c"].categorical.values is None


def test_bool_column_gets_a_measured_class_balance():
    stats = _stats([_feature("label", "bool")], _rows("label", [True, False, True]))
    assert stats["label"].categorical.distinct_count == 2


# --- numeric -------------------------------------------------------------------------------------


def test_numeric_stats_and_cardinality():
    stats = _stats([_feature("n", "int64")], _rows("n", [0, 4, 2, 2, 3]))["n"]
    assert (stats.numeric.min, stats.numeric.max) == (0.0, 4.0)
    assert stats.numeric.mean == 2.2
    assert stats.categorical.distinct_count == 4  # {0, 2, 3, 4}


def test_numeric_cardinality_counts_without_quoting():
    stats = _stats([_feature("n", "int64")], _rows("n", [1, 2, 3]))["n"]
    assert stats.categorical.distinct_count == 3
    assert stats.categorical.values is None


def test_numeric_stats_ignore_non_finite_values():
    # NaN / +-inf poison min/max/mean and serialize to JSON null, which then fails to re-validate
    # against NumericStats' required floats -- making the whole profile unreadable. Drop them.
    values = [1.0, float("nan"), 3.0, float("inf"), float("-inf"), 5.0]
    stats = _stats([_feature("n", "float64")], _rows("n", values))["n"]
    assert (stats.numeric.min, stats.numeric.max, stats.numeric.mean) == (1.0, 5.0, 3.0)
    ColumnStats.model_validate_json(stats.model_dump_json())  # round-trips: no NaN/inf leaked into JSON


def test_numeric_all_non_finite_yields_no_numeric_summary():
    stats = _stats([_feature("n", "float64")], _rows("n", [float("nan"), float("inf")]))
    assert stats.get("n") is None or stats["n"].numeric is None


# --- messages ------------------------------------------------------------------------------------


def test_message_stats_shape_signals():
    rows = [
        {"m": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello there"}]},
        {"m": [{"role": "user", "content": "again"}, {"role": "assistant", "content": "yes"}]},
    ]
    stats = _stats([_feature("m", "messages")], rows)["m"]
    assert stats.messages.turns.max == 2
    assert stats.messages.roles_seen == ["user", "assistant"]  # first-seen order
    assert stats.messages.ends_with_assistant_rate == 1.0
    assert stats.messages.valid_alternation_rate == 1.0
    assert stats.messages.has_tool_calls is False


def test_message_stats_detects_tool_calls_and_user_ending():
    rows = [{"m": [{"role": "user", "content": "run"}, {"role": "assistant", "tool_calls": [{"id": "1"}]}]}]
    stats = _stats([_feature("m", "messages")], rows)["m"]
    assert stats.messages.has_tool_calls is True
    assert stats.messages.ends_with_assistant_rate == 1.0  # last turn is the assistant tool call


def test_message_ends_with_user_turn_is_prompt_only_signal():
    rows = [{"m": [{"role": "user", "content": "solve"}]}]
    stats = _stats([_feature("m", "messages")], rows)["m"]
    assert stats.messages.ends_with_assistant_rate == 0.0


def test_message_stats_read_sharegpt_from_value():
    rows = [{"m": [{"from": "human", "value": "hi"}, {"from": "gpt", "value": "hello there"}]}]
    stats = _stats([_feature("m", "messages")], rows)["m"]
    assert stats.messages.roles_seen == ["human", "gpt"]  # verbatim, not normalized
    assert stats.messages.content_chars.max == len("hi") + len("hello there")
    assert stats.messages.ends_with_assistant_rate == 1.0  # "gpt" is the responder turn


def test_assistant_equivalent_roles_count_as_the_training_target():
    # Matching only the literal "assistant" made every other convention look prompt-only.
    for responder in ("assistant", "gpt", "bot", "model", "AI"):
        rows = [{"m": [{"role": "user", "content": "q"}, {"role": responder, "content": "a"}]}]
        stats = _stats([_feature("m", "messages")], rows)["m"]
        assert stats.messages.ends_with_assistant_rate == 1.0, responder


def test_non_string_role_does_not_break_measurement():
    # roles_seen is typed list[str]; a numeric role used to raise a ValidationError from inside the
    # one stage the pipeline did not guard, aborting the whole profile.
    rows = [{"m": [{"role": 1, "content": "hi"}]}]
    stats = _stats([_feature("m", "messages")], rows)["m"]
    assert stats.messages.roles_seen == ["1"]


def test_declared_but_unset_tool_calls_is_not_tool_use():
    # parquet materializes every declared struct field, so `"tool_calls" in message` reported tool
    # use for any schema that merely declares the field.
    rows = [{"m": [{"role": "user", "content": "hi", "tool_calls": None}]}]
    stats = _stats([_feature("m", "messages")], rows)["m"]
    assert stats.messages.has_tool_calls is False


def test_message_content_parts_tolerate_non_string_text():
    # A VLM-style content part whose "text" key is present but not a string must not crash measurement.
    rows = [{"m": [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": None}]}]}]
    stats = _stats([_feature("m", "messages")], rows)["m"]
    assert stats.messages.content_chars.max == 0  # no measurable text, and no crash


# --- sparsity and null rate ----------------------------------------------------------------------


def test_unmeasured_dtypes_are_omitted():
    features = [_feature("s", "struct"), _feature("j", "json")]
    rows = [{"s": {"a": 1}, "j": object()}]
    assert _stats(features, rows) == {}


def test_null_rate_is_reported():
    stats = _stats([_feature("t", "string")], _rows("t", ["a", None, "c", None]))["t"]
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


# --- quoting a controlled vocabulary ---------------------------------------------------------------


def _quoted(name, dtype, values, role):
    """Run the real two-step: measure, then quote by role, and report what was stored."""
    feature = _feature(name, dtype)
    feature.semantic_role = role
    rows = _rows(name, values)
    stats = _stats([feature], rows)
    quote_enumerations([feature], stats, rows)
    return stats[name].categorical.values


def test_quotes_a_controlled_vocabulary_role():
    assert _quoted("label", "bool", [True, False, True], "label") == ["False", "True"]
    assert _quoted("source", "string", ["gsm8k", "math", "gsm8k"], "provenance") == ["gsm8k", "math"]
    assert _quoted("category", "string", ["code", "math"], "meta") == ["code", "math"]


def test_refuses_to_quote_free_text_however_few_distinct_values():
    # The failure the cardinality gate could not see: in a tiny dataset every column holds under the
    # cap, so a whole column of prompts was quotable and the profile stored it verbatim.
    rows = ["Patient Alice, SSN 123-45-6000", "Patient Bob, SSN 123-45-6001"]
    assert _quoted("prompt", "string", rows, "prompt") is None
    assert _quoted("completion", "string", rows, "completion") is None
    assert _quoted("chosen", "string", rows, "chosen") is None


def test_refuses_to_quote_an_unroled_column():
    # An unrecognized column is unknown, which here is the same as free text: an allowlist means it
    # fails to silence rather than to exposure.
    assert _quoted("mystery", "string", ["a", "b"], None) is None


def test_refuses_to_quote_a_vocabulary_larger_than_the_cap():
    # Role grants permission; cardinality still bounds the size, so a provenance column holding a
    # URL list is not mistaken for an enumeration.
    assert _quoted("source", "string", [f"src-{i}" for i in range(40)], "provenance") is None
