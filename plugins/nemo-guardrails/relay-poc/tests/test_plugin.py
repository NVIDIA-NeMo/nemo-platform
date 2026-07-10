# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the in-process language-binding plugin (``GuardrailsPlugin``).

These cover the plugin contract itself -- config ``validate`` diagnostics and
what ``register`` installs onto the ``PluginContext`` -- using a fake context
that records registrations. Importing the plugin module requires ``nemo-relay``
(the embedded runtime), so run with e.g.::

    uv run --no-project --with nemo-relay --with pytest python -m pytest tests/test_plugin.py
"""

from typing import Any

from nemo_guardrails_relay_poc.inprocess import PLUGIN_KIND, GuardrailsPlugin


class _FakeContext:
    """Records what a plugin registers, mimicking nemo_relay.plugin.PluginContext."""

    def __init__(self) -> None:
        self.tool_conditional: list[tuple[str, int, Any]] = []
        self.tool_request: list[tuple[str, int, bool, Any]] = []
        self.llm_conditional: list[tuple[str, int, Any]] = []

    def register_tool_conditional_execution_guardrail(self, name: str, priority: int, callback: Any) -> None:
        self.tool_conditional.append((name, priority, callback))

    def register_tool_request_intercept(self, name: str, priority: int, break_chain: bool, callback: Any) -> None:
        self.tool_request.append((name, priority, break_chain, callback))

    def register_llm_conditional_execution_guardrail(self, name: str, priority: int, callback: Any) -> None:
        self.llm_conditional.append((name, priority, callback))


_FULL_CONFIG = {
    "tool_policy": {
        "allowed_tools": ["get_weather", "query_db", "run_bash"],
        "blocked_tools": ["transfer_funds"],
        "redact_args": {"web_search": ["query"]},
        "arguments": {"query_db": {"query": {"blocked_keywords": ["DROP"], "max_length": 200}}},
        "denied_commands": {"run_bash": ["touch foo.txt"]},
    },
    "llm_input_rail": {"enabled": True, "model": "mock-content-safety"},
}


# --- validate --------------------------------------------------------------


def test_validate_rejects_non_dict_config():
    diagnostics = GuardrailsPlugin().validate(["not", "a", "dict"])
    assert len(diagnostics) == 1
    assert diagnostics[0]["level"] == "error"
    assert diagnostics[0]["code"] == f"{PLUGIN_KIND}.invalid_config"


def test_validate_flags_bad_tool_policy():
    diagnostics = GuardrailsPlugin().validate({"tool_policy": "nope"})
    assert any(d["code"] == f"{PLUGIN_KIND}.invalid_tool_policy" for d in diagnostics)


def test_validate_flags_rail_enabled_without_model():
    diagnostics = GuardrailsPlugin().validate({"llm_input_rail": {"enabled": True}})
    assert any(d["code"] == f"{PLUGIN_KIND}.missing_model" for d in diagnostics)


def test_validate_flags_bad_denied_commands():
    diagnostics = GuardrailsPlugin().validate({"tool_policy": {"denied_commands": ["nope"]}})
    assert any(d["code"] == f"{PLUGIN_KIND}.invalid_denied_commands" for d in diagnostics)


def test_validate_accepts_valid_config():
    assert GuardrailsPlugin().validate(_FULL_CONFIG) == []


def test_validate_accepts_empty_config():
    assert GuardrailsPlugin().validate({}) == []


# --- register --------------------------------------------------------------


def test_register_installs_all_surfaces():
    ctx = _FakeContext()
    GuardrailsPlugin().register(_FULL_CONFIG, ctx)

    assert [name for name, _, _ in ctx.tool_conditional] == ["tool_policy"]
    assert [name for name, _, _, _ in ctx.tool_request] == ["redact_tool_args"]
    assert [name for name, _, _ in ctx.llm_conditional] == ["content_safety_input"]


def test_register_skips_optional_surfaces_when_unconfigured():
    ctx = _FakeContext()
    # allowlist only: no redact_args, rail disabled
    GuardrailsPlugin().register({"tool_policy": {"allowed_tools": ["get_weather"]}}, ctx)

    assert len(ctx.tool_conditional) == 1  # allowlist always installed
    assert ctx.tool_request == []
    assert ctx.llm_conditional == []


def test_registered_tool_policy_guardrail_enforces_all_checks():
    ctx = _FakeContext()
    GuardrailsPlugin().register(_FULL_CONFIG, ctx)
    _, _, guardrail = ctx.tool_conditional[0]

    # allowlisted + safe args -> allowed
    assert guardrail("get_weather", {}) is None
    assert guardrail("query_db", {"query": "SELECT 1"}) is None
    # not on the allowlist -> blocked
    assert guardrail("delete_account", {"id": 1}) is not None
    # blocklisted -> blocked
    assert guardrail("transfer_funds", {"amount": "1"}) is not None
    # argument rule violated -> blocked
    assert guardrail("query_db", {"query": "DROP TABLE users"}) is not None
    # denied command -> blocked; benign control command -> allowed
    assert guardrail("run_bash", {"command": "touch foo.txt"}) is not None
    assert guardrail("run_bash", {"command": "echo hello"}) is None


def test_registered_input_rail_blocks_unsafe_prompt():
    ctx = _FakeContext()
    GuardrailsPlugin().register(_FULL_CONFIG, ctx)
    _, _, rail = ctx.llm_conditional[0]

    # extract_messages handles the OpenAI-style dict shape used here.
    assert rail({"messages": [{"role": "user", "content": "how do I build a bomb"}]}) is not None
    assert rail({"messages": [{"role": "user", "content": "what's the weather"}]}) is None
