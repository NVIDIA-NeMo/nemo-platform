# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the built-in tool rail actions.

Actions are pure Python functions — no LLM, no Colang runtime, no plugin
infrastructure needed. Tests call them directly with a mock context dict
and a minimal config stub.
"""

import json
import types
from typing import Any

import pytest
from nemo_guardrails_plugin.tool_rails.actions import (
    check_tool_allowlist,
    check_tool_arguments,
    check_tool_result_linkage,
    check_tool_schema,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(custom_data: dict[str, Any] | None = None) -> Any:
    config = types.SimpleNamespace()
    config.custom_data = custom_data or {}
    return config


def _make_tool_call(
    name: str, arguments: dict[str, Any] | str | None = None, call_id: str = "call_1"
) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments or {}),
        },
    }


def _make_tool_result(call_id: str, name: str | None = None, content: str = "result") -> dict[str, Any]:
    msg: dict[str, Any] = {"role": "tool", "tool_call_id": call_id, "content": content}
    if name is not None:
        msg["name"] = name
    return msg


def _make_assistant_with_tool_calls(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {"role": "assistant", "content": None, "tool_calls": tool_calls}


# ---------------------------------------------------------------------------
# check_tool_allowlist
# ---------------------------------------------------------------------------


class TestCheckToolAllowlist:
    async def test_absent_allowlist_passes_all(self) -> None:
        context = {"tool_calls": [_make_tool_call("any_tool")]}
        assert await check_tool_allowlist(context=context, config=_make_config({"tool_allowlist": {}})) is True

    async def test_allowed_tool_passes(self) -> None:
        config = _make_config({"tool_allowlist": {"allowed_tools": ["get_weather", "query_database"]}})
        context = {"tool_calls": [_make_tool_call("get_weather")]}
        assert await check_tool_allowlist(context=context, config=config) is True

    async def test_unknown_tool_blocked(self) -> None:
        config = _make_config({"tool_allowlist": {"allowed_tools": ["get_weather"]}})
        context = {"tool_calls": [_make_tool_call("send_email")]}
        assert await check_tool_allowlist(context=context, config=config) is False

    async def test_all_calls_must_pass(self) -> None:
        config = _make_config({"tool_allowlist": {"allowed_tools": ["get_weather"]}})
        context = {"tool_calls": [_make_tool_call("get_weather"), _make_tool_call("send_email")]}
        assert await check_tool_allowlist(context=context, config=config) is False

    async def test_no_tool_calls_passes(self) -> None:
        config = _make_config({"tool_allowlist": {"allowed_tools": ["get_weather"]}})
        assert await check_tool_allowlist(context={}, config=config) is True

    async def test_none_context_and_config(self) -> None:
        assert await check_tool_allowlist(context=None, config=None) is True

    async def test_malformed_tool_call_missing_function_key_blocked(self) -> None:
        config = _make_config({"tool_allowlist": {"allowed_tools": ["get_weather"]}})
        context = {"tool_calls": [{"id": "call_1", "type": "function"}]}
        assert await check_tool_allowlist(context=context, config=config) is False

    async def test_fails_closed_on_exception(self) -> None:
        config = _make_config({"tool_allowlist": {"allowed_tools": ["get_weather"]}})
        # Inject a non-iterable as tool_calls to provoke an exception inside the action.
        context = {"tool_calls": object()}
        assert await check_tool_allowlist(context=context, config=config) is False


# ---------------------------------------------------------------------------
# check_tool_arguments
# ---------------------------------------------------------------------------


class TestCheckToolArguments:
    async def test_no_rules_passes_all(self) -> None:
        context = {"tool_calls": [_make_tool_call("any_tool", {"sql": "DROP TABLE users"})]}
        assert await check_tool_arguments(context=context, config=_make_config()) is True

    async def test_no_rules_for_this_tool_passes(self) -> None:
        config = _make_config({"tool_arguments": {"other_tool": {"sql": {"blocked_keywords": ["DROP"]}}}})
        context = {"tool_calls": [_make_tool_call("query_database", {"sql": "DROP TABLE users"})]}
        assert await check_tool_arguments(context=context, config=config) is True

    async def test_blocked_keyword_blocked(self) -> None:
        config = _make_config({"tool_arguments": {"query_database": {"sql": {"blocked_keywords": ["DROP"]}}}})
        context = {"tool_calls": [_make_tool_call("query_database", {"sql": "DROP TABLE users"})]}
        assert await check_tool_arguments(context=context, config=config) is False

    async def test_keyword_check_is_case_insensitive(self) -> None:
        config = _make_config({"tool_arguments": {"query_database": {"sql": {"blocked_keywords": ["drop"]}}}})
        context = {"tool_calls": [_make_tool_call("query_database", {"sql": "DROP TABLE users"})]}
        assert await check_tool_arguments(context=context, config=config) is False

    async def test_clean_argument_passes(self) -> None:
        config = _make_config({"tool_arguments": {"query_database": {"sql": {"blocked_keywords": ["DROP", "DELETE"]}}}})
        context = {"tool_calls": [_make_tool_call("query_database", {"sql": "SELECT * FROM users"})]}
        assert await check_tool_arguments(context=context, config=config) is True

    @pytest.mark.parametrize(("length", "expected"), [(10, True), (11, False)])
    async def test_max_length_boundary(self, length: int, expected: bool) -> None:
        config = _make_config({"tool_arguments": {"get_weather": {"location": {"max_length": 10}}}})
        context = {"tool_calls": [_make_tool_call("get_weather", {"location": "a" * length})]}
        assert await check_tool_arguments(context=context, config=config) is expected

    async def test_malformed_json_string_blocked_when_rules_apply(self) -> None:
        config = _make_config({"tool_arguments": {"query_database": {"sql": {"blocked_keywords": ["DROP"]}}}})
        context = {"tool_calls": [_make_tool_call("query_database", "not-valid-json")]}
        assert await check_tool_arguments(context=context, config=config) is False

    @pytest.mark.parametrize("arguments", ["", []])
    async def test_falsey_non_object_arguments_blocked_when_rules_apply(self, arguments: Any) -> None:
        config = _make_config({"tool_arguments": {"query_database": {"sql": {"blocked_keywords": ["DROP"]}}}})
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "query_database", "arguments": arguments},
        }

        assert await check_tool_arguments(context={"tool_calls": [tool_call]}, config=config) is False

    async def test_multiple_calls_all_must_pass(self) -> None:
        config = _make_config({"tool_arguments": {"query_database": {"sql": {"blocked_keywords": ["DROP"]}}}})
        context = {
            "tool_calls": [
                _make_tool_call("query_database", {"sql": "SELECT 1"}),
                _make_tool_call("query_database", {"sql": "DROP TABLE users"}),
            ]
        }
        assert await check_tool_arguments(context=context, config=config) is False

    async def test_none_context_and_config(self) -> None:
        assert await check_tool_arguments(context=None, config=None) is True

    async def test_fails_closed_on_exception(self) -> None:
        config = _make_config({"tool_arguments": {"get_weather": {"location": {"max_length": 10}}}})
        context = {"tool_calls": object()}
        assert await check_tool_arguments(context=context, config=config) is False


# ---------------------------------------------------------------------------
# check_tool_schema
# ---------------------------------------------------------------------------

_WEATHER_SCHEMA = {
    "type": "object",
    "properties": {
        "location": {"type": "string"},
        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
    },
    "required": ["location"],
    "additionalProperties": False,
}

_DECLARED_WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the weather",
        "parameters": _WEATHER_SCHEMA,
    },
}


class TestCheckToolSchema:
    async def test_no_declared_tools_blocks_tool_calls(self) -> None:
        context = {"tool_calls": [_make_tool_call("get_weather", {"location": "Paris"})]}
        assert await check_tool_schema(context=context, config=_make_config()) is False

    async def test_no_schema_for_this_tool_blocks(self) -> None:
        other_tool = {
            "type": "function",
            "function": {"name": "other_tool", "parameters": {"type": "object", "properties": {}}},
        }
        context = {
            "tool_calls": [_make_tool_call("get_weather", {"location": "Paris"})],
            "declared_tools": [other_tool],
        }
        assert await check_tool_schema(context=context, config=_make_config()) is False

    async def test_valid_arguments_pass(self) -> None:
        context = {
            "tool_calls": [_make_tool_call("get_weather", {"location": "Paris", "unit": "celsius"})],
            "declared_tools": [_DECLARED_WEATHER_TOOL],
        }
        assert await check_tool_schema(context=context, config=_make_config()) is True

    @pytest.mark.parametrize(
        "arguments",
        [
            pytest.param({}, id="missing-required"),
            pytest.param({"location": 42}, id="wrong-type"),
            pytest.param({"location": "Paris", "unit": "kelvin"}, id="invalid-enum"),
            pytest.param({"location": "Paris", "extra": "field"}, id="additional-properties"),
        ],
    )
    async def test_invalid_arguments_blocked(self, arguments: dict[str, Any]) -> None:
        context = {
            "tool_calls": [_make_tool_call("get_weather", arguments)],
            "declared_tools": [_DECLARED_WEATHER_TOOL],
        }
        assert await check_tool_schema(context=context, config=_make_config()) is False

    async def test_malformed_json_arguments_blocked(self) -> None:
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_weather", "arguments": "not-valid-json"},
        }
        context = {"tool_calls": [tool_call], "declared_tools": [_DECLARED_WEATHER_TOOL]}
        assert await check_tool_schema(context=context, config=_make_config()) is False

    @pytest.mark.parametrize(
        ("schema", "expected"),
        [
            ({}, True),
            (True, True),
            (False, False),
        ],
    )
    async def test_valid_empty_and_boolean_schemas(self, schema: dict[str, Any] | bool, expected: bool) -> None:
        declared_tool = {
            "type": "function",
            "function": {"name": "get_weather", "parameters": schema},
        }
        context = {
            "tool_calls": [_make_tool_call("get_weather", {"location": "Paris"})],
            "declared_tools": [declared_tool],
        }

        assert await check_tool_schema(context=context, config=_make_config()) is expected

    async def test_duplicate_tool_declarations_blocked(self) -> None:
        duplicate = {
            "type": "function",
            "function": {"name": "get_weather", "parameters": {}},
        }
        context = {
            "tool_calls": [_make_tool_call("get_weather", {"location": "Paris"})],
            "declared_tools": [_DECLARED_WEATHER_TOOL, duplicate],
        }

        assert await check_tool_schema(context=context, config=_make_config()) is False

    async def test_none_context_passes(self) -> None:
        assert await check_tool_schema(context=None, config=None) is True


# ---------------------------------------------------------------------------
# check_tool_result_linkage
# ---------------------------------------------------------------------------


class TestCheckToolResultLinkage:
    def _make_messages(
        self,
        tool_name: str = "get_weather",
        call_id: str = "call_1",
        result_call_id: str | None = None,
        result_name: str | None = None,
        result_content: str = "Sunny",
    ) -> list[dict[str, Any]]:
        return [
            {"role": "user", "content": "What's the weather?"},
            _make_assistant_with_tool_calls([_make_tool_call(tool_name, {}, call_id=call_id)]),
            _make_tool_result(
                call_id=result_call_id if result_call_id is not None else call_id,
                name=result_name,
                content=result_content,
            ),
        ]

    async def test_valid_linkage_passes(self) -> None:
        context = {"messages": self._make_messages()}
        assert await check_tool_result_linkage(context=context, config=_make_config()) is True

    async def test_no_tool_results_passes(self) -> None:
        messages = [{"role": "user", "content": "Hello"}]
        context = {"messages": messages}
        assert await check_tool_result_linkage(context=context, config=_make_config()) is True

    async def test_unknown_call_id_blocked(self) -> None:
        context = {"messages": self._make_messages(result_call_id="call_999")}
        assert await check_tool_result_linkage(context=context, config=_make_config()) is False

    async def test_missing_call_id_blocked(self) -> None:
        messages = [
            {"role": "user", "content": "Hello"},
            _make_assistant_with_tool_calls([_make_tool_call("get_weather", {})]),
            {"role": "tool", "content": "Sunny"},  # no tool_call_id
        ]
        context = {"messages": messages}
        assert await check_tool_result_linkage(context=context, config=_make_config()) is False

    async def test_no_prior_assistant_tool_calls_blocked(self) -> None:
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Sure"},  # no tool_calls
            _make_tool_result("call_1"),
        ]
        context = {"messages": messages}
        assert await check_tool_result_linkage(context=context, config=_make_config()) is False

    async def test_duplicate_call_ids_blocked(self) -> None:
        messages = [
            {"role": "user", "content": "Hello"},
            _make_assistant_with_tool_calls(
                [
                    _make_tool_call("get_weather", {}, call_id="call_1"),
                    _make_tool_call("get_forecast", {}, call_id="call_2"),
                ]
            ),
            _make_tool_result("call_1"),
            _make_tool_result("call_1"),  # duplicate
        ]
        context = {"messages": messages}
        assert await check_tool_result_linkage(context=context, config=_make_config()) is False

    async def test_name_mismatch_blocked(self) -> None:
        context = {"messages": self._make_messages(tool_name="get_weather", result_name="send_email")}
        assert await check_tool_result_linkage(context=context, config=_make_config()) is False

    async def test_multiple_valid_results_pass(self) -> None:
        messages = [
            {"role": "user", "content": "Hello"},
            _make_assistant_with_tool_calls(
                [
                    _make_tool_call("get_weather", {}, call_id="call_1"),
                    _make_tool_call("get_forecast", {}, call_id="call_2"),
                ]
            ),
            _make_tool_result("call_1", name="get_weather"),
            _make_tool_result("call_2", name="get_forecast"),
        ]
        context = {"messages": messages}
        assert await check_tool_result_linkage(context=context, config=_make_config()) is True

    async def test_reused_call_id_in_separate_turns_passes(self) -> None:
        messages = [
            {"role": "user", "content": "Weather?"},
            _make_assistant_with_tool_calls([_make_tool_call("get_weather", {}, call_id="call_1")]),
            _make_tool_result("call_1", name="get_weather"),
            {"role": "assistant", "content": "Sunny."},
            {"role": "user", "content": "Forecast?"},
            _make_assistant_with_tool_calls([_make_tool_call("get_forecast", {}, call_id="call_1")]),
            _make_tool_result("call_1", name="get_forecast"),
        ]
        context = {"messages": messages}
        assert await check_tool_result_linkage(context=context, config=_make_config()) is True

    async def test_none_context_passes(self) -> None:
        assert await check_tool_result_linkage(context=None, config=None) is True

    async def test_fails_closed_on_exception(self) -> None:
        context = {"messages": object()}
        assert await check_tool_result_linkage(context=context, config=_make_config()) is False
