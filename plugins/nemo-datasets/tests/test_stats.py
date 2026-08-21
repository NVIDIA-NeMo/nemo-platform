# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for per-column statistics."""

import math

import pytest
from nemo_datasets_plugin.profiler import stats as stats_module
from nemo_datasets_plugin.profiler.stats import (
    _MAX_VOCABULARY_BYTES,
    _MAX_VOCABULARY_VALUE_CHARS,
    _MAX_VOCABULARY_VALUES,
    _NON_ASCII_RUN,
    _WHITESPACE_RUN,
    _non_ascii_count,
    _whitespace_count,
    measure_columns,
    quote_enumerations,
)
from nemo_platform_plugin.files.dataset_profile import ColumnStats, FeatureSchema


def _stats(features, rows):
    """Statistics only. Asserts nothing failed: these tests measure values, not the guard, and a
    swallowed exception would surface here as a confusing KeyError instead of its own message."""
    measured = measure_columns(features, rows)
    assert not measured.errors, measured.errors
    return measured.stats


def _probes(features, rows):
    """The content probes alone. `measure_columns` measures both in one pass; these tests want one."""
    return measure_columns(features, rows).probes


def _feature(name, dtype):
    return FeatureSchema(name=name, dtype=dtype)


def _rows(name, values):
    return [{name: value} for value in values]


# --- length histogram ----------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 1, 31, 32, 33, 63, 64, 255, 256, 1_000, 1_300, 65_535, 1_000_000, 33_554_432])
def test_every_length_lands_in_a_bucket_that_contains_it(value):
    # The bounds are what a quantile is read off, so they have to invert the bucketing exactly. A
    # bucket whose range does not contain its own values would report a plausible wrong number.
    low, high = stats_module._bucket_bounds(stats_module._length_bucket(value))
    assert low <= value < high


def test_short_lengths_are_recorded_exactly():
    # Below the slice count every length gets its own counter. That is what keeps the small fixtures
    # in this file exact, and it is why a column of short strings loses nothing to bucketing.
    hist = stats_module._LengthHistogram()
    for n in range(stats_module._HISTOGRAM_SLICES):
        hist.add(n)
    quantiles = hist.quantiles()
    assert (quantiles.p50, quantiles.p95, quantiles.p99, quantiles.max) == (15, 30, 31, 31)


def test_quantiles_stay_within_the_bound_on_a_heavy_tail():
    # The shape that matters: most rows short, a thin long tail. It is also the shape a mean cannot
    # describe, which is why the distribution is carried at all.
    values = [10] * 5000 + [200] * 3000 + [4000] * 1500 + [90_000] * 500
    hist = stats_module._LengthHistogram()
    for value in values:
        hist.add(value)
    quantiles = hist.quantiles()

    ordered = sorted(values)
    for percentile, got in ((50, quantiles.p50), (95, quantiles.p95), (99, quantiles.p99)):
        want = ordered[min(math.ceil(percentile / 100 * len(ordered)), len(ordered)) - 1]
        assert abs(got - want) / want <= 0.02, (percentile, want, got)
    assert quantiles.max == 90_000  # exact, never rounded to a bucket
    assert quantiles.p50 <= quantiles.p95 <= quantiles.p99 <= quantiles.max


def test_an_empty_histogram_reports_zeros():
    quantiles = stats_module._LengthHistogram().quantiles()
    assert (quantiles.p50, quantiles.p95, quantiles.p99, quantiles.max) == (0, 0, 0, 0)


def test_roles_seen_stops_growing():
    # Fed straight from row content, so without a bound one malformed column could hold a string per
    # message -- and membership is checked against the list, so it is quadratic as well as unbounded.
    rows = _rows("m", [[{"role": f"role-{i}", "content": "x"}] for i in range(stats_module._MAX_ROLES_SEEN * 3)])
    measured = _stats([_feature("m", "messages")], rows)["m"]
    assert len(measured.messages.roles_seen) == stats_module._MAX_ROLES_SEEN
    # The rates still count every row: only the vocabulary of roles is bounded, not the measurement.
    assert measured.messages.turns.max == 1


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
        lambda feature, expected_rows=None: (
            Boom() if feature.name == "bad" else real_accumulator_for(feature, expected_rows)
        ),
    )

    features = [_feature("good", "string"), _feature("bad", "string")]
    result = measure_columns(features, [{"good": "x", "bad": "y"}])
    measured, probes, errors = result.stats, result.probes, result.errors

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

    probes, errors = measure_columns(features, rows).probes, measure_columns(features, rows).errors

    assert errors == []
    assert probes == _probes(features, rows)  # probes come off the base class


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
    result = measure_columns(features, rows)
    measured, probes, errors = result.stats, result.probes, result.errors

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
    result = measure_columns([_feature("s", "struct")], [{"s": {"a": 1}}])
    measured, probes, errors = result.stats, result.probes, result.errors
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


