#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic audit coverage from ATIF tool calls."""

from __future__ import annotations

from typing import Any, TypeAlias

try:
    from harbor.models.trajectories import Trajectory  # ty: ignore[unresolved-import]
except ImportError:
    Trajectory = Any  # type: ignore[assignment,misc]

JsonObject: TypeAlias = dict[str, Any]

METHOD_NAME = "tool_calls"
ITEM_KIND = "tool"
DETAILS_SCHEMA = "nemo.eval_author.audit_tool_calls_details.v1"


def measure(audit: JsonObject, trajectory: Trajectory) -> JsonObject:
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


def _tool_calls(trajectory: Trajectory, *, trajectory_path: str) -> list[JsonObject]:
    calls: list[JsonObject] = []
    trajectory_id = _optional_string(trajectory.trajectory_id)
    for step_index, step in enumerate(trajectory.steps or [], start=1):
        step_id = step.step_id or step_index
        for tool_call in step.tool_calls or []:
            function_name = tool_call.function_name
            if not isinstance(function_name, str) or not function_name.strip():
                continue
            call: JsonObject = {
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

    for index, subagent in enumerate(trajectory.subagent_trajectories or []):
        calls.extend(_tool_calls(subagent, trajectory_path=f"{trajectory_path}.subagent_trajectories[{index}]"))
    return calls


def _tool_call_counts(tool_calls: list[JsonObject]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for call in tool_calls:
        tool = call["tool"]
        counts[tool] = counts.get(tool, 0) + 1
    return counts


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
