# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for FilterOperation.matches() — in-memory filter-tree evaluation.

These mirror the SQL semantics of ``SQLAlchemyFilterRepository`` (see the
parity test at services/core/entities/tests/test_filter_matches_sql_parity.py).
"""

from datetime import datetime

import pytest
from nemo_platform_plugin.filter_ops import (
    ComparisonOperation,
    FilterOperation,
    FilterOperator,
    LogicalOperation,
)


class Entity:
    """Simple object whose attributes mirror entity columns (plain + data JSON)."""

    def __init__(self, name=None, score=None, data=None):
        self.name = name
        self.score = score
        self.data = data if data is not None else {}


def cmp(operator, field, value):
    return ComparisonOperation(operator=operator, field=field, value=value)


class TestEqPlainAttribute:
    def test_eq_string_hit(self):
        assert cmp(FilterOperator.EQ, "name", "llama").matches(Entity(name="llama")) is True

    def test_eq_string_miss(self):
        assert cmp(FilterOperator.EQ, "name", "llama").matches(Entity(name="other")) is False

    def test_eq_int(self):
        assert cmp(FilterOperator.EQ, "score", 5).matches(Entity(score=5)) is True
        assert cmp(FilterOperator.EQ, "score", 5).matches(Entity(score=6)) is False

    def test_eq_none_matches_none_attribute(self):
        assert cmp(FilterOperator.EQ, "name", None).matches(Entity(name=None)) is True

    def test_eq_none_does_not_match_set_attribute(self):
        assert cmp(FilterOperator.EQ, "name", None).matches(Entity(name="x")) is False

    def test_eq_works_on_dict_entity(self):
        assert cmp(FilterOperator.EQ, "name", "llama").matches({"name": "llama"}) is True


class TestEqDataPath:
    def test_eq_nested_string(self):
        e = Entity(data={"finetuning_type": "LoRA"})
        assert cmp(FilterOperator.EQ, "data.finetuning_type", "LoRA").matches(e) is True
        assert cmp(FilterOperator.EQ, "data.finetuning_type", "lora").matches(e) is False

    def test_eq_int_coerced_to_text(self):
        e = Entity(data={"score": 5})
        assert cmp(FilterOperator.EQ, "data.score", 5).matches(e) is True
        assert cmp(FilterOperator.EQ, "data.score", "5").matches(e) is True

    def test_eq_float(self):
        e = Entity(data={"x": 1.5})
        assert cmp(FilterOperator.EQ, "data.x", 1.5).matches(e) is True

    def test_eq_bool_true(self):
        assert cmp(FilterOperator.EQ, "data.flag", True).matches(Entity(data={"flag": True})) is True
        assert cmp(FilterOperator.EQ, "data.flag", True).matches(Entity(data={"flag": False})) is False

    def test_eq_bool_false(self):
        assert cmp(FilterOperator.EQ, "data.flag", False).matches(Entity(data={"flag": False})) is True

    def test_eq_none_matches_explicit_null(self):
        assert cmp(FilterOperator.EQ, "data.k", None).matches(Entity(data={"k": None})) is True

    def test_eq_none_matches_missing_key(self):
        assert cmp(FilterOperator.EQ, "data.k", None).matches(Entity(data={})) is True

    def test_eq_value_does_not_match_missing_key(self):
        assert cmp(FilterOperator.EQ, "data.k", "v").matches(Entity(data={})) is False

    def test_eq_deeply_nested(self):
        e = Entity(data={"a": {"b": {"c": "deep"}}})
        assert cmp(FilterOperator.EQ, "data.a.b.c", "deep").matches(e) is True
        assert cmp(FilterOperator.EQ, "data.a.b.c", "shallow").matches(e) is False

    def test_eq_descend_into_non_dict_is_missing(self):
        e = Entity(data={"a": "scalar"})
        assert cmp(FilterOperator.EQ, "data.a.b", None).matches(e) is True


class TestLike:
    def test_like_substring_hit_plain(self):
        assert cmp(FilterOperator.LIKE, "name", "lam").matches(Entity(name="llama")) is True

    def test_like_case_insensitive(self):
        assert cmp(FilterOperator.LIKE, "name", "LLAMA").matches(Entity(name="my-llama-2")) is True

    def test_like_miss(self):
        assert cmp(FilterOperator.LIKE, "name", "zebra").matches(Entity(name="llama")) is False

    def test_like_not_regex(self):
        # `%` is a literal here, NOT a wildcard.
        assert cmp(FilterOperator.LIKE, "name", "a%b").matches(Entity(name="xaybz")) is False
        assert cmp(FilterOperator.LIKE, "name", "a%b").matches(Entity(name="xa%bz")) is True

    def test_like_none_plain_never_matches(self):
        assert cmp(FilterOperator.LIKE, "name", "x").matches(Entity(name=None)) is False

    def test_like_data_path(self):
        e = Entity(data={"desc": "a Llama model"})
        assert cmp(FilterOperator.LIKE, "data.desc", "llama").matches(e) is True

    def test_like_data_null_renders_as_text_null(self):
        # JSON null/missing renders as literal text "null"; "null" contains "ull".
        assert cmp(FilterOperator.LIKE, "data.k", "ull").matches(Entity(data={})) is True


class TestInNin:
    def test_in_plain_hit(self):
        assert cmp(FilterOperator.IN, "name", ["a", "b"]).matches(Entity(name="b")) is True

    def test_in_plain_miss(self):
        assert cmp(FilterOperator.IN, "name", ["a", "b"]).matches(Entity(name="c")) is False

    def test_in_none_plain_never_matches(self):
        assert cmp(FilterOperator.IN, "name", ["a"]).matches(Entity(name=None)) is False

    def test_nin_plain_hit(self):
        assert cmp(FilterOperator.NIN, "name", ["a", "b"]).matches(Entity(name="c")) is True

    def test_nin_plain_excludes_member(self):
        assert cmp(FilterOperator.NIN, "name", ["a", "b"]).matches(Entity(name="a")) is False

    def test_nin_none_plain_never_matches(self):
        # NULL NOT IN (...) is NULL -> not matched.
        assert cmp(FilterOperator.NIN, "name", ["a"]).matches(Entity(name=None)) is False

    def test_in_data_text_coercion(self):
        e = Entity(data={"score": 5})
        assert cmp(FilterOperator.IN, "data.score", [5, 6]).matches(e) is True
        assert cmp(FilterOperator.IN, "data.score", ["5"]).matches(e) is True

    def test_nin_data_null_satisfies_unless_excluded(self):
        # JSON null/missing renders "null", which is NOT in ["v"], so $nin matches.
        assert cmp(FilterOperator.NIN, "data.k", ["v"]).matches(Entity(data={})) is True
        # ...but excluding "null" itself flips it.
        assert cmp(FilterOperator.NIN, "data.k", ["null"]).matches(Entity(data={})) is False


class TestOrdered:
    def test_gt_plain_int(self):
        assert cmp(FilterOperator.GT, "score", 5).matches(Entity(score=9)) is True
        assert cmp(FilterOperator.GT, "score", 5).matches(Entity(score=5)) is False

    def test_gte_plain(self):
        assert cmp(FilterOperator.GTE, "score", 5).matches(Entity(score=5)) is True

    def test_lt_plain(self):
        assert cmp(FilterOperator.LT, "score", 5).matches(Entity(score=4)) is True

    def test_lte_plain(self):
        assert cmp(FilterOperator.LTE, "score", 5).matches(Entity(score=5)) is True

    def test_ordered_none_plain_never_matches(self):
        assert cmp(FilterOperator.GT, "score", 5).matches(Entity(score=None)) is False
        assert cmp(FilterOperator.LT, "score", 5).matches(Entity(score=None)) is False

    def test_gt_data_numeric(self):
        e = Entity(data={"score": 100})
        assert cmp(FilterOperator.GT, "data.score", 9).matches(e) is True

    def test_lt_data_numeric_string_stored(self):
        # Numeric value -> both sides cast to float; stored numeric text parses.
        e = Entity(data={"score": "9"})
        assert cmp(FilterOperator.LT, "data.score", 10).matches(e) is True

    def test_ordered_data_text_compare(self):
        e = Entity(data={"tier": "m"})
        assert cmp(FilterOperator.GT, "data.tier", "a").matches(e) is True
        assert cmp(FilterOperator.LT, "data.tier", "z").matches(e) is True

    def test_gt_data_null_numeric_casts_zero(self):
        # JSON null/missing casts to 0.0 for numeric comparison (SQLite CAST).
        assert cmp(FilterOperator.GT, "data.k", -1).matches(Entity(data={})) is True
        assert cmp(FilterOperator.GT, "data.k", 0).matches(Entity(data={})) is False

    def test_ordered_datetime_iso_string(self):
        e = Entity(score=datetime(2024, 6, 1, 12, 0, 0))
        assert cmp(FilterOperator.GT, "score", "2024-01-01T00:00:00").matches(e) is True
        assert cmp(FilterOperator.LT, "score", "2024-01-01T00:00:00").matches(e) is False


class TestLogical:
    def test_and_all_true(self):
        op = LogicalOperation(
            operator=FilterOperator.AND,
            operations=[
                cmp(FilterOperator.EQ, "name", "llama"),
                cmp(FilterOperator.GT, "score", 5),
            ],
        )
        assert op.matches(Entity(name="llama", score=9)) is True
        assert op.matches(Entity(name="llama", score=1)) is False

    def test_or_any_true(self):
        op = LogicalOperation(
            operator=FilterOperator.OR,
            operations=[
                cmp(FilterOperator.EQ, "name", "a"),
                cmp(FilterOperator.EQ, "name", "b"),
            ],
        )
        assert op.matches(Entity(name="b")) is True
        assert op.matches(Entity(name="c")) is False

    def test_not_negates(self):
        op = LogicalOperation(
            operator=FilterOperator.NOT,
            operations=[cmp(FilterOperator.EQ, "name", "llama")],
        )
        assert op.matches(Entity(name="other")) is True
        assert op.matches(Entity(name="llama")) is False

    def test_nested_and_or_not(self):
        # name == "llama" AND NOT (score < 5)
        op = LogicalOperation(
            operator=FilterOperator.AND,
            operations=[
                cmp(FilterOperator.EQ, "name", "llama"),
                LogicalOperation(
                    operator=FilterOperator.NOT,
                    operations=[cmp(FilterOperator.LT, "score", 5)],
                ),
            ],
        )
        assert op.matches(Entity(name="llama", score=9)) is True
        assert op.matches(Entity(name="llama", score=2)) is False
        assert op.matches(Entity(name="other", score=9)) is False

    def test_not_requires_exactly_one_operand(self):
        op = LogicalOperation(
            operator=FilterOperator.NOT,
            operations=[
                cmp(FilterOperator.EQ, "name", "a"),
                cmp(FilterOperator.EQ, "name", "b"),
            ],
        )
        with pytest.raises(ValueError, match="exactly one operand"):
            op.matches(Entity(name="a"))


class TestUnsupported:
    def test_exists_raises_not_implemented(self):
        # Use a data.* field so resolution succeeds and the operator dispatch is
        # reached; $exists is relationship-only and must raise NotImplementedError.
        with pytest.raises(NotImplementedError):
            cmp(FilterOperator.EXISTS, "data.adapters", True).matches(Entity())

    def test_base_matches_default_raises(self):
        # A FilterOperation subclass with no matches() override inherits the
        # concrete default, which raises (rather than being abstract).
        class Custom(FilterOperation):
            def apply(self, repository):
                return None

            def to_dict(self):
                return {}

        with pytest.raises(NotImplementedError):
            Custom(operator=FilterOperator.EXISTS).matches(Entity())

    def test_unknown_field_raises_value_error(self):
        with pytest.raises(ValueError, match="does not exist"):
            cmp(FilterOperator.EQ, "nonexistent", "x").matches(Entity())


class TestSqliteEdgeCases:
    """Coverage for the subtle SQLite-mirroring branches (cross-checked in the
    parity test); these pin the behavior deterministically."""

    def test_like_on_json_bool_renders_sqlite_form(self):
        # A JSON boolean renders as "1"/"0" (SQLite), so $like sees that text —
        # exercises the bool branch of _json_text via a non-$eq operator.
        assert cmp(FilterOperator.LIKE, "data.flag", "1").matches(Entity(data={"flag": True})) is True
        assert cmp(FilterOperator.LIKE, "data.flag", "1").matches(Entity(data={"flag": False})) is False
        assert cmp(FilterOperator.LIKE, "data.flag", "0").matches(Entity(data={"flag": False})) is True

    def test_in_on_json_bool_renders_sqlite_form(self):
        assert cmp(FilterOperator.IN, "data.flag", ["1"]).matches(Entity(data={"flag": True})) is True
        assert cmp(FilterOperator.IN, "data.flag", ["1"]).matches(Entity(data={"flag": False})) is False

    def test_ordered_numeric_against_leading_numeric_text(self):
        # Numeric comparison vs non-numeric JSON text uses SQLite's lenient
        # leading-numeric cast: "5abc" -> 5.0 (exercises _sqlite_cast_float regex).
        e = Entity(data={"n": "5abc"})
        assert cmp(FilterOperator.GT, "data.n", 4).matches(e) is True
        assert cmp(FilterOperator.LT, "data.n", 6).matches(e) is True
        assert cmp(FilterOperator.GT, "data.n", 5).matches(e) is False

    def test_ordered_fully_nonnumeric_text_casts_zero(self):
        # Text with no leading number casts to 0.0.
        e = Entity(data={"n": "abc"})
        assert cmp(FilterOperator.GT, "data.n", -1).matches(e) is True
        assert cmp(FilterOperator.GT, "data.n", 1).matches(e) is False

    def test_ordered_incomparable_types_returns_false(self):
        # Comparing a str column to an int is incomparable in Python; matches()
        # treats a TypeError as "no match" (mirrors SQL's NULL/three-valued result).
        assert cmp(FilterOperator.GT, "name", 5).matches(Entity(name="llama")) is False
        assert cmp(FilterOperator.LT, "name", 5).matches(Entity(name="llama")) is False

    def test_comparison_op_with_logical_operator_raises(self):
        # A ComparisonOperation carrying a logical operator is malformed; matches()
        # rejects it rather than silently mis-evaluating.
        op = ComparisonOperation(operator=FilterOperator.AND, field="name", value="x")
        with pytest.raises(ValueError, match="Unknown comparison operator"):
            op.matches(Entity(name="x"))

    def test_logical_op_with_comparison_operator_raises(self):
        op = LogicalOperation(
            operator=FilterOperator.EQ,
            operations=[cmp(FilterOperator.EQ, "name", "x")],
        )
        with pytest.raises(ValueError, match="Unknown logical operator"):
            op.matches(Entity(name="x"))
