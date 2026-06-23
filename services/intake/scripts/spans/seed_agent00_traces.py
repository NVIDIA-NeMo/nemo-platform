#!/usr/bin/env python
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Seed local Intake with traces whose spans are agent00 like meta-function calls.

Each span's Subject is a made-up meta function (e.g. ``_on_task_setup``,
``_convert_pdfs_to_markdown``, ``_task_file_mutation_allowed``), set via
``gen_ai.tool.name`` -> ``tool_name`` (the top-precedence field in Studio's
``getSpanSubject``). The call/result land on the ``input.value`` /
``output.value`` attributes intake reads first (see ``spans/ingest/otlp.py``):

* ``input.value``  - the small function call with string and dict arguments.
* ``output.value`` - the result: a 10-20 line Python body or a JSON document.

Both are stored as raw strings (no code fences). Each trace pairs two meta
functions (a root span invoking a child span) so the tree has structure.

These traces are standalone (no experiment linkage); they populate the intake
trace/span views for the target workspace.

Usage::

    uv run services/intake/scripts/spans/seed_code_traces.py \\
        --base-url http://127.0.0.1:8080 --workspace agent00

The workspace must already exist. Re-running ingests a fresh batch of traces.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind as OtelSpanKind

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_WORKSPACE = "agent00"


# ---------------------------------------------------------------------------
# Meta-function samples. The span subject is the function name (set via
# gen_ai.tool.name -> tool_name, the top-precedence subject in getSpanSubject).
# input.value is the small call (strings + dicts); output.value is the result,
# either a 10-20 line Python body or a JSON document. All stored as raw strings.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodeSample:
    # The made-up meta function; shown as the span Subject column.
    name: str
    # The small function call (strings + dicts). Goes to input.value.
    call: str
    # The result: a Python function body or a JSON document. Goes to output.value.
    result: str


