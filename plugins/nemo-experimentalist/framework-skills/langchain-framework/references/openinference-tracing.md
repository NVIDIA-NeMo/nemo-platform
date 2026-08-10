<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# OpenInference tracing for LangChain

Wire LangChain spans to a JSONL file using [OpenInference](https://github.com/Arize-ai/openinference) instrumentation on top of an OpenTelemetry SDK tracer provider. OpenInference defines cross-framework semantic conventions for LLM observability (`openinference.span.kind`, `llm.input_messages.*`, `tool.name`, …); the `openinference-instrumentation-langchain` package auto-instruments LangChain to emit those attributes on every LLM, tool, and chain span.

## When to use

- Debugging a multi-step agent: inspect every LLM and tool call after the run.
- Producing structured trace files for downstream tooling.
- Running the agent inside an evaluation harness that collects per-trial traces from disk.

## Install

```bash
uv add openinference-instrumentation-langchain opentelemetry-sdk
```

## Wire it into `main.py`

Set up the tracer **before** constructing any LangChain object (model, tools, agent). Spans created during construction won't be captured otherwise.

```python
from pathlib import Path

from openinference.instrumentation.langchain import LangChainInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)


class _FileSpanExporter(SpanExporter):
    """Append one ReadableSpan.to_json() per line to a JSONL file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("")  # truncate at start of each run

    def export(self, spans) -> SpanExportResult:
        try:
            with self._path.open("a", encoding="utf-8") as f:
                for span in spans:
                    f.write(span.to_json(indent=None) + "\n")
            return SpanExportResult.SUCCESS
        except Exception:
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        return None


def setup_tracing(trace_path: str | Path) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(_FileSpanExporter(trace_path)))
    trace.set_tracer_provider(provider)
    LangChainInstrumentor().instrument(tracer_provider=provider)
    return provider
```

Call it early in `main()` and force a flush before exit. Put the flush/shutdown — and any post-run trace conversion — inside `finally` so they run even when the agent raises (recursion limit, tool errors, etc.):

```python
def main() -> None:
    provider = setup_tracing("traces/run.jsonl")
    try:
        # ... build model / tools / agent and run ...
        ...
    finally:
        provider.force_flush(timeout_millis=5000)
        provider.shutdown()
```

## Why `SimpleSpanProcessor`

`SimpleSpanProcessor` exports each span synchronously when it ends. For a single-shot agent run this is reliable and order-preserving — no risk of losing spans if the process exits before a background batch flushes. `BatchSpanProcessor` is preferable in long-running services where throughput matters; for one-off agent runs it's not worth the failure mode.

## Output format

Each line of the JSONL file is one `ReadableSpan.to_json()`:

```json
{"name": "ChatOpenAI", "context": {"trace_id": "0x...", "span_id": "0x..."}, "kind": "SpanKind.INTERNAL", "parent_id": "0x...", "start_time": "...", "end_time": "...", "status": {"status_code": "OK"}, "attributes": {"openinference.span.kind": "LLM", "llm.model_name": "...", "llm.input_messages.0.message.role": "system", "llm.input_messages.0.message.content": "...", "llm.output_messages.0.message.role": "assistant", "llm.output_messages.0.message.content": "...", "input.value": "...", "output.value": "..."}, "events": [], "links": [], "resource": {...}}
```

OpenInference attributes you'll see most often:

| Attribute | Meaning |
|---|---|
| `openinference.span.kind` | One of `AGENT`, `CHAIN`, `LLM`, `TOOL`, `RETRIEVER`, `EMBEDDING` |
| `input.value`, `output.value` | Serialized inputs/outputs of the span |
| `llm.model_name`, `llm.provider` | Model identification on LLM spans |
| `llm.input_messages.{i}.message.role`, `…content` | Each prompt message, indexed |
| `llm.output_messages.{i}.message.role`, `…content` | Each model output message |
| `llm.token_count.prompt`, `…completion`, `…total` | Token usage on LLM spans |
| `tool.name`, `tool.description` | Tool identification on TOOL spans |

## Privacy controls

OpenInference includes message content by default. To redact, set environment variables before `instrument()` runs:

- `OPENINFERENCE_HIDE_INPUTS=true` — drop `input.value` and `llm.input_messages.*`
- `OPENINFERENCE_HIDE_OUTPUTS=true` — drop `output.value` and `llm.output_messages.*`
- `OPENINFERENCE_HIDE_LLM_INVOCATION_PARAMETERS=true` — drop sampling params

## Common pitfalls

- **Instrumenting after construction**: if `setup_tracing()` runs after `create_agent(...)` or `ChatOpenAI(...)`, spans from those objects aren't captured. Always set up tracing first.
- **Forgetting to flush**: even with `SimpleSpanProcessor`, calling `provider.shutdown()` (or `force_flush()`) before exit ensures any in-flight async work completes. Without it, you may see truncated files when running under `asyncio`.
- **Multiple tracer providers**: do not call `trace.set_tracer_provider()` more than once. If your agent imports a library that also configures tracing, decide which one wins and configure only that.
