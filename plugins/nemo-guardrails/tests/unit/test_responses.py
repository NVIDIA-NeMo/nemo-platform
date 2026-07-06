# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from typing import Any

import pytest
from nemo_guardrails_plugin.constants import GUARDRAILS_DATA_MESSAGE_ROLE
from nemo_guardrails_plugin.rails import build_generation_response_logs
from nemo_guardrails_plugin.responses import (
    build_assistant_message_from_response_result,
    build_blocked_output_response_body,
    build_immediate_response,
    build_inference_response,
    build_output_response_body,
    guardrails_data_to_dict,
)
from nemo_platform_plugin.inference_middleware import InferenceMiddlewareError, InferenceResponse
from nemoguardrails.rails.llm.options import ActivatedRail, GenerationLog, GenerationResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_generation_response(*, stopped: bool = False, content: str = "I can't help with that.") -> GenerationResponse:
    return GenerationResponse(
        response=[{"role": "assistant", "content": content}],
        log=GenerationLog(
            activated_rails=[ActivatedRail(type="output", name="self check output", stop=stopped)],
        ),
    )


def _make_response_result(content: str = "Hello!") -> dict[str, Any]:
    return {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "model": "my-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


# ---------------------------------------------------------------------------
# build_assistant_message_from_response_result
# ---------------------------------------------------------------------------


def _make_tool_call_response_result(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "chatcmpl-456",
        "object": "chat.completion",
        "model": "my-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": None, "tool_calls": tool_calls},
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


class TestBuildAssistantMessageFromResponseResult:
    def test_extracts_content(self) -> None:
        result = build_assistant_message_from_response_result(_make_response_result("Hello!"))
        assert result == {"role": "assistant", "content": "Hello!"}

    def test_preserves_tool_calls(self) -> None:
        tool_calls = [{"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}]
        result = build_assistant_message_from_response_result(_make_tool_call_response_result(tool_calls))
        assert result["role"] == "assistant"
        assert result["content"] == ""
        assert result["tool_calls"] == tool_calls

    def test_no_tool_calls_key_on_normal_response(self) -> None:
        result = build_assistant_message_from_response_result(_make_response_result("Hello!"))
        assert "tool_calls" not in result

    def test_empty_tool_calls_list_not_forwarded(self) -> None:
        result = build_assistant_message_from_response_result(_make_tool_call_response_result([]))
        assert "tool_calls" not in result
        assert result["content"] == ""

    @pytest.mark.parametrize(
        "response_result",
        [
            "not-a-dict",
            {},
            {"choices": []},
            {"choices": [{}]},
            {"choices": [{"message": None}]},
        ],
    )
    def test_fallback_to_empty_content(self, response_result: Any) -> None:
        result = build_assistant_message_from_response_result(response_result)
        assert result == {"role": "assistant", "content": ""}


# ---------------------------------------------------------------------------
# build_blocked_output_response_body
# ---------------------------------------------------------------------------


class TestBuildBlockedOutputResponseBody:
    def test_preserves_envelope_overwrites_choices(self) -> None:
        original = _make_response_result("unsafe content")
        generation_response = _make_generation_response(stopped=True, content="I can't do that.")

        result = build_blocked_output_response_body(
            config_id="ws/my-config",
            original_response=original,
            generation_response=generation_response,
            input_generation_logs=None,
            user_log_options=None,
        )

        assert result["id"] == original["id"]
        assert result["model"] == original["model"]
        assert result["usage"] == original["usage"]
        assert result["choices"] == [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "I can't do that."},
                "finish_reason": "content_filter",
            }
        ]
        assert "guardrails_data" in result
        assert result["guardrails_data"]["config_ids"] == ["ws/my-config"]

    def test_return_choice_appends_guardrails_choice(self) -> None:
        result = build_blocked_output_response_body(
            config_id="ws/my-config",
            original_response=_make_response_result(),
            generation_response=_make_generation_response(stopped=True),
            input_generation_logs=None,
            user_log_options=None,
            return_guardrails_data_as_choice=True,
        )

        assert "guardrails_data" not in result
        assert len(result["choices"]) == 2
        guardrails_choice = result["choices"][1]
        assert guardrails_choice["index"] == 1
        assert guardrails_choice["message"]["role"] == GUARDRAILS_DATA_MESSAGE_ROLE
        assert json.loads(guardrails_choice["message"]["content"])["config_ids"] == ["ws/my-config"]

    def test_guardrails_data_serializer_falls_back_when_model_dump_fails(self) -> None:
        class BrokenModelDump:
            def __init__(self) -> None:
                self.config_ids = ["ws/my-config"]
                self.log = {"activated_rails": [{"name": "check tool allowlist", "type": "tool_output"}]}

            def model_dump(self, **_: Any) -> dict[str, Any]:
                raise TypeError("'NoneType' object cannot be converted to 'SchemaSerializer'")

        assert guardrails_data_to_dict(BrokenModelDump()) == {
            "config_ids": ["ws/my-config"],
            "log": {"activated_rails": [{"name": "check tool allowlist", "type": "tool_output"}]},
        }


# ---------------------------------------------------------------------------
# build_immediate_response
# ---------------------------------------------------------------------------


class TestBuildImmediateResponse:
    def test_moves_guardrails_data_to_annotations(self) -> None:
        result = build_immediate_response(
            response_body={
                "id": "chatcmpl-123",
                "choices": [],
                "guardrails_data": {"config_ids": ["ws/my-config"]},
            },
        )

        assert result.data == {"id": "chatcmpl-123", "choices": []}
        assert result.response_body_annotations == {"guardrails_data": {"config_ids": ["ws/my-config"]}}


# ---------------------------------------------------------------------------
# build_output_response_body
# ---------------------------------------------------------------------------


class TestBuildOutputResponseBody:
    def test_raises_clear_error_when_choices_missing(self) -> None:
        with pytest.raises(
            InferenceMiddlewareError,
            match="expected upstream response to include a 'choices' field",
        ) as exc_info:
            build_output_response_body(
                config_id="ws/my-config",
                original_response={"id": "chatcmpl-123"},
                generation_response=None,
                input_generation_logs=None,
                user_log_options=None,
            )

        assert exc_info.value.status_code == 500

    def test_preserves_single_choice_sets_guardrails_data(self) -> None:
        original = _make_response_result("Hello!")

        result = build_output_response_body(
            config_id="ws/my-config",
            original_response=original,
            generation_response=_make_generation_response(),
            input_generation_logs=None,
            user_log_options=None,
        )

        assert result["choices"] == original["choices"]
        assert "guardrails_data" in result
        assert result["guardrails_data"]["config_ids"] == ["ws/my-config"]

    def test_keeps_only_first_choice(self) -> None:
        original = {
            "id": "chatcmpl-123",
            "choices": [
                {"index": 3, "message": {"role": "assistant", "content": "A"}, "finish_reason": "stop"},
                {"index": 4, "message": {"role": "assistant", "content": "B"}, "finish_reason": "stop"},
            ],
        }

        result = build_output_response_body(
            config_id="ws/my-config",
            original_response=original,
            generation_response=_make_generation_response(),
            input_generation_logs=None,
            user_log_options=None,
        )

        assert result["choices"] == [
            {"index": 0, "message": {"role": "assistant", "content": "A"}, "finish_reason": "stop"}
        ]

    def test_return_choice_appends_at_correct_index(self) -> None:
        original = {
            "id": "chatcmpl-123",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "A"}, "finish_reason": "stop"},
                {"index": 1, "message": {"role": "assistant", "content": "B"}, "finish_reason": "stop"},
            ],
        }

        result = build_output_response_body(
            config_id="ws/my-config",
            original_response=original,
            generation_response=_make_generation_response(),
            input_generation_logs=None,
            user_log_options=None,
            return_guardrails_data_as_choice=True,
        )

        assert "guardrails_data" not in result
        assert len(result["choices"]) == 2
        assert result["choices"][0]["message"]["content"] == "A"

        guardrails_choice = result["choices"][1]
        assert guardrails_choice["index"] == 1
        assert guardrails_choice["message"]["role"] == GUARDRAILS_DATA_MESSAGE_ROLE
        assert json.loads(guardrails_choice["message"]["content"])["config_ids"] == ["ws/my-config"]

        # Verify original choices were not mutated
        assert original["choices"] == [
            {"index": 0, "message": {"role": "assistant", "content": "A"}, "finish_reason": "stop"},
            {"index": 1, "message": {"role": "assistant", "content": "B"}, "finish_reason": "stop"},
        ]

    def test_return_choice_does_not_mutate_original_choices_when_output_rails_skipped(self) -> None:
        original = {
            "id": "chatcmpl-123",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "A"}, "finish_reason": "stop"},
                {"index": 1, "message": {"role": "assistant", "content": "B"}, "finish_reason": "stop"},
            ],
        }

        input_response = _make_generation_response()
        result = build_output_response_body(
            config_id="ws/my-config",
            original_response=original,
            generation_response=None,
            input_generation_logs=build_generation_response_logs(input_response),
            user_log_options=None,
            return_guardrails_data_as_choice=True,
        )

        assert len(result["choices"]) == 3

        # Verify original choices were not mutated
        assert original["choices"] == [
            {"index": 0, "message": {"role": "assistant", "content": "A"}, "finish_reason": "stop"},
            {"index": 1, "message": {"role": "assistant", "content": "B"}, "finish_reason": "stop"},
        ]

    def test_no_output_generation_response(self) -> None:
        original = {
            "id": "chatcmpl-123",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "A"}, "finish_reason": "stop"},
                {"index": 1, "message": {"role": "assistant", "content": "B"}, "finish_reason": "stop"},
            ],
        }

        input_response = _make_generation_response()
        result = build_output_response_body(
            config_id="ws/my-config",
            original_response=original,
            generation_response=None,
            input_generation_logs=build_generation_response_logs(input_response),
            user_log_options=None,
        )

        assert result["choices"] == original["choices"]
        assert result["guardrails_data"]["config_ids"] == ["ws/my-config"]


