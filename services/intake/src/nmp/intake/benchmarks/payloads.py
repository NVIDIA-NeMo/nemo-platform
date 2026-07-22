# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic OTLP payload generation for Intake load tests."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.trace.v1.trace_pb2 import Status

_SERVICE_NAME = "nemo-platform-intake-load-test"
_SCOPE_NAME = "nmp.intake.benchmarks"
_SCOPE_VERSION = "1.0.0"


@dataclass(frozen=True)
class GeneratedPayload:
    """One serialized OTLP request and the identities needed for verification."""

    content: bytes
    session_id: str
    trace_id: str
    span_ids: tuple[str, ...]

    @property
    def span_count(self) -> int:
        return len(self.span_ids)


def build_otlp_payload(
    *,
    run_id: str,
    request_index: int,
    spans_per_request: int,
    now_ns: int | None = None,
) -> GeneratedPayload:
    """Build one valid trace containing ``spans_per_request`` unique spans."""

    if not run_id:
        raise ValueError("run_id must not be empty")
    if request_index < 0:
        raise ValueError("request_index must be non-negative")
    if spans_per_request < 1:
        raise ValueError("spans_per_request must be at least 1")

    trace_id_bytes = _digest_bytes(f"{run_id}:trace:{request_index}", length=16)
    span_id_bytes = tuple(
        _digest_bytes(f"{run_id}:trace:{request_index}:span:{span_index}", length=8)
        for span_index in range(spans_per_request)
    )
    session_id = f"load-testing-{run_id}-{request_index:012d}"
    base_time_ns = now_ns if now_ns is not None else time.time_ns()

    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    _add_attributes(
        resource_spans.resource.attributes,
        {
            "service.name": _SERVICE_NAME,
            "load_test.run_id": run_id,
        },
    )
    scope_spans = resource_spans.scope_spans.add()
    scope_spans.scope.name = _SCOPE_NAME
    scope_spans.scope.version = _SCOPE_VERSION

    root_span_id = span_id_bytes[0]
    for span_index, span_id in enumerate(span_id_bytes):
        span = scope_spans.spans.add()
        span.trace_id = trace_id_bytes
        span.span_id = span_id
        if span_index > 0:
            span.parent_span_id = root_span_id
        span.name = _span_name(span_index)
        span.start_time_unix_nano = base_time_ns + span_index * 1_000_000
        span.end_time_unix_nano = span.start_time_unix_nano + 10_000_000
        span.status.code = Status.STATUS_CODE_OK
        _add_attributes(span.attributes, _span_attributes(span_index=span_index, session_id=session_id))

    return GeneratedPayload(
        content=request.SerializeToString(),
        session_id=session_id,
        trace_id=trace_id_bytes.hex(),
        span_ids=tuple(span_id.hex() for span_id in span_id_bytes),
    )


def _digest_bytes(value: str, *, length: int) -> bytes:
    digest = hashlib.sha256(value.encode("utf-8")).digest()[:length]
    if not any(digest):
        raise RuntimeError("generated an invalid all-zero OTLP identifier")
    return digest


def _span_name(span_index: int) -> str:
    if span_index == 0:
        return "load-test-agent"
    if span_index % 3 == 1:
        return "load-test-llm"
    if span_index % 3 == 2:
        return "load-test-tool"
    return "load-test-guardrail"


def _span_attributes(*, span_index: int, session_id: str) -> dict[str, Any]:
    common: dict[str, Any] = {
        "gen_ai.conversation.id": session_id,
        "load_test.span_index": span_index,
    }
    if span_index == 0:
        return {
            **common,
            "openinference.span.kind": "AGENT",
            "gen_ai.agent.name": "intake-load-test-agent",
            "gen_ai.agent.version": "1.0.0",
            "input.value": json.dumps({"messages": [{"role": "user", "content": "load test"}]}),
            "output.value": json.dumps({"messages": [{"role": "assistant", "content": "ok"}]}),
        }
    if span_index % 3 == 1:
        return {
            **common,
            "openinference.span.kind": "LLM",
            "gen_ai.system": "openai",
            "gen_ai.request.model": "load-test-model",
            "gen_ai.usage.input_tokens": 128 + span_index,
            "gen_ai.usage.output_tokens": 32 + span_index,
            "llm.cost.total": 0.001 + span_index / 1_000_000,
            "input.value": json.dumps({"prompt": "x" * 256}),
            "output.value": json.dumps({"completion": "y" * 128}),
        }
    if span_index % 3 == 2:
        return {
            **common,
            "openinference.span.kind": "TOOL",
            "gen_ai.tool.name": "load_test_tool",
            "input.value": json.dumps({"argument": span_index}),
            "output.value": json.dumps({"result": span_index}),
        }
    return {
        **common,
        "openinference.span.kind": "GUARDRAIL",
        "input.value": json.dumps({"text": "safe"}),
        "output.value": json.dumps({"allowed": True}),
    }


def _add_attributes(attributes: Any, values: dict[str, Any]) -> None:
    for key, value in values.items():
        item = attributes.add()
        item.key = key
        _set_any_value(item.value, value)


def _set_any_value(any_value: Any, value: Any) -> None:
    if isinstance(value, bool):
        any_value.bool_value = value
    elif isinstance(value, int):
        any_value.int_value = value
    elif isinstance(value, float):
        any_value.double_value = value
    elif isinstance(value, list):
        for item in value:
            _set_any_value(any_value.array_value.values.add(), item)
    elif isinstance(value, dict):
        _add_attributes(any_value.kvlist_value.values, value)
    else:
        any_value.string_value = str(value)
