# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os

from coding_agents.claude_code.process import scrubbed_env


# Core safety property: env vars that signal "you are inside Claude Code"
# are stripped before spawning the child. Without this, a child `claude`
# can detect the parent session and reuse its config dir / session ID.
def test_scrubbed_env_drops_claudecode_marker(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    monkeypatch.setenv("CLAUDE_EFFORT", "high")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))

    env = scrubbed_env()

    assert "CLAUDECODE" not in env
    assert "CLAUDE_CODE_SESSION_ID" not in env
    assert "CLAUDE_CODE_ENTRYPOINT" not in env
    assert "CLAUDE_EFFORT" not in env


# Negative guard: ANTHROPIC_* vars are legitimate auth, not session markers.
# Stripping them would break callers who authenticate via API key instead
# of interactive `claude auth login`.
def test_scrubbed_env_keeps_anthropic_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

    env = scrubbed_env()

    assert env.get("ANTHROPIC_API_KEY") == "sk-test"
    assert env.get("ANTHROPIC_BASE_URL") == "https://api.anthropic.com"


# Sanity check: don't over-scrub. PATH (used to find `claude`) and HOME
# (used to find ~/.claude/credentials) must always pass through.
def test_scrubbed_env_keeps_path_and_home(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("HOME", "/home/test")

    env = scrubbed_env()

    assert env["PATH"] == "/usr/bin:/bin"
    assert env["HOME"] == "/home/test"


# Contract: the optional `extras` dict is applied *after* scrubbing, so
# callers can both add their own vars and re-introduce scrubbed ones if
# they really want to (e.g. testing the parent-detection behavior).
def test_scrubbed_env_applies_extras(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")

    env = scrubbed_env({"MY_VAR": "value", "CLAUDECODE": "ignored"})

    assert env["MY_VAR"] == "value"
    # extras are applied after scrubbing, so they can re-introduce vars if caller wants
    assert env["CLAUDECODE"] == "ignored"
