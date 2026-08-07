# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for row-schema derivation (from a declared arrow schema and from sampled rows)."""

import pyarrow as pa
from nemo_datasets_plugin.profiler.schema import MAX_COLUMNS, columns_were_capped, derive_features

# --- from a declared arrow schema (parquet) ------------------------------------------------------


def test_from_arrow_scalars_keep_declared_widths():
    schema = pa.schema(
        [("s", pa.string()), ("i", pa.int64()), ("i32", pa.int32()), ("b", pa.bool_()), ("f", pa.float64())]
    )
    features = {f.name: f.dtype for f in derive_features([], schema)}
    assert features == {"s": "string", "i": "int64", "i32": "int32", "b": "bool", "f": "float64"}


def test_from_arrow_list_of_role_content_structs_is_messages():
    schema = pa.schema([("prompt", pa.list_(pa.struct([("role", pa.string()), ("content", pa.string())])))])
    feature = derive_features([], schema)[0]
    assert feature.dtype == "messages"
    assert feature.items.dtype == "struct"
    assert [f.name for f in feature.items.fields] == ["role", "content"]


def test_from_arrow_fixed_and_variable_lists_agree_on_shape():
    # A fixed-size list is still a list of its element type. The constant length itself is no longer
    # recorded, so the two cases must be indistinguishable rather than one silently losing `items`.
    fixed = derive_features([], pa.schema([("embedding", pa.list_(pa.float32(), 768))]))[0]
    assert (fixed.dtype, fixed.items.dtype) == ("list", "float32")

    variable = derive_features([], pa.schema([("tags", pa.list_(pa.string()))]))[0]
    assert (variable.dtype, variable.items.dtype) == ("list", "string")


# --- inferred from sampled rows (jsonl) ----------------------------------------------------------


def test_from_rows_scalars_widen_int_and_float():
    rows = [{"a": 1, "b": 1.5, "c": "x", "d": True}, {"a": 2, "b": 2, "c": "y", "d": False}]
    features = {f.name: f.dtype for f in derive_features(rows)}
    assert features == {"a": "int64", "b": "float64", "c": "string", "d": "bool"}


def test_from_rows_list_of_role_content_structs_is_messages():
    rows = [{"conv": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]}]
    feature = derive_features(rows)[0]
    assert feature.dtype == "messages"
    assert {f.name for f in feature.items.fields} == {"role", "content"}


def test_from_rows_sharegpt_from_value_is_messages():
    # ShareGPT spells the same structure {from, value}. Recognizing only {role, content} left it a
    # plain list, which then failed the messages dtype gate and profiled as `unknown` with no stats.
    rows = [{"conversations": [{"from": "human", "value": "hi"}, {"from": "gpt", "value": "yo"}]}]
    feature = derive_features(rows)[0]
    assert feature.dtype == "messages"
    assert {f.name for f in feature.items.fields} == {"from", "value"}


def test_from_arrow_sharegpt_from_value_is_messages():
    schema = pa.schema([("conversations", pa.list_(pa.struct([("from", pa.string()), ("value", pa.string())])))])
    assert derive_features([], schema)[0].dtype == "messages"


def test_from_rows_lists_infer_their_element_type():
    constant = derive_features([{"e": [0.1, 0.2, 0.3]}, {"e": [0.4, 0.5, 0.6]}])[0]
    assert (constant.dtype, constant.items.dtype) == ("list", "float64")

    variable = derive_features([{"e": [1, 2]}, {"e": [1, 2, 3]}])[0]
    assert (variable.dtype, variable.items.dtype) == ("list", "int64")


def test_from_rows_nested_struct():
    feature = derive_features([{"meta": {"id": 1, "src": "a"}}, {"meta": {"id": 2, "src": "b"}}])[0]
    assert feature.dtype == "struct"
    assert {f.name for f in feature.fields} == {"id", "src"}


def test_from_rows_all_null_column_is_json():
    assert derive_features([{"x": None}, {"x": None}])[0].dtype == "json"


def test_derive_features_prefers_declared_arrow_schema():
    feature = derive_features([{"x": 1}], pa.schema([("x", pa.int32())]))[0]
    assert feature.dtype == "int32"  # declared width beats the int64 inference from rows


def test_column_count_is_bounded_and_says_when_it_stopped():
    # A malformed file whose rows carry unique keys would otherwise mint a column -- and later an
    # accumulator -- for every row. The row budget used to bound this by accident; an unbounded read
    # does not, so the bound is stated and the truncation is reported rather than silent.
    rows = [{f"col{i}": i} for i in range(MAX_COLUMNS + 500)]
    features = derive_features(rows)
    assert len(features) == MAX_COLUMNS
    assert columns_were_capped(features)

    assert not columns_were_capped(derive_features([{"a": 1, "b": 2}]))
