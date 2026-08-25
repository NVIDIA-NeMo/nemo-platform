#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic audit measurement from ATIF tool calls."""

from __future__ import annotations

from typing import Any

from _atif import AtifTraceFacts

METHOD_NAME = "tool_calls"
SUPPORTED_EVIDENCE_KINDS = frozenset({"tool_call"})


def measure_item(item: dict[str, Any], trace: AtifTraceFacts) -> dict[str, Any]:
    """Measure one audit item against the tool calls present in an ATIF trace."""
    evidence_results = [_measure_evidence(evidence, trace) for evidence in item["evidence_required"]]
    status = _item_status(evidence_results)
    return {
        "name": item["name"],
        "kind": item["kind"],
        "status": status,
        "covered": status == "covered",
        "evidence": evidence_results,
    }


def _measure_evidence(evidence: dict[str, Any], trace: AtifTraceFacts) -> dict[str, Any]:
    kind = evidence["kind"]
    result: dict[str, Any] = {
        "kind": kind,
        "description": evidence["description"],
    }
    if kind != "tool_call":
        result.update(
            {
                "status": "unmeasured",
                "measured": False,
                "reason": f"method {METHOD_NAME!r} supports only tool_call evidence",
            }
        )
        return result

    tool = evidence["tool"]
    matches = trace.matches(tool)
    result.update(
        {
            "status": "covered" if matches else "not_covered",
            "measured": True,
            "tool": tool,
            "matches": matches,
        }
    )
    return result


def _item_status(evidence_results: list[dict[str, Any]]) -> str:
    statuses = {result["status"] for result in evidence_results}
    if statuses == {"covered"}:
        return "covered"
    if "covered" in statuses:
        return "partial"
    if statuses == {"unmeasured"}:
        return "unmeasured"
    return "not_covered"
