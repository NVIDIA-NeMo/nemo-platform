# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from typing import Any

import httpx
import openai
import pytest
from nemo_guardrails_plugin.constants import GUARDRAILS_DATA_MESSAGE_ROLE
from nemo_guardrails_plugin.responses import (
    build_assistant_message_from_response_result,
    build_blocked_output_response_body,
    build_immediate_response,
    build_inference_response,
    build_output_response_body,
    extract_upstream_error,
)
from nemo_platform_plugin.inference_middleware import InferenceMiddlewareError, InferenceResponse
from nemoguardrails.exceptions import LLMCallException
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


class TestBuildAssistantMessageFromResponseResult:
    def test_extracts_content(self) -> None:
        result = build_assistant_message_from_response_result(_make_response_result("Hello!"))
        assert result == {"role": "assistant", "content": "Hello!"}

    @pytest.mark.parametrize(
        "response_result",
        [
            "not-a-dict",
            {},
            {"choices": []},
            {"choices": [{}]},
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
            input_generation_response=None,
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
            input_generation_response=None,
            user_log_options=None,
            return_guardrails_data_as_choice=True,
        )

        assert "guardrails_data" not in result
        assert len(result["choices"]) == 2
        guardrails_choice = result["choices"][1]
        assert guardrails_choice["index"] == 1
        assert guardrails_choice["message"]["role"] == GUARDRAILS_DATA_MESSAGE_ROLE
        assert json.loads(guardrails_choice["message"]["content"])["config_ids"] == ["ws/my-config"]


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
                input_generation_response=None,
                user_log_options=None,
            )

        assert exc_info.value.status_code == 500

    def test_preserves_single_choice_sets_guardrails_data(self) -> None:
        original = _make_response_result("Hello!")

        result = build_output_response_body(
            config_id="ws/my-config",
            original_response=original,
            generation_response=_make_generation_response(),
            input_generation_response=None,
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
            input_generation_response=None,
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
            input_generation_response=None,
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

        result = build_output_response_body(
            config_id="ws/my-config",
            original_response=original,
            generation_response=None,
            input_generation_response=_make_generation_response(),
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

        result = build_output_response_body(
            config_id="ws/my-config",
            original_response=original,
            generation_response=None,
            input_generation_response=_make_generation_response(),
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


# ---------------------------------------------------------------------------
# extract_upstream_error
# ---------------------------------------------------------------------------


class TestExtractUpstreamError:
    def test_status_code_attribute_4xx_preserved(self) -> None:
        """A genuine ``status_code`` attribute (``openai.APIStatusError``) is
        read directly, no message parsing."""
        response = httpx.Response(422, request=httpx.Request("POST", "http://example.test"))
        inner = openai.BadRequestError("Unsupported parameter: foo", response=response, body=None)
        try:
            raise LLMCallException(inner, detail="Error invoking LLM") from inner
        except LLMCallException as exc:
            result = extract_upstream_error(exc)

        assert result is not None
        assert result.status_code == 422
        assert result.detail == "Error invoking LLM: Unsupported parameter: foo"

    def test_bracketed_prefix_4xx_preserved(self) -> None:
        """With no structured ``status_code``, the ``[<status>] ...`` prefix is
        parsed off ``inner_exception`` (the langchain library's convention)."""
        inner = Exception(  # noqa: TRY002 - mirrors langchain_nvidia_ai_endpoints._format_error
            '[400] Unknown Error {"object":"error","message":'
            '"At most 1 image(s) may be provided in one request.",'
            '"type":"BadRequestError","param":null,"code":400}'
        )
        try:
            raise LLMCallException(inner, detail="Error invoking LLM (model=vision-judge)") from inner
        except LLMCallException as exc:
            result = extract_upstream_error(exc)

        assert result is not None
        assert result.status_code == 400
        # LLMCallException.detail is prefixed; "Unknown Error"/raw JSON dropped.
        assert result.detail == (
            "Error invoking LLM (model=vision-judge): At most 1 image(s) may be provided in one request."
        )

    def test_bracketed_prefix_without_wrapping_preserved(self) -> None:
        """A bare bracketed exception (no ``LLMCallException``) works too, with
        no context to prefix."""
        exc = Exception("[404] Model not found")  # noqa: TRY002

        result = extract_upstream_error(exc)

        assert result is not None
        assert result.status_code == 404
        assert result.detail == "Model not found"

    def test_bracketed_prefix_unparseable_json_uses_raw_text(self) -> None:
        """Non-JSON text after the status prefix is used as-is."""
        exc = Exception("[400] Bad Request: not-json-at-all")  # noqa: TRY002

        result = extract_upstream_error(exc)

        assert result is not None
        assert result.status_code == 400
        assert result.detail == "Bad Request: not-json-at-all"

    def test_string_inner_exception_returns_none(self) -> None:
        """A string ``inner_exception`` (its type is ``BaseException | str``)
        is skipped without crashing, returning ``None``."""
        exc = LLMCallException("no exception object here, just a string", detail="Error invoking LLM")

        assert extract_upstream_error(exc) is None

    def test_status_code_attribute_5xx_preserved(self) -> None:
        """A ``status_code`` attribute is preserved for a 5xx too, not
        collapsed to the middleware's generic 503."""
        response = httpx.Response(500, request=httpx.Request("POST", "http://example.test"))
        inner = openai.InternalServerError("Upstream exploded", response=response, body=None)
        try:
            raise LLMCallException(inner, detail="Error invoking LLM") from inner
        except LLMCallException as exc:
            result = extract_upstream_error(exc)

        assert result is not None
        assert result.status_code == 500
        assert result.detail == "Error invoking LLM: Upstream exploded"

    def test_bracketed_prefix_5xx_preserved(self) -> None:
        """A ``[5xx]``-prefixed failure is preserved, same as a 4xx."""
        exc = Exception("[503] Service temporarily overloaded")  # noqa: TRY002

        result = extract_upstream_error(exc)

        assert result is not None
        assert result.status_code == 503
        assert result.detail == "Service temporarily overloaded"

    def test_non_error_status_returns_none(self) -> None:
        """A 1xx-3xx status embedded in the error message is ignored."""
        exc = Exception("[302] Found")  # noqa: TRY002

        assert extract_upstream_error(exc) is None

    def test_no_recoverable_status_returns_none(self) -> None:
        """No status anywhere → ``None``, so the caller keeps its 503 fallback."""
        inner = ValueError("something went wrong")
        try:
            raise LLMCallException(inner, detail="Error invoking LLM") from inner
        except LLMCallException as exc:
            result = extract_upstream_error(exc)

        assert result is None
