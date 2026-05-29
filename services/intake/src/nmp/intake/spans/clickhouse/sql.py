# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed SQL fragments for Intake ClickHouse query builders."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, init=False)
class TrustedSql:
    """SQL fragment constructed only by local query helpers."""

    sql: str

    def __init__(self, sql: str) -> None:
        raise TypeError("Use a trusted SQL helper instead of constructing TrustedSql directly")

    @classmethod
    def _from_sql(cls, sql: str) -> TrustedSql:
        instance = object.__new__(cls)
        object.__setattr__(instance, "sql", sql)
        return instance


@dataclass(frozen=True, init=False)
class BuiltQuery:
    """Rendered SQL and bound parameters from trusted query builders."""

    sql: str
    parameters: dict[str, Any]

    def __init__(self, sql: str, parameters: Mapping[str, Any] | None = None) -> None:
        raise TypeError("Use a trusted query helper instead of constructing BuiltQuery directly")

    @classmethod
    def _from_parts(cls, sql: str, parameters: Mapping[str, Any] | None = None) -> BuiltQuery:
        instance = object.__new__(cls)
        object.__setattr__(instance, "sql", sql)
        object.__setattr__(instance, "parameters", dict(parameters or {}))
        return instance


def _trusted_sql(sql: str) -> TrustedSql:
    return TrustedSql._from_sql(sql)


def _trusted_query(sql: str, parameters: Mapping[str, Any] | None = None) -> BuiltQuery:
    return BuiltQuery._from_parts(sql, parameters)
