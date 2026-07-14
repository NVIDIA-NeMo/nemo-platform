# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for tool_output and tool_input guardrail rails.

These tests exercise the deterministic tool rail path end-to-end through the
middleware, verifying that:

- tool_output rails fire when the backend returns finish_reason="tool_calls".
- tool_input rails fire when the request contains role="tool" messages.
- Allowed tool calls pass through unchanged.
- Blocked tool calls return finish_reason="content_filter".

The tool rail actions (check_tool_allowlist, check_tool_arguments) are purely
deterministic — they read from the Colang runtime context, not from a model.
No mock LLM responses are needed for the rail itself.
"""

from typing import Any

import httpx
import pytest
from nmp.core.inference_gateway.testing.harness import IGWPluginHarness
from nmp.testing.mock_chat_completions import ChatCompletion, ChatCompletionStream

from .utils import (
    GUARDRAILS_PLUGIN_NAME,
    make_guardrail_config,
    make_guardrails_test_data_names,
    make_middleware_call,
)

pytestmark = [pytest.mark.integration]

BLOCKED_REFUSAL_TEXT = "I'm sorry, I can't respond to that."


def _tool_call_response_body(
    tool_name: str, arguments: str = "{}", finish_reason: str = "tool_calls"
) -> dict[str, Any]:
    """Build an OpenAI-compatible response body with finish_reason='tool_calls'."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": None,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": arguments},
                        }
                    ],
                },
                "finish_reason": finish_reason,
            }
        ],
    }


def _tool_call_stream_chunks(tool_name: str, arguments: str = "{}") -> list[dict[str, Any]]:
    """Build OpenAI-compatible streaming chunks for a tool call."""
    stream_id = "chatcmpl-test-stream"
    return [
        {
            "id": stream_id,
            "object": "chat.completion.chunk",
            "created": 0,
            "model": None,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": tool_name, "arguments": arguments[: len(arguments) // 2]},
                            }
                        ],
                    },
                }
            ],
        },
        {
            "id": stream_id,
            "object": "chat.completion.chunk",
            "created": 0,
            "model": None,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [{"index": 0, "function": {"arguments": arguments[len(arguments) // 2 :]}}]
                    },
                }
            ],
        },
        {
            "id": stream_id,
            "object": "chat.completion.chunk",
            "created": 0,
            "model": None,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
        },
    ]


