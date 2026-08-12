# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from collections.abc import Collection
from enum import Enum

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from pydantic import BaseModel, Field, field_validator

from nemo_evaluator_sdk.enums import ModelFormat
from nemo_evaluator_sdk.inference import InferenceFn, PreprocessRequest, deep_merge
from nemo_evaluator_sdk.values import Model


class StructuredOutputMode(str, Enum):
    OPENAI_RESPONSE_FORMAT = "openai_response_format"
    ROOT_GUIDED_JSON = "root_guided_json"
    NVEXT_GUIDED_JSON = "nvext_guided_json"
    UNSUPPORTED = "unsupported"


class StructuredOutput(BaseModel):
    name: str | None = None
    json_schema: dict = Field(alias="schema")
    strict: bool = False

    @field_validator("json_schema")
    @classmethod
    def validate_json_schema(cls, value: dict):
        validator = validator_for(value)
        validator.check_schema(value)
        return value


class InferenceStructuredOutput(PreprocessRequest):
    """Format structured output request parameters based on provider mode."""

    def __init__(self, mode: StructuredOutputMode, structured_output: dict):
        if not structured_output:
            raise ValueError("structured_output cannot be empty")
        try:
            output = StructuredOutput(**structured_output)
            self._json_schema = output.json_schema
            self._strict = output.strict
            self.mode = mode
            self.inference_param = self._build_inference_param(mode)
        except SchemaError as e:
            raise ValueError("structured output contains invalid JSON schema") from e

    @property
    def json_schema(self) -> dict:
        return self._json_schema

    def set_mode(self, mode: StructuredOutputMode) -> None:
        self.mode = mode
        self.inference_param = self._build_inference_param(mode)

    def _build_inference_param(self, mode: StructuredOutputMode) -> dict:
        if mode == StructuredOutputMode.OPENAI_RESPONSE_FORMAT:
            return {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_output",
                        "schema": self._json_schema,
                        "strict": self._strict,
                    },
                }
            }
        if mode == StructuredOutputMode.ROOT_GUIDED_JSON:
            return {"extra_body": {"guided_json": self._json_schema}}
        if mode == StructuredOutputMode.NVEXT_GUIDED_JSON:
            return {"extra_body": {"nvext": {"guided_json": self._json_schema}}}
        if mode == StructuredOutputMode.UNSUPPORTED:
            return {}
        raise ValueError(f"Unsupported structured output mode: {mode}")

    def _apply_fallback_instruction(self, request: dict) -> dict:
        schema_str = json.dumps(self._json_schema, separators=(",", ":"))
        instruction = f"Return ONLY valid JSON and ensure it matches this JSON schema exactly: {schema_str}"
        if request.get("messages"):
            msg = request["messages"][0]
            if msg.get("role") == "system":
                request["messages"][0]["content"] = f"{instruction} {msg['content']}"
            else:
                request["messages"].insert(0, {"role": "system", "content": instruction})
        elif request.get("prompt"):
            request["prompt"] = f"{instruction} {request['prompt']}"
        return request

    def preprocess(self, request: dict, id: str | None = None) -> dict:
        _ = id  # Required by preprocess hook interface.
        if self.mode == StructuredOutputMode.UNSUPPORTED:
            return self._apply_fallback_instruction(request)
        # Use merge instead of update to avoid overwriting nested dicts
        return deep_merge(request, self.inference_param)


def default_structured_output_mode(format: str) -> StructuredOutputMode:
    if format == ModelFormat.OPEN_AI:
        return StructuredOutputMode.OPENAI_RESPONSE_FORMAT
    if format == ModelFormat.NVIDIA_NIM:
        # Backward-compatible default before preflight detection overrides this.
        return StructuredOutputMode.NVEXT_GUIDED_JSON
    raise ValueError(f"Unsupported structured output format: {format}")


_STRUCTURED_OUTPUT_PARAMS = ("guided_json", "nvext", "extra_body", "response_format")


def _rejected_field_text(lowered_message: str) -> str:
    """Drop the trailing list of accepted fields so only the rejected one is matched."""
    return lowered_message.split("expected one of", 1)[0]


def looks_like_unsupported_structured_output_error(message: str) -> bool:
    """Whether *message* reads as a backend rejecting a structured-output parameter."""
    lowered = message.lower()
    signatures = (
        "is unsupported",
        "is not supported",
        "unexpected keyword argument",
        "extra_forbidden",
        "extra inputs are not permitted",
        "unknown field",
    )
    if not any(sig in lowered for sig in signatures):
        return False
    rejected = _rejected_field_text(lowered)
    return any(param in rejected for param in _STRUCTURED_OUTPUT_PARAMS)


def next_structured_output_mode(
    current: StructuredOutputMode,
    message: str,
    rejected_modes: Collection[StructuredOutputMode],
) -> StructuredOutputMode:
    """Mode to try after *current* was rejected, ending at prompt-level JSON instruction."""
    rejected = _rejected_field_text(message.lower())
    if (
        current == StructuredOutputMode.NVEXT_GUIDED_JSON
        and StructuredOutputMode.ROOT_GUIDED_JSON not in rejected_modes
        and "nvext" in rejected
        and "guided_json" not in rejected
    ):
        return StructuredOutputMode.ROOT_GUIDED_JSON
    return StructuredOutputMode.UNSUPPORTED


def _extract_chat_content(response: dict) -> str | None:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    msg = choices[0].get("message", {})
    content = msg.get("content")
    return content if isinstance(content, str) else None


def _is_probe_valid_json(content: str, probe_schema: dict) -> bool:
    try:
        obj = json.loads(content)
    except (TypeError, ValueError):
        return False
    if not isinstance(obj, dict):
        return False
    try:
        validator = validator_for(probe_schema)
        validator.check_schema(probe_schema)
        validator(probe_schema).validate(obj)
        return True
    except Exception:
        return False


async def detect_structured_output_mode(
    *,
    format: str,
    model: Model,
    inference_fn: InferenceFn,
    api_key: str | None,
    probe_schema: dict,
) -> StructuredOutputMode:
    """Detect working structured output mode for the given model/format."""
    if format == ModelFormat.OPEN_AI:
        return StructuredOutputMode.OPENAI_RESPONSE_FORMAT
    if format != ModelFormat.NVIDIA_NIM:
        return StructuredOutputMode.UNSUPPORTED

    probe_message = "Return ONLY a JSON object that matches the provided schema exactly. No prose or code fences."
    base_request = {
        "messages": [{"role": "user", "content": probe_message}],
        "temperature": 0,
        "max_tokens": 128,
    }
    candidates: list[tuple[StructuredOutputMode, dict]] = [
        (StructuredOutputMode.ROOT_GUIDED_JSON, {"extra_body": {"guided_json": probe_schema}}),
        (StructuredOutputMode.NVEXT_GUIDED_JSON, {"extra_body": {"nvext": {"guided_json": probe_schema}}}),
    ]
    for mode, structured_param in candidates:
        try:
            response = await inference_fn(model, {**base_request, **structured_param}, 1, api_key=api_key)
            content = _extract_chat_content(response)
            if content and _is_probe_valid_json(content, probe_schema):
                return mode
        except Exception as e:
            if looks_like_unsupported_structured_output_error(str(e)):
                continue
            # Probe failures should not abort evaluation startup. If no mode works,
            # caller will fall back to prompt-level strict JSON instruction.
            continue
    return StructuredOutputMode.UNSUPPORTED
