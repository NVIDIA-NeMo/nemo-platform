# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for classification: role assignment, format/prompt-form axes, and dataset type."""

from nemo_datasets_plugin.profiler.classify import PrefixPairFold, classify
from nemo_datasets_plugin.profiler.stats import measure_columns
from nemo_platform_plugin.files.dataset_profile import (
    CategoricalStats,
    ColumnStats,
    FeatureSchema,
    MessageStats,
    Quantiles,
)


def _probes(features, rows):
    return measure_columns(features, rows).probes


def classify_rows(features, stats, rows, **kwargs):
    """Classify from rows the way the pipeline does: fold first, then interpret the folds."""
    prefix = PrefixPairFold()
    prefix.update(rows)
    return classify(features, stats, probes=_probes(features, rows), prefix_pair=prefix.result(), **kwargs)


def _f(name, dtype):
    return FeatureSchema(name=name, dtype=dtype)


def _binary_column():
    """A column observed to hold two distinct values -- what makes an int/bool a real label."""
    return ColumnStats(categorical=CategoricalStats(distinct_count=2))


def _messages_column(ends_with_assistant_rate):
    q = Quantiles(p50=1, p95=1, p99=1, max=1)
    return ColumnStats(
        messages=MessageStats(
            turns=q,
            content_chars=q,
            roles_seen=["user", "assistant"],
            ends_with_assistant_rate=ends_with_assistant_rate,
            valid_alternation_rate=1.0,
        )
    )


# --- roles ---------------------------------------------------------------------------------------


def test_roles_assigned_by_name_and_dtype():
    features = [_f("prompt", "string"), _f("response", "string"), _f("helpfulness", "int64")]
    classify(features, {})
    assert [f.semantic_role for f in features] == ["prompt", "completion", "score"]


def test_dtype_gate_rejects_mismatched_aliases():
    # "label" only counts as a label when boolean; a string column named "messages" is not messages.
    features = [_f("label", "string"), _f("messages", "string")]
    classify(features, {})
    assert all(f.semantic_role is None for f in features)


def test_physical_name_differs_from_role():
    features = [_f("response", "string")]
    classify(features, {})
    assert features[0].semantic_role == "completion"


# --- format axis ---------------------------------------------------------------------------------


def test_format_standard_conversational_and_mixed():
    assert classify([_f("prompt", "string"), _f("completion", "string")], {}).format == "standard"
    assert classify([_f("prompt", "messages"), _f("completion", "messages")], {}).format == "conversational"
    mixed = [_f("prompt", "string"), _f("chosen", "messages"), _f("rejected", "messages")]
    assert classify(mixed, {}).format == "mixed"


# --- dataset type + prompt form ------------------------------------------------------------------


def test_prompt_completion_with_explicit_prompt():
    result = classify([_f("prompt", "string"), _f("completion", "string")], {})
    assert result.dataset_type == "prompt_completion"
    assert result.prompt_form == "explicit"


def test_preference_pair_is_implicit_without_a_prompt():
    result = classify([_f("chosen", "string"), _f("rejected", "string")], {})
    assert result.dataset_type == "preference_pair"
    assert result.prompt_form == "implicit"


def test_scored_response_beats_prompt_completion():
    features = [
        _f("prompt", "string"),
        _f("response", "string"),
        _f("helpfulness", "int64"),
        _f("correctness", "int64"),
    ]
    assert classify(features, {}).dataset_type == "scored_response"


def test_unpaired_preference_accepts_a_boolean_label():
    features = [_f("prompt", "string"), _f("completion", "string"), _f("label", "bool")]
    assert classify(features, {}).dataset_type == "unpaired_preference"


def test_unpaired_preference_accepts_a_binary_integer_label():
    # 0/1 is the usual on-disk encoding; requiring a bool made unpaired_preference unreachable for
    # most real datasets.
    features = [_f("prompt", "string"), _f("completion", "string"), _f("label", "int64")]
    stats = {"label": ColumnStats(categorical=CategoricalStats(distinct_count=2))}
    assert classify(features, stats).dataset_type == "unpaired_preference"
    assert features[2].semantic_role == "label"


def test_wide_integer_label_is_not_a_preference_label():
    # A multi-class index or a rating is a different claim from a binary preference.
    features = [_f("prompt", "string"), _f("completion", "string"), _f("label", "int64")]
    stats = {"label": ColumnStats(categorical=CategoricalStats(distinct_count=7))}
    assert classify(features, stats).dataset_type == "prompt_completion"
    assert features[2].semantic_role is None


# --- rank ------------------------------------------------------------------------------------


