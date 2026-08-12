# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock

import pytest
from nemo_evaluator_sdk.structured_output import (
    InferenceStructuredOutput,
    Model,
    ModelFormat,
    StructuredOutputMode,
    detect_structured_output_mode,
    looks_like_unsupported_structured_output_error,
    next_structured_output_mode,
)
from pydantic import ValidationError


def _test_model() -> Model:
    return Model(url="https://example.com/v1/chat/completions", name="test/model")


def test_inference_structured_output_validation_error():
    with pytest.raises(ValueError, match="structured_output cannot be empty"):
        InferenceStructuredOutput(StructuredOutputMode.NVEXT_GUIDED_JSON, {})

    with pytest.raises(ValueError, match="Unsupported structured output mode"):
        InferenceStructuredOutput("unsupported-format", {"schema": {}})  # ty: ignore[invalid-argument-type]

    with pytest.raises(ValidationError, match="schema\n +Input should be a valid dictionary"):
        structured_output = {"schema": "string"}
        InferenceStructuredOutput(StructuredOutputMode.NVEXT_GUIDED_JSON, structured_output)


def test_inference_structured_output():
    structured_output = {
        "schema": {"type": "object", "properties": {"quality": {"type": "number"}}},
        "strict": True,  # ignored by NIM
    }

    request = {
        "model": "meta/llama-3.2-1b-instruct",
        "messages": [],
    }

    hook = InferenceStructuredOutput(StructuredOutputMode.NVEXT_GUIDED_JSON, structured_output)
    modified_request = hook.preprocess(request)

    assert "extra_body" in modified_request
    assert "nvext" in modified_request["extra_body"]
    assert "guided_json" in modified_request["extra_body"]["nvext"]
    assert modified_request["extra_body"]["nvext"]["guided_json"] == structured_output["schema"]


def test_inference_structured_output_preserves_existing_extra_body():
    structured_output = {
        "schema": {"type": "object", "properties": {"quality": {"type": "number"}}},
        "strict": True,
    }
    request = {
        "model": "meta/llama-3.2-1b-instruct",
        "messages": [],
        "extra_body": {
            "nvext": {
                "max_thinking_tokens": 256,
            }
        },
    }

    hook = InferenceStructuredOutput(StructuredOutputMode.NVEXT_GUIDED_JSON, structured_output)
    modified_request = hook.preprocess(request)

    assert modified_request["extra_body"]["nvext"] == {
        "max_thinking_tokens": 256,
        "guided_json": structured_output["schema"],
    }


def test_inference_structured_output_openai():
    """Test that OpenAI format produces correct response_format structure."""
    structured_output = {
        "schema": {"type": "object", "properties": {"quality": {"type": "number"}}},
        "strict": True,
    }
    request = {
        "model": "openai/model",
        "messages": [{"role": "user", "content": "test"}],
    }

    hook = InferenceStructuredOutput(StructuredOutputMode.OPENAI_RESPONSE_FORMAT, structured_output)
    modified_request = hook.preprocess(request)

    assert "response_format" in modified_request
    response_format = modified_request["response_format"]
    assert response_format["type"] == "json_schema"
    assert "json_schema" in response_format
    assert response_format["json_schema"]["name"] == "structured_output"
    assert response_format["json_schema"]["schema"] == structured_output["schema"]
    assert response_format["json_schema"]["strict"] is True


def test_inference_structured_output_openai_default_strict():
    """Test that OpenAI format uses the strict value from input (defaults to False)."""
    structured_output = {
        "schema": {"type": "object", "properties": {"quality": {"type": "number"}}},
    }

    hook = InferenceStructuredOutput(StructuredOutputMode.OPENAI_RESPONSE_FORMAT, structured_output)

    # StructuredOutput.strict defaults to False when not specified
    response_format = hook.inference_param.get("response_format")
    assert isinstance(response_format, dict)
    json_schema = response_format.get("json_schema")
    assert isinstance(json_schema, dict)
    assert json_schema["strict"] is False


@pytest.mark.asyncio
async def test_detect_structured_output_mode_openai_skips_probe():
    inference_fn = AsyncMock()
    mode = await detect_structured_output_mode(
        format=ModelFormat.OPEN_AI,
        model=_test_model(),
        inference_fn=inference_fn,
        api_key=None,
        probe_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    )
    assert mode == StructuredOutputMode.OPENAI_RESPONSE_FORMAT
    inference_fn.assert_not_called()


@pytest.mark.asyncio
async def test_detect_structured_output_mode_prefers_root_guided_json():
    requests: list[dict] = []

    async def inference_fn(model, request, max_retries, **kwargs):
        requests.append(request)
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    mode = await detect_structured_output_mode(
        format=ModelFormat.NVIDIA_NIM,
        model=_test_model(),
        inference_fn=inference_fn,
        api_key="secret",
        probe_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    )

    assert mode == StructuredOutputMode.ROOT_GUIDED_JSON
    assert len(requests) == 1
    assert requests[0]["extra_body"] == {
        "guided_json": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    }