def test_the_quality_sample_does_not_alias_against_periodic_data(monkeypatch):
    # A set that round-robins over sources, or carries k responses per prompt, is periodic by
    # construction. An evenly-spaced step whose spacing shares a factor with that period samples one
    # phase and only that phase: 500,000 rows with every tenth corrupt gave a step of ten and a
    # repetition score of 1.000 against a truth of 0.100. A contiguous block longer than the period
    # sees every phase of it, whatever the period turns out to be.
    monkeypatch.setattr(stats_module, "_QUALITY_SAMPLE_ROWS", 1_000)
    monkeypatch.setattr(stats_module, "_QUALITY_SAMPLE_BLOCK", 64)
    period, n = 10, 100_000
    values = ["aaaaaaaaaaaa" if i % period == 0 else "the quick brown fox" for i in range(n)]

    known = stats_module.StringAccumulator(n)
    known.update(values)
    assert known.finalize()[0].quality.repetition_score == pytest.approx(1 / period, abs=0.02)

    unknown = stats_module.StringAccumulator(None)
    unknown.update(values)
    assert unknown.finalize()[0].quality.repetition_score == pytest.approx(1 / period, abs=0.02)


def test_a_known_row_count_strides_evenly_and_deterministically(monkeypatch):
    # With the row count known up front the stride is fixed, so the sample is spread evenly over the
    # whole column -- and two runs over the same bytes agree, which is why no RNG is involved.
    monkeypatch.setattr(stats_module, "_QUALITY_SAMPLE_ROWS", 10)
    values = ["clean text"] * 100 + ["aaaaaaaaaaaa"] * 100

    def quality(expected_rows):
        acc = stats_module.StringAccumulator(expected_rows)
        acc.update(values)
        return acc.finalize()[0].quality.repetition_score

    assert quality(len(values)) == quality(len(values))  # deterministic
    # Half the column is corrupt and the stride spans it, so the estimate lands near a half.
    assert 0.4 <= quality(len(values)) <= 0.6


def test_an_unknown_row_count_thins_as_it_goes_and_stays_unbiased(monkeypatch):
    # No footer, so no length to spread blocks over: the cycle starts at one block and doubles as the
    # sample fills. Sampling is then densest at the head, which would skew the answer -- weighting
    # each sampled row by the rows its block stood for is what corrects it.
    monkeypatch.setattr(stats_module, "_QUALITY_SAMPLE_ROWS", 40)
    monkeypatch.setattr(stats_module, "_QUALITY_SAMPLE_BLOCK", 8)
    values = ["clean text"] * 500 + ["aaaaaaaaaaaa"] * 500

    acc = stats_module.StringAccumulator(None)
    acc.update(values)
    score = acc.finalize()[0].quality.repetition_score

    assert acc._cycle > acc._block  # it did thin
    assert 0.35 <= score <= 0.65  # ...and still found roughly half the column corrupt


def test_quality_is_measured_across_the_column_not_its_head(monkeypatch):
    # Corruption confined to the second half. A head sample would report a clean column; a stride
    # sees it. This is why the sample is strided and not simply the first N rows.
    monkeypatch.setattr(stats_module, "_QUALITY_SAMPLE_ROWS", 4)
    values = ["ordinary sentence"] * 8 + ["aaaaaaaaaaaa"] * 8
    quality = _stats([_feature("t", "string")], _rows("t", values))["t"].quality
    assert quality.repetition_score > 0.4