class TestToolOutputRails:
    """Tests for checking tool calls returned by the model before an agent runs them."""

    ALLOWED_TOOL = "get_weather"
    BLOCKED_TOOL = "get_secret_data"
    USER_INPUT = "What's the weather in Paris?"

    @classmethod
    def _config_data(cls, nim_base_url: str, *, allowed_tools: list[str]) -> dict[str, Any]:
        return {
            "models": [
                {
                    "type": "main",
                    "engine": "nim",
                    "model": "rail-main-placeholder",
                    "parameters": {"base_url": nim_base_url},
                }
            ],
            "rails": {"tool_output": {"flows": ["check tool allowlist"]}},
            "custom_data": {"tool_allowlist": {"allowed_tools": allowed_tools}},
        }

    def test_allowed_tool_passes_through(self, igw_plugin_harness: IGWPluginHarness) -> None:
        """If the model asks to call an allowed tool, we return that tool call unchanged."""
        harness = igw_plugin_harness
        names = make_guardrails_test_data_names(workspace=harness.workspace)

        harness.mock_chat_completions(
            names.main_model_served_name,
            responses=[ChatCompletion(body=_tool_call_response_body(self.ALLOWED_TOOL))],
        )
        harness.add_provider(
            workspace=harness.workspace,
            name=names.model_provider_name,
            served_models={names.main_model_served_name: names.main_model_served_name},
        )

        config = make_guardrail_config(
            harness.workspace,
            names.guardrail_config_name,
            data=self._config_data(harness.nim_base_url, allowed_tools=[self.ALLOWED_TOOL]),
        )
        with harness.load_plugin(GUARDRAILS_PLUGIN_NAME):
            harness.add_virtual_model(
                workspace=harness.workspace,
                name=names.request_virtual_model_name,
                default_model_entity=names.main_model_entity_ref,
                response_middleware=[make_middleware_call(config)],
            )
            response = harness.chat_completions(
                workspace=harness.workspace,
                body={
                    "model": names.request_virtual_model_name,
                    "messages": [{"role": "user", "content": self.USER_INPUT}],
                },
            )

        # The backend was called once; no rail LLM call.
        harness.assert_called_once(names.main_model_served_name)
        # Allowed tool passes through — finish_reason stays tool_calls.
        assert response["choices"][0]["finish_reason"] == "tool_calls"
        tool_calls = response["choices"][0]["message"]["tool_calls"]
        assert tool_calls[0]["function"]["name"] == self.ALLOWED_TOOL

    def test_blocked_tool_returns_content_filter(self, igw_plugin_harness: IGWPluginHarness) -> None:
        """If the model asks to call a disallowed tool, we return a refusal instead of the tool call."""
        harness = igw_plugin_harness
        names = make_guardrails_test_data_names(workspace=harness.workspace)

        harness.mock_chat_completions(
            names.main_model_served_name,
            responses=[ChatCompletion(body=_tool_call_response_body(self.BLOCKED_TOOL))],
        )
        harness.add_provider(
            workspace=harness.workspace,
            name=names.model_provider_name,
            served_models={names.main_model_served_name: names.main_model_served_name},
        )

        config = make_guardrail_config(
            harness.workspace,
            names.guardrail_config_name,
            data=self._config_data(harness.nim_base_url, allowed_tools=[self.ALLOWED_TOOL]),
        )
        with harness.load_plugin(GUARDRAILS_PLUGIN_NAME):
            harness.add_virtual_model(
                workspace=harness.workspace,
                name=names.request_virtual_model_name,
                default_model_entity=names.main_model_entity_ref,
                response_middleware=[make_middleware_call(config)],
            )
            response = harness.chat_completions(
                workspace=harness.workspace,
                body={
                    "model": names.request_virtual_model_name,
                    "messages": [{"role": "user", "content": self.USER_INPUT}],
                    "guardrails": {"options": {"log": {"activated_rails": True, "internal_events": True}}},
                },
            )

        harness.assert_called_once(names.main_model_served_name)
        assert response["choices"][0]["finish_reason"] == "content_filter"
        assert response["choices"][0]["message"]["content"] == BLOCKED_REFUSAL_TEXT
        guardrails_data = response.get("guardrails_data") or {}
        assert guardrails_data["config_ids"] == [f"<inline:{names.guardrail_config_name}>"]
        activated_rails = guardrails_data["log"]["activated_rails"]
        assert any(rail["type"] == "tool_output" for rail in activated_rails)

    def test_streaming_tool_output_rails_are_rejected(self, igw_plugin_harness: IGWPluginHarness) -> None:
        """Streaming requests cannot use tool_output rails yet."""
        harness = igw_plugin_harness
        names = make_guardrails_test_data_names(workspace=harness.workspace)

        harness.mock_chat_completions(
            names.main_model_served_name,
            responses=[ChatCompletionStream(chunks=_tool_call_stream_chunks(self.ALLOWED_TOOL))],
        )
        harness.add_provider(
            workspace=harness.workspace,
            name=names.model_provider_name,
            served_models={names.main_model_served_name: names.main_model_served_name},
        )

        config = make_guardrail_config(
            harness.workspace,
            names.guardrail_config_name,
            data=self._config_data(harness.nim_base_url, allowed_tools=[self.ALLOWED_TOOL]),
        )
        with harness.load_plugin(GUARDRAILS_PLUGIN_NAME):
            harness.add_virtual_model(
                workspace=harness.workspace,
                name=names.request_virtual_model_name,
                default_model_entity=names.main_model_entity_ref,
                response_middleware=[make_middleware_call(config)],
            )
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                harness.stream_chat_completions(
                    workspace=harness.workspace,
                    body={
                        "model": names.request_virtual_model_name,
                        "messages": [{"role": "user", "content": self.USER_INPUT}],
                    },
                )

        assert exc_info.value.response.status_code == 400
        assert "Streaming tool_output rails are not supported" in exc_info.value.response.text

    def test_tool_calls_blocked_even_when_finish_reason_is_not_tool_calls(
        self, igw_plugin_harness: IGWPluginHarness
    ) -> None:
        """We check tool calls even when the provider sets the wrong finish_reason."""
        harness = igw_plugin_harness
        names = make_guardrails_test_data_names(workspace=harness.workspace)

        harness.mock_chat_completions(
            names.main_model_served_name,
            responses=[ChatCompletion(body=_tool_call_response_body(self.BLOCKED_TOOL, finish_reason="stop"))],
        )
        harness.add_provider(
            workspace=harness.workspace,
            name=names.model_provider_name,
            served_models={names.main_model_served_name: names.main_model_served_name},
        )

        config = make_guardrail_config(
            harness.workspace,
            names.guardrail_config_name,
            data=self._config_data(harness.nim_base_url, allowed_tools=[self.ALLOWED_TOOL]),
        )
        with harness.load_plugin(GUARDRAILS_PLUGIN_NAME):
            harness.add_virtual_model(
                workspace=harness.workspace,
                name=names.request_virtual_model_name,
                default_model_entity=names.main_model_entity_ref,
                response_middleware=[make_middleware_call(config)],
            )
            response = harness.chat_completions(
                workspace=harness.workspace,
                body={
                    "model": names.request_virtual_model_name,
                    "messages": [{"role": "user", "content": self.USER_INPUT}],
                },
            )

        harness.assert_called_once(names.main_model_served_name)
        assert response["choices"][0]["finish_reason"] == "content_filter"
        assert response["choices"][0]["message"]["content"] == BLOCKED_REFUSAL_TEXT


