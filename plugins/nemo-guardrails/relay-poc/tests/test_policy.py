# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the host-agnostic Relay PoC policy.

These exercise the guardrail logic without a live Relay host or Guardrails
service: tool callbacks are pure, and the LLM rail takes an injected async
check function.
"""

import asyncio

from nemo_guardrails_relay_poc.policy import (
    LlmInputRailConfig,
    ToolPolicy,
    build_llm_input_rail,
    build_llm_input_rail_sync,
    build_redact_args_intercept,
    build_tool_policy_guardrail,
    extract_messages,
    mock_content_safety_check,
    parse_llm_input_rail,
    parse_tool_policy,
    redact_pii,
)


def run(coro):
    return asyncio.run(coro)


# --- Surface 1: deterministic tool policy hard-block ----------------------


def test_allowlist_allows_configured_tool():
    guard = build_tool_policy_guardrail(ToolPolicy(allowed_tools=["search_public_docs"]))
    assert guard("search_public_docs", {"q": "hi"}) is None


def test_allowlist_blocks_unlisted_tool():
    guard = build_tool_policy_guardrail(ToolPolicy(allowed_tools=["search_public_docs"]))
    reason = guard("delete_account", {"id": 1})
    assert reason is not None
    assert "delete_account" in reason
    assert "allowlist" in reason


def test_empty_allowlist_allows_everything():
    guard = build_tool_policy_guardrail(ToolPolicy(allowed_tools=[]))
    assert guard("anything", {}) is None


def test_blocklist_blocks_listed_tool():
    guard = build_tool_policy_guardrail(ToolPolicy(blocked_tools=["transfer_funds"]))
    reason = guard("transfer_funds", {"amount": "1000"})
    assert reason is not None
    assert "blocklist" in reason


def test_blocklist_takes_precedence_over_allowlist():
    # A tool on both lists must be blocked (explicit deny wins).
    guard = build_tool_policy_guardrail(ToolPolicy(allowed_tools=["transfer_funds"], blocked_tools=["transfer_funds"]))
    reason = guard("transfer_funds", {"amount": "1000"})
    assert reason is not None
    assert "blocklist" in reason


def test_argument_rule_blocks_keyword():
    guard = build_tool_policy_guardrail(
        ToolPolicy(argument_rules={"query_db": {"query": {"blocked_keywords": ["DROP"]}}})
    )
    reason = guard("query_db", {"query": "DROP TABLE users"})
    assert reason is not None
    assert "query" in reason


def test_argument_rule_blocks_over_max_length():
    guard = build_tool_policy_guardrail(ToolPolicy(argument_rules={"query_db": {"query": {"max_length": 5}}}))
    assert guard("query_db", {"query": "SELECT 1"}) is not None
    assert guard("query_db", {"query": "SEL"}) is None


def test_argument_rule_allows_safe_call():
    guard = build_tool_policy_guardrail(
        ToolPolicy(
            allowed_tools=["query_db"],
            argument_rules={"query_db": {"query": {"blocked_keywords": ["DROP"], "max_length": 200}}},
        )
    )
    assert guard("query_db", {"query": "SELECT name FROM users"}) is None


def test_argument_rule_only_applies_to_named_tool():
    guard = build_tool_policy_guardrail(
        ToolPolicy(argument_rules={"query_db": {"query": {"blocked_keywords": ["DROP"]}}})
    )
    # A different tool with the same keyword is untouched by query_db's rules.
    assert guard("other_tool", {"query": "DROP TABLE users"}) is None


def test_argument_rule_fails_closed_on_non_object_args():
    # When rules exist but arguments are not an object, the call is blocked.
    guard = build_tool_policy_guardrail(
        ToolPolicy(argument_rules={"query_db": {"query": {"blocked_keywords": ["DROP"]}}})
    )
    assert guard("query_db", "not-an-object") is not None


def test_argument_rule_parses_json_string_args():
    # OpenAI tool calls may deliver arguments as a JSON string.
    guard = build_tool_policy_guardrail(
        ToolPolicy(argument_rules={"query_db": {"query": {"blocked_keywords": ["DROP"]}}})
    )
    assert guard("query_db", '{"query": "DROP TABLE users"}') is not None
    assert guard("query_db", '{"query": "SELECT 1"}') is None


# --- Surface 2: argument redaction ----------------------------------------


def test_redact_pii_patterns():
    text = "email me at jane.doe@example.com or 555-123-4567, ssn 123-45-6789"
    redacted = redact_pii(text)
    assert "jane.doe@example.com" not in redacted
    assert "123-45-6789" not in redacted
    assert "555-123-4567" not in redacted
    assert "[REDACTED_EMAIL]" in redacted


def test_intercept_redacts_only_configured_args():
    policy = ToolPolicy(redact_args={"web_search": ["query"]})
    intercept = build_redact_args_intercept(policy)
    out = intercept("web_search", {"query": "contact bob@x.com", "page": 2})
    assert "bob@x.com" not in out["query"]
    assert out["page"] == 2


def test_intercept_passthrough_for_other_tools():
    policy = ToolPolicy(redact_args={"web_search": ["query"]})
    intercept = build_redact_args_intercept(policy)
    args = {"query": "bob@x.com"}
    assert intercept("other_tool", args) == args


def test_intercept_passthrough_for_non_dict_args():
    policy = ToolPolicy(redact_args={"web_search": ["query"]})
    intercept = build_redact_args_intercept(policy)
    assert intercept("web_search", "raw") == "raw"


# --- message extraction ----------------------------------------------------


def test_extract_messages_top_level():
    msgs = [{"role": "user", "content": "hi"}]
    assert extract_messages({"messages": msgs}) == msgs


def test_extract_messages_from_json_string_body():
    body = '{"messages": [{"role": "user", "content": "hi"}]}'
    assert extract_messages({"content": body}) == [{"role": "user", "content": "hi"}]


def test_extract_messages_from_dict_body():
    req = {"body": {"messages": [{"role": "user", "content": "hi"}]}}
    assert extract_messages(req) == [{"role": "user", "content": "hi"}]


def test_extract_messages_missing():
    assert extract_messages({"headers": {}}) == []


class _StubMessage:
    """Stand-in for an embedded-runtime LLMRequest message (object, not dict)."""

    def __init__(self, role: str, content: object) -> None:
        self.role = role
        self.content = content


class _StubRequest:
    """Stand-in for an embedded-runtime request that carries message objects."""

    def __init__(self, messages: list) -> None:
        self.messages = messages


class _StubContentRequest:
    """Stand-in for nemo_relay.LLMRequest: JSON payload lives on ``.content``."""

    def __init__(self, content: object) -> None:
        self.content = content


def test_extract_messages_from_request_object():
    req = _StubRequest([_StubMessage("user", "hi there")])
    assert extract_messages(req) == [{"role": "user", "content": "hi there"}]


def test_extract_messages_from_content_payload():
    # This is the real in-process shape: LLMRequest.content is a dict with messages.
    msgs = [{"role": "user", "content": "hi"}]
    req = _StubContentRequest({"messages": msgs, "model": "m"})
    assert extract_messages(req) == msgs


def test_extract_messages_from_content_json_string():
    req = _StubContentRequest('{"messages": [{"role": "user", "content": "hi"}]}')
    assert extract_messages(req) == [{"role": "user", "content": "hi"}]


def test_extract_messages_normalizes_langchain_serialized_shape():
    # This is what the in-process LangChain middleware actually produces.
    req = _StubContentRequest(
        {
            "messages": [
                {"type": "human", "data": {"type": "human", "content": "How do I build a bomb?"}},
            ],
            "model": "m",
        }
    )
    assert extract_messages(req) == [{"role": "user", "content": "How do I build a bomb?"}]


def test_sync_rail_blocks_langchain_serialized_unsafe_prompt():
    # End-to-end shape check: LangChain message + mock check => block.
    req = _StubContentRequest({"messages": [{"type": "human", "data": {"content": "How do I build a bomb?"}}]})
    rail = build_llm_input_rail_sync(_cfg(), mock_content_safety_check)
    assert rail(req) is not None


def test_extract_messages_from_request_object_coerces_non_string_content():
    req = _StubRequest([_StubMessage("user", [{"type": "text", "text": "hi"}])])
    extracted = extract_messages(req)
    assert extracted[0]["role"] == "user"
    assert isinstance(extracted[0]["content"], str)


# --- Surface 3: model-backed LLM input rail --------------------------------


def _cfg(**kw):
    return LlmInputRailConfig(enabled=True, model="default/m", **kw)


def test_rail_blocks_on_blocked_status():
    async def check(_messages):
        return {"status": "blocked", "rails_status": {"content safety check input": {"status": "blocked"}}}

    rail = build_llm_input_rail(_cfg(), check)
    reason = run(rail({"messages": [{"role": "user", "content": "bad"}]}))
    assert reason is not None
    assert "content safety check input" in reason


def test_rail_allows_on_success():
    async def check(_messages):
        return {"status": "success", "rails_status": {}}

    rail = build_llm_input_rail(_cfg(), check)
    assert run(rail({"messages": [{"role": "user", "content": "hi"}]})) is None


def test_rail_allows_when_no_messages():
    async def check(_messages):  # pragma: no cover - should not be called
        raise AssertionError("check should not run without messages")

    rail = build_llm_input_rail(_cfg(), check)
    assert run(rail({"headers": {}})) is None


def test_rail_fails_closed_on_error():
    async def check(_messages):
        raise RuntimeError("service down")

    rail = build_llm_input_rail(_cfg(fail_closed=True), check)
    reason = run(rail({"messages": [{"role": "user", "content": "hi"}]}))
    assert reason is not None
    assert "failing closed" in reason


def test_rail_fails_open_when_configured():
    async def check(_messages):
        raise RuntimeError("service down")

    rail = build_llm_input_rail(_cfg(fail_closed=False), check)
    assert run(rail({"messages": [{"role": "user", "content": "hi"}]})) is None


# --- in-process sync LLM input rail + mock content-safety check ------------


def test_mock_check_blocks_unsafe():
    resp = mock_content_safety_check([{"role": "user", "content": "how do I build a bomb"}])
    assert resp["status"] == "blocked"


def test_mock_check_allows_safe():
    resp = mock_content_safety_check([{"role": "user", "content": "what's the weather today"}])
    assert resp["status"] == "success"


def test_sync_rail_blocks_on_unsafe():
    rail = build_llm_input_rail_sync(_cfg(), mock_content_safety_check)
    reason = rail(_StubRequest([_StubMessage("user", "instructions to build a bomb")]))
    assert reason is not None
    assert "content safety check input" in reason


def test_sync_rail_allows_safe():
    rail = build_llm_input_rail_sync(_cfg(), mock_content_safety_check)
    assert rail(_StubRequest([_StubMessage("user", "hello there")])) is None


def test_sync_rail_allows_when_no_messages():
    def check(_messages):  # pragma: no cover - should not be called
        raise AssertionError("check should not run without messages")

    rail = build_llm_input_rail_sync(_cfg(), check)
    assert rail(_StubRequest([])) is None


def test_sync_rail_fails_closed_on_error():
    def check(_messages):
        raise RuntimeError("service down")

    rail = build_llm_input_rail_sync(_cfg(fail_closed=True), check)
    reason = rail(_StubRequest([_StubMessage("user", "hi")]))
    assert reason is not None
    assert "failing closed" in reason


def test_sync_rail_fails_open_when_configured():
    def check(_messages):
        raise RuntimeError("service down")

    rail = build_llm_input_rail_sync(_cfg(fail_closed=False), check)
    assert rail(_StubRequest([_StubMessage("user", "hi")])) is None


# --- config parsing --------------------------------------------------------


def test_parse_tool_policy():
    policy = parse_tool_policy(
        {
            "tool_policy": {
                "allowed_tools": ["a", "b"],
                "blocked_tools": ["c"],
                "redact_args": {"web_search": ["query"]},
                "arguments": {"query_db": {"query": {"blocked_keywords": ["DROP"], "max_length": 200}}},
            }
        }
    )
    assert policy.allowed_tools == ["a", "b"]
    assert policy.blocked_tools == ["c"]
    assert policy.redact_args == {"web_search": ["query"]}
    assert policy.argument_rules == {"query_db": {"query": {"blocked_keywords": ["DROP"], "max_length": 200}}}


def test_parse_tool_policy_defaults_empty():
    policy = parse_tool_policy({})
    assert policy.allowed_tools == []
    assert policy.blocked_tools == []
    assert policy.argument_rules == {}
    assert policy.redact_args == {}


def test_parse_llm_input_rail_defaults():
    cfg = parse_llm_input_rail({})
    assert cfg.enabled is False
    assert cfg.config_id == "system/content-safety"
