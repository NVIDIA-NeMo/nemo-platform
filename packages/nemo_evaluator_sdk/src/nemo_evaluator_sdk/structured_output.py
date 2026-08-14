# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import copy
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from enum import Enum

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from pydantic import BaseModel, Field, field_validator

from nemo_evaluator_sdk.inference import InferenceFn, PreprocessRequest, deep_merge
from nemo_evaluator_sdk.values import Model

_logger = logging.getLogger(__name__)

#: Schema used to probe an endpoint for structured output support. The marker property name is
#: deliberately unguessable: the probe never shows the schema to the model, so a mode only passes
#: when the server actually injected the grammar. Shared by every probing call site so that the
#: judge path and the target-generation path agree on what a probe request looks like.
#:
#: Never pass this object directly into a request-building path; use :func:`_default_probe_schema`.
#: Pydantic copies only the top level when validating, so the nested ``properties`` dict would stay
#: shared with the request payload, and a later mutation of that payload would silently corrupt this
#: constant for every probe in the process.
_DEFAULT_PROBE_SCHEMA: dict = {
    "type": "object",
    "properties": {"__nmp_probe_score": {"type": "integer"}},
    "required": ["__nmp_probe_score"],
    "additionalProperties": False,
}


def _default_probe_schema() -> dict:
    """Return a fresh copy of the endpoint probe schema."""
    return copy.deepcopy(_DEFAULT_PROBE_SCHEMA)


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

    def __init__(self, mode: StructuredOutputMode, structured_output: dict, *, resolved: bool = True):
        """Build the hook.

        Args:
            mode: Structured output encoding to emit.
            structured_output: ``{"schema": ..., "strict": ...}`` payload.
            resolved: Whether ``mode`` reflects what the endpoint actually accepts. Callers that
                pass a provisional default must set this False so that using the hook without
                probing is reported instead of silently emitting a guessed encoding.
        """
        if not structured_output:
            raise ValueError("structured_output cannot be empty")
        try:
            output = StructuredOutput(**structured_output)
            self._json_schema = output.json_schema
            self._strict = output.strict
            self.mode = mode
            self._resolved = resolved
            self._warned_unresolved = False
            self.inference_param = self._build_inference_param(mode)
        except SchemaError as e:
            raise ValueError("structured output contains invalid JSON schema") from e

    @property
    def json_schema(self) -> dict:
        return self._json_schema

    @property
    def resolved(self) -> bool:
        """Whether the mode reflects a real endpoint probe rather than a provisional default."""
        return self._resolved

    def set_mode(self, mode: StructuredOutputMode) -> None:
        """Set the encoding, marking it as reflecting a real endpoint probe."""
        self.mode = mode
        self._resolved = True
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
        if not self._resolved and not self._warned_unresolved:
            # Warn once per hook rather than per row. A generation path that builds this hook and
            # never probes sends a guessed encoding, which an endpoint may silently ignore -- the
            # structured output constraint then disappears with no other signal. Every first-party
            # path probes; this exists so a new or forgotten one is visible instead of silent.
            self._warned_unresolved = True
            _logger.warning(
                "Structured output encoding was never resolved against the endpoint; sending %s as "
                "a guess. Call detect_structured_output_mode() (or "
                "resolve_target_structured_output_mode()) before generating, or the constraint may "
                "be silently dropped.",
                self.mode.value,
            )
        if self.mode == StructuredOutputMode.UNSUPPORTED:
            return self._apply_fallback_instruction(request)
        # Use merge instead of update to avoid overwriting nested dicts
        return deep_merge(request, self.inference_param)


def default_structured_output_mode(format: str | None = None) -> StructuredOutputMode:
    """Return the pre-detection structured output mode.

    ``format`` is accepted for call compatibility and ignored: which structured output mode an
    endpoint accepts is a property of the endpoint, not of the label attached to the model. The
    OpenAI ``response_format`` field is the broadest-support starting point, and
    :func:`detect_structured_output_mode` refines it during preflight.
    """
    _ = format  # Deprecated: retained so existing callers keep working.
    return StructuredOutputMode.OPENAI_RESPONSE_FORMAT


