# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from scaled_evals.api.schemas.common import decode_cursor

_SAFE_SQL_IDENTIFIERS = frozenset({"created_at", "id"})


class RepositoryError(Exception):
    """Base class for repository-domain failures."""


@dataclass(slots=True)
class NotFound(RepositoryError):
    resource: str
    message: str


@dataclass(slots=True)
class Conflict(RepositoryError):
    code: str
    message: str


@dataclass(slots=True)
class InvalidReference(RepositoryError):
    message: str


def normalize_order(order: str) -> str:
    if order not in {"asc", "desc"}:
        raise ValueError("order must be 'asc' or 'desc'")
    return order


def order_by_clause(columns: Iterable[str], order: str) -> str:
    direction = normalize_order(order).upper()
    normalized_columns = list(columns)
    for column in normalized_columns:
        if column not in _SAFE_SQL_IDENTIFIERS:
            raise ValueError(f"column is not orderable: {column}")
    return ", ".join(f"{column} {direction}" for column in normalized_columns)


def created_at_cursor_clause(cursor: str | None, order: str) -> tuple[str, list[Any]]:
    position = decode_cursor(cursor)
    if position is None:
        return "", []
    direction = normalize_order(order)
    operator = ">" if direction == "asc" else "<"
    return f"(created_at, id) {operator} (%s, %s)", [position.created_at, position.id]


def join_where(clauses: Iterable[str]) -> str:
    return " AND ".join(clauses)


def substring_search_pattern(query: str | None) -> str | None:
    """Return a literal, case-insensitive SQL LIKE pattern for a user query."""
    if query is None or not (normalized := query.strip()):
        return None
    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def patch_set_clause(
    updates: Iterable[tuple[str, Any]],
    patchable_columns: frozenset[str],
) -> tuple[list[str], list[Any]]:
    sets: list[str] = []
    params: list[Any] = []
    for column, value in updates:
        if column not in patchable_columns:
            raise ValueError(f"column is not patchable: {column}")
        if column not in _SAFE_SQL_IDENTIFIERS and not column.replace("_", "").isalnum():
            raise ValueError(f"unsafe patch column: {column}")
        if value is not None:
            sets.append(f"{column} = %s")
            params.append(value)
    return sets, params