def test_rank_needs_something_to_rank():
    # A lone numeric column named "rank" used to short-circuit every more specific structure.
    features = [_f("rank", "int64")]
    assert classify(features, {}).dataset_type == "unknown"


def test_rank_does_not_override_a_preference_pair():
    features = [_f("chosen", "string"), _f("rejected", "string"), _f("rank", "int64")]
    assert classify(features, {}).dataset_type == "preference_pair"


def test_rank_does_not_override_scored_responses():
    features = [_f("prompt", "string"), _f("response", "string"), _f("helpfulness", "int64"), _f("rank", "int64")]
    assert classify(features, {}).dataset_type == "scored_response"


def test_rank_alongside_a_completion_is_ranked_responses():
    features = [_f("prompt", "string"), _f("completion", "string"), _f("rank", "int64")]
    assert classify(features, {}).dataset_type == "ranked_responses"


def test_messages_ending_on_assistant_is_messages_type():
    result = classify([_f("messages", "messages")], {"messages": _messages_column(1.0)})
    assert result.dataset_type == "messages"
    assert result.prompt_form == "n/a"


def test_messages_ending_on_user_is_prompt_only():
    result = classify([_f("messages", "messages")], {"messages": _messages_column(0.0)})
    assert result.dataset_type == "prompt_only"


def test_single_text_column_is_text():
    assert classify([_f("text", "string")], {}).dataset_type == "text"


def test_unrecognized_columns_are_unknown():
    result = classify([_f("foo", "int64"), _f("bar", "int64")], {})
    assert result.dataset_type == "unknown"
    assert result.prompt_form is None  # no axes asserted for unknown data


# --- evidence ------------------------------------------------------------------------------------


def test_classification_records_evidence():
    result = classify([_f("prompt", "string"), _f("completion", "string")], {})
    assert {e.kind for e in result.evidence} >= {"column_name", "column_dtype"}


# --- verifiability + content probes --------------------------------------------------------------


def test_verifiability_extractable_gsm8k_answer():
    features = [_f("problem", "string"), _f("solution", "string")]
    rows = [{"problem": "q", "solution": "steps #### 18"}, {"problem": "q", "solution": "no final answer"}]
    result = classify_rows(features, {}, rows)
    assert result.verifiability.method == "extractable_final_answer"
    assert result.verifiability.coverage == 0.5


def test_verifiability_boxed_answer():
    features = [_f("prompt", "string"), _f("completion", "string")]
    result = classify_rows(features, {}, [{"prompt": "q", "completion": r"reasoning \boxed{42}"}])
    assert result.verifiability.method == "extractable_final_answer"
    assert result.verifiability.coverage == 1.0


def test_verifiability_ground_truth_column_coverage():
    features = [_f("prompt", "string"), _f("ground_truth", "string")]
    rows = [{"prompt": "q", "ground_truth": "42"}, {"prompt": "q", "ground_truth": None}]
    result = classify_rows(features, {}, rows)
    assert result.verifiability.method == "ground_truth_column"
    assert result.verifiability.coverage == 0.5


def test_no_verifiability_without_a_target():
    features = [_f("prompt", "string"), _f("completion", "string")]
    result = classify_rows(features, {}, [{"prompt": "q", "completion": "just prose, no answer"}])
    assert result.verifiability is None


def test_verifiability_ignores_below_threshold_extractable_noise():
    # One coincidental "#### <n>" in a large sample is noise, not a verifiable dataset (kto-mix-14k).
    features = [_f("prompt", "string"), _f("completion", "string")]
    rows = [{"prompt": "q", "completion": "just prose"} for _ in range(100)]
    rows[0]["completion"] = "the answer is #### 7"  # 1/100 = 1% < 5% floor
    assert classify_rows(features, {}, rows).verifiability is None


def test_verifiability_asserted_above_coverage_floor():
    features = [_f("prompt", "string"), _f("completion", "string")]
    rows = [{"prompt": "q", "completion": "just prose"} for _ in range(10)]
    for row in rows[:2]:
        row["completion"] = "answer #### 7"  # 2/10 = 20% >= 5% floor
    result = classify_rows(features, {}, rows)
    assert result.verifiability.method == "extractable_final_answer"
    assert result.verifiability.coverage == 0.2


def test_sparse_ground_truth_falls_through_to_extractable_answer():
    # A ground_truth column present in too few rows must not mask a strong extractable-answer signal.
    features = [_f("completion", "string"), _f("ground_truth", "string")]
    rows = [{"completion": "reasoning #### 5", "ground_truth": None} for _ in range(100)]
    rows[0]["ground_truth"] = "5"  # 1/100 ground_truth coverage -> below floor, must fall through
    result = classify_rows(features, {}, rows)
    assert result.verifiability.method == "extractable_final_answer"
    assert result.verifiability.coverage == 1.0


