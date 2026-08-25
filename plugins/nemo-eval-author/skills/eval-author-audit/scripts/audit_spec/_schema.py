#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Schema validation for the audit-spec coverage denominator."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from _markdown import extract_schema_block

AUDIT_SCHEMA = "nemo.eval_author.audit.v1"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "audit.schema.json"
ITEM_KINDS = frozenset({"tool", "capability", "failure_case"})


class AuditSpecError(ValueError):
    """Raised when an audit spec fails schema validation."""


def load_audit_spec(path: Path) -> dict[str, Any]:
    """Load and validate an ``audit.md`` file."""
    block = extract_schema_block(path)
    try:
        payload = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        raise AuditSpecError(f"audit YAML does not parse: {exc}") from exc
    return validate_audit_spec(payload)


def load_items_file(path: Path) -> list[dict[str, Any]]:
    """Load a YAML items file accepted by ``generate.py``."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise AuditSpecError(f"could not load items from {path}: {exc}") from exc
    if isinstance(payload, dict):
        payload = payload.get("items")
    if not isinstance(payload, list):
        raise AuditSpecError(f"{path} must contain an item list or a mapping with an 'items' list")
    return payload


def validate_audit_spec(payload: Any) -> dict[str, Any]:
    """Return *payload* when it satisfies the audit spec."""
    _validate_json_schema(payload)
    if not isinstance(payload, dict):
        raise AuditSpecError("audit spec must be a mapping")
    return _validate_semantics(payload)


def item_counts(spec: dict[str, Any]) -> dict[str, int]:
    """Return item counts by kind."""
    counts = Counter(item["kind"] for item in spec["items"])
    return {kind: counts.get(kind, 0) for kind in sorted(ITEM_KINDS)}


def _validate_json_schema(payload: Any) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise AuditSpecError("jsonschema is required to validate audit specs") from exc

    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditSpecError(f"could not load audit JSON Schema from {SCHEMA_PATH}: {exc}") from exc

    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: (list(error.absolute_path), error.message))
    if errors:
        raise AuditSpecError("\n".join(_format_schema_error(error) for error in errors))


def _validate_semantics(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    items = payload["items"]
    item_ids: set[str] = set()
    tool_names: set[str] = set()
    capability_ids: set[str] = set()
    names_by_kind: dict[str, set[str]] = {kind: set() for kind in ITEM_KINDS}

    for index, item in enumerate(items):
        path = f"audit.items[{index}]"
        kind = item.get("kind")
        item_id = item["id"]
        if item_id in item_ids:
            errors.append(f"{path}.id {item_id!r} is duplicated")
        item_ids.add(item_id)
        if kind == "capability":
            capability_ids.add(item_id)

        name = _check_name(f"{path}.name", item.get("name"), errors)
        if name is not None:
            if name in names_by_kind[kind]:
                errors.append(f"{path}.name {name!r} is duplicated for kind {kind!r}")
            names_by_kind[kind].add(name)
            if kind == "tool":
                tool_names.add(name)

    if errors:
        raise AuditSpecError("\n".join(errors))

    for index, item in enumerate(items):
        path = f"audit.items[{index}]"
        for field in ("required_tools", "expected_tools", "prohibited_tools"):
            _check_known_tools(f"{path}.{field}", item.get(field), tool_names, errors)
        for evidence_index, evidence in enumerate(item["evidence_required"]):
            if "tool" in evidence:
                _check_known_tools(
                    f"{path}.evidence_required[{evidence_index}].tool", [evidence["tool"]], tool_names, errors
                )
        if item["kind"] == "failure_case":
            for ref in item["applies_to"]:
                if ref not in capability_ids:
                    errors.append(f"{path}.applies_to references unknown capability id {ref!r}")

    if errors:
        raise AuditSpecError("\n".join(errors))
    return payload


def _check_name(path: str, value: Any, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"^[A-Za-z][A-Za-z0-9_.:/-]*$", value):
        errors.append(f"{path} must be a non-empty identifier matching ^[A-Za-z][A-Za-z0-9_.:/-]*$")
        return None
    return value


def _check_known_tools(path: str, values: Any, tool_names: set[str], errors: list[str]) -> None:
    if values is None:
        return
    for value in values:
        if value not in tool_names:
            errors.append(f"{path} references unknown tool name {value!r}")


def _format_schema_error(error: Any) -> str:
    if error.validator == "oneOf":
        matching_kind_errors = list(_matching_kind_context_errors(error))
        if matching_kind_errors:
            return "\n".join(_format_schema_error(context) for context in matching_kind_errors)
    return f"{_json_path(error.absolute_path)}: {error.message}"


def _matching_kind_context_errors(error: Any) -> Iterable[Any]:
    instance = error.instance
    if not isinstance(instance, dict):
        return ()
    kind = instance.get("kind")
    if not isinstance(kind, str):
        return ()
    return (
        context
        for context in error.context
        if context.schema.get("properties", {}).get("kind", {}).get("const") == kind
    )


def _json_path(parts: Iterable[Any]) -> str:
    path = "audit"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path
