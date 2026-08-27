# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Row-schema derivation.

Derive the ``features`` tree (a list of :class:`FeatureSchema`) from the data. Parquet carries a
declared schema, so it is converted directly; formats without one are inferred from the rows by
resolving each column's dtype. A list of ``{role, content}`` structs, or the equivalent
``{from, value}`` spelling, becomes the ``messages`` dtype.
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa
from nemo_platform_plugin.files.dataset_profile import FeatureSchema

# A list element carrying either key set is a chat message, giving the column the `messages` dtype.
# Both spellings are common; recognizing only `{role, content}` typed much public chat data as a
# plain `list`, which fails the `messages` dtype gate in classification and profiles as `unknown`
# with no stats.
_MESSAGE_KEY_SETS = ({"role", "content"}, {"from", "value"})


# Columns a partition may have before the profiler stops describing it. Nothing legitimate reaches
# this; it guards against a malformed file whose rows carry unique keys, which would otherwise mint
# a column, and an accumulator, per row. A row budget used to bound this by accident, since a schema
# inferred from N rows has at most N keys. An unbounded read does not, so the bound is stated.
MAX_COLUMNS = 4096


def derive_features(rows: list[dict[str, Any]], arrow_schema: pa.Schema | None = None) -> list[FeatureSchema]:
    """The row schema. Uses the declared arrow schema when present, else infers from ``rows``.

    Truncated at :data:`MAX_COLUMNS`. Use :func:`columns_were_capped` to distinguish a dataset that
    really is that wide from one with runaway keys, so the caller can report the difference rather
    than describe part of a file as though it were all of it.
    """
    if arrow_schema is not None:
        return [
            _feature_from_arrow(arrow_schema.field(i).name, arrow_schema.field(i).type)
            for i in range(min(len(arrow_schema), MAX_COLUMNS))
        ]
    return _features_from_rows(rows)


def columns_were_capped(features: list[FeatureSchema]) -> bool:
    """Whether the schema stopped at the cap rather than at the end of the data."""
    return len(features) >= MAX_COLUMNS


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
    # Named rather than left to fall through to `json`. None of them carry statistics -- pyarrow
    # hands back `date` / `datetime` / `bytes` / `Decimal`, which no measurement reads -- but `json`
    # reads as "the profiler could not understand this column", and these are understood exactly.
    # Naming them also lets the role gates refuse them on purpose: a timestamp column called
    # `answer` was a permitted `ground_truth` only because `json` is in that gate's allowed set.
    (pa.types.is_date, "date"),
    (pa.types.is_time, "time"),
    (pa.types.is_timestamp, "timestamp"),
    (pa.types.is_duration, "duration"),
    (pa.types.is_binary, "binary"),
    (pa.types.is_large_binary, "binary"),
    (pa.types.is_fixed_size_binary, "binary"),
    (pa.types.is_decimal, "decimal"),
]


def _arrow_scalar_dtype(arrow_type: pa.DataType) -> str:
    for predicate, dtype in _ARROW_SCALAR_DTYPES:
        if predicate(arrow_type):
            return dtype
    return "json"


def _feature_from_arrow(name: str, arrow_type: pa.DataType) -> FeatureSchema:
    # Dictionary encoding is how a column is *stored*, not what it holds: pyarrow decodes it on the
    # way out, so the values arrive as the value type and measure exactly like it. Unwrapped first,
    # ahead of every other test, because it can wrap any of them.
    #
    # This is the common case, not an exotic one. `DataFrame.to_parquet` emits a dictionary column
    # for every `category` dtype, and typing those as `json` cost them their stats, their
    # `semantic_role`, and -- with the role gone -- the whole partition's classification.
    if pa.types.is_dictionary(arrow_type):
        return _feature_from_arrow(name, arrow_type.value_type)
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
                if len(ordered_keys) >= MAX_COLUMNS:
                    break
        if len(ordered_keys) >= MAX_COLUMNS:
            break
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


def _python_dtype(value: Any) -> str:
    """The dtype one value implies, on its own."""
    if isinstance(value, bool):  # bool before int: bool is a subclass of int
        return "bool"
    if isinstance(value, int):
        return "int64"
    if isinstance(value, float):
        return "float64"
    if isinstance(value, str):
        return "string"
    return "json"


