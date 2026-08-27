#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Composite audit coverage for capability items."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TypeAlias

from measurements.trace_tools import collect_tool_calls, tool_call_counts

try:
    from harbor.models.trajectories import Trajectory  # ty: ignore[unresolved-import]
except ImportError:
    Trajectory = Any  # type: ignore[assignment,misc]

JsonObject: TypeAlias = dict[str, Any]

METHOD_NAME = "capabilities"
ITEM_KIND = "capability"
DETAILS_SCHEMA = "nemo.eval_author.audit_capabilities_details.v1"
JUDGMENTS_SCHEMA = "nemo.eval_author.audit_capability_judgments.v1"
DETERMINISTIC_EVIDENCE_KINDS = frozenset({"tool_call"})
JUDGEABLE_EVIDENCE_KINDS = frozenset(
    {
        "environment_state",
        "outcome",
        "output",
        "policy_boundary",
        "state_change",
        "trace_span",
        "user_intent",
        "verifier",
    }
)
EvidenceTarget: TypeAlias = tuple[str, int]


def measure(audit: JsonObject, trajectory: Trajectory, *, judgments: JsonObject | None = None) -> JsonObject:
    """Measure capability items from deterministic trace evidence plus optional judgments."""
    audit_capabilities = [item for item in audit["items"] if item["kind"] == ITEM_KIND]
    observed_tool_calls = collect_tool_calls(trajectory)
    calls_by_tool = _calls_by_tool(observed_tool_calls)
    judgments_by_target = _judgments_by_target(audit_capabilities, judgments)
    capability_results = {
        item["name"]: _capability_result(
            item,
            calls_by_tool=calls_by_tool,
            judgments_by_target=judgments_by_target,
        )
        for item in audit_capabilities
    }
    covered = [name for name, result in capability_results.items() if result["covered"]]
    missing = [name for name in capability_results if name not in covered]
    return {
        "item_kind": ITEM_KIND,
        "covered": covered,
        "details": {
            "schema": DETAILS_SCHEMA,
            "item_kind": ITEM_KIND,
            "audit_capabilities": [item["name"] for item in audit_capabilities],
            "covered": covered,
            "missing": missing,
            "judgment_input": _judgment_input_summary(judgments),
            "judged_evidence_kinds": _evidence_kinds_with_status(
                capability_results.values(),
                statuses={"satisfied", "missing", "unclear"},
                measurements={"judged"},
            ),
            "unjudged_evidence_kinds": _evidence_kinds_with_status(
                capability_results.values(),
                statuses={"unjudged"},
            ),
            "unsupported_evidence_kinds": _unsupported_evidence_kinds(capability_results.values()),
            "observed_tool_calls": observed_tool_calls,
            "tool_call_counts": tool_call_counts(observed_tool_calls),
            "capability_results": capability_results,
        },
    }


def _capability_result(
    item: JsonObject,
    *,
    calls_by_tool: dict[str, list[JsonObject]],
    judgments_by_target: dict[EvidenceTarget, JsonObject],
) -> JsonObject:
    """Return per-capability evidence status after applying deterministic and judged evidence."""
    required_tools = _dedupe_names(item["required_tools"])
    required_tool_results = [_required_tool_result(tool, calls_by_tool=calls_by_tool) for tool in required_tools]
    evidence_results = [
        _evidence_result(
            item["name"],
            evidence_index,
            evidence,
            calls_by_tool=calls_by_tool,
            judgments_by_target=judgments_by_target,
        )
        for evidence_index, evidence in enumerate(item["evidence_required"])
    ]
    missing_reasons = _missing_reasons(
        required_tool_results=required_tool_results,
        evidence_results=evidence_results,
    )
    return {
        "name": item["name"],
        "covered": not missing_reasons,
        "required_tools": required_tools,
        "required_tool_results": required_tool_results,
        "evidence_results": evidence_results,
        "missing_reasons": missing_reasons,
    }


def _required_tool_result(tool: str, *, calls_by_tool: dict[str, list[JsonObject]]) -> JsonObject:
    """Return whether a capability's declared required tool appeared in the trace."""
    matches = calls_by_tool.get(tool, [])
    return {
        "tool": tool,
        "status": "satisfied" if matches else "missing",
        "matches": matches,
    }


def _evidence_result(
    capability_name: str,
    evidence_index: int,
    evidence: JsonObject,
    *,
    calls_by_tool: dict[str, list[JsonObject]],
    judgments_by_target: dict[EvidenceTarget, JsonObject],
) -> JsonObject:
    """Return deterministic or judged status for one evidence requirement."""
    kind = evidence["kind"]
    result: JsonObject = {
        "kind": kind,
        "evidence_index": evidence_index,
        "description": evidence["description"],
    }
    if kind in DETERMINISTIC_EVIDENCE_KINDS:
        tool = evidence["tool"]
        matches = calls_by_tool.get(tool, [])
        result.update(
            {
                "measurement": "deterministic",
                "tool": tool,
                "status": "satisfied" if matches else "missing",
                "matches": matches,
            }
        )
        return result

    if kind in JUDGEABLE_EVIDENCE_KINDS:
        judgment = judgments_by_target.get((capability_name, evidence_index))
        if judgment is None:
            result.update(
                {
                    "measurement": "judgment_required",
                    "status": "unjudged",
                }
            )
            return result
        result.update(
            {
                "measurement": "judged",
                "status": judgment["status"],
                "confidence": judgment["confidence"],
                "rationale": judgment["rationale"],
            }
        )
        if "supporting_trace_refs" in judgment:
            result["supporting_trace_refs"] = judgment["supporting_trace_refs"]
        return result

    result["measurement"] = "unsupported"
    result["status"] = "unsupported"
    return result


