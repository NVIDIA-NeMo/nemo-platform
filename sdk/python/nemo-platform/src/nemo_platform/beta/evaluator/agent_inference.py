# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent inference module.

Provides ``make_agent_inference_request`` — the public entrypoint for running
inference against agent endpoints. Routes by ``agent.format`` to format-specific
executors:

- ``generic``: HTTP POST with Jinja-templated body, JSONPath response extraction.
- ``nemo_agent_toolkit``: SSE streaming via ``/generate/full?filter_steps=none``.

Both executors normalise output into an OpenAI-like dict so existing downstream
code (``process_output``, hooks, metrics) works unchanged.
"""

# ruff: noqa: I001 - the vendored SDK mirror uses different import-order settings.

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Awaitable, Mapping
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

import httpx
from httpx import Timeout
from jsonpath_ng import parse as jsonpath_parse
from pydantic import BaseModel, ConfigDict, Field

from nemo_platform.beta.evaluator.agent_stream_translation import (
    NatSSEFrame,
    NatStreamTranslation,
    NatStreamTranslationContext,
    NatStreamTranslator,
)
from nemo_platform.beta.evaluator.enums import AgentFormat
from nemo_platform.beta.evaluator.inference import get_logger, requests_log_var
from nemo_platform.beta.evaluator.resilience.api import run_with_resilience
from nemo_platform.beta.evaluator.resilience.classifier import endpoint_identity
from nemo_platform.beta.evaluator.templates import render_template
from nemo_platform.beta.evaluator.values.agents import Agent, NatAgentConfig
from nemo_platform.beta.evaluator.values.evidence import CandidateEvidence, EvidenceDescriptor

# Default timeout for agent requests (seconds).
_DEFAULT_TIMEOUT = 120.0


class AgentInvocationStatus(str, Enum):
    """Agent invocation outcome before it is adapted into an agent-eval trial."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class AgentInvocationResult(BaseModel):
    """Typed agent response with optional evidence and partial-run status."""

    model_config = ConfigDict(extra="forbid")

    status: AgentInvocationStatus
    response: dict[str, Any]
    output_text: str | None = None
    evidence: CandidateEvidence | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# SSE field names look like ``data``, ``intermediate_data``, ``observability_trace``;
# require the pre-colon token to match before treating a line as a frame, so a bare
# JSON line (e.g. ``{"value": 1}``) is not mis-split at an interior colon.
_NAT_CHANNEL_PATTERN = re.compile(r"^[A-Za-z_][\w-]*$")


class _NatStreamCapture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_lines: list[str] = Field(default_factory=list)
    frames: list[NatSSEFrame] = Field(default_factory=list)
    final_payload: Any | None = None
    # Raw extracted response value (any JSON type); preserved so the OpenAI-like
    # response keeps the original type instead of an unconditional ``str()`` cast.
    final_value: Any | None = None
    output_text: str | None = None
    status_code: int | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


