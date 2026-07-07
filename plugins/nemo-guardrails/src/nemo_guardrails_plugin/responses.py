# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from nemo_guardrails_plugin.constants import GUARDRAILS_DATA_MESSAGE_ROLE
from nemo_guardrails_plugin.rails import build_generation_response_logs, build_guardrails_data
from nemo_platform.types.guardrail import GenerationLogOptionsParam
from nemo_platform_plugin.inference_middleware import (
    ImmediateResponse,
    InferenceMiddlewareError,
    InferenceResponse,
    ResponseResult,
)
from nemoguardrails.rails.llm.options import GenerationLog as LibraryGenerationLog
from nemoguardrails.rails.llm.options import GenerationResponse

logger = logging.getLogger(__name__)

GUARDRAILS_DATA_FIELD = "guardrails_data"


def build_chat_completion_response_id() -> str:
    """Build a chat completion response ID consistent with OpenAI-style responses."""
    return f"chatcmpl-{uuid.uuid4()}"


def is_blocked_generation_response(generation_response: GenerationResponse) -> bool:
    """
    Returns True if the GenerationResponse indicates the request was blocked by a guardrail.
    """
    log = generation_response.log

    if not log:
        logger.debug("Received GenerationResponse with empty log. ")
        return True

    activated_rails = log.activated_rails or []

    return any(rail.stop is True for rail in activated_rails)


def first_response_choice(response_body: dict[str, Any]) -> dict[str, Any]:
    choices = response_body.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return choices[0]
    return {}


def first_response_message(response_body: dict[str, Any]) -> dict[str, Any]:
    message = first_response_choice(response_body).get("message")
    return message if isinstance(message, dict) else {}


def first_response_finish_reason(response_body: dict[str, Any]) -> Any:
    return first_response_choice(response_body).get("finish_reason")


def response_tool_calls(response_body: dict[str, Any]) -> Any:
    """Return the raw tool_calls value from the first response choice.

    Tool rail actions fail closed on malformed shapes. Keep the raw value for
    rail context, and use the safe helpers below for middleware logging/branching.
    """
    return first_response_message(response_body).get("tool_calls") or []


def has_tool_calls(tool_calls: Any) -> bool:
    return bool(tool_calls)


def tool_call_count(tool_calls: Any) -> int:
    return len(tool_calls) if isinstance(tool_calls, list) else int(bool(tool_calls))


def tool_call_names(tool_calls: Any) -> list[Any]:
    if not isinstance(tool_calls, list):
        return []
    return [tc.get("function", {}).get("name") for tc in tool_calls if isinstance(tc, dict)]


def has_assistant_content(response_body: dict[str, Any]) -> bool:
    return bool(first_response_message(response_body).get("content"))


def extract_response_content(generation_response: GenerationResponse) -> str:
    """
    Extract the last assistant message content from a GenerationResponse.
    """
    response = generation_response.response
    if isinstance(response, list):
        for item in reversed(response):
            if item.get("role") == "assistant" and item.get("content"):
                return item.get("content", "")

        return ""

    return response


