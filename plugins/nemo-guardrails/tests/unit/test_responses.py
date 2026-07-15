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
    extract_upstream_client_error,
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
# extract_upstream_client_error
# ---------------------------------------------------------------------------


class TestExtractUpstreamClientError:
    def test_openai_status_error_status_code_preserved(self) -> None:
        """A genuine ``status_code`` attribute (as set by ``openai.APIStatusError``
        and all its subclasses) is picked up directly via duck typing — no
        message parsing needed."""
        response = httpx.Response(422, request=httpx.Request("POST", "http://example.test"))
        inner = openai.BadRequestError("Unsupported parameter: foo", response=response, body=None)
        try:
            raise LLMCallException(inner, detail="Error invoking LLM") from inner
        except LLMCallException as exc:
            result = extract_upstream_client_error(exc)

        assert result is not None
        assert result.status_code == 422
        assert result.detail == "Error invoking LLM: Unsupported parameter: foo"

    def test_bracketed_status_prefix_fallback_on_inner_exception(self) -> None:
        """When ``inner_exception`` has no structured ``status_code``, falls
        back to parsing the ``[<status>] <detail>`` prefix convention used by
        ``langchain_nvidia_ai_endpoints`` — checked on ``inner_exception``,
        not the outer ``LLMCallException``, since the outer exception's
        message (``"Error invoking LLM (...): ..."``) never itself starts
        with a bracketed status."""
        inner = Exception(  # noqa: TRY002 - mirrors langchain_nvidia_ai_endpoints._format_error
            '[400] Unknown Error {"object":"error","message":'
            '"At most 1 image(s) may be provided in one request.",'
            '"type":"BadRequestError","param":null,"code":400}'
        )
        try:
            raise LLMCallException(inner, detail="Error invoking LLM (model=vision-judge)") from inner
        except LLMCallException as exc:
            result = extract_upstream_client_error(exc)

        assert result is not None
        assert result.status_code == 400
        # The outer LLMCallException's ``detail`` is preserved alongside the
        # sanitized upstream message, and the "Unknown Error" placeholder /
        # raw JSON body is not leaked verbatim.
        assert result.detail == (
            "Error invoking LLM (model=vision-judge): At most 1 image(s) may be provided in one request."
        )

    def test_bracketed_status_prefix_without_llm_call_exception_wrapping(self) -> None:
        """The bracketed-prefix fallback also applies to a bare exception with
        no ``LLMCallException`` wrapping at all, in which case there is no
        context to prefix."""
        exc = Exception("[404] Model not found")  # noqa: TRY002

        result = extract_upstream_client_error(exc)

        assert result is not None
        assert result.status_code == 404
        assert result.detail == "Model not found"

    def test_bracketed_status_prefix_with_unparseable_json_body_falls_back_to_raw_text(self) -> None:
        """If the text after the bracketed status prefix isn't valid JSON,
        the raw text is used as-is rather than raising or dropping the
        message."""
        exc = Exception("[400] Bad Request: not-json-at-all")  # noqa: TRY002

        result = extract_upstream_client_error(exc)

        assert result is not None
        assert result.status_code == 400
        assert result.detail == "Bad Request: not-json-at-all"

    def test_does_not_follow_plain_cause_chain_when_not_llm_call_exception(self) -> None:
        """Only two objects are ever examined: ``exc`` itself, and
        ``exc.inner_exception`` if ``exc`` is an ``LLMCallException``. A plain
        ``__cause__`` link (e.g. from a bare ``raise ... from ...``, with no
        ``LLMCallException`` involved at all) is deliberately *not* followed
        — this doesn't happen on either real error path (nemoguardrails has a
        single call site that constructs ``LLMCallException``, and it's never
        nested), so a bracketed 4xx one hop further back via plain
        ``__cause__`` is not recovered."""
        inner = Exception("[400] Nested bad request")  # noqa: TRY002
        try:
            raise RuntimeError("wrapper") from inner
        except RuntimeError as wrapper:
            exc = wrapper

        assert extract_upstream_client_error(exc) is None

    def test_inner_exception_as_string_falls_back_to_checking_exc_itself(self) -> None:
        """``LLMCallException.inner_exception`` is typed as ``BaseException | str``
        — when it's a bare string (no attributes, nothing to unwrap), ``exc``
        itself is checked instead of crashing on a non-exception ``candidate``.
        ``exc`` never has a recoverable status of its own, so this returns
        ``None`` rather than raising."""
        exc = LLMCallException("no exception object here, just a string", detail="Error invoking LLM")

        assert extract_upstream_client_error(exc) is None

    def test_status_code_outside_client_error_range_is_ignored(self) -> None:
        """A ``status_code`` attribute present but outside the 4xx range
        (e.g. a genuine 500) is not treated as a recoverable client error."""
        response = httpx.Response(500, request=httpx.Request("POST", "http://example.test"))
        inner = openai.InternalServerError("Upstream exploded", response=response, body=None)
        try:
            raise LLMCallException(inner, detail="Error invoking LLM") from inner
        except LLMCallException as exc:
            result = extract_upstream_client_error(exc)

        assert result is None

    def test_bracketed_5xx_prefix_returns_none(self) -> None:
        """A ``[5xx]``-prefixed failure is left alone — only 4xx is safe to
        reinterpret as a preserved client error; a 5xx is a genuine outage."""
        exc = Exception("[503] Service temporarily overloaded")  # noqa: TRY002

        assert extract_upstream_client_error(exc) is None

    def test_no_recoverable_status_anywhere_returns_none(self) -> None:
        """When neither ``exc`` nor ``exc.inner_exception`` has a status code
        or bracketed prefix, returns ``None`` so the caller keeps its
        existing 503 fallback."""
        inner = ValueError("something went wrong")
        try:
            raise LLMCallException(inner, detail="Error invoking LLM") from inner
        except LLMCallException as exc:
            result = extract_upstream_client_error(exc)

        assert result is None