@runtime_checkable
class AgentInferenceFn(Protocol):
    """Callable protocol for agent inference function dependency injection."""

    def __call__(
        self,
        agent: Agent,
        request: dict,
        *,
        client: httpx.AsyncClient | None = None,
        max_retries: int | None,
        api_key: str | None = None,
        default_headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Awaitable[dict | AgentInvocationResult]: ...


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def new_agent_inference_client(timeout: float | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=Timeout(timeout or _DEFAULT_TIMEOUT))


async def make_agent_inference_request(
    agent: Agent,
    request: dict,
    *,
    client: httpx.AsyncClient | None = None,
    max_retries: int | None = 3,
    api_key: str | None = None,
    default_headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> dict:
    """Run inference against an agent endpoint.

    Routes to the appropriate executor based on ``agent.format``:

    - ``generic`` — HTTP POST with templated body and JSONPath extraction.
    - ``nemo_agent_toolkit`` — SSE streaming via ``/generate/full``.

    Returns a normalised OpenAI-like response dict compatible with
    ``process_output()`` and downstream hooks.
    """
    if agent.format == AgentFormat.NEMO_AGENT_TOOLKIT:
        return await _make_nat_agent_request(
            agent,
            request,
            client=client,
            max_retries=max_retries,
            api_key=api_key,
            default_headers=default_headers,
            timeout=timeout,
        )
    else:
        return await _make_generic_agent_request(
            agent,
            request,
            client=client,
            max_retries=max_retries,
            api_key=api_key,
            default_headers=default_headers,
            timeout=timeout,
        )


async def invoke_agent(
    agent: Agent,
    request: dict,
    *,
    client: httpx.AsyncClient | None = None,
    max_retries: int | None = 3,
    api_key: str | None = None,
    default_headers: dict[str, str] | None = None,
    timeout: float | None = None,
    evidence_dir: str | Path | None = None,
    nat_stream_translator: NatStreamTranslator | None = None,
    invocation_context: Mapping[str, Any] | None = None,
) -> AgentInvocationResult:
    """Invoke an agent and preserve structured status and evidence."""
    if agent.format == AgentFormat.NEMO_AGENT_TOOLKIT:
        return await _invoke_nat_agent(
            agent,
            request,
            client=client,
            max_retries=max_retries,
            api_key=api_key,
            default_headers=default_headers,
            timeout=timeout,
            evidence_dir=evidence_dir,
            nat_stream_translator=nat_stream_translator,
            invocation_context=invocation_context,
        )

    response = await _make_generic_agent_request(
        agent,
        request,
        client=client,
        max_retries=max_retries,
        api_key=api_key,
        default_headers=default_headers,
        timeout=timeout,
    )
    return AgentInvocationResult(
        status=AgentInvocationStatus.COMPLETED,
        response=response,
        output_text=_openai_response_text(response),
    )


# ---------------------------------------------------------------------------
# Generic executor
# ---------------------------------------------------------------------------


# TODO: There need to be just one agent inference function, NAT is generic agent with certain fields pre-filled.
async def _make_generic_agent_request(
    agent: Agent,
    request: dict,
    *,
    client: httpx.AsyncClient | None = None,
    max_retries: int | None = 3,
    api_key: str | None = None,
    default_headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> dict:
    """Execute inference against a generic agent endpoint.

    1. Render ``agent.body`` Jinja template with the request context.
    2. POST to ``agent.url``.
    3. Extract response text via ``agent.response_path`` JSONPath.
    4. Optionally extract trajectory via ``agent.trajectory_path``.
    """
    log = get_logger()

    resolved_api_key = api_key or agent.api_key
    effective_timeout = timeout or _DEFAULT_TIMEOUT

    # Build context from the incoming request for template rendering.
    context: dict[str, Any] = {**request, "request": request}

    if agent.body is None:
        raise ValueError("body is required for generic agents")
    if agent.response_path is None:
        raise ValueError("response_path is required for generic agents")

    rendered_body = render_template(agent.body, context=context)
    payload = rendered_body if isinstance(rendered_body, dict) else {"args": rendered_body}

    headers: dict[str, str] = {**(default_headers or {}), "Content-Type": "application/json"}
    if resolved_api_key:
        headers["Authorization"] = f"Bearer {resolved_api_key}"

    endpoint_key = endpoint_identity(agent.url, model_id=agent.name, auth_identity=resolved_api_key)
    max_attempts = max(1, (max_retries if max_retries is not None else 0) + 1)

    log.info("Making generic agent request to %s", agent.url)

    if client:
        inference_client = client
    else:
        inference_client = new_agent_inference_client(timeout=effective_timeout)

    async def _invoke_post() -> dict[str, Any]:
        response = await inference_client.post(agent.url, json=payload, headers=headers, timeout=effective_timeout)
        response.raise_for_status()
        return response.json()

    try:
        result_data: dict[str, Any] = await run_with_resilience(
            endpoint_key,
            _invoke_post,
            max_attempts=max_attempts,
        )
    except Exception:
        log.exception("Generic agent request to %s failed after %d attempts", agent.url, max_attempts)
        raise
    finally:
        if not client:
            # Close instantiated client scoped to function
            await inference_client.aclose()

    # Record request/response for audit
    requests_log = requests_log_var.get([])
    requests_log.append({"request": payload, "response": result_data})

    # Extract response text via JSONPath
    response_text = _extract_jsonpath(result_data, agent.response_path, field_name="response_path")

    # Build normalised response
    normalised: dict[str, Any] = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": str(response_text),
                }
            }
        ]
    }

    # Optionally extract trajectory
    if agent.trajectory_path:
        trajectory = _extract_jsonpath(result_data, agent.trajectory_path, field_name="trajectory_path", required=False)
        if trajectory is not None:
            normalised["trajectory"] = trajectory

    log.info("Generic agent request to %s completed", agent.url)
    return normalised