def build_assistant_message_from_response_result(response_result: ResponseResult) -> dict[str, Any]:
    """
    Build an assistant message object with the content from the given response.
    """
    assistant_message: dict[str, Any] = {
        "role": "assistant",
        "content": "",
    }

    if isinstance(response_result, AsyncIterator):
        return assistant_message

    try:
        message = response_result["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return assistant_message

    if not isinstance(message, dict):
        return assistant_message

    assistant_message["content"] = message.get("content") or ""
    if tool_calls := message.get("tool_calls"):
        assistant_message["tool_calls"] = tool_calls
    return assistant_message


def build_blocked_immediate_response_body(
    config_id: str,
    request_body: dict[str, Any],
    generation_response: GenerationResponse,
    user_log_options: GenerationLogOptionsParam | None,
    prior_generation_logs: list[LibraryGenerationLog] | None = None,
) -> dict[str, Any]:
    """
    Build the response body to return when an input or output rail blocks the request.
    """
    blocked: dict[str, Any] = {
        "id": build_chat_completion_response_id(),
        "object": "chat.completion",
        "model": request_body.get("model", ""),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": extract_response_content(generation_response)},
                "finish_reason": "content_filter",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }

    guardrails_data = build_guardrails_data(
        config_id,
        prior_generation_logs=prior_generation_logs
        if prior_generation_logs is not None
        else build_generation_response_logs(generation_response),
        user_log_options=user_log_options,
    )
    if guardrails_data is not None:
        blocked[GUARDRAILS_DATA_FIELD] = guardrails_data.to_dict(mode="json", exclude_none=True)

    return blocked


def build_immediate_response(
    *,
    response_body: dict[str, Any],
) -> ImmediateResponse:
    """Build the ImmediateResponse returned by the process_request handler."""
    result = dict(response_body)
    annotations = {}
    # If we should include guardrails_data in the result, add it as an annotation. IGW handles
    # merging the annotations into the response before returning to the caller.
    if GUARDRAILS_DATA_FIELD in result:
        annotations[GUARDRAILS_DATA_FIELD] = result.pop(GUARDRAILS_DATA_FIELD)

    return ImmediateResponse(
        data=result,
        response_body_annotations=annotations,
    )


def build_blocked_output_response_body(
    config_id: str,
    original_response: dict[str, Any],
    generation_response: GenerationResponse,
    prior_generation_logs: list[LibraryGenerationLog] | None,
    user_log_options: GenerationLogOptionsParam | None,
    return_guardrails_data_as_choice: bool = False,
) -> dict[str, Any]:
    """
    Build the response body to return when an output rail blocks the model's response.

    Preserves the original response shape, but overwrites the choices with a blocked
    assistant message.
    """
    blocked_response: dict[str, Any] = {
        **original_response,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": extract_response_content(generation_response)},
                "finish_reason": "content_filter",
            }
        ],
    }

    guardrails_data = build_guardrails_data(
        config_id,
        prior_generation_logs=prior_generation_logs,
        final_generation_log=generation_response.log,
        user_log_options=user_log_options,
    )

    if return_guardrails_data_as_choice:
        blocked_response["choices"].append(
            {
                "index": 1,
                "message": {
                    "role": GUARDRAILS_DATA_MESSAGE_ROLE,
                    "content": json.dumps(
                        guardrails_data.to_dict(mode="json", exclude_none=True),
                        separators=(",", ":"),
                    ),
                },
            }
        )
    else:
        blocked_response[GUARDRAILS_DATA_FIELD] = guardrails_data.to_dict(mode="json", exclude_none=True)

    return blocked_response


def build_output_response_body(
    config_id: str,
    original_response: dict[str, Any],
    generation_response: GenerationResponse | None,
    prior_generation_logs: list[LibraryGenerationLog] | None,
    user_log_options: GenerationLogOptionsParam | None,
    return_guardrails_data_as_choice: bool = False,
) -> dict[str, Any]:
    """
    Build the response body to return when the model's response passes, or skips, the output rails.
    """
    response: dict[str, Any] = dict(original_response)
    if "choices" not in response:
        raise InferenceMiddlewareError(
            "Guardrails response middleware expected upstream response to include a 'choices' field.",
            status_code=500,
        )

    choices = list(response.get("choices", [])) if isinstance(response.get("choices"), list) else []
    response["choices"] = choices
    # Output rails validate choices[0].message, so return only the choice that was checked
    if generation_response is not None and choices:
        response["choices"] = [{**choices[0], "index": 0}]

    guardrails_data = build_guardrails_data(
        config_id,
        prior_generation_logs=prior_generation_logs,
        final_generation_log=generation_response.log if generation_response else None,
        user_log_options=user_log_options,
    )

    if return_guardrails_data_as_choice:
        response["choices"].append(
            {
                "index": len(response["choices"]),
                "message": {
                    "role": GUARDRAILS_DATA_MESSAGE_ROLE,
                    "content": json.dumps(
                        guardrails_data.to_dict(mode="json", exclude_none=True),
                        separators=(",", ":"),
                    ),
                },
            }
        )
    else:
        response[GUARDRAILS_DATA_FIELD] = guardrails_data.to_dict(mode="json", exclude_none=True)

    return response


def build_inference_response(
    *,
    response: InferenceResponse,
    response_body: dict[str, Any],
    return_guardrails_data_as_choice: bool = False,
) -> InferenceResponse:
    """Build the InferenceResponse returned by the process_response handler."""
    result = dict(response_body)
    annotations = dict(response.response_body_annotations)

    # If returning guardrails_data as a choice, remove it from the result and annotations.
    if return_guardrails_data_as_choice:
        annotations.pop(GUARDRAILS_DATA_FIELD, None)
        result.pop(GUARDRAILS_DATA_FIELD, None)
    # If we should include guardrails_data in the result, add it as an annotation. IGW handles
    # merging the annotations into the response before returning to the caller.
    elif GUARDRAILS_DATA_FIELD in result:
        annotations[GUARDRAILS_DATA_FIELD] = result.pop(GUARDRAILS_DATA_FIELD)

    return InferenceResponse(
        result=result,
        headers=response.headers,
        response_body_annotations=annotations,
    )
