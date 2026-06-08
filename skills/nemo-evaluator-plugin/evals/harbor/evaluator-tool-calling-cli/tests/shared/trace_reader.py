# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Utility for reading agent session transcripts during agentic-use eval verification.

Supports two agent backends:

1. **Claude Code / Harbor (original):** Session data is stored as JSONL files at
   ``/logs/agent/sessions/projects/-app/<session-id>.jsonl``
   (Harbor sets ``CLAUDE_CONFIG_DIR=/logs/agent/sessions``).

2. **NAT agent (new):** When ``NAT_AGENT=1`` is set in the environment (injected by
   ``nat_runner.py``), there are no Claude Code JSONL files.  Calls to
   :func:`get_session` will issue ``pytest.skip()`` so that trace-level assertions
   are skipped rather than failing.  API-state assertions in the same test file are
   unaffected and continue to run normally.

   Phase 2 work will replace this skip with real NAT observability traces (via
   OpenTelemetry / Phoenix spans) once that integration is wired up.

This module provides functions to:
1. Find the session file(s) from the most recent agent run
2. Parse the JSONL transcript
3. Extract tool calls (Bash commands, MCP calls, etc.)

Usage in test_outputs.py:
    from trace_reader import get_session, get_bash_commands

    def test_agent_used_correct_commands():
        session = get_session()  # skips under NAT agent; runs under Claude Code
        commands = get_bash_commands(session)
        assert any("nemo workspaces create" in cmd for cmd in commands)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Default Claude Code session directory inside Harbor container
# Harbor sets CLAUDE_CONFIG_DIR=/logs/agent/sessions, so projects are at:
_DEFAULT_PROJECTS_DIR = Path("/logs/agent/sessions/projects")


def _get_projects_dir(override: Path | None = None) -> Path:
    """Get projects directory, checking env var at call time if no override provided."""
    if override is not None:
        return override
    if "CLAUDE_PROJECTS_DIR" in os.environ:
        return Path(os.environ["CLAUDE_PROJECTS_DIR"])
    return _DEFAULT_PROJECTS_DIR


@dataclass
class ToolCall:
    """Represents a single tool call from the session."""

    name: str
    tool_id: str
    input: dict[str, Any]
    timestamp: str | None = None

    @property
    def command(self) -> str | None:
        """For Bash tool calls, return the command string."""
        if self.name == "Bash":
            return self.input.get("command")
        return None


@dataclass
class ToolResult:
    """Represents a tool result returned to the assistant."""

    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class Session:
    """Parsed Claude Code session transcript."""

    session_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)

    def get_tool_calls_by_name(self, name: str) -> list[ToolCall]:
        """Get all tool calls with a specific tool name."""
        return [tc for tc in self.tool_calls if tc.name == name]

    def get_bash_commands(self) -> list[str]:
        """Get all Bash commands executed during the session."""
        return [tc.command for tc in self.tool_calls if tc.command is not None]

    def get_mcp_calls(self) -> list[ToolCall]:
        """Get all MCP tool calls (tools starting with 'mcp__')."""
        return [tc for tc in self.tool_calls if tc.name.startswith("mcp__")]

    def get_tool_results(self, tool_name: str | None = None) -> list[ToolResult]:
        """Get tool results, optionally filtered by the originating tool name.

        Args:
            tool_name: If provided, only return results for tool calls with this name.

        Returns:
            List of ToolResult objects.
        """
        if tool_name is None:
            return list(self.tool_results)
        # Build set of tool_ids that match the requested tool name
        matching_ids = {tc.tool_id for tc in self.tool_calls if tc.name == tool_name}
        return [tr for tr in self.tool_results if tr.tool_use_id in matching_ids]


