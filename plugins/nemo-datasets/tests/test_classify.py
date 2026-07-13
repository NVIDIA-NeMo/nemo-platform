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
