#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic audit coverage from ATIF tool calls."""

from __future__ import annotations

from typing import Any

METHOD_NAME = "tool_calls"
ITEM_KIND = "tool"
DETAILS_SCHEMA = "nemo.eval_author.audit_tool_calls_details.v1"


def measure(audit: dict[str, Any], trajectory: Any) -> dict[str, Any]:
    """Measure audit tool items against the tool calls present in an ATIF trace."""
    audit_tools = [item["name"] for item in audit["items"] if item["kind"] == ITEM_KIND]
    observed_tool_calls = _tool_calls(trajectory, trajectory_path="$")
    matches = {tool: [call for call in observed_tool_calls if call["tool"] == tool] for tool in audit_tools}
    covered = [tool for tool in audit_tools if matches[tool]]
    missing = [tool for tool in audit_tools if tool not in covered]
    return {
        "item_kind": ITEM_KIND,
        "covered": covered,
        "details": {
            "schema": DETAILS_SCHEMA,
            "item_kind": ITEM_KIND,
            "audit_tools": audit_tools,
            "covered": covered,
            "missing": missing,
            "observed_tool_calls": observed_tool_calls,
            "tool_call_counts": _tool_call_counts(observed_tool_calls),
            "matches": matches,
        },
    }


def _tool_calls(trajectory: Any, *, trajectory_path: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    trajectory_id = _optional_string(getattr(trajectory, "trajectory_id", None))
    for step_index, step in enumerate(getattr(trajectory, "steps", []) or [], start=1):
        step_id = getattr(step, "step_id", None) or step_index
        for tool_call in getattr(step, "tool_calls", None) or []:
            function_name = getattr(tool_call, "function_name", None)
            if not isinstance(function_name, str) or not function_name.strip():
                continue
            call: dict[str, Any] = {
                "tool": function_name.strip(),
                "step_id": step_id,
                "trajectory_path": trajectory_path,
            }
            tool_call_id = _optional_string(getattr(tool_call, "tool_call_id", None))
            if tool_call_id is not None:
                call["tool_call_id"] = tool_call_id
            if trajectory_id is not None:
                call["trajectory_id"] = trajectory_id
            calls.append(call)

    for index, subagent in enumerate(getattr(trajectory, "subagent_trajectories", None) or []):
        calls.extend(_tool_calls(subagent, trajectory_path=f"{trajectory_path}.subagent_trajectories[{index}]"))
    return calls


def _tool_call_counts(tool_calls: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for call in tool_calls:
        tool = call["tool"]
        counts[tool] = counts.get(tool, 0) + 1
    return counts


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