def test_a_sparse_column_does_not_outrank_the_real_answer_column():
    """Coverage is a fraction of the column's rows, not of the rows that happened to hold text.

    Scored the other way, a column present in one row out of a thousand rates 1.0 and outranks the
    genuine answer column at 0.8 -- and the profile then reports that 1.0 as the coverage, which the
    contract says a consumer may read literally. It would point a verifier at the wrong column.
    """
    features = [_f("q", "string"), _f("a", "string"), _f("note", "string")]
    rows = [
        {"q": f"question {i}", "a": (f"reasoning #### {i}" if i % 10 < 8 else "no marker"), "note": None}
        for i in range(1000)
    ]
    rows[0]["note"] = "\\boxed{7}"  # the only row this column is present in at all

    result = classify_rows(features, {}, rows)

    assert result.verifiability.method == "extractable_final_answer"
    assert result.verifiability.coverage == 0.8
    assert "'a'" in result.verifiability.evidence[0].detail


def test_a_column_present_in_one_row_is_not_a_verification_target():
    """The same ranking read on its own: one hit in a thousand rows is below the coverage floor."""
    features = [_f("q", "string"), _f("note", "string")]
    rows = [{"q": f"question {i}", "note": None} for i in range(1000)]
    rows[0]["note"] = "\\boxed{7}"

    assert classify_rows(features, {}, rows).verifiability is None


def test_implicit_prompt_evidence_from_embedded_transcript():
    features = [_f("chosen", "string"), _f("rejected", "string")]
    rows = [{"chosen": "\n\nHuman: hi\n\nAssistant: hello", "rejected": "\n\nHuman: hi\n\nAssistant: hey"}]
    result = classify_rows(features, {}, rows)
    assert result.prompt_form == "implicit"
    assert any(e.kind == "content_probe" for e in result.evidence)


def test_ground_truth_may_be_a_container_dtype():
    # test_cases (list) and verification_info (struct) are verification targets, not free text,
    # so the text-only dtype gate must not drop them.
    features = [_f("prompt", "string"), _f("test_cases", "list"), _f("verification_info", "struct")]
    classify(features, {})
    assert features[1].semantic_role == "ground_truth"
    assert features[2].semantic_role == "ground_truth"


def test_container_ground_truth_drives_verifiability():
    features = [_f("prompt", "string"), _f("test_cases", "list")]
    rows = [{"prompt": "q", "test_cases": [{"in": "1", "out": "2"}]}, {"prompt": "q2", "test_cases": []}]
    result = classify_rows(features, {}, rows)
    assert result.verifiability.method == "ground_truth_column"
    assert result.verifiability.coverage == 0.5  # the empty test_cases list is not a usable target


def test_bare_scalar_ground_truth_alias_is_still_rejected():
    # A numeric column named "ground_truth" is far more likely a label/score than a target.
    features = [_f("ground_truth", "int64")]
    classify(features, {})
    assert features[0].semantic_role is None


def test_verifiability_survives_an_unrecognized_column_name():
    # Gating the probes on roles made a content signal reachable only through a recognized column
    # name: the `#### <n>` markers were in the data and the regex would have matched them, but
    # nothing knew where to look. The finding must name the column it came from.
    features = [_f("q", "string"), _f("a", "string")]
    rows = [{"q": "what is 2+2?", "a": f"add them #### {i}"} for i in range(10)]
    result = classify_rows(features, {}, rows)

    assert {f.semantic_role for f in features} == {None}  # still unroled, and honest about it
    assert result.dataset_type == "unknown"
    assert result.verifiability.method == "extractable_final_answer"
    assert result.verifiability.coverage == 1.0
    assert "'a'" in result.verifiability.evidence[0].detail


def test_a_named_completion_still_decides_where_to_look():
    # Roles order the interpretation even though they no longer gate it: a column *known* to be the
    # completion is a better answer than one that merely looks like it.
    features = [_f("completion", "string"), _f("notes", "string")]
    rows = [{"completion": "just prose", "notes": "scratch #### 9"} for _ in range(10)]
    assert classify_rows(features, {}, rows).verifiability is None


def test_verifiability_reads_a_from_value_conversational_completion():
    features = [_f("prompt", "string"), _f("completion", "messages")]
    rows = [{"prompt": "q", "completion": [{"from": "human", "value": "q"}, {"from": "gpt", "value": "#### 4"}]}]
    result = classify_rows(features, {}, rows)
    assert result.verifiability.method == "extractable_final_answer"
    assert result.verifiability.coverage == 1.0


