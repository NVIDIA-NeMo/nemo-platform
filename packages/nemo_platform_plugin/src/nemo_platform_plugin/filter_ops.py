# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Filter operation base types for the entity store.

These are the minimal types needed by EntityClient and Filter. The full parsing
engine (parse_json_filter, parse_bracket_filter, etc.) lives in nmp.common.api.filter.
"""

import re
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel

# Sentinel distinguishing "field/key is absent" from an explicit None value.
_MISSING = object()


class FilterOperator(str, Enum):
    """Filter operator."""

    # Comparison operators
    EQ = "$eq"
    LIKE = "$like"
    LT = "$lt"
    LTE = "$lte"
    GT = "$gt"
    GTE = "$gte"
    IN = "$in"
    NIN = "$nin"

    # Logical operators
    OR = "$or"
    AND = "$and"
    NOT = "$not"

    # Relationship operators
    EXISTS = "$exists"


class FilterRepository(ABC):
    """Abstract base class for repository implementations that execute filter operations."""

    @abstractmethod
    def eq(self, field: str, value: Any) -> Any:
        pass

    @abstractmethod
    def like(self, field: str, value: str) -> Any:
        pass

    @abstractmethod
    def lt(self, field: str, value: Any) -> Any:
        pass

    @abstractmethod
    def lte(self, field: str, value: Any) -> Any:
        pass

    @abstractmethod
    def gt(self, field: str, value: Any) -> Any:
        pass

    @abstractmethod
    def gte(self, field: str, value: Any) -> Any:
        pass

    @abstractmethod
    def in_op(self, field: str, values: List[Any]) -> Any:
        pass

    @abstractmethod
    def nin(self, field: str, values: List[Any]) -> Any:
        pass

    @abstractmethod
    def and_op(self, operations: List[Any]) -> Any:
        pass

    @abstractmethod
    def or_op(self, operations: List[Any]) -> Any:
        pass

    @abstractmethod
    def not_op(self, operation: Any) -> Any:
        pass

    def relationship_exists(
        self,
        target_entity_type: str,
        join_field: str,
        child_condition: "FilterOperation | None",
        negate: bool,
    ) -> Any:
        raise NotImplementedError("Relationship queries not supported by this repository")


class FilterOperation(BaseModel, ABC):
    """Abstract base class for filter operations."""

    operator: FilterOperator

    @abstractmethod
    def apply(self, repository: FilterRepository) -> Any:
        """Apply this operation using the given repository."""
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        pass

    def matches(self, entity: Any) -> bool:
        """Evaluate this filter operation against an in-memory entity.

        This is a Python-side mirror of the SQL/repository layer (see
        ``SQLAlchemyFilterRepository``) so callers can ask "does this entity
        match the filter?" without re-implementing per-field checks.

        Concrete by design (not abstract): subclasses that have no in-memory
        evaluation (e.g. relationship/EXISTS operations) inherit this default,
        which raises rather than forcing them to implement it.
        """
        raise NotImplementedError(f"matches() is not supported for {type(self).__name__}")


class ComparisonOperation(FilterOperation):
    """Comparison operation (e.g., eq, lt, gte, like)."""

    operator: FilterOperator
    field: str
    value: Any

    def apply(self, repository: FilterRepository) -> Any:
        if self.operator == FilterOperator.EQ:
            return repository.eq(self.field, self.value)
        elif self.operator == FilterOperator.LIKE:
            return repository.like(self.field, self.value)
        elif self.operator == FilterOperator.LT:
            return repository.lt(self.field, self.value)
        elif self.operator == FilterOperator.LTE:
            return repository.lte(self.field, self.value)
        elif self.operator == FilterOperator.GT:
            return repository.gt(self.field, self.value)
        elif self.operator == FilterOperator.GTE:
            return repository.gte(self.field, self.value)
        elif self.operator == FilterOperator.IN:
            return repository.in_op(self.field, self.value)
        elif self.operator == FilterOperator.NIN:
            return repository.nin(self.field, self.value)
        elif self.operator == FilterOperator.EXISTS:
            raise NotImplementedError(
                "$exists requires a relationship-aware repository (use the entities service parser)"
            )
        else:
            raise ValueError(f"Unknown comparison operator: {self.operator}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {self.field: {self.operator.value: self.value}}

    def _resolve_field(self, entity: Any) -> tuple[Any, bool]:
        """Resolve this operation's field on an in-memory entity.

        Mirrors ``SQLAlchemyFilterRepository._get_column``: prefer a plain
        attribute; otherwise, for a ``data.``-prefixed dotted field, walk the
        nested ``data`` mapping along the dotted path.

        Returns:
            A tuple ``(value, is_json)`` where ``value`` is the resolved value
            (``_MISSING`` if absent) and ``is_json`` indicates the value came
            from the ``data`` JSON mapping (so SQL JSON-coercion rules apply).
        """
        # Plain attribute access (mirrors `hasattr(model, field)`).
        if _has_attr(entity, self.field):
            return _get_attr(entity, self.field, _MISSING), False

        # JSON `data.<path>` navigation (mirrors the `data.` subscript walk).
        if self.field.startswith("data."):
            data = _get_attr(entity, "data", _MISSING)
            path = self.field.split(".")[1:]
            return _walk_json_path(data, path), True

        raise ValueError(f"Field '{self.field}' does not exist on {type(entity).__name__}")

    def matches(self, entity: Any) -> bool:
        field_value, is_json = self._resolve_field(entity)

        if self.operator == FilterOperator.EQ:
            return _eq_matches(field_value, self.value, is_json)
        elif self.operator == FilterOperator.LIKE:
            return _like_matches(field_value, self.value, is_json)
        elif self.operator == FilterOperator.IN:
            return _in_matches(field_value, self.value, is_json)
        elif self.operator == FilterOperator.NIN:
            return _nin_matches(field_value, self.value, is_json)
        elif self.operator == FilterOperator.LT:
            return _ordered_matches(field_value, self.value, is_json, "lt")
        elif self.operator == FilterOperator.LTE:
            return _ordered_matches(field_value, self.value, is_json, "lte")
        elif self.operator == FilterOperator.GT:
            return _ordered_matches(field_value, self.value, is_json, "gt")
        elif self.operator == FilterOperator.GTE:
            return _ordered_matches(field_value, self.value, is_json, "gte")
        elif self.operator == FilterOperator.EXISTS:
            raise NotImplementedError(
                "$exists requires a relationship-aware repository (use the entities service parser)"
            )
        else:
            raise ValueError(f"Unknown comparison operator: {self.operator}")


class LogicalOperation(FilterOperation):
    """Logical operation (and, or, not)."""

    operator: FilterOperator
    operations: List[FilterOperation]

    def apply(self, repository: FilterRepository) -> Any:
        if self.operator == FilterOperator.AND:
            return repository.and_op([op.apply(repository) for op in self.operations])
        elif self.operator == FilterOperator.OR:
            return repository.or_op([op.apply(repository) for op in self.operations])
        elif self.operator == FilterOperator.NOT:
            if len(self.operations) != 1:
                raise ValueError("NOT operation must have exactly one operand")
            return repository.not_op(self.operations[0].apply(repository))
        else:
            raise ValueError(f"Unknown logical operator: {self.operator}")

    def to_dict(self) -> Dict[str, Any]:
        if self.operator == FilterOperator.NOT:
            return {self.operator.value: self.operations[0].to_dict()}
        return {self.operator.value: [op.to_dict() for op in self.operations]}

    def matches(self, entity: Any) -> bool:
        if self.operator == FilterOperator.AND:
            return all(op.matches(entity) for op in self.operations)
        elif self.operator == FilterOperator.OR:
            return any(op.matches(entity) for op in self.operations)
        elif self.operator == FilterOperator.NOT:
            if len(self.operations) != 1:
                raise ValueError("NOT operation must have exactly one operand")
            return not self.operations[0].matches(entity)
        else:
            raise ValueError(f"Unknown logical operator: {self.operator}")


def _has_attr(entity: Any, field: str) -> bool:
    """Whether `field` is a key (mapping) or attribute (object) of `entity`."""
    if isinstance(entity, dict):
        return field in entity
    return hasattr(entity, field)


def _get_attr(entity: Any, field: str, default: Any) -> Any:
    """Read `field` as a key (mapping) or attribute (object), else `default`."""
    if isinstance(entity, dict):
        return entity.get(field, default)
    return getattr(entity, field, default)


def _walk_json_path(data: Any, path: List[str]) -> Any:
    """Navigate a dotted `data.<a>.<b>` path through nested mappings.

    Mirrors the SQL JSON subscript walk. A missing key (or descending into a
    non-mapping) yields ``_MISSING`` so callers apply SQL null semantics.
    """
    current = data
    for key in path:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return _MISSING
    return current


def _json_text(field_value: Any) -> str:
    """Render a JSON field value the way the SQL layer compares it on SQLite.

    SQLAlchemy emits ``trim(CAST(JSON_QUOTE(json_extract(...)) AS VARCHAR), '"')``.
    The observable consequences this mirrors:

    - A missing key or an explicit JSON ``null`` both become the literal text
      ``"null"`` (``JSON_QUOTE(NULL)`` is the string ``'null'``).
    - A JSON string ``"x"`` compares as ``x`` (surrounding quotes trimmed).
    - A JSON boolean stores as an integer on SQLite, so it renders ``"1"`` /
      ``"0"`` (PostgreSQL would render ``"true"`` / ``"false"`` — a documented
      backend difference; this Python mirror tracks the SQLite engine used by
      the parity tests).
    - Numbers render via ``str()``.
    """
    if field_value is _MISSING or field_value is None:
        return "null"
    if isinstance(field_value, bool):
        return "1" if field_value else "0"
    return str(field_value)


def _sqlite_cast_float(text: str) -> float:
    """Emulate SQLite ``CAST(<text> AS FLOAT)``.

    SQLite performs a lenient leading-numeric parse (``"5abc"`` -> 5.0,
    ``"abc"`` / ``"null"`` -> 0.0) rather than Python's strict ``float()``.
    """
    try:
        return float(text)
    except (TypeError, ValueError):
        pass
    match = re.match(r"\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", text)
    if match and match.group(0).strip():
        try:
            return float(match.group(0))
        except ValueError:
            return 0.0
    return 0.0


def _eq_matches(field_value: Any, value: Any, is_json: bool) -> bool:
    """Mirror ``SQLAlchemyFilterRepository.eq``."""
    if is_json:
        # Missing key or explicit null: SQL renders both as text "null" and the
        # eq() null branch matches them (cast == "null").
        if value is None:
            return field_value is _MISSING or field_value is None
        # Booleans match either the SQLite ("1"/"0") or PostgreSQL
        # ("true"/"false") canonical forms; comparing the actual stored value
        # captures both.
        if isinstance(value, bool):
            return field_value == value
        return _json_text(field_value) == str(value)

    # Plain attribute: native Python equality (missing -> treated as None,
    # mirroring `column == value` over a NULL column / `column IS NULL`).
    if field_value is _MISSING:
        field_value = None
    return field_value == value


def _like_matches(field_value: Any, value: Any, is_json: bool) -> bool:
    """Mirror ``SQLAlchemyFilterRepository.like``: case-insensitive substring.

    `$like` is NOT regex: SQL does ``column.ilike("%" + value + "%")``, an
    unanchored case-insensitive contains. `%`/`_` in the value are NOT treated
    as wildcards here.

    For a plain column a NULL value never matches (``NULL ILIKE x`` is NULL).
    For a JSON field, null/missing renders as the literal text ``"null"`` and
    is matched as such.
    """
    needle = str(value).lower()
    if is_json:
        return needle in _json_text(field_value).lower()
    if field_value is _MISSING or field_value is None:
        return False
    return needle in str(field_value).lower()


def _in_matches(field_value: Any, values: Any, is_json: bool) -> bool:
    """Mirror ``SQLAlchemyFilterRepository.in_op`` (membership test).

    JSON members are coerced to text (null/missing renders as ``"null"``);
    plain columns use native membership, where a NULL field matches nothing.
    """
    if is_json:
        return _json_text(field_value) in [str(v) for v in values]
    if field_value is _MISSING or field_value is None:
        return False
    return field_value in values


def _nin_matches(field_value: Any, values: Any, is_json: bool) -> bool:
    """Mirror ``SQLAlchemyFilterRepository.nin``.

    JSON: the complement of `$in` (null/missing renders as ``"null"`` and so
    *does* satisfy `$nin` unless ``"null"`` is one of the excluded values).
    Plain column: a NULL field never matches (``NULL NOT IN (...)`` is NULL,
    i.e. not true) — this is NOT simply ``not _in_matches``.
    """
    if is_json:
        return _json_text(field_value) not in [str(v) for v in values]
    if field_value is _MISSING or field_value is None:
        return False
    return field_value not in values


def _compare(left: Any, right: Any, op: str) -> bool:
    """Apply an ordered comparison, returning False on incomparable operands.

    ``left``/``right`` are intentionally ``Any``: the SQL layer compares
    heterogeneous values (e.g. numeric vs text), and a genuine Python type
    mismatch is treated as "no match" (mirrors SQL three-valued NULL results).
    """
    try:
        if op == "lt":
            return left < right
        elif op == "lte":
            return left <= right
        elif op == "gt":
            return left > right
        else:  # "gte"
            return left >= right
    except TypeError:
        return False


def _ordered_matches(field_value: Any, value: Any, is_json: bool, op: str) -> bool:
    """Mirror ``SQLAlchemyFilterRepository._json_comparison`` for lt/lte/gt/gte."""
    if is_json:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            # Numeric cast on both sides (CAST(... AS FLOAT) in SQL); null/
            # missing and non-numeric text cast to 0.0 on SQLite.
            return _compare(_sqlite_cast_float(_json_text(field_value)), float(value), op)
        return _compare(_json_text(field_value), str(value), op)

    # Plain column: a NULL/missing field never satisfies an ordered comparison
    # (SQL `NULL < x` is NULL, i.e. not true).
    if field_value is _MISSING or field_value is None:
        return False
    # Datetime columns coerce ISO-format string inputs (mirrors
    # `_coerce_value_for_column`).
    if isinstance(field_value, datetime) and isinstance(value, str):
        value = datetime.fromisoformat(value).replace(tzinfo=None)
    return _compare(field_value, value, op)
