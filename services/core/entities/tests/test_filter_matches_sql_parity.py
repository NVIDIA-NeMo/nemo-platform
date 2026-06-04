# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SQL-parity safety net for FilterOperation.matches().

Each parametrized FilterOperation tree is run two ways against the same seeded
SQLite rows:
  1. Through SQLAlchemyFilterRepository (the SQL source of truth).
  2. Through op.matches(row) over the ORM instances (the in-memory mirror).

The two must select exactly the same set of row ids. This guards matches()
against drift from the repository's coercion/null semantics.
"""

import pytest
from nmp.common.api.filter import ComparisonOperation, FilterOperator, LogicalOperation
from nmp.core.entities.app.repository.sqlalchemy.filter import SQLAlchemyFilterRepository
from sqlalchemy import JSON, Column, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class FakeEntity(Base):
    __tablename__ = "fake_entity"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    data = Column(JSON)


SEED = [
    dict(id=1, name="llama", data={"score": 5, "tier": "free", "flag": True, "k": None}),
    dict(id=2, name="Llama-2", data={"score": 9, "tier": "pro", "flag": False}),
    dict(id=3, name="zephyr", data={"score": 10, "tier": "pro", "flag": True, "k": "v"}),
    dict(id=4, name="mistral", data={"score": 100, "tier": "enterprise"}),
    dict(id=5, name=None, data={}),
]


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([FakeEntity(**row) for row in SEED])
        session.commit()
        yield session


def C(operator, field, value):
    return ComparisonOperation(operator=operator, field=field, value=value)


def AND(*ops):
    return LogicalOperation(operator=FilterOperator.AND, operations=list(ops))


def OR(*ops):
    return LogicalOperation(operator=FilterOperator.OR, operations=list(ops))


def NOT(op):
    return LogicalOperation(operator=FilterOperator.NOT, operations=[op])


# (label, FilterOperation tree)
CASES = [
    ("eq_name_hit", C(FilterOperator.EQ, "name", "llama")),
    ("eq_name_none", C(FilterOperator.EQ, "name", None)),
    ("eq_data_tier", C(FilterOperator.EQ, "data.tier", "pro")),
    ("eq_data_score_int", C(FilterOperator.EQ, "data.score", 5)),
    ("eq_data_score_str", C(FilterOperator.EQ, "data.score", "5")),
    ("eq_data_flag_true", C(FilterOperator.EQ, "data.flag", True)),
    ("eq_data_flag_false", C(FilterOperator.EQ, "data.flag", False)),
    ("eq_data_k_none", C(FilterOperator.EQ, "data.k", None)),
    ("like_name", C(FilterOperator.LIKE, "name", "llama")),
    ("like_name_lower", C(FilterOperator.LIKE, "name", "LAMA")),
    ("like_data_tier", C(FilterOperator.LIKE, "data.tier", "pr")),
    ("like_data_miss", C(FilterOperator.LIKE, "data.tier", "zzz")),
    ("in_name", C(FilterOperator.IN, "name", ["llama", "mistral"])),
    ("in_data_tier", C(FilterOperator.IN, "data.tier", ["pro", "free"])),
    ("in_data_score", C(FilterOperator.IN, "data.score", [5, 10])),
    ("nin_name", C(FilterOperator.NIN, "name", ["llama"])),
    ("nin_data_tier", C(FilterOperator.NIN, "data.tier", ["pro"])),
    ("nin_data_score", C(FilterOperator.NIN, "data.score", [5, 9])),
    ("gt_data_score", C(FilterOperator.GT, "data.score", 9)),
    ("gte_data_score", C(FilterOperator.GTE, "data.score", 10)),
    ("lt_data_score", C(FilterOperator.LT, "data.score", 10)),
    ("lte_data_score", C(FilterOperator.LTE, "data.score", 9)),
    ("gt_data_tier_text", C(FilterOperator.GT, "data.tier", "a")),
    ("lt_data_tier_text", C(FilterOperator.LT, "data.tier", "g")),
    ("and_tree", AND(C(FilterOperator.EQ, "data.tier", "pro"), C(FilterOperator.GT, "data.score", 9))),
    ("or_tree", OR(C(FilterOperator.EQ, "name", "llama"), C(FilterOperator.EQ, "name", "zephyr"))),
    ("not_tree", NOT(C(FilterOperator.EQ, "data.tier", "pro"))),
    (
        "nested_and_or_not",
        AND(
            OR(C(FilterOperator.EQ, "data.tier", "pro"), C(FilterOperator.EQ, "data.tier", "free")),
            NOT(C(FilterOperator.LT, "data.score", 9)),
        ),
    ),
]


@pytest.mark.parametrize("label,op", CASES, ids=[c[0] for c in CASES])
def test_matches_matches_sql(db, label, op):
    repo = SQLAlchemyFilterRepository(FakeEntity)
    condition = op.apply(repo)
    sql_ids = {r.id for r in db.execute(select(FakeEntity).where(condition)).scalars().all()}

    all_rows = db.execute(select(FakeEntity)).scalars().all()
    py_ids = {r.id for r in all_rows if op.matches(r)}

    assert py_ids == sql_ids, f"{label}: matches()={sorted(py_ids)} != SQL={sorted(sql_ids)}"