# ---------------------------------------------------------------------------
# build_inference_response
# ---------------------------------------------------------------------------


class TestBuildInferenceResponse:
    def test_moves_guardrails_data_to_annotations(self) -> None:
        upstream = InferenceResponse(
            result={"id": "raw"},
            headers={"x-test": "1"},
            response_body_annotations={"existing": True},
        )

        result = build_inference_response(
            response=upstream,
            response_body={
                "id": "chatcmpl-123",
                "choices": [],
                "guardrails_data": {"config_ids": ["ws/my-config"]},
            },
        )

        assert result.result == {"id": "chatcmpl-123", "choices": []}
        assert result.headers == {"x-test": "1"}
        assert result.typed_body is None
        assert result.response_body_annotations == {
            "existing": True,
            "guardrails_data": {"config_ids": ["ws/my-config"]},
        }

    def test_return_choice_removes_top_level_guardrails_data_from_annotations_and_body(self) -> None:
        upstream = InferenceResponse(
            result={"id": "raw"},
            headers={"x-test": "1"},
            response_body_annotations={
                "existing": True,
                "guardrails_data": {"config_ids": ["request/fallback"]},
            },
        )

        result = build_inference_response(
            response=upstream,
            response_body={
                "id": "chatcmpl-123",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "Hi"}, "finish_reason": "stop"},
                    {
                        "index": 1,
                        "message": {"role": GUARDRAILS_DATA_MESSAGE_ROLE, "content": '{"config_ids":["ws/my-config"]}'},
                    },
                ],
                "guardrails_data": {"config_ids": ["body/fallback"]},
            },
            return_guardrails_data_as_choice=True,
        )

        assert result.result == {
            "id": "chatcmpl-123",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "Hi"}, "finish_reason": "stop"},
                {
                    "index": 1,
                    "message": {"role": GUARDRAILS_DATA_MESSAGE_ROLE, "content": '{"config_ids":["ws/my-config"]}'},
                },
            ],
        }
        assert result.response_body_annotations == {"existing": True}

    def test_return_choice_preserves_unrelated_response_body_annotations(self) -> None:
        upstream = InferenceResponse(
            result={"id": "raw"},
            headers={"x-test": "1"},
            response_body_annotations={
                "guardrails_data": {"config_ids": ["request/fallback"]},
                "other_plugin": {"trace_id": "abc"},
            },
        )

        result = build_inference_response(
            response=upstream,
            response_body={"id": "chatcmpl-123", "choices": []},
            return_guardrails_data_as_choice=True,
        )

        assert result.response_body_annotations == {"other_plugin": {"trace_id": "abc"}}
