#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Permissive ATIF trace facts for audit measurement."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AtifTraceError(ValueError):
    """Raised when a trace cannot be read as an ATIF trajectory."""


@dataclass(frozen=True)
class ToolCallFact:
    """A tool call found in one ATIF trajectory step."""

    tool: str
    step_id: int | str | None
    tool_call_id: str | None
    trajectory_id: str | None
    trajectory_path: str

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool": self.tool,
            "trajectory_path": self.trajectory_path,
        }
        if self.step_id is not None:
            payload["step_id"] = self.step_id
        if self.tool_call_id is not None:
            payload["tool_call_id"] = self.tool_call_id
        if self.trajectory_id is not None:
            payload["trajectory_id"] = self.trajectory_id
        return payload


@dataclass(frozen=True)
class AtifTraceFacts:
    """The trace facts audit measurement methods can consume."""

    path: Path
    schema_version: str
    session_id: str | None
    trajectory_id: str | None
    tool_calls: tuple[ToolCallFact, ...]

    @property
    def tool_call_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for call in self.tool_calls:
            counts[call.tool] = counts.get(call.tool, 0) + 1
        return counts

    def matches(self, tool: str) -> list[dict[str, Any]]:
        return [call.to_json() for call in self.tool_calls if call.tool == tool]


def load_atif_trace(path: Path) -> AtifTraceFacts:
    """Read an ATIF trajectory and return the facts used by measurement."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AtifTraceError(f"could not read ATIF trace at {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AtifTraceError(f"ATIF trace at {path} is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise AtifTraceError(f"ATIF trace at {path} must be a JSON object")
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.startswith("ATIF-"):
        raise AtifTraceError(f"{path} is not an ATIF trajectory: expected schema_version starting with 'ATIF-'")
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise AtifTraceError(f"ATIF trace at {path} must contain a steps list")

    return AtifTraceFacts(
        path=path,
        schema_version=schema_version,
        session_id=_optional_string(payload.get("session_id")),
        trajectory_id=_optional_string(payload.get("trajectory_id")),
        tool_calls=tuple(_tool_calls(payload, trajectory_path="$")),
    )


def _tool_calls(trajectory: dict[str, Any], *, trajectory_path: str) -> list[ToolCallFact]:
    calls: list[ToolCallFact] = []
    trajectory_id = _optional_string(trajectory.get("trajectory_id"))
    steps = trajectory.get("steps")
    if isinstance(steps, list):
        for step_index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            step_id = step.get("step_id") if isinstance(step.get("step_id"), int | str) else step_index + 1
            for call in _step_tool_calls(step):
                calls.append(
                    ToolCallFact(
                        tool=call["tool"],
                        step_id=step_id,
                        tool_call_id=call["tool_call_id"],
                        trajectory_id=trajectory_id,
                        trajectory_path=trajectory_path,
                    )
                )

    subagents = trajectory.get("subagent_trajectories")
    if isinstance(subagents, list):
        for index, subagent in enumerate(subagents):
            if isinstance(subagent, dict):
                calls.extend(_tool_calls(subagent, trajectory_path=f"{trajectory_path}.subagent_trajectories[{index}]"))
    return calls


def _step_tool_calls(step: dict[str, Any]) -> list[dict[str, str | None]]:
    tool_calls = step.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []

    calls: list[dict[str, str | None]] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        tool = _tool_name(tool_call)
        if tool is None:
            continue
        calls.append({"tool": tool, "tool_call_id": _optional_string(tool_call.get("tool_call_id"))})
    return calls


def _tool_name(tool_call: dict[str, Any]) -> str | None:
    function_name = tool_call.get("function_name")
    if isinstance(function_name, str) and function_name.strip():
        return function_name.strip()
    name = tool_call.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    function = tool_call.get("function")
    if isinstance(function, dict):
        function_name = function.get("name")
        if isinstance(function_name, str) and function_name.strip():
            return function_name.strip()
    return None


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