# ---------------------------------------------------------------------------
# NeMo Agent Toolkit SSE executor
# ---------------------------------------------------------------------------


async def _make_nat_agent_request(
    agent: Agent,
    request: dict,
    *,
    client: httpx.AsyncClient | None = None,
    max_retries: int | None = 3,
    api_key: str | None = None,
    default_headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> dict:
    """Execute inference against a NeMo Agent Toolkit endpoint.

    1. Derive ``input_message`` from the request (``messages`` or ``prompt``).
    2. POST to ``{agent.url}/generate/full?filter_steps=none``.
    3. Stream SSE response, capture last ``value`` field.
    4. Return normalised OpenAI-like dict.
    """
    result = await _invoke_nat_agent(
        agent,
        request,
        client=client,
        max_retries=max_retries,
        api_key=api_key,
        default_headers=default_headers,
        timeout=timeout,
    )
    if result.status is not AgentInvocationStatus.COMPLETED:
        endpoint = _nat_endpoint(agent, agent.nat or NatAgentConfig())
        raise RuntimeError(
            f"NAT agent at {endpoint} completed the SSE stream without producing a final value. "
            "Verify that the agent endpoint is functioning correctly."
        )
    return result.response


async def _invoke_nat_agent(
    agent: Agent,
    request: dict,
    *,
    client: httpx.AsyncClient | None = None,
    max_retries: int | None = 3,
    api_key: str | None = None,
    default_headers: dict[str, str] | None = None,
    timeout: float | None = None,
    evidence_dir: str | Path | None = None,
    nat_stream_translator: NatStreamTranslator | None = None,
    invocation_context: Mapping[str, Any] | None = None,
) -> AgentInvocationResult:
    log = get_logger()
    config = agent.nat or NatAgentConfig()
    resolved_api_key = api_key or agent.api_key
    effective_timeout = timeout or _DEFAULT_TIMEOUT
    endpoint = _nat_endpoint(agent, config)
    payload = request if config.request_mode == "passthrough" else {"input_message": _derive_input_message(request)}

    headers: dict[str, str] = {**(default_headers or {}), "Content-Type": "application/json"}
    if resolved_api_key:
        headers["Authorization"] = f"Bearer {resolved_api_key}"

    endpoint_key = endpoint_identity(endpoint, model_id=agent.name, auth_identity=resolved_api_key)
    max_attempts = max(1, (max_retries if max_retries is not None else 0) + 1)
    inference_client = client or new_agent_inference_client(timeout=effective_timeout)

    async def _invoke_stream() -> _NatStreamCapture:
        capture = _NatStreamCapture()
        try:
            async with inference_client.stream(
                "POST",
                endpoint,
                json=payload,
                headers=headers,
                params=config.query_params,
                timeout=effective_timeout,
            ) as response:
                capture.status_code = response.status_code if isinstance(response.status_code, int) else None
                capture.response_headers = _string_headers(response.headers)
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    capture.raw_lines.append(raw_line)
                    frame = _parse_nat_frame(raw_line)
                    if frame is None:
                        continue
                    capture.frames.append(frame)
                    if frame.channel != "data" or frame.payload == "[DONE]":
                        continue
                    capture.final_payload = frame.payload
                    value = _extract_jsonpath(
                        frame.payload,
                        config.response_path,
                        field_name="nat.response_path",
                        required=False,
                    )
                    if value is not None:
                        capture.final_value = value
                        # Preserve the original type in the response; expose
                        # ``output_text`` only when the value is already textual.
                        capture.output_text = value if isinstance(value, str) else None
                    capture.error = capture.error or _stream_error(frame.payload)
        except Exception as exc:
            if not capture.frames:
                raise
            capture.error = f"{type(exc).__name__}: {exc}"
        return capture

    log.info("Making NAT agent request to %s", endpoint)
    try:
        capture = await run_with_resilience(endpoint_key, _invoke_stream, max_attempts=max_attempts)
    except Exception as exc:
        log.exception("NAT agent request to %s failed after %d attempts", endpoint, max_attempts)
        # When evidence capture or a stream translator is enabled, surface an HTTP
        # failure that occurred before the first stream frame as a PARTIAL result
        # with http_metadata evidence instead of raising, so the trial stays
        # inspectable.
        # The legacy ``_make_nat_agent_request`` path keeps capture disabled, so it
        # still raises (it converts non-COMPLETED results into a RuntimeError).
        http_error = _http_status_error(exc) if config.capture_evidence or nat_stream_translator is not None else None
        if http_error is None:
            raise
        capture = _NatStreamCapture(
            status_code=http_error.response.status_code,
            response_headers=_string_headers(http_error.response.headers),
            error=f"HTTP {http_error.response.status_code}",
        )
    finally:
        if client is None:
            await inference_client.aclose()

    # COMPLETED only when a non-empty value was extracted and no terminal stream
    # error occurred. An extracted-but-empty value (e.g. "") stays PARTIAL.
    has_output = capture.final_value is not None and capture.final_value != ""
    status = AgentInvocationStatus.COMPLETED if has_output and capture.error is None else AgentInvocationStatus.PARTIAL
    response = _openai_response(capture.final_value)
    evidence = (
        _nat_evidence(capture, payload, headers)
        if config.capture_evidence or nat_stream_translator is not None
        else None
    )
    translation_metadata: dict[str, Any] = {}
    if nat_stream_translator is not None and capture.frames:
        values = dict(invocation_context or {})
        context = NatStreamTranslationContext(
            agent_name=agent.name,
            endpoint=endpoint,
            request_payload=payload,
            final_payload=capture.final_payload,
            output_text=capture.output_text,
            run_id=_optional_string(values.get("run_id")),
            task_id=_optional_string(values.get("task_id")),
            invocation_id=_optional_string(values.get("invocation_id")),
            conversation_id=_optional_string(payload.get("conversation_id")),
            http_status=capture.status_code,
            stream_error=capture.error,
        )
        try:
            raw_translation = nat_stream_translator(capture.frames, context=context)
            translation = NatStreamTranslation.model_validate(
                raw_translation.model_dump(mode="python")
                if isinstance(raw_translation, NatStreamTranslation)
                else raw_translation
            )
            schema_version = translation.trajectory.get("schema_version")
            if schema_version != "ATIF-v1.7":
                raise ValueError(
                    f"NAT stream translators must return a canonical ATIF-v1.7 trajectory, got {schema_version}"
                )
            reserved = {
                "trace",
                "raw_stream",
                "stream_events",
                "request_payload",
                "request_headers",
                "http_metadata",
            }
            collisions = reserved.intersection(translation.evidence)
            if collisions:
                raise ValueError(f"translator evidence uses reserved names: {sorted(collisions)}")
            descriptors = dict(evidence.descriptors) if evidence is not None else {}
            descriptors["trace"] = EvidenceDescriptor(
                kind="trace",
                format="atif",
                data=translation.trajectory,
            )
            descriptors.update(translation.evidence)
            evidence = CandidateEvidence(
                descriptors=descriptors,
                metadata=dict(evidence.metadata) if evidence is not None else {},
            )
            translation_metadata = translation.metadata
        except Exception as exc:
            status = AgentInvocationStatus.FAILED
            descriptors = dict(evidence.descriptors) if evidence is not None else {}
            descriptors["translation_error"] = EvidenceDescriptor(
                kind="error",
                format="json",
                data={"error_type": type(exc).__name__, "error": str(exc)},
            )
            evidence = CandidateEvidence(descriptors=descriptors)
            translation_metadata = {
                "translation_error": str(exc),
                "translation_error_type": type(exc).__name__,
            }
    if evidence is not None and evidence_dir is not None:
        evidence = _persist_nat_evidence(evidence, Path(evidence_dir))

    # Record request/response for audit
    requests_log = requests_log_var.get([])
    requests_log.append({"request": payload, "response": capture.final_payload})

    log.info("NAT agent request to %s completed", endpoint)
    return AgentInvocationResult(
        status=status,
        response=response,
        output_text=capture.output_text,
        evidence=evidence,
        metadata={
            "endpoint": endpoint,
            "event_count": len(capture.frames),
            "final_payload": capture.final_payload,
            "http_status": capture.status_code,
            "stream_error": capture.error,
            **translation_metadata,
        },
    )


def _nat_endpoint(agent: Agent, config: NatAgentConfig) -> str:
    if urlparse(config.endpoint).scheme:
        return config.endpoint
    return f"{agent.url.rstrip('/')}/{config.endpoint.lstrip('/')}"


def _parse_nat_frame(raw_line: str) -> NatSSEFrame | None:
    line = raw_line.strip()
    if not line or line.startswith("event:") or ":" not in line:
        return None
    channel, payload_text = line.split(":", 1)
    channel = channel.strip()
    # Only treat the line as a frame when the pre-colon token is a valid SSE
    # field name; otherwise it is a bare payload line (e.g. raw JSON) and is skipped.
    if not _NAT_CHANNEL_PATTERN.match(channel):
        return None
    payload_text = payload_text.strip()
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        payload = payload_text
    return NatSSEFrame(channel=channel, payload=payload, raw=raw_line)


def _http_status_error(exc: BaseException) -> httpx.HTTPStatusError | None:
    """Return the first ``HTTPStatusError`` in the exception's ``__cause__`` chain.

    A non-retryable HTTP error re-raises directly, while a retryable one that
    exhausts attempts is wrapped by the resilience scheduler with the original
    error chained via ``from exc``; walk the chain to find either.
    """
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, httpx.HTTPStatusError):
            return current
        current = current.__cause__
    return None