def test_a_sparse_column_is_sampled_across_itself_not_across_the_partition(monkeypatch):
    """The cycle strides over present strings; `expected_rows` counts the partition's rows.

    On a mostly-null column those are different units, and a cycle sized in the wrong one never
    completes a revolution: only the first block is ever eligible and the sample collapses onto the
    head. A column of 2,000 values in a 200,000-row partition measured its first 512 and called a
    half-degenerate column perfectly clean.
    """
    monkeypatch.setattr(stats_module, "_QUALITY_SAMPLE_ROWS", 100)
    monkeypatch.setattr(stats_module, "_QUALITY_SAMPLE_BLOCK", 8)
    partition_rows, every = 4_000, 20
    present = ["clean text"] * 100 + ["aaaaaaaaaaaa"] * 100  # 200 values, corruption in the tail
    values = [present[i // every] if i % every == 0 else None for i in range(partition_rows)]

    acc = stats_module.StringAccumulator(partition_rows)
    acc.update(values)

    assert acc._seen == len(present)
    # Retargeted from the partition's 4,000 rows down to the 200 values the column actually holds,
    # which is what keeps the stride wrapping instead of stalling inside its first block.
    assert acc._cycle < stats_module._quality_cycle(partition_rows)
    assert acc.finalize()[0].quality.repetition_score == pytest.approx(0.5, abs=0.05)


def test_a_sparse_column_measures_the_same_declared_or_inferred(monkeypatch):
    """The deferred accumulator drives the string one directly, bypassing the row counter the
    retarget reads. It hands the count over, so both paths place the sample in the same rows."""
    monkeypatch.setattr(stats_module, "_QUALITY_SAMPLE_ROWS", 100)
    monkeypatch.setattr(stats_module, "_QUALITY_SAMPLE_BLOCK", 8)
    partition_rows, every = 4_000, 20
    present = ["clean text"] * 100 + ["aaaaaaaaaaaa"] * 100
    values = [present[i // every] if i % every == 0 else None for i in range(partition_rows)]

    declared = stats_module.StringAccumulator(partition_rows)
    declared.update(values)
    inferred = stats_module.DeferredAccumulator("t", partition_rows)
    inferred.update(values)

    assert inferred.feature().dtype == "string"
    assert inferred.finalize()[0].quality == declared.finalize()[0].quality


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
    probes = _probes(features, rows)

    assert set(probes) == {"q", "a"}
    assert probes["a"].texts == 2
    assert probes["a"].extractable_answer == 1
    assert probes["q"].extractable_answer == 0


def test_probes_read_the_final_turn_of_a_chat_column():
    rows = [{"m": [{"role": "user", "content": "q"}, {"role": "assistant", "content": "steps #### 7"}]}]
    probes = _probes([_feature("m", "messages")], rows)
    assert probes["m"].texts == 1
    assert probes["m"].extractable_answer == 1


def test_probes_read_the_sharegpt_message_spelling():
    # {from, value} is handled in schema derivation and message stats; reading only {role, content}
    # here cost every ShareGPT-shaped dataset its verifiability.
    rows = [{"m": [{"from": "human", "value": "q"}, {"from": "gpt", "value": "steps #### 7"}]}]
    probes = _probes([_feature("m", "messages")], rows)
    assert probes["m"].texts == 1
    assert probes["m"].extractable_answer == 1


def test_probes_count_non_empty_across_container_dtypes():
    # `non_empty` is what a ground_truth column's coverage is measured from, and a verification
    # target is just as often a list or struct as a string.
    features = [_feature("gt", "list")]
    rows = [{"gt": [{"in": "1"}]}, {"gt": []}, {"gt": None}]
    probes = _probes(features, rows)
    assert probes["gt"].rows == 3
    assert probes["gt"].non_empty == 1


def test_probes_detect_embedded_transcripts():
    rows = [{"c": "\n\nHuman: hi\n\nAssistant: hello"}, {"c": "plain prose"}]
    probes = _probes([_feature("c", "string")], rows)
    assert probes["c"].transcript_marker == 1


# --- quoting a controlled vocabulary ---------------------------------------------------------------


def _quoted(name, dtype, values, role):
    """Run the real two-step: measure, then quote by role, and report what was stored."""
    feature = _feature(name, dtype)
    feature.semantic_role = role
    rows = _rows(name, values)
    measured = measure_columns([feature], rows)
    quote_enumerations([feature], measured.stats, measured.vocabularies)
    return measured.stats[name].categorical.values


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