def find_session_files(projects_dir: Path | None = None) -> list[Path]:
    """
    Find all Claude Code session JSONL files.

    Args:
        projects_dir: Override the default projects directory (for testing)

    Returns:
        List of paths to session .jsonl files, sorted by modification time (newest first)
    """
    projects_dir = _get_projects_dir(projects_dir)

    if not projects_dir.exists():
        return []

    # Session files are at: projects/<project-name>/<session-id>.jsonl
    session_files = list(projects_dir.glob("**/*.jsonl"))

    # Sort by modification time, newest first
    session_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return session_files


def parse_session(jsonl_path: Path) -> Session:
    """
    Parse a Claude Code session JSONL file.

    Args:
        jsonl_path: Path to the .jsonl session file

    Returns:
        Parsed Session object with messages and tool calls
    """
    messages: list[dict[str, Any]] = []
    tool_calls: list[ToolCall] = []
    tool_results: list[ToolResult] = []

    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            messages.append(entry)

            # Extract tool calls from assistant messages
            if entry.get("type") == "assistant":
                content = entry.get("message", {}).get("content", [])
                timestamp = entry.get("timestamp")

                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_use":
                        tool_calls.append(
                            ToolCall(
                                name=item.get("name", ""),
                                tool_id=item.get("id", ""),
                                input=item.get("input", {}),
                                timestamp=timestamp,
                            )
                        )

            # Extract tool results from user messages
            if entry.get("type") == "user":
                content = entry.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            tool_results.append(
                                ToolResult(
                                    tool_use_id=item.get("tool_use_id", ""),
                                    content=item.get("content", ""),
                                    is_error=item.get("is_error", False),
                                )
                            )

    # Extract session ID from path or first message
    session_id = jsonl_path.stem
    for msg in messages:
        if "sessionId" in msg:
            session_id = msg["sessionId"]
            break

    return Session(session_id=session_id, messages=messages, tool_calls=tool_calls, tool_results=tool_results)


def get_session(projects_dir: Path | None = None) -> Session:
    """
    Get the most recent agent session transcript.

    When running under the NAT agent (``NAT_AGENT=1`` environment variable), this
    function issues ``pytest.skip()`` so that trace-level assertions are skipped
    gracefully rather than failing.  API-state assertions in the same test file
    are completely unaffected.

    This is the main entry point for test files.

    Args:
        projects_dir: Override the default projects directory (for testing)

    Returns:
        The most recent Session (Claude Code backend only)

    Raises:
        FileNotFoundError: If no session files are found (non-pytest context)
    """
    # Under NAT, there are no Claude Code JSONL session files.
    # Skip the trace assertion rather than failing hard so that the
    # API-state tests in the same test file still execute and produce
    # a meaningful reward signal.
    #
    # Only skip when no explicit projects_dir override is given — unit tests
    # for trace_reader itself pass a synthetic directory, so they should
    # continue to exercise the parsing logic regardless of NAT_AGENT.
    if os.environ.get("NAT_AGENT") and projects_dir is None:
        try:
            import pytest  # noqa: PLC0415

            pytest.skip(
                "Trace assertions are not available with the NAT agent backend. "
                "These tests will be re-enabled in Phase 2 once NAT OpenTelemetry "
                "span integration is wired up.  API-state assertions in this file "
                "continue to run normally."
            )
        except ImportError:
            # pytest not available (e.g. called from a plain Python script)
            return Session(session_id="nat-stub", messages=[], tool_calls=[], tool_results=[])

    session_files = find_session_files(projects_dir)

    if not session_files:
        search_dir = _get_projects_dir(projects_dir)
        raise FileNotFoundError(
            f"No Claude Code session files found in {search_dir}. Ensure Harbor ran the agent before verification."
        )

    # Return the most recent session
    return parse_session(session_files[0])


def get_bash_commands(session: Session | None = None) -> list[str]:
    """
    Convenience function to get all Bash commands from a session.

    Args:
        session: Optional session object. If None, loads the most recent session.

    Returns:
        List of command strings
    """
    if session is None:
        session = get_session()
    return session.get_bash_commands()
