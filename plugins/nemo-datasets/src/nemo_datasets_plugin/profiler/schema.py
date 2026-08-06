# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Row-schema derivation.

Derive the ``features`` tree (a list of :class:`FeatureSchema`) de novo from the data. Parquet
carries a declared schema, so it is converted directly; formats without one (jsonl) are inferred
from the sampled rows by resolving each column's dtype. A list of ``{role, content}`` structs — or
ShareGPT's ``{from, value}`` spelling of the same thing — is recognized as the ``messages`` dtype,
and a list of ``{role, content}`` structs is recognized as the ``messages`` dtype.
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa
from nemo_platform_plugin.files.dataset_profile import FeatureSchema

# A list element carrying at least one of these key sets is treated as a chat message (the messages
# dtype). ShareGPT-style data spells the same structure `{from, value}`; recognizing only
# `{role, content}` left a large slice of public chat data typed as a plain `list`, which then failed
# the `messages` dtype gate in classification and profiled as `unknown` with no stats at all.
_MESSAGE_KEY_SETS = ({"role", "content"}, {"from", "value"})


def derive_features(rows: list[dict[str, Any]], arrow_schema: pa.Schema | None = None) -> list[FeatureSchema]:
    """The row schema. Uses the declared arrow schema when present, else infers from ``rows``."""
    if arrow_schema is not None:
        return [
            _feature_from_arrow(arrow_schema.field(i).name, arrow_schema.field(i).type)
            for i in range(len(arrow_schema))
        ]
    return _features_from_rows(rows)


def _is_message_struct(item: FeatureSchema) -> bool:
    if item.dtype != "struct" or item.fields is None:
        return False
    names = {field.name for field in item.fields}
    return any(keys <= names for keys in _MESSAGE_KEY_SETS)


# --- from a declared arrow schema (parquet) ------------------------------------------------------

_ARROW_SCALAR_DTYPES = [
    (pa.types.is_boolean, "bool"),
    (pa.types.is_int8, "int8"),
    (pa.types.is_int16, "int16"),
    (pa.types.is_int32, "int32"),
    (pa.types.is_int64, "int64"),
    (pa.types.is_uint8, "uint8"),
    (pa.types.is_uint16, "uint16"),
    (pa.types.is_uint32, "uint32"),
    (pa.types.is_uint64, "uint64"),
    (pa.types.is_float16, "float16"),
    (pa.types.is_float32, "float32"),
    (pa.types.is_float64, "float64"),
    (pa.types.is_string, "string"),
    (pa.types.is_large_string, "string"),
]


def _arrow_scalar_dtype(arrow_type: pa.DataType) -> str:
    for predicate, dtype in _ARROW_SCALAR_DTYPES:
        if predicate(arrow_type):
            return dtype
    return "json"


def _feature_from_arrow(name: str, arrow_type: pa.DataType) -> FeatureSchema:
    if pa.types.is_struct(arrow_type):
        fields = [
            _feature_from_arrow(arrow_type.field(i).name, arrow_type.field(i).type)
            for i in range(arrow_type.num_fields)
        ]
        return FeatureSchema(name=name, dtype="struct", fields=fields)
    if pa.types.is_list(arrow_type) or pa.types.is_large_list(arrow_type) or pa.types.is_fixed_size_list(arrow_type):
        item = _feature_from_arrow("", arrow_type.value_type)
        dtype = "messages" if _is_message_struct(item) else "list"
        return FeatureSchema(name=name, dtype=dtype, items=item)
    return FeatureSchema(name=name, dtype=_arrow_scalar_dtype(arrow_type))


# --- inferred from sampled rows (jsonl) ----------------------------------------------------------


def _features_from_rows(rows: list[dict[str, Any]]) -> list[FeatureSchema]:
    ordered_keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                ordered_keys.append(key)
    return [_infer_feature(key, [row.get(key) for row in rows]) for key in ordered_keys]


def _infer_feature(name: str, values: list[Any]) -> FeatureSchema:
    present = [value for value in values if value is not None]
    if not present:
        return FeatureSchema(name=name, dtype="json")

    if all(isinstance(value, dict) for value in present):
        child_keys: list[str] = []
        seen: set[str] = set()
        for record in present:
            for key in record:
                if key not in seen:
                    seen.add(key)
                    child_keys.append(key)
        fields = [_infer_feature(key, [record.get(key) for record in present]) for key in child_keys]
        return FeatureSchema(name=name, dtype="struct", fields=fields)

    if all(isinstance(value, list) for value in present):
        item = _infer_feature("", [element for value in present for element in value])
        if _is_message_struct(item):
            return FeatureSchema(name=name, dtype="messages", items=item)
        return FeatureSchema(name=name, dtype="list", items=item)

    return FeatureSchema(name=name, dtype=_scalar_dtype(present))


def _scalar_dtype(values: list[Any]) -> str:
    dtypes: set[str] = set()
    for value in values:
        if isinstance(value, bool):  # bool before int: bool is a subclass of int
            dtypes.add("bool")
        elif isinstance(value, int):
            dtypes.add("int64")
        elif isinstance(value, float):
            dtypes.add("float64")
        elif isinstance(value, str):
            dtypes.add("string")
        else:
            dtypes.add("json")
    if dtypes <= {"int64", "float64"} and dtypes:
        return "float64" if "float64" in dtypes else "int64"
    if len(dtypes) == 1:
        return dtypes.pop()
    return "json"