class TestToolSchemaRails:
    """Tests for checking model tool calls against the tools declared in the request."""

    USER_INPUT = "What's the weather in Paris?"

    @classmethod
    def _config_data(cls, nim_base_url: str) -> dict[str, Any]:
        return {
            "models": [
                {
                    "type": "main",
                    "engine": "nim",
                    "model": "rail-main-placeholder",
                    "parameters": {"base_url": nim_base_url},
                }
            ],
            "rails": {"tool_output": {"flows": ["check tool schema"]}},
        }

    def test_no_tools_in_request_blocks_tool_call(self, igw_plugin_harness: IGWPluginHarness) -> None:
        """If the request declares no tools, any model tool call is blocked."""
        harness = igw_plugin_harness
        names = make_guardrails_test_data_names(workspace=harness.workspace)

        harness.mock_chat_completions(
            names.main_model_served_name,
            responses=[ChatCompletion(body=_tool_call_response_body("get_weather", '{"unit": "kelvin"}'))],
        )
        harness.add_provider(
            workspace=harness.workspace,
            name=names.model_provider_name,
            served_models={names.main_model_served_name: names.main_model_served_name},
        )

        config = make_guardrail_config(
            harness.workspace,
            names.guardrail_config_name,
            data=self._config_data(harness.nim_base_url),
        )
        with harness.load_plugin(GUARDRAILS_PLUGIN_NAME):
            harness.add_virtual_model(
                workspace=harness.workspace,
                name=names.request_virtual_model_name,
                default_model_entity=names.main_model_entity_ref,
                response_middleware=[make_middleware_call(config)],
            )
            response = harness.chat_completions(
                workspace=harness.workspace,
                body={
                    "model": names.request_virtual_model_name,
                    "messages": [{"role": "user", "content": self.USER_INPUT}],
                    # no "tools" field
                },
            )

        harness.assert_called_once(names.main_model_served_name)
        assert response["choices"][0]["finish_reason"] == "content_filter"
        assert response["choices"][0]["message"]["content"] == BLOCKED_REFUSAL_TEXT