def _resolve_scalar(dtypes: set[str]) -> str:
    """The one dtype a column of these observed types has. Ints and floats widen; any other
    disagreement is ``json``, the honest answer for a column holding two shapes."""
    if dtypes <= {"int64", "float64"} and dtypes:
        return "float64" if "float64" in dtypes else "int64"
    if len(dtypes) == 1:
        # `next(iter(...))`, never `pop()`: the set belongs to a SchemaFold still using it, and
        # emptying it made a second call resolve the same column to `json`.
        return next(iter(dtypes))
    return "json"


def _scalar_dtype(values: list[Any]) -> str:
    return _resolve_scalar({_python_dtype(value) for value in values})


class SchemaFold:
    """One column's schema, folded from values as they arrive rather than decided over all of them.

    An inferred dtype is a whole-column question -- the observed types are unioned and a disagreement
    widens to ``json`` -- so it is not known until the last row.

    Folding costs nothing extra. :func:`_infer_feature` is already a set union over observed types, a
    union over a struct's child keys, and a recursion over a list's flattened elements: state
    proportional to the schema, not the row count.
    """

    def __init__(self, name: str = "") -> None:
        self._name = name
        self._present = 0
        self._dicts = 0
        self._lists = 0
        self._dtypes: set[str] = set()
        self._fields: dict[str, SchemaFold] = {}
        self._field_order: list[str] = []
        self._item: SchemaFold | None = None

    def update(self, values: list[Any]) -> None:
        for value in values:
            if value is None:
                continue  # a null says nothing about the type; an all-null column resolves to json
            self._present += 1
            self._dtypes.add(_python_dtype(value))
            if isinstance(value, dict):
                self._dicts += 1
                for key, child in value.items():
                    fold = self._fields.get(key)
                    if fold is None:
                        fold = SchemaFold(key)
                        self._fields[key] = fold
                        self._field_order.append(key)
                    fold.update([child])
            elif isinstance(value, list):
                self._lists += 1
                if self._item is None:
                    self._item = SchemaFold()
                self._item.update(value)

    def update_partitioned(
        self,
        strings: list[Any],
        ints: list[Any],
        floats: list[Any],
        bools: list[Any],
        lists: list[Any],
        dicts: list[Any],
    ) -> None:
        """:meth:`update`, over values a caller has already partitioned by exact python type.

        The caller makes that partition anyway, to send each value to the measurement that reports
        it, so folding from the partition costs nothing and spares this class deriving every value's
        type a second time.

        What makes the scalar buckets O(1) rather than O(values) is that the dtype union is a *set*:
        adding ``string`` once for a bucket of five hundred strings is the same fact as adding it
        five hundred times. Dicts and lists still cost a step each, because they recurse.

        A value whose class is a *subclass* of a builtin cannot be placed by an exact class and so
        never arrives here; :meth:`update` is still the one that types it.
        """
        for bucket, dtype in ((strings, "string"), (ints, "int64"), (floats, "float64"), (bools, "bool")):
            if bucket:
                self._present += len(bucket)
                self._dtypes.add(dtype)
        if dicts:
            self._present += len(dicts)
            self._dicts += len(dicts)
            self._dtypes.add("json")
            for value in dicts:
                for key, child in value.items():
                    fold = self._fields.get(key)
                    if fold is None:
                        fold = SchemaFold(key)
                        self._fields[key] = fold
                        self._field_order.append(key)
                    fold.update([child])
        if lists:
            self._present += len(lists)
            self._lists += len(lists)
            self._dtypes.add("json")
            if self._item is None:
                self._item = SchemaFold()
            for value in lists:
                self._item.update(value)

    def finalize(self) -> FeatureSchema:
        if not self._present:
            return FeatureSchema(name=self._name, dtype="json")
        if self._dicts == self._present:
            return FeatureSchema(
                name=self._name,
                dtype="struct",
                fields=[self._fields[key].finalize() for key in self._field_order],
            )
        if self._lists == self._present:
            item = (self._item or SchemaFold()).finalize()
            return FeatureSchema(
                name=self._name,
                dtype="messages" if _is_message_struct(item) else "list",
                items=item,
            )
        return FeatureSchema(name=self._name, dtype=_resolve_scalar(self._dtypes))