def _looks_like_unsupported_guided_json_error(message: str) -> bool:
    lowered = message.lower()
    signatures = (
        "guided_json is unsupported",
        "unexpected keyword argument 'guided_json'",
        "unexpected keyword argument 'nvext'",
        "extra_forbidden",
        "extra inputs are not permitted",
    )
    if any(sig in lowered for sig in signatures):
        return "guided_json" in lowered or "nvext" in lowered or "extra_body" in lowered
    return False


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


#: Detected mode per endpoint for the duration of one run, so a probe costs one round trip per
#: endpoint instead of one per caller. Paths that build hooks per row (agent evaluation, the
#: ProfBench judge) depend on this: without it they could not probe without a request per row.
#:
#: Run-scoped rather than process-global, which is what makes caching a negative result safe. A
#: probe can fail for reasons unrelated to capability -- a rate limit, a 500, a network blip -- and
#: a process-global negative would silently disable enforcement for that endpoint until restart.
#: Bounded to a run, the same failure costs enforcement for one run and is re-probed by the next.
#:
#: Endpoint capability changing mid-process is rare and is NOT the motivation here.
#:
#: Entries are keyed on (url, name) only, so a session is assumed to be single-principal. The same
#: (url, name) can route to different backends per principal through the inference gateway; a
#: session that mixed credentials would reuse the first principal's result for the second. No
#: first-party path does that today -- one run carries one credential -- and keying on the API key
#: would put a secret in a cache key, so this is recorded as an assumption rather than defended
#: against. Revisit if a run ever fans out across principals.
_MODE_CACHE_VAR: ContextVar[dict[tuple[str, str], StructuredOutputMode] | None] = ContextVar(
    "structured_output_mode_cache", default=None
)
_MODE_CACHE_LOCK_VAR: ContextVar[asyncio.Lock | None] = ContextVar("structured_output_mode_lock", default=None)


@asynccontextmanager
async def structured_output_mode_session() -> AsyncIterator[None]:
    """Scope endpoint structured-output detection to one run.

    Detection results are cached only inside this boundary. Outside one, every call probes, which
    is correct but costs a round trip per caller -- open a session around a run to avoid that.

    Re-entrant: opening a session inside another joins the outer one rather than shadowing it. Entry
    points nest (a backend opens one around metric preparation, then evaluate_metric opens one of
    its own), and a fresh inner cache would re-probe endpoints the outer run already resolved.
    """
    if _MODE_CACHE_VAR.get() is not None:
        yield
        return

    cache_token = _MODE_CACHE_VAR.set({})
    lock_token = _MODE_CACHE_LOCK_VAR.set(asyncio.Lock())
    try:
        yield
    finally:
        _MODE_CACHE_VAR.reset(cache_token)
        _MODE_CACHE_LOCK_VAR.reset(lock_token)


