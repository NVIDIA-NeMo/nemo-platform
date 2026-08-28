# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Minimal OTLP JSONL trace writer — standard library only."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

TRACES_DIR = Path(os.environ.get("TRACE_DIR", "/app/traces"))


def _attrs(values: dict[str, str]) -> list[dict[str, str | dict[str, str]]]:
    return [{"key": key, "value": {"stringValue": value}} for key, value in values.items()]


def write_trace(session_id: str, instruction: str, answer: str, handler: str) -> Path:
    """Write a two-span trace (agent chain and handler) as OTLP JSONL."""
    now = time.time_ns()
    trace_id = f"{now:032x}"[-32:]
    root_span_id, child_span_id = f"{now:016x}"[-16:], f"{now + 1:016x}"[-16:]
    document = {
        "resourceSpans": [
            {
                "resource": {"attributes": _attrs({"service.name": "hello-harbor-agent", "session.id": session_id})},
                "scopeSpans": [
                    {
                        "scope": {"name": "hello-harbor-agent"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": root_span_id,
                                "name": "HelloAgent.solve",
                                "kind": "SPAN_KIND_INTERNAL",
                                "startTimeUnixNano": str(now),
                                "endTimeUnixNano": str(now + 1_000_000),
                                "attributes": _attrs(
                                    {
                                        "openinference.span.kind": "CHAIN",
                                        "input.value": instruction,
                                        "output.value": answer,
                                    }
                                ),
                                "status": {"code": "STATUS_CODE_OK"},
                            },
                            {
                                "traceId": trace_id,
                                "spanId": child_span_id,
                                "parentSpanId": root_span_id,
                                "name": handler,
                                "kind": "SPAN_KIND_INTERNAL",
                                "startTimeUnixNano": str(now),
                                "endTimeUnixNano": str(now + 500_000),
                                "attributes": _attrs(
                                    {
                                        "openinference.span.kind": "TOOL",
                                        "tool.name": handler,
                                        "input.value": instruction,
                                        "output.value": answer,
                                    }
                                ),
                                "status": {"code": "STATUS_CODE_OK"},
                            },
                        ],
                    }
                ],
            }
        ]
    }
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACES_DIR / "agent.jsonl"
    path.write_text(json.dumps(document, separators=(",", ":")) + "\n", encoding="utf-8")
    return path
