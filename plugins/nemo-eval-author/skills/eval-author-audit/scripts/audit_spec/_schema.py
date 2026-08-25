#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Schema validation for the audit-spec coverage denominator."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from _markdown import extract_schema_block

AUDIT_SCHEMA = "nemo.eval_author.audit.v1"

ETHOS_SECTION_TITLES = frozenset(
    {
        "Role",
        "Purpose",
        "Scope",
        "Tools",
        "Model",
        "Framework",
        "Harness",
        "Behavior",
        "Success Criteria",
        "Evaluation Setup",
        "Change Scope",
        "Signals",
        "Open Questions",
    }
)

ITEM_KINDS = frozenset({"tool", "capability", "failure_case"})
STATUS_VALUES = frozenset({"draft", "approved"})
EVIDENCE_KINDS = frozenset(
    {
        "environment_state",
        "outcome",
        "output",
        "policy_boundary",
        "state_change",
        "tool_call",
        "trace_span",
        "user_intent",
        "verifier",
    }
)

_TOP_LEVEL_FIELDS = frozenset({"schema", "agent", "source_ethos", "source_ethos_sha256", "status", "items"})
_COMMON_ITEM_FIELDS = frozenset({"kind", "id", "name", "ethos_refs", "description", "evidence_required"})
_TOOL_FIELDS = _COMMON_ITEM_FIELDS | frozenset({"expected_use", "expected_failure_behavior"})
_CAPABILITY_FIELDS = _COMMON_ITEM_FIELDS | frozenset({"required_tools", "expected_behavior"})
_FAILURE_CASE_FIELDS = _COMMON_ITEM_FIELDS | frozenset(
    {"applies_to", "trigger", "expected_behavior", "expected_tools", "prohibited_tools", "prohibited_outputs"}
)
_ITEM_FIELDS_BY_KIND = {
    "tool": _TOOL_FIELDS,
    "capability": _CAPABILITY_FIELDS,
    "failure_case": _FAILURE_CASE_FIELDS,
}
_REQUIRED_BY_KIND = {
    "tool": _COMMON_ITEM_FIELDS | frozenset({"expected_use", "expected_failure_behavior"}),
    "capability": _COMMON_ITEM_FIELDS | frozenset({"required_tools", "expected_behavior"}),
    "failure_case": _COMMON_ITEM_FIELDS | frozenset({"applies_to", "trigger", "expected_behavior"}),
}
_ID_PREFIX_BY_KIND = {"tool": "TOOL-", "capability": "CAP-", "failure_case": "FAIL-"}
_EVIDENCE_FIELDS = frozenset({"kind", "description", "tool"})
_ID_RE = re.compile(r"^[A-Z]+-[0-9]{3,}$")
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:/-]*$")


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
    """Return *payload* when it satisfies the audit-spec schema."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        raise AuditSpecError("audit spec must be a mapping")

    _check_fields("audit", payload, required=_TOP_LEVEL_FIELDS, allowed=_TOP_LEVEL_FIELDS, errors=errors)
    _check_literal("audit.schema", payload.get("schema"), AUDIT_SCHEMA, errors)
    _check_nonempty_string("audit.agent", payload.get("agent"), errors)
    _check_nonempty_string("audit.source_ethos", payload.get("source_ethos"), errors)
    _check_hash("audit.source_ethos_sha256", payload.get("source_ethos_sha256"), errors)
    _check_enum("audit.status", payload.get("status"), STATUS_VALUES, errors)

    items = payload.get("items")
    if not isinstance(items, list) or not items:
        errors.append("audit.items must be a non-empty list")
        raise AuditSpecError("\n".join(errors))

    item_ids: set[str] = set()
    tool_names: set[str] = set()
    capability_ids: set[str] = set()
    names_by_kind: dict[str, set[str]] = {kind: set() for kind in ITEM_KINDS}

    for index, item in enumerate(items):
        path = f"audit.items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be a mapping")
            continue
        kind = item.get("kind")
        _check_enum(f"{path}.kind", kind, ITEM_KINDS, errors)
        if kind not in ITEM_KINDS:
            continue
        _check_fields(
            path,
            item,
            required=_REQUIRED_BY_KIND[kind],
            allowed=_ITEM_FIELDS_BY_KIND[kind],
            errors=errors,
        )
        item_id = _check_id(f"{path}.id", item.get("id"), _ID_PREFIX_BY_KIND[kind], errors)
        if item_id is not None:
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
        _check_string_list(f"{path}.ethos_refs", item.get("ethos_refs"), errors, allowed=ETHOS_SECTION_TITLES)
        _check_nonempty_string(f"{path}.description", item.get("description"), errors)
        _check_evidence(f"{path}.evidence_required", item.get("evidence_required"), errors)
        if kind == "tool":
            _check_nonempty_string(f"{path}.expected_use", item.get("expected_use"), errors)
            _check_nonempty_string(f"{path}.expected_failure_behavior", item.get("expected_failure_behavior"), errors)
        elif kind == "capability":
            _check_string_list(f"{path}.required_tools", item.get("required_tools"), errors)
            _check_nonempty_string(f"{path}.expected_behavior", item.get("expected_behavior"), errors)
        elif kind == "failure_case":
            _check_string_list(f"{path}.applies_to", item.get("applies_to"), errors)
            _check_nonempty_string(f"{path}.trigger", item.get("trigger"), errors)
            _check_nonempty_string(f"{path}.expected_behavior", item.get("expected_behavior"), errors)
            _check_optional_string_list(f"{path}.expected_tools", item.get("expected_tools"), errors)
            _check_optional_string_list(f"{path}.prohibited_tools", item.get("prohibited_tools"), errors)
            _check_optional_string_list(f"{path}.prohibited_outputs", item.get("prohibited_outputs"), errors)

    if errors:
        raise AuditSpecError("\n".join(errors))

    for index, item in enumerate(items):
        path = f"audit.items[{index}]"
        for field in ("required_tools", "expected_tools", "prohibited_tools"):
            _check_known_tools(f"{path}.{field}", item.get(field), tool_names, errors)
        for evidence_index, evidence in enumerate(item["evidence_required"]):
            _check_known_tools(
                f"{path}.evidence_required[{evidence_index}].tool", [evidence.get("tool")], tool_names, errors
            )
        if item["kind"] == "failure_case":
            for ref in item["applies_to"]:
                if ref not in capability_ids:
                    errors.append(f"{path}.applies_to references unknown capability id {ref!r}")

    if errors:
        raise AuditSpecError("\n".join(errors))
    return payload


def item_counts(spec: dict[str, Any]) -> dict[str, int]:
    """Return item counts by kind."""
    counts = Counter(item["kind"] for item in spec["items"])
    return {kind: counts.get(kind, 0) for kind in sorted(ITEM_KINDS)}


def _check_fields(
    path: str,
    payload: dict[str, Any],
    *,
    required: frozenset[str],
    allowed: frozenset[str],
    errors: list[str],
) -> None:
    missing = sorted(required - payload.keys())
    extra = sorted(payload.keys() - allowed)
    if missing:
        errors.append(f"{path} missing required fields: {', '.join(missing)}")
    if extra:
        errors.append(f"{path} has unknown fields: {', '.join(extra)}")


def _check_literal(path: str, value: Any, expected: str, errors: list[str]) -> None:
    if value != expected:
        errors.append(f"{path} must be {expected!r}")


def _check_enum(path: str, value: Any, allowed: frozenset[str], errors: list[str]) -> None:
    if not isinstance(value, str) or value not in allowed:
        errors.append(f"{path} must be one of {sorted(allowed)}")


def _check_nonempty_string(path: str, value: Any, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be a non-empty string")
        return None
    return value


def _check_hash(path: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        errors.append(f"{path} must be a sha256:<64 hex chars> digest")


def _check_id(path: str, value: Any, prefix: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        errors.append(f"{path} must match {_ID_RE.pattern}")
        return None
    if not value.startswith(prefix):
        errors.append(f"{path} must start with {prefix!r}")
    return value


def _check_name(path: str, value: Any, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not _NAME_RE.fullmatch(value):
        errors.append(f"{path} must be a non-empty identifier matching {_NAME_RE.pattern}")
        return None
    return value


def _check_string_list(
    path: str,
    value: Any,
    errors: list[str],
    *,
    allowed: frozenset[str] | None = None,
) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{path} must be a non-empty list of strings")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{path}[{index}] must be a non-empty string")
            continue
        if allowed is not None and item not in allowed:
            errors.append(f"{path}[{index}] must be one of {sorted(allowed)}")
        result.append(item)
    return result


def _check_optional_string_list(path: str, value: Any, errors: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{path} must be a list of strings")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{path}[{index}] must be a non-empty string")
            continue
        result.append(item)
    return result


def _check_evidence(path: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{path} must be a non-empty list")
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_path} must be a mapping")
            continue
        _check_fields(
            item_path,
            item,
            required=frozenset({"kind", "description"}),
            allowed=_EVIDENCE_FIELDS,
            errors=errors,
        )
        _check_enum(f"{item_path}.kind", item.get("kind"), EVIDENCE_KINDS, errors)
        _check_nonempty_string(f"{item_path}.description", item.get("description"), errors)
        if "tool" in item:
            _check_name(f"{item_path}.tool", item.get("tool"), errors)


def _check_known_tools(path: str, values: Any, tool_names: set[str], errors: list[str]) -> None:
    if values is None:
        return
    if not isinstance(values, list):
        errors.append(f"{path} must be a list of tool names")
        return
    for value in values:
        if value is None:
            continue
        if value not in tool_names:
            errors.append(f"{path} references unknown tool name {value!r}")