class TestToolInputRails:
    """Tests for checking tool result messages before they are sent back to the model.

    These requests contain role="tool" messages, which are the results from
    tools the agent already ran.
    """

    ALLOWED_TOOL = "get_weather"
    BLOCKED_TOOL = "get_secret_data"
    BACKEND_RESPONSE = "The weather in Paris is sunny."

    @classmethod
    def _messages_with_tool_result(cls, tool_name: str, result: str) -> list[dict[str, Any]]:
        return [
            {"role": "user", "content": "What's the weather?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": tool_name, "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "name": tool_name,
                "content": result,
            },
        ]

    @classmethod
    def _config_data(cls, nim_base_url: str, *, allowed_tools: list[str]) -> dict[str, Any]:
        return {
            "models": [
                {
                    "type": "main",
                    "engine": "nim",
                    "model": "rail-main-placeholder",
                    "parameters": {"base_url": nim_base_url},
                }
            ],
            "rails": {"tool_input": {"flows": ["check tool allowlist"]}},
            "custom_data": {"tool_allowlist": {"allowed_tools": allowed_tools}},
        }

    def test_allowed_tool_result_reaches_backend(self, igw_plugin_harness: IGWPluginHarness) -> None:
        """If a tool result is from an allowed tool, we send it back to the model."""
        harness = igw_plugin_harness
        names = make_guardrails_test_data_names(workspace=harness.workspace)

        harness.mock_chat_completions(
            names.main_model_served_name,
            responses=[
                ChatCompletion(
                    body={
                        "id": "chatcmpl-test",
                        "object": "chat.completion",
                        "created": 0,
                        "model": None,
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": self.BACKEND_RESPONSE},
                                "finish_reason": "stop",
                            }
                        ],
                    }
                )
            ],
        )
        harness.add_provider(
            workspace=harness.workspace,
            name=names.model_provider_name,
            served_models={names.main_model_served_name: names.main_model_served_name},
        )

        config = make_guardrail_config(
            harness.workspace,
            names.guardrail_config_name,
            data=self._config_data(harness.nim_base_url, allowed_tools=[self.ALLOWED_TOOL]),
        )
        with harness.load_plugin(GUARDRAILS_PLUGIN_NAME):
            harness.add_virtual_model(
                workspace=harness.workspace,
                name=names.request_virtual_model_name,
                default_model_entity=names.main_model_entity_ref,
                request_middleware=[make_middleware_call(config)],
            )
            response = harness.chat_completions(
                workspace=harness.workspace,
                body={
                    "model": names.request_virtual_model_name,
                    "messages": self._messages_with_tool_result(self.ALLOWED_TOOL, "Sunny, 25°C"),
                },
            )

        # The backend was called; the tool result passed the rail.
        harness.assert_called_once(names.main_model_served_name)
        assert response["choices"][0]["message"]["content"] == self.BACKEND_RESPONSE

    def test_tool_input_and_tool_output_logs_both_reported(self, igw_plugin_harness: IGWPluginHarness) -> None:
        """If both request and response rails run, guardrails_data reports both of them."""
        harness = igw_plugin_harness
        names = make_guardrails_test_data_names(workspace=harness.workspace)

        harness.mock_chat_completions(
            names.main_model_served_name,
            responses=[ChatCompletion(body=_tool_call_response_body(self.ALLOWED_TOOL))],
        )
        harness.add_provider(
            workspace=harness.workspace,
            name=names.model_provider_name,
            served_models={names.main_model_served_name: names.main_model_served_name},
        )

        config = make_guardrail_config(
            harness.workspace,
            names.guardrail_config_name,
            data={
                **self._config_data(harness.nim_base_url, allowed_tools=[self.ALLOWED_TOOL]),
                "rails": {
                    "tool_input": {"flows": ["check tool allowlist"]},
                    "tool_output": {"flows": ["check tool allowlist"]},
                },
            },
        )
        with harness.load_plugin(GUARDRAILS_PLUGIN_NAME):
            harness.add_virtual_model(
                workspace=harness.workspace,
                name=names.request_virtual_model_name,
                default_model_entity=names.main_model_entity_ref,
                request_middleware=[make_middleware_call(config)],
                response_middleware=[make_middleware_call(config)],
            )
            response = harness.chat_completions(
                workspace=harness.workspace,
                body={
                    "model": names.request_virtual_model_name,
                    "messages": self._messages_with_tool_result(self.ALLOWED_TOOL, "Sunny, 25°C"),
                    "guardrails": {"options": {"log": {"activated_rails": True}}},
                },
            )

        harness.assert_called_once(names.main_model_served_name)
        assert response["choices"][0]["finish_reason"] == "tool_calls"

        guardrails_data = response.get("guardrails_data") or {}
        activated_rails = guardrails_data["log"]["activated_rails"]
        assert [(rail["type"], rail["name"]) for rail in activated_rails] == [
            ("tool_input", "check tool allowlist"),
            ("tool_output", "check tool allowlist"),
        ]

    def test_blocked_tool_result_returns_immediate_response(self, igw_plugin_harness: IGWPluginHarness) -> None:
        """If a tool result is from a disallowed tool, we refuse before calling the model.

        The model should never see the blocked tool result.
        """
        harness = igw_plugin_harness
        names = make_guardrails_test_data_names(workspace=harness.workspace)

        harness.add_provider(
            workspace=harness.workspace,
            name=names.model_provider_name,
            served_models={names.main_model_served_name: names.main_model_served_name},
        )

        config = make_guardrail_config(
            harness.workspace,
            names.guardrail_config_name,
            data=self._config_data(harness.nim_base_url, allowed_tools=[self.ALLOWED_TOOL]),
        )
        with harness.load_plugin(GUARDRAILS_PLUGIN_NAME):
            harness.add_virtual_model(
                workspace=harness.workspace,
                name=names.request_virtual_model_name,
                default_model_entity=names.main_model_entity_ref,
                request_middleware=[make_middleware_call(config)],
            )
            response = harness.chat_completions(
                workspace=harness.workspace,
                body={
                    "model": names.request_virtual_model_name,
                    "messages": self._messages_with_tool_result(self.BLOCKED_TOOL, "secret payload"),
                },
            )

        # The backend was never called — blocked at request time.
        harness.assert_no_calls_to(names.main_model_served_name)
        assert response["choices"][0]["finish_reason"] == "content_filter"
        assert response["choices"][0]["message"]["content"] == BLOCKED_REFUSAL_TEXT