def _stream_error(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if error is None and isinstance(payload.get("value"), dict):
        error = payload["value"].get("error")
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
        if code and message:
            return f"{code}: {message}"
        return str(message or code or error)
    if error is not None:
        return str(error)
    return None


def _openai_response(content: Any) -> dict[str, Any]:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _openai_response_text(response: dict[str, Any]) -> str | None:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    return content if isinstance(content, str) else None


def _string_headers(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    sensitive = {"authorization", "cookie", "proxy-authorization", "set-cookie", "x-api-key"}
    return {key: "<redacted>" if key.lower() in sensitive else value for key, value in headers.items()}


def _nat_evidence(
    capture: _NatStreamCapture,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> CandidateEvidence:
    raw_stream = "\n".join(capture.raw_lines) + ("\n" if capture.raw_lines else "")
    values: dict[str, tuple[str, str, Any]] = {
        "raw_stream": ("agent_stream", "text", raw_stream),
        "stream_events": (
            "agent_stream_events",
            "json",
            [frame.model_dump(mode="json") for frame in capture.frames],
        ),
        "request_payload": ("request_payload", "json", payload),
        "request_headers": ("request_headers", "json", _redact_headers(headers)),
        "http_metadata": (
            "http_metadata",
            "json",
            {
                "status_code": capture.status_code,
                "headers": _redact_headers(capture.response_headers),
                "error": capture.error,
            },
        ),
    }
    descriptors: dict[str, EvidenceDescriptor] = {}
    for name, (kind, format_name, data) in values.items():
        descriptors[name] = EvidenceDescriptor(kind=kind, format=format_name, data=data)
    return CandidateEvidence(descriptors=descriptors)


def _evidence_filename(
    name: str,
    descriptor: EvidenceDescriptor,
    *,
    reserved_filenames: set[str],
    used_filenames: set[str],
) -> str:
    suffix = "txt" if descriptor.format in {"text", "txt"} else "json"
    canonical_trace = name == "trace" and descriptor.format == "atif"
    if canonical_trace:
        filename = "atif_trace.json"
    else:
        stem = "".join(char if char.isalnum() or char in "-_." else "-" for char in name)
        stem = stem.strip("-_.")[:96] or "evidence"
        filename = f"{stem}.{suffix}"

    filename_key = filename.casefold()
    if not canonical_trace and (filename_key in reserved_filenames or filename_key in used_filenames):
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
        stem = filename.rsplit(".", maxsplit=1)[0][:79]
        filename = f"{stem}-{digest}.{suffix}"
        filename_key = filename.casefold()

    if filename_key in used_filenames:
        raise ValueError(f"evidence descriptors map to the same filename: {filename!r}")
    used_filenames.add(filename_key)
    return filename


def _persist_nat_evidence(evidence: CandidateEvidence, root: Path) -> CandidateEvidence:
    """Replace one SDK-owned invocation directory with file-backed evidence."""
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    canonical_trace = evidence.descriptors.get("trace")
    reserved_filenames = (
        {"atif_trace.json"}
        if canonical_trace is not None and canonical_trace.data is not None and canonical_trace.format == "atif"
        else set()
    )
    used_filenames: set[str] = set()
    persisted: dict[str, EvidenceDescriptor] = {}
    for name, descriptor in evidence.descriptors.items():
        if descriptor.data is None:
            persisted[name] = descriptor
            continue
        filename = _evidence_filename(
            name,
            descriptor,
            reserved_filenames=reserved_filenames,
            used_filenames=used_filenames,
        )
        path = root / filename
        if descriptor.format in {"text", "txt"}:
            path.write_text(str(descriptor.data), encoding="utf-8")
        else:
            path.write_text(
                json.dumps(descriptor.data, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        persisted[name] = descriptor.model_copy(update={"ref": str(path.resolve()), "data": None})
    return evidence.model_copy(update={"descriptors": persisted})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _derive_input_message(request: dict) -> str:
    """Derive a single input_message string from an inference request.

    Handles both chat-style (``messages``) and completion-style (``prompt``)
    requests.
    """
    if "messages" in request:
        messages = request["messages"]
        # Use the last user message content, or concatenate all messages
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return str(msg["content"])
        # Fallback: concatenate all message contents
        return "\n".join(str(msg.get("content", "")) for msg in messages)

    if "prompt" in request:
        return str(request["prompt"])

    raise ValueError("Agent inference request must contain 'messages' or 'prompt'.")


def _extract_jsonpath(
    data: dict[str, Any],
    path: str,
    *,
    field_name: str = "path",
    required: bool = True,
) -> Any:
    """Extract a value from data using a JSONPath expression."""
    expr = jsonpath_parse(path)
    matches = expr.find(data)
    if not matches:
        if required:
            raise ValueError(f"JSONPath '{path}' ({field_name}) did not match any value in agent response: {data}")
        return None
    return matches[-1].value
