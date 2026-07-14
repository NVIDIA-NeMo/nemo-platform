# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for classification: role assignment, format/prompt-form axes, and dataset type."""

from nemo_datasets_plugin.profiler.classify import classify
from nemo_platform_plugin.files.dataset_profile import ColumnStats, FeatureSchema, MessageStats, Quantiles


def _f(name, dtype):
    return FeatureSchema(name=name, dtype=dtype)


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


def test_unpaired_preference_needs_boolean_label():
    features = [_f("prompt", "string"), _f("completion", "string"), _f("label", "bool")]
    assert classify(features, {}).dataset_type == "unpaired_preference"


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
    result = classify(features, {}, rows)
    assert result.verifiability.method == "extractable_final_answer"
    assert result.verifiability.coverage == 0.5


def test_verifiability_boxed_answer():
    features = [_f("prompt", "string"), _f("completion", "string")]
    result = classify(features, {}, [{"prompt": "q", "completion": r"reasoning \boxed{42}"}])
    assert result.verifiability.method == "extractable_final_answer"
    assert result.verifiability.coverage == 1.0


def test_verifiability_ground_truth_column_coverage():
    features = [_f("prompt", "string"), _f("ground_truth", "string")]
    rows = [{"prompt": "q", "ground_truth": "42"}, {"prompt": "q", "ground_truth": None}]
    result = classify(features, {}, rows)
    assert result.verifiability.method == "ground_truth_column"
    assert result.verifiability.coverage == 0.5


def test_no_verifiability_without_a_target():
    features = [_f("prompt", "string"), _f("completion", "string")]
    result = classify(features, {}, [{"prompt": "q", "completion": "just prose, no answer"}])
    assert result.verifiability is None


def test_verifiability_ignores_below_threshold_extractable_noise():
    # One coincidental "#### <n>" in a large sample is noise, not a verifiable dataset (kto-mix-14k).
    features = [_f("prompt", "string"), _f("completion", "string")]
    rows = [{"prompt": "q", "completion": "just prose"} for _ in range(100)]
    rows[0]["completion"] = "the answer is #### 7"  # 1/100 = 1% < 5% floor
    assert classify(features, {}, rows).verifiability is None


def test_verifiability_asserted_above_coverage_floor():
    features = [_f("prompt", "string"), _f("completion", "string")]
    rows = [{"prompt": "q", "completion": "just prose"} for _ in range(10)]
    for row in rows[:2]:
        row["completion"] = "answer #### 7"  # 2/10 = 20% >= 5% floor
    result = classify(features, {}, rows)
    assert result.verifiability.method == "extractable_final_answer"
    assert result.verifiability.coverage == 0.2


def test_sparse_ground_truth_falls_through_to_extractable_answer():
    # A ground_truth column present in too few rows must not mask a strong extractable-answer signal.
    features = [_f("completion", "string"), _f("ground_truth", "string")]
    rows = [{"completion": "reasoning #### 5", "ground_truth": None} for _ in range(100)]
    rows[0]["ground_truth"] = "5"  # 1/100 ground_truth coverage -> below floor, must fall through
    result = classify(features, {}, rows)
    assert result.verifiability.method == "extractable_final_answer"
    assert result.verifiability.coverage == 1.0


def test_implicit_prompt_evidence_from_embedded_transcript():
    features = [_f("chosen", "string"), _f("rejected", "string")]
    rows = [{"chosen": "\n\nHuman: hi\n\nAssistant: hello", "rejected": "\n\nHuman: hi\n\nAssistant: hey"}]
    result = classify(features, {}, rows)
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
    result = classify(features, {}, rows)
    assert result.verifiability.method == "ground_truth_column"
    assert result.verifiability.coverage == 0.5  # the empty test_cases list is not a usable target


def test_bare_scalar_ground_truth_alias_is_still_rejected():
    # A numeric column named "ground_truth" is far more likely a label/score than a target.
    features = [_f("ground_truth", "int64")]
    classify(features, {})
    assert features[0].semantic_role is None