SAMPLES: tuple[CodeSample, ...] = (
    CodeSample(
        name="_on_task_setup",
        call='_on_task_setup("ingest-quarterly-report", {"workspace": "agent00", "dry_run": False})',
        result='''def _on_task_setup(task_name, context):
    workspace = context.get("workspace", "default")
    dry_run = bool(context.get("dry_run", False))
    run_id = f"{task_name}-{uuid4().hex[:8]}"
    state = {
        "run_id": run_id,
        "workspace": workspace,
        "dry_run": dry_run,
        "started_at": time.time(),
        "steps": [],
    }
    _register_run(state)
    logger.info("task %s set up in %s (dry_run=%s)", task_name, workspace, dry_run)
    return state''',
    ),
    CodeSample(
        name="_convert_pdfs_to_markdown",
        call='_convert_pdfs_to_markdown(["specs/intro.pdf", "specs/api.pdf"], {"ocr": True, "max_pages": 50})',
        result='''{
  "converted": [
    {"source": "specs/intro.pdf", "markdown": "specs/intro.md", "pages": 12, "ocr": true},
    {"source": "specs/api.pdf", "markdown": "specs/api.md", "pages": 34, "ocr": true}
  ],
  "skipped": [],
  "total_pages": 46,
  "duration_ms": 8123,
  "ok": true
}''',
    ),
    CodeSample(
        name="_task_file_mutation_allowed",
        call='_task_file_mutation_allowed("src/server/app.py", {"role": "editor", "protected_paths": ["src/server/secrets.py"]})',
        result='''def _task_file_mutation_allowed(path, policy):
    role = policy.get("role", "viewer")
    protected = set(policy.get("protected_paths", []))
    if role not in ("editor", "admin"):
        return False
    if path in protected:
        return False
    normalized = path.replace("\\\\", "/").lstrip("./")
    if normalized.startswith(".git/") or normalized.endswith(".lock"):
        return False
    if any(normalized.startswith(prefix) for prefix in ("dist/", "build/")):
        return False
    return True''',
    ),
    CodeSample(
        name="_resolve_tool_dependencies",
        call='_resolve_tool_dependencies("web_search", {"available": ["http", "cache"], "strict": True})',
        result='''{
  "tool": "web_search",
  "resolved": ["http", "cache"],
  "missing": [],
  "load_order": ["cache", "http", "web_search"],
  "strict": true,
  "ok": true
}''',
    ),
    CodeSample(
        name="_summarize_subtask_result",
        call='_summarize_subtask_result("extract-tables", {"rows": 128, "errors": 2})',
        result='''def _summarize_subtask_result(subtask, stats):
    rows = stats.get("rows", 0)
    errors = stats.get("errors", 0)
    success_rate = (rows - errors) / rows if rows else 0.0
    status = "ok" if errors == 0 else "degraded"
    summary = {
        "subtask": subtask,
        "rows": rows,
        "errors": errors,
        "success_rate": round(success_rate, 4),
        "status": status,
    }
    _emit_metric(f"subtask.{subtask}.success_rate", success_rate)
    return summary''',
    ),
    CodeSample(
        name="_should_retry_step",
        call='_should_retry_step("upload-artifacts", {"attempt": 2, "max_attempts": 5, "last_error": "timeout"})',
        result='''def _should_retry_step(step, state):
    attempt = state.get("attempt", 1)
    max_attempts = state.get("max_attempts", 3)
    last_error = state.get("last_error", "")
    if attempt >= max_attempts:
        return False
    transient = {"timeout", "rate_limit", "connection_reset"}
    if last_error not in transient:
        return False
    backoff = min(2 ** attempt, 30)
    _schedule_retry(step, delay=backoff)
    return True''',
    ),
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument(
        "--n-traces",
        type=int,
        default=18,
        help="Total traces to emit (round-robin over the code samples).",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    _preflight(base_url)
    _send_code_traces(base_url, args.workspace, args.n_traces)
    _verify(base_url, args.workspace)


# ---------------------------------------------------------------------------
# OTLP: traces with Python in span input/output
# ---------------------------------------------------------------------------


def _send_code_traces(base_url: str, workspace: str, n_traces: int) -> None:
    endpoint = _intake_url(base_url, workspace, "/ingest/otlp/v1/traces")
    provider = TracerProvider(resource=Resource.create({"service.name": "intake-code-fixtures"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    tracer = provider.get_tracer("nmp.intake.spans.code_fixtures")

    for i in range(n_traces):
        # Pair two meta functions per trace so the tree shows a call invoking another.
        root_sample = SAMPLES[i % len(SAMPLES)]
        child_sample = SAMPLES[(i + 1) % len(SAMPLES)]
        session_id = f"00agent-trace-{i:04d}"
        _emit_trace(tracer, root_sample, child_sample, session_id)

    provider.force_flush()
    provider.shutdown()
    print(f"[otlp] sent {n_traces} code traces to {endpoint}")


def _emit_span(span: trace.Span, sample: CodeSample, session_id: str) -> None:
    # TOOL kind + gen_ai.tool.name makes the function name the span Subject; the call is
    # input.value and the result (Python or JSON) is output.value -- raw strings, no fences.
    span.set_attribute("openinference.span.kind", "TOOL")
    span.set_attribute("gen_ai.tool.name", sample.name)
    span.set_attribute("gen_ai.conversation.id", session_id)
    span.set_attribute("project.name", "00agent-code-fixtures")
    span.set_attribute("input.value", sample.call)
    span.set_attribute("output.value", sample.result)


def _emit_trace(
    tracer: trace.Tracer,
    root_sample: CodeSample,
    child_sample: CodeSample,
    session_id: str,
) -> None:
    with tracer.start_as_current_span(root_sample.name, kind=OtelSpanKind.SERVER) as root:
        _emit_span(root, root_sample, session_id)
        with tracer.start_as_current_span(child_sample.name, kind=OtelSpanKind.INTERNAL) as child:
            _emit_span(child, child_sample, session_id)


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def _verify(base_url: str, workspace: str) -> None:
    spans_url = _intake_url(base_url, workspace, "/spans")
    with httpx.Client(timeout=10.0) as client:
        data: list[dict] = []
        for _ in range(20):
            response = client.get(spans_url, params={"page_size": 5})
            response.raise_for_status()
            data = response.json().get("data", []) or []
            if data:
                break
        print(f"[verify] workspace '{workspace}' spans returned: {len(data)} (showing up to 5)")
        for span in data[:5]:
            name = span.get("name")
            input_preview = (_payload(span, "input.value") or "").splitlines()[:1]
            output_lines = (_payload(span, "output.value") or "").count("\n") + 1
            print(f"           span name={name!r} input={input_preview} output_lines={output_lines}")


def _payload(span: dict, key: str) -> str | None:
    # Newer servers may promote input/output to top-level fields; otherwise read the bag.
    promoted = span.get("input" if key == "input.value" else "output")
    if promoted:
        return promoted
    return (span.get("attributes_string", {}) or {}).get(key)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _preflight(base_url: str) -> None:
    try:
        response = httpx.get(_replace_path(base_url, "/openapi.json"), timeout=2.0)
        response.raise_for_status()
    except Exception as exc:
        raise SystemExit(f"Cannot reach NeMo Platform at {base_url}: {exc}") from exc


def _intake_url(base_url: str, workspace: str, suffix: str) -> str:
    return f"{base_url}/apis/intake/v2/workspaces/{workspace}{suffix}"


def _replace_path(base_url: str, path: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


if __name__ == "__main__":
    main()