class TestToolResultLinkageRails:
    """Tests for checking that tool results match tool calls from the same request."""

    TOOL_NAME = "get_weather"

    @classmethod
    def _config_data(cls, nim_base_url: str) -> dict[str, Any]:
        return {
            "models": [
                {
                    "type": "main",
                    "engine": "nim",
                    "model": "rail-main-placeholder",
                    "parameters": {"base_url": nim_base_url},
                }
            ],
            "rails": {"tool_input": {"flows": ["check tool result linkage"]}},
        }

    @classmethod
    def _messages_with_tool_result(
        cls, call_id: str = "call_1", result_call_id: str = "call_1", tool_name: str = "get_weather"
    ) -> list[dict[str, Any]]:
        return [
            {"role": "user", "content": "What's the weather?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": result_call_id,
                "name": tool_name,
                "content": "Sunny, 25°C",
            },
        ]

    def test_orphaned_call_id_blocked(self, igw_plugin_harness: IGWPluginHarness) -> None:
        """If a tool result has no matching assistant tool call, we refuse before calling the model."""
        harness = igw_plugin_harness
        names = make_guardrails_test_data_names(workspace=harness.workspace)

        harness.add_provider(
            workspace=harness.workspace,
            name=names.model_provider_name,
            served_models={names.main_model_served_name: names.main_model_served_name},
        )

        config = make_guardrail_config(
            harness.workspace,
            names.guardrail_config_name,
            data=self._config_data(harness.nim_base_url),
        )
        with harness.load_plugin(GUARDRAILS_PLUGIN_NAME):
            harness.add_virtual_model(
                workspace=harness.workspace,
                name=names.request_virtual_model_name,
                default_model_entity=names.main_model_entity_ref,
                request_middleware=[make_middleware_call(config)],
            )
            response = harness.chat_completions(
                workspace=harness.workspace,
                body={
                    "model": names.request_virtual_model_name,
                    # result references "call_999" but the prior call has id "call_1"
                    "messages": self._messages_with_tool_result(call_id="call_1", result_call_id="call_999"),
                },
            )

        harness.assert_no_calls_to(names.main_model_served_name)
        assert response["choices"][0]["finish_reason"] == "content_filter"
        assert response["choices"][0]["message"]["content"] == BLOCKED_REFUSAL_TEXT