def test_classification_without_probes_claims_nothing_rather_than_guessing():
    # classify() used to derive probes from rows when it was handed none. It no longer sees rows at
    # all, so absent probes must read as "nothing was measured" -- never as "nothing is there".
    rows = [{"prompt": "q", "completion": f"steps #### {i}"} for i in range(10)]
    features = [_f("prompt", "string"), _f("completion", "string")]

    blind = classify(features, {})
    assert blind.verifiability is None

    measured = classify([_f("prompt", "string"), _f("completion", "string")], {}, probes=_probes(features, rows))
    assert measured.verifiability.method == "extractable_final_answer"
    assert measured.verifiability.coverage == 1.0


# --- candidates ------------------------------------------------------------------------------------


def test_candidates_list_every_structure_the_roles_satisfy():
    # prompt + completion + score + label is genuinely both scored_response and unpaired_preference.
    # Reporting only the first made rule order an invisible tie-break.
    features = [_f("prompt", "string"), _f("completion", "string"), _f("score", "float64"), _f("label", "bool")]
    result = classify(features, {"label": _binary_column()})

    assert result.candidates == ["scored_response", "unpaired_preference", "prompt_completion"]
    assert result.dataset_type == result.candidates[0]  # the summary is the head, never more


def test_candidates_collapse_to_one_when_the_structure_is_unambiguous():
    result = classify([_f("prompt", "string"), _f("completion", "string")], {})
    assert result.candidates == ["prompt_completion"]


def test_unknown_is_still_reported_as_a_candidate():
    result = classify([_f("foo", "int64"), _f("bar", "int64")], {})
    assert result.dataset_type == "unknown"
    assert result.candidates == ["unknown"]


def test_prompt_only_is_not_claimed_alongside_a_training_target():
    # Collecting candidates rather than returning early risks a prompt+completion set also claiming
    # prompt_only, which asserts the opposite of what the data holds.
    result = classify([_f("prompt", "string"), _f("completion", "string")], {})
    assert "prompt_only" not in result.candidates


# --- declared roles (hints) ------------------------------------------------------------------------


def test_a_hint_names_a_column_the_alias_table_does_not_know():
    features = [_f("q", "string"), _f("a", "string")]
    result = classify(features, {}, column_roles={"q": "prompt", "a": "completion"})

    assert [(f.semantic_role, f.semantic_role_source) for f in features] == [
        ("prompt", "declared"),
        ("completion", "declared"),
    ]
    assert result.dataset_type == "prompt_completion"


def test_a_hint_takes_precedence_over_the_name_alias():
    # The caller knows their schema; the table is ~35 English names.
    features = [_f("prompt", "string")]
    classify(features, {}, column_roles={"prompt": "context"})
    assert features[0].semantic_role == "context"
    assert features[0].semantic_role_source == "declared"


def test_a_hint_the_dtype_cannot_support_is_rejected_loudly():
    # A hint says which column, not what the data is. Accepting it unconditionally would let one
    # typo produce a nonsense classification, and silence is what made the table's misses costly.
    features = [_f("n", "int64")]
    result = classify(features, {}, column_roles={"n": "prompt"})

    assert features[0].semantic_role is None
    rejections = [e for e in result.evidence if e.kind == "user_hint"]
    assert len(rejections) == 1
    assert "n -> prompt" in rejections[0].detail and "int64" in rejections[0].detail


def test_a_hint_naming_a_role_that_does_not_exist_is_rejected():
    # The dtype gate has no constraint to apply to a role it does not recognize, so it used to wave
    # a typo through: `semantic_role="prmpt"` reached the profile as a `declared` role, evidence
    # claimed the columns matched, and nothing downstream read it -- so the dataset classified as
    # `unknown` with the profile asserting the opposite.
    features = [_f("q", "string")]
    result = classify(features, {}, column_roles={"q": "prmpt"})

    assert features[0].semantic_role is None
    assert features[0].semantic_role_source is None
    rejections = [e for e in result.evidence if e.kind == "user_hint"]
    assert len(rejections) == 1
    assert "q -> prmpt" in rejections[0].detail
    assert not any("prmpt" in e.detail for e in result.evidence if e.kind == "column_name")


def test_a_rejected_hint_falls_back_to_detection():
    # `answer` is a known alias; a bad hint on it must not cost the role the table would have found.
    features = [_f("answer", "string")]
    classify(features, {}, column_roles={"answer": "messages"})  # messages needs the messages dtype
    assert features[0].semantic_role == "completion"
    assert features[0].semantic_role_source == "detected"


def test_detected_roles_are_marked_as_detected():
    features = [_f("prompt", "string")]
    classify(features, {})
    assert features[0].semantic_role_source == "detected"