@pytest.mark.asyncio
async def test_detect_structured_output_mode_falls_back_to_nvext_when_root_invalid():
    requests: list[dict] = []

    async def inference_fn(model, request, max_retries, **kwargs):
        requests.append(request)
        if request.get("extra_body", {}).get("guided_json") is not None:
            # Invalid for schema ("ok" must be boolean)
            return {"choices": [{"message": {"content": '{"ok":"not-bool"}'}}]}
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    mode = await detect_structured_output_mode(
        format=ModelFormat.NVIDIA_NIM,
        model=_test_model(),
        inference_fn=inference_fn,
        api_key=None,
        probe_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    )

    assert mode == StructuredOutputMode.NVEXT_GUIDED_JSON
    assert len(requests) == 2
    assert "guided_json" in requests[0]["extra_body"]
    assert requests[1]["extra_body"] == {
        "nvext": {"guided_json": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}}
    }


@pytest.mark.asyncio
async def test_detect_structured_output_mode_returns_unsupported_on_probe_exceptions():
    async def inference_fn(model, request, max_retries, **kwargs):
        raise RuntimeError("Error code: 500 - {'detail': 'internal server error'}")

    mode = await detect_structured_output_mode(
        format=ModelFormat.NVIDIA_NIM,
        model=_test_model(),
        inference_fn=inference_fn,
        api_key=None,
        probe_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    )

    assert mode == StructuredOutputMode.UNSUPPORTED


@pytest.mark.asyncio
async def test_detect_structured_output_mode_unsupported_signature_then_unsupported():
    async def inference_fn(model, request, max_retries, **kwargs):
        raise RuntimeError("extra_forbidden: extra inputs are not permitted for extra_body.guided_json")

    mode = await detect_structured_output_mode(
        format=ModelFormat.NVIDIA_NIM,
        model=_test_model(),
        inference_fn=inference_fn,
        api_key=None,
        probe_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    )

    assert mode == StructuredOutputMode.UNSUPPORTED


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("extra_forbidden for extra_body.guided_json", True),
        ("extra inputs are not permitted: nvext.guided_json", True),
        ("unexpected keyword argument 'guided_json'", True),
        ("unexpected keyword argument 'nvext'", True),
        ("extra inputs are not permitted", False),
        ("unknown field `guided_json`, expected one of `greed_sampling`, `use_raw_prompt`", True),
        ("unknown field `temperature`", False),
        ("unknown field `top_k`, expected one of `guided_json`, `nvext`, `use_raw_prompt`", False),
        ("unknown field `response_format`", True),
        ("response_format is not supported", True),
        ("Error code: 400 - response_format is not supported by this model", True),
        ("create() got an unexpected keyword argument 'response_format'", True),
        ("create() got an unexpected keyword argument 'extra_body'", True),
        ("guided_json is not supported", True),
        ("create() got an unexpected keyword argument 'temperature'", False),
        ("model nvidia/does-not-exist is not supported", False),
    ],
)
def test_looks_like_unsupported_structured_output_error(message: str, expected: bool):
    assert looks_like_unsupported_structured_output_error(message) is expected


@pytest.mark.parametrize(
    ("current", "message", "rejected_modes", "expected"),
    [
        (
            StructuredOutputMode.NVEXT_GUIDED_JSON,
            "unknown field `nvext`",
            (),
            StructuredOutputMode.ROOT_GUIDED_JSON,
        ),
        (
            StructuredOutputMode.NVEXT_GUIDED_JSON,
            "unknown field `nvext`",
            (StructuredOutputMode.ROOT_GUIDED_JSON,),
            StructuredOutputMode.UNSUPPORTED,
        ),
        (
            StructuredOutputMode.NVEXT_GUIDED_JSON,
            "unknown field `guided_json`",
            (),
            StructuredOutputMode.UNSUPPORTED,
        ),
        (
            StructuredOutputMode.ROOT_GUIDED_JSON,
            "unknown field `guided_json`",
            (),
            StructuredOutputMode.UNSUPPORTED,
        ),
        (
            StructuredOutputMode.OPENAI_RESPONSE_FORMAT,
            "unknown field `response_format`",
            (),
            StructuredOutputMode.UNSUPPORTED,
        ),
    ],
)
def test_next_structured_output_mode(
    current: StructuredOutputMode,
    message: str,
    rejected_modes: tuple[StructuredOutputMode, ...],
    expected: StructuredOutputMode,
):
    assert next_structured_output_mode(current, message, rejected_modes) is expected