async def detect_structured_output_mode(
    *,
    format: str | None = None,
    model: Model,
    inference_fn: InferenceFn,
    api_key: str | None,
    probe_schema: dict | None = None,
    use_cache: bool = True,
) -> StructuredOutputMode:
    """Detect the structured output mode an endpoint actually honours.

    Every endpoint is probed with the same ordered candidate list regardless of the label on the
    model, because support is a property of the endpoint: ``integrate.api.nvidia.com`` is served
    under the ``nim`` label yet rejects ``nvext.guided_json`` and silently ignores root
    ``guided_json``, while honouring OpenAI ``response_format``. Branching on the label caused that
    endpoint to resolve to UNSUPPORTED and fall back to an unenforced prompt instruction.

    The OpenAI ``response_format`` field is probed first as the broadest-support option, then the
    two legacy ``guided_json`` placements. An endpoint that accepts none of them falls back to a
    prompt-level instruction, which is *not* enforced.

    Results are cached per endpoint for the duration of the enclosing
    :func:`structured_output_mode_session`; outside a session every call probes. Pass
    ``use_cache=False`` to force a fresh probe inside one.

    UNSUPPORTED is cached like any other result, which is only safe because the cache is
    run-scoped: a transient probe failure costs enforcement for this run rather than until the
    process restarts, and a genuinely unsupported endpoint costs three probes per run rather than
    three per row.

    ``format`` is accepted for call compatibility and ignored.
    """
    _ = format  # Deprecated: retained so existing callers keep working.

    cache = _MODE_CACHE_VAR.get() if use_cache else None
    if cache is None:
        return await _probe_structured_output_mode(
            model=model, inference_fn=inference_fn, api_key=api_key, probe_schema=probe_schema
        )

    cache_key = (model.url, model.name)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    lock = _MODE_CACHE_LOCK_VAR.get()
    if lock is None:  # pragma: no cover - a session always sets both vars together
        lock = asyncio.Lock()
    async with lock:
        # Re-check under the lock: concurrent rows would otherwise each probe the same endpoint.
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        mode = await _probe_structured_output_mode(
            model=model, inference_fn=inference_fn, api_key=api_key, probe_schema=probe_schema
        )
        cache[cache_key] = mode
        return mode


async def _probe_structured_output_mode(
    *,
    model: Model,
    inference_fn: InferenceFn,
    api_key: str | None,
    probe_schema: dict | None,
) -> StructuredOutputMode:
    """Probe an endpoint for the structured output encoding it honours, without consulting cache."""
    probe_schema = _default_probe_schema() if probe_schema is None else probe_schema

    # The probe instructs the model to match "the provided schema" without ever showing it. A mode
    # therefore only passes when the server actually injected the grammar; a capable model that is
    # merely following the prompt cannot guess the schema's field names. Do not add the schema to
    # probe_message -- every mode would then report success and enforcement would silently vanish.
    probe_message = "Return ONLY a JSON object that matches the provided schema exactly. No prose or code fences."
    base_request = {
        "messages": [{"role": "user", "content": probe_message}],
        "temperature": 0,
        "max_tokens": 128,
    }
    # Built through InferenceStructuredOutput so each probe sends the exact payload the hook would
    # send in production; a divergence here would detect a mode that then fails during evaluation.
    # A malformed probe_schema must degrade to the prompt-level fallback rather than abort startup.
    # The hook gets its own deep copy: validation copies only the top level of a dict field, so the
    # nested schema would otherwise stay shared with the outgoing request. `probe_schema` must stay
    # unreachable from any request payload, since it is what the response is validated against --
    # and it may be a caller's object, which this function has no business mutating either.
    try:
        probe = InferenceStructuredOutput(StructuredOutputMode.UNSUPPORTED, {"schema": copy.deepcopy(probe_schema)})
    except ValueError:
        return StructuredOutputMode.UNSUPPORTED

    candidates: list[StructuredOutputMode] = [
        StructuredOutputMode.OPENAI_RESPONSE_FORMAT,
        StructuredOutputMode.ROOT_GUIDED_JSON,
        StructuredOutputMode.NVEXT_GUIDED_JSON,
    ]
    for mode in candidates:
        probe.set_mode(mode)
        try:
            response = await inference_fn(model, {**base_request, **probe.inference_param}, 1, api_key=api_key)
            content = _extract_chat_content(response)
            if content and _is_probe_valid_json(content, probe_schema):
                return mode
        except Exception as e:
            if _looks_like_unsupported_guided_json_error(str(e)):
                continue
            # Probe failures should not abort evaluation startup. If no mode works,
            # caller will fall back to prompt-level strict JSON instruction.
            continue
    return StructuredOutputMode.UNSUPPORTED
