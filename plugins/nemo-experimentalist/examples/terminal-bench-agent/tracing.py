# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OpenInference instrumentation with OTLP JSONL file export."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from openinference.instrumentation.langchain import LangChainInstrumentor
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult


class OtlpJsonlExporter(SpanExporter):
    """Append OTLP ExportTraceServiceRequest objects to a JSONL file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("", encoding="utf-8")

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            request = encode_spans(spans)
            document = MessageToDict(request)
            with self._path.open("a", encoding="utf-8") as trace_file:
                trace_file.write(json.dumps(document, separators=(",", ":")) + "\n")
        except (OSError, TypeError, ValueError):
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def setup_tracing(path: Path) -> TracerProvider:
    """Configure LangChain OpenInference spans before constructing the agent."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(OtlpJsonlExporter(path)))
    trace.set_tracer_provider(provider)
    LangChainInstrumentor().instrument(tracer_provider=provider)
    return provider