def _missing_reasons(
    *,
    required_tool_results: list[JsonObject],
    evidence_results: list[JsonObject],
) -> list[str]:
    """Return stable reason codes for why a capability was not covered."""
    reasons: list[str] = []
    if any(result["status"] == "missing" for result in required_tool_results):
        reasons.append("missing_required_tool")
    if any(result["measurement"] == "deterministic" and result["status"] == "missing" for result in evidence_results):
        reasons.append("missing_tool_call_evidence")
    if any(result["status"] == "unjudged" for result in evidence_results):
        reasons.append("unjudged_evidence")
    if any(result["measurement"] == "judged" and result["status"] != "satisfied" for result in evidence_results):
        reasons.append("judged_evidence_not_satisfied")
    if any(result["status"] == "unsupported" for result in evidence_results):
        reasons.append("unsupported_evidence_kind")
    return reasons


def _judgments_by_target(
    audit_capabilities: list[JsonObject], judgments: JsonObject | None
) -> dict[EvidenceTarget, JsonObject]:
    """Index capability judgments and reject stale or unsafe targets."""
    if judgments is None:
        return {}

    capabilities_by_name = {item["name"]: item for item in audit_capabilities}
    indexed: dict[EvidenceTarget, JsonObject] = {}
    errors: list[str] = []
    for index, judgment in enumerate(judgments["judgments"]):
        capability_name = judgment["capability"]
        evidence_index = judgment["evidence_index"]
        target = (capability_name, evidence_index)
        capability = capabilities_by_name.get(capability_name)
        if capability is None:
            errors.append(f"judgments[{index}] references unknown capability {capability_name!r}")
            continue
        evidence_items = capability["evidence_required"]
        if evidence_index < 0 or evidence_index >= len(evidence_items):
            errors.append(f"judgments[{index}] references missing evidence index {evidence_index}")
            continue
        evidence = evidence_items[evidence_index]
        if evidence["kind"] in DETERMINISTIC_EVIDENCE_KINDS:
            errors.append(f"judgments[{index}] targets deterministic evidence kind {evidence['kind']!r}")
        if evidence["kind"] != judgment["kind"]:
            errors.append(
                f"judgments[{index}] kind {judgment['kind']!r} does not match audit evidence kind {evidence['kind']!r}"
            )
        if evidence["description"] != judgment["description"]:
            errors.append(f"judgments[{index}] description does not match audit evidence description")
        if target in indexed:
            errors.append(
                f"judgments[{index}] duplicates capability {capability_name!r} evidence index {evidence_index}"
            )
        indexed[target] = judgment

    if errors:
        raise ValueError("invalid capability judgments:\n" + "\n".join(errors))
    return indexed


def _judgment_input_summary(judgments: JsonObject | None) -> JsonObject:
    """Return reproducibility metadata about the optional judgment input."""
    if judgments is None:
        return {"provided": False, "judgment_count": 0}
    summary: JsonObject = {
        "provided": True,
        "schema": judgments["schema"],
        "judgment_count": len(judgments["judgments"]),
    }
    judged_by = judgments.get("judged_by")
    if isinstance(judged_by, str) and judged_by.strip():
        summary["judged_by"] = judged_by.strip()
    return summary


def _evidence_kinds_with_status(
    results: Iterable[JsonObject],
    *,
    statuses: set[str],
    measurements: set[str] | None = None,
) -> list[str]:
    """Return evidence kinds matching status and optional measurement filters."""
    kinds: list[str] = []
    for result in results:
        for evidence in result["evidence_results"]:
            if evidence["status"] not in statuses:
                continue
            if measurements is not None and evidence["measurement"] not in measurements:
                continue
            kinds.append(evidence["kind"])
    return list(dict.fromkeys(kinds))


def _unsupported_evidence_kinds(results: Iterable[JsonObject]) -> list[str]:
    """Return unsupported evidence kinds observed across capability results."""
    kinds: list[str] = []
    for result in results:
        for evidence in result["evidence_results"]:
            if evidence["status"] == "unsupported":
                kinds.append(evidence["kind"])
    return list(dict.fromkeys(kinds))


def _dedupe_names(names: Iterable[str]) -> list[str]:
    """Dedupe declared names while preserving audit order."""
    return list(dict.fromkeys(names))


def _calls_by_tool(tool_calls: list[JsonObject]) -> dict[str, list[JsonObject]]:
    """Group observed ATIF tool calls by function name."""
    grouped: dict[str, list[JsonObject]] = {}
    for call in tool_calls:
        grouped.setdefault(call["tool"], []).append(call)
    return grouped
