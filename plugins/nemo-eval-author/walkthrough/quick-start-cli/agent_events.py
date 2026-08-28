# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parse coding-agent CLI output into short activity summaries."""

from __future__ import annotations

import json
import queue
from collections import deque
from typing import Any


def _first_str(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _summarize_tool_call(tool_call: dict[str, Any], *, completed: bool) -> str | None:
    for name, body in tool_call.items():
        if not name.endswith("ToolCall") or not isinstance(body, dict):
            continue
        args = body.get("args")
        if not isinstance(args, dict):
            args = {}

        prefix = "Done" if completed else "Running"
        description = _first_str(body.get("description"), args.get("description"))

        if name == "shellToolCall":
            command = _first_str(args.get("command"))
            detail = description or command
            return f"{prefix}: shell — {detail}" if detail else f"{prefix}: shell"

        if name == "readToolCall":
            path = _first_str(args.get("path"))
            return f"{prefix}: read — {path or description or 'file'}"

        if name in {"writeToolCall", "editToolCall", "searchReplaceToolCall", "applyPatchToolCall"}:
            path = _first_str(args.get("path"), args.get("file_path"))
            return f"{prefix}: edit — {path or description or 'file'}"

        if name == "grepToolCall":
            pattern = _first_str(args.get("pattern"))
            return f"{prefix}: search — {pattern or description or 'codebase'}"

        if name == "globToolCall":
            pattern = _first_str(args.get("globPattern"), args.get("pattern"))
            return f"{prefix}: glob — {pattern or description or 'files'}"

        if name == "listToolCall":
            path = _first_str(args.get("path"))
            return f"{prefix}: list — {path or description or 'directory'}"

        label = name.removesuffix("ToolCall")
        return f"{prefix}: {label}" + (f" — {description}" if description else "")

    return None


def parse_cursor_stream_line(line: str) -> str | None:
    """Turn one Cursor ``stream-json`` line into a human activity summary."""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    event_type = payload.get("type")
    subtype = payload.get("subtype")

    if event_type == "system" and subtype == "init":
        model = _first_str(payload.get("model"))
        return f"Agent started{f' ({model})' if model else ''}"

    if event_type == "thinking" and subtype == "delta":
        return "Thinking…"

    if event_type == "tool_call":
        tool_call = payload.get("tool_call")
        if isinstance(tool_call, dict):
            completed = subtype == "completed"
            return _summarize_tool_call(tool_call, completed=completed)

    if event_type == "assistant":
        return "Composing response…"

    if event_type == "result":
        if subtype == "success":
            return "Agent turn finished"
        if subtype == "error" or payload.get("is_error"):
            return "Agent reported an error"

    return None


class AgentActivityTracker:
    """Track the latest agent activity summaries from streamed CLI output."""

    def __init__(self, *, parse_line: Any = parse_cursor_stream_line, max_history: int = 50) -> None:
        self._parse_line = parse_line
        self._status = "Starting agent…"
        self._history: deque[str] = deque(maxlen=max_history)
        self._pending: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._last_emitted: str | None = None

    @property
    def status(self) -> str:
        return self._status

    def feed(self, line: str) -> None:
        summary = self._parse_line(line)
        if summary is None or summary == self._last_emitted:
            return
        self._last_emitted = summary
        self._status = summary
        self._history.append(summary)
        self._pending.put(summary)

    def drain(self, limit: int = 3) -> list[str]:
        drained: list[str] = []
        while len(drained) < limit:
            try:
                drained.append(self._pending.get_nowait())
            except queue.Empty:
                break
        return drained
