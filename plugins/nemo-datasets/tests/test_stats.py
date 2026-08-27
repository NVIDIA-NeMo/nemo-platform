# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for per-column statistics."""

import pytest
from nemo_datasets_plugin.profiler.stats import (
    _MAX_ROLE_CHARS,
    _MAX_VOCABULARY_BYTES,
    _MAX_VOCABULARY_VALUE_CHARS,
    _MAX_VOCABULARY_VALUES,
    RoutedAccumulator,
    RowFold,
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


def test_non_finite_floats_are_not_distinct_values():
    # NaN compares unequal to itself, so a set counts every one as its own distinct value: a parquet
    # float column of NaNs reported its own row count as its cardinality, and past the vocabulary
    # bound it saturated and took the column's whole `categorical` block with it. Dropped from the
    # vocabulary for the same reason they are already dropped from the extrema.
    stats = _stats([_feature("score", "float64")], _rows("score", [float("nan") for _ in range(100)]))
    assert stats["score"].categorical.distinct_count == 0
    assert stats["score"].numeric is None


def test_finite_values_are_still_counted_alongside_non_finite_ones():
    values = [1.0, 2.0, 1.0, float("nan"), float("inf"), float("-inf")]
    stats = _stats([_feature("score", "float64")], _rows("score", values))
    assert stats["score"].categorical.distinct_count == 2
    assert (stats["score"].numeric.min, stats["score"].numeric.max) == (1.0, 2.0)


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


def test_a_role_too_long_to_be_a_role_is_truncated():
    # `roles_seen` is fed straight from row content and was the one place unbounded row values
    # reached the profile -- outside the role gate the contract calls its only exception, and with
    # no per-value cap where `_Vocabulary` has one. A mis-shaped export put whole message bodies in
    # it. Truncated rather than dropped: the length is itself the finding.
    rows = _rows("messages", [[{"role": "u" * 3200, "content": "hi"}, {"role": "assistant", "content": "yo"}]])
    stats = _stats([_feature("messages", "messages")], rows)

    roles = stats["messages"].messages.roles_seen
    assert max(len(role) for role in roles) == _MAX_ROLE_CHARS
    assert "assistant" in roles  # a real role is untouched


def test_message_stats_read_the_from_value_spelling():
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


def test_probes_read_the_from_value_message_spelling():
    # {from, value} is handled in schema derivation and message stats; reading only {role, content}
    # here cost every dataset spelled that way its verifiability.
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


def test_the_fold_reports_the_cap_it_hit_at_either_level():
    from nemo_datasets_plugin.profiler.schema import MAX_COLUMNS

    # Reported by the fold that stopped, not read off the length of what came back: a partition with
    # exactly MAX_COLUMNS columns is complete and the same length as one that was cut short.
    wide = RowFold(None)
    wide.update([{f"c{i}": i for i in range(MAX_COLUMNS + 500)}])
    features, _ = wide.finalize()
    assert len(features) == MAX_COLUMNS
    assert wide.columns_were_capped() is True

    # And one level down, which used to defeat the cap entirely: the top level stayed at one column
    # while a fold was minted per row inside `meta`.
    nested = RowFold(None)
    for i in range(MAX_COLUMNS + 500):
        nested.update([{"meta": {f"k{i}": 1}}])
    features, _ = nested.finalize()
    assert len(features) == 1
    assert len(features[0].fields) == MAX_COLUMNS
    assert nested.columns_were_capped() is True

    ordinary = RowFold(None)
    ordinary.update([{"a": 1, "b": {"x": 1}}])
    ordinary.finalize()
    assert ordinary.columns_were_capped() is False


def test_asking_for_the_schema_mid_stream_does_not_freeze_it():
    # The folded schema is kept once asked for, because `finalize` asks three times -- the feature
    # itself, then `_stat_blocks` and `vocabulary`, each needing the dtype to pick a measurement --
    # and every ask recurses the column's whole nested schema. It is dropped on each batch, so the
    # kept value can never be older than the data behind it.
    fold = RowFold(None)
    fold.update([{"a": 1}])
    assert fold._accumulators["a"].feature().dtype == "int64"
    fold.update([{"a": "x"}])
    assert fold._accumulators["a"].feature().dtype == "json"
    features, _ = fold.finalize()
    assert features[0].dtype == "json"


# --- routing -------------------------------------------------------------------------------------

# A column's values are routed to their measurements by exact class, which cannot place a subclass
# of a builtin. Those batches fall back to `isinstance`. The two are one routing decision taken two
# ways, so these tests pin the fallback's reason to exist and then hold the two to the same answer.


class _StrSubclass(str):
    """A string no exact class can place. JSON never produces one; a caller handing rows to the SDK
    from python can, and a pandas or pyarrow extension type is the same shape of problem."""


class _ListSubclass(list):
    pass


def _fold_rows(rows, batch, observe):
    """Fold `rows`, `batch` at a time, with `observe` as the router."""
    original = RoutedAccumulator._observe
    RoutedAccumulator._observe = observe
    try:
        fold = RowFold(None)
        for start in range(0, len(rows), batch):
            fold.update(rows[start : start + batch])
        return fold.finalize()
    finally:
        RoutedAccumulator._observe = original


_ROUTES = [RoutedAccumulator._observe, RoutedAccumulator._observe_by_isinstance]
_ROUTE_IDS = ["exact-class", "isinstance"]

_MIXED = [
    {"text": "hello world", "n": 1, "flag": True, "meta": {"k": 1}, "turns": [{"role": "user", "content": "hi"}]},
    {
        "text": "",
        "n": 2.5,
        "flag": False,
        "meta": {"k": 2, "j": "x"},
        "turns": [{"role": "assistant", "content": "yo"}],
    },
    {"text": _StrSubclass("subclassed"), "n": None, "late": "a column no earlier row mentioned"},
    {"text": None, "n": 4, "flag": None, "meta": {"k": None}, "turns": []},
    {"disagrees": 1},
    {"disagrees": "one"},
    {"plain": [1, 2, 3]},
    {"plain": ["a"]},
]


@pytest.mark.parametrize("observe", _ROUTES, ids=_ROUTE_IDS)
def test_a_string_subclass_still_reaches_the_string_measurement(observe):
    # The fallback's whole reason to exist. A draft that folded unplaceable values in *after* the
    # partition dropped them from the string measurement outright, and did it silently: the column
    # kept its dtype and its null rate, so only the missing length quantiles showed it.
    features, measured = _fold_rows(_rows("a", [_StrSubclass("hello"), "world"]), 8, observe)
    assert features[0].dtype == "string"
    assert measured.stats["a"].text.chars.max == 5
    assert measured.vocabularies["a"] == {"hello", "world"}


@pytest.mark.parametrize("observe", _ROUTES, ids=_ROUTE_IDS)
def test_a_list_subclass_still_reaches_the_messages_measurement(observe):
    turns = _ListSubclass([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}])
    features, measured = _fold_rows(_rows("m", [turns]), 8, observe)
    assert features[0].dtype == "messages"
    assert measured.stats["m"].messages.roles_seen == ["user", "assistant"]


@pytest.mark.parametrize("observe", _ROUTES, ids=_ROUTE_IDS)
def test_ints_and_floats_widen_and_every_value_is_measured(observe):
    # The partition folds ints and floats as two batches rather than one interleaved list, which is
    # only sound because an accumulator handed a column in pieces answers as one handed all of it.
    features, measured = _fold_rows(_rows("n", [1, 2.5, 3, 4.5]), 8, observe)
    assert features[0].dtype == "float64"
    numeric = measured.stats["n"].numeric
    assert (numeric.min, numeric.max, numeric.mean) == (1.0, 4.5, 2.75)


@pytest.mark.parametrize("observe", _ROUTES, ids=_ROUTE_IDS)
def test_bools_are_never_folded_in_with_ints(observe):
    features, measured = _fold_rows(_rows("flag", [True, False, True]), 8, observe)
    assert features[0].dtype == "bool"
    assert measured.stats["flag"].numeric is None
    assert measured.stats["flag"].categorical.distinct_count == 2
    # And a column holding both is two shapes, not a numeric column with two odd values in it.
    features, _ = _fold_rows(_rows("flag", [True, 3]), 8, observe)
    assert features[0].dtype == "json"


@pytest.mark.parametrize("observe", _ROUTES, ids=_ROUTE_IDS)
def test_disagreeing_types_widen_to_json_and_report_no_stats(observe):
    features, measured = _fold_rows(_rows("a", [1, "x"]), 8, observe)
    assert features[0].dtype == "json"
    assert "a" not in measured.stats


def test_ordinary_rows_never_reach_the_fallback():
    # Guards every test above. The partition and the fallback agreeing proves nothing if the
    # partition is never the one that ran.
    reached = []
    original = RoutedAccumulator._observe_by_isinstance

    def spy(self, present):
        reached.append(present)
        return original(self, present)

    RoutedAccumulator._observe_by_isinstance = spy
    try:
        _fold_rows(_MIXED[:2] + _MIXED[3:], 3, RoutedAccumulator._observe)
    finally:
        RoutedAccumulator._observe_by_isinstance = original
    assert reached == []


@pytest.mark.parametrize("batch", [1, 3, 1000], ids=["per-row", "split", "whole"])
def test_both_routes_agree_whatever_the_batch_size(batch):
    # Compared over everything `finalize` returns, not just the stats: the partition is rebuilt per
    # batch, and a draft that agreed on dtypes disagreed on vocabularies.
    assert _fold_rows(_MIXED, batch, _ROUTES[0]) == _fold_rows(_MIXED, batch, _ROUTES[1])


def test_batching_does_not_change_the_answer():
    assert _fold_rows(_MIXED, 1, _ROUTES[0]) == _fold_rows(_MIXED, 1000, _ROUTES[0])
