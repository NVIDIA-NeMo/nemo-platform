#!/usr/bin/env python
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Seed local Intake with error-carrying traces tied to a single experiment.

Built for the Studio team designing error-display surfaces on the span/trace
views. Hybrid path: creates one experiment group + experiment via the entity
store (so the rollup resolves the experiment by name), then sends OTLP traces
tagged with that ``experiment.id`` so they tie to the experiment *and* exercise
the full OTEL error key surface.

Every trace contains at least one error. Four shapes are emitted round-robin so
the layout work can cover each case:

* ``llm_rate_limit``  - root + child both error; full keys
  (``status=error``, ``exception.type``, ``exception.message``, stacktrace event).
* ``tool_timeout``    - root + child both error; a different ``exception.type``.
* ``child_only``      - root **success**, one child span errors. The "hidden
  failure" case: trace ``status=success`` but ``error_count > 0``.
* ``status_only``     - root errors with a status message but **no**
  ``exception.type`` attribute. The degraded case the UI must tolerate.

Error keys this populates, and where they land (see span_attribute_catalog.py):

* ``status``            -> top-level span column / trace root status
* ``exception.type``    -> attributes_string['exception.type']  (error_type)
* ``exception.message`` -> attributes_string['exception.message'] (error_message)
* ``exception.stacktrace`` -> raw bag key + an "exception" event in otel.events
* ``error_count``       -> trace-level countIf(status='error') across all spans

Usage::

    uv run services/intake/scripts/spans/seed_error_traces.py \\
        --base-url http://127.0.0.1:8000

Re-running is safe: the group/experiment are created once (skipped on conflict),
and each run sends a fresh batch of traces under new run ids.
"""

from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind as OtelSpanKind
from opentelemetry.trace import Status, StatusCode

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_WORKSPACE = "default"
DEFAULT_GROUP = "error-display-fixtures"
DEFAULT_EXPERIMENT = "error-trace-fixtures"
DEFAULT_DATASET = "error-fixtures"
DEFAULT_DATASET_VERSION = "v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_PROVIDER = "openai"


# ---------------------------------------------------------------------------
# Error scenarios
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ErrorScenario:
    key: str
    # Whether the root span itself carries an error status.
    root_error: bool
    # Child span kind ("LLM" or "TOOL") and whether it errors.
    child_kind: str
    child_error: bool
    exception_type: str | None
    exception_message: str
    # Emit exception.type/message as span attributes (catalog -> error_type/message).
    # When False, only set_status(message) is used, so exception.type stays absent.
    set_exception_attributes: bool
    # Also record a real exception (populates an "exception" event in otel.events).
    record_event: bool


SCENARIOS: tuple[ErrorScenario, ...] = (
    ErrorScenario(
        key="llm_rate_limit",
        root_error=True,
        child_kind="LLM",
        child_error=True,
        exception_type="RateLimitError",
        exception_message="429 Too Many Requests: token rate limit exceeded for gpt-4o-mini",
        set_exception_attributes=True,
        record_event=True,
    ),
    ErrorScenario(
        key="tool_timeout",
        root_error=True,
        child_kind="TOOL",
        child_error=True,
        exception_type="ToolExecutionTimeout",
        exception_message="tool 'web_search' timed out after 30000ms",
        set_exception_attributes=True,
        record_event=True,
    ),
    ErrorScenario(
        key="child_only",
        root_error=False,
        child_kind="LLM",
        child_error=True,
        exception_type="OutputValidationError",
        exception_message="model returned malformed JSON; failed schema validation",
        set_exception_attributes=True,
        record_event=False,
    ),
    ErrorScenario(
        key="status_only",
        root_error=True,
        child_kind="LLM",
        child_error=False,
        exception_type=None,
        exception_message="upstream returned 503 Service Unavailable",
        set_exception_attributes=False,
        record_event=False,
    ),
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--group", default=DEFAULT_GROUP)
    parser.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    parser.add_argument("--n-traces", type=int, default=24, help="Total traces to emit (round-robin over 4 shapes).")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    _preflight(base_url)

    with httpx.Client(timeout=10.0) as client:
        group_id = _create_group_if_missing(client, base_url, args.workspace, args.group)
        _create_experiment_if_missing(client, base_url, args.workspace, args.experiment, group_id, args.group)
        sessions = _send_error_traces(base_url, args.workspace, args.experiment, args.n_traces)
        _verify(client, base_url, args.workspace, args.experiment, sessions)


# ---------------------------------------------------------------------------
# Entity store: experiment group + experiment
# ---------------------------------------------------------------------------


def _create_group_if_missing(client: httpx.Client, base_url: str, workspace: str, name: str) -> str | None:
    url = _intake_url(base_url, workspace, "/experiment-groups")
    response = client.post(url, json={"name": name, "description": "Error-display fixtures for span/trace UI work."})
    if response.status_code == 409:
        print(f"[skip] group '{name}' already exists")
        existing = client.get(url, params={"page": 1, "page_size": 1000})
        existing.raise_for_status()
        for row in existing.json().get("data", []):
            if row.get("name") == name:
                return row.get("id")
        return None
    response.raise_for_status()
    print(f"[group] created '{name}'")
    return response.json()["id"]


def _create_experiment_if_missing(
    client: httpx.Client,
    base_url: str,
    workspace: str,
    name: str,
    group_id: str | None,
    group_name: str,
) -> None:
    body = {
        "name": name,
        "dataset_name": DEFAULT_DATASET,
        "dataset_version": DEFAULT_DATASET_VERSION,
        "description": "Traces with errors for designing the error-display surfaces.",
        "metadata": {
            "seeded_by": "services/intake/scripts/spans/seed_error_traces.py",
            "model_name": DEFAULT_MODEL,
        },
    }
    if group_id is not None:
        body["experiment_group_id"] = group_id
    response = client.post(_intake_url(base_url, workspace, "/experiments"), json=body)
    # An already-exists conflict surfaces as 409. Only that is a safe skip; anything else
    # (e.g. a 422 schema-validation error) must raise so it can't be silently swallowed —
    # treating 422 as "already exists" once let the experiment never get created at all.
    if response.status_code == 409:
        print(f"[skip] experiment '{name}' already exists")
        return
    response.raise_for_status()
    print(f"[experiment] created '{name}' in group '{group_name}'")


# ---------------------------------------------------------------------------
# OTLP: error traces tied to the experiment
# ---------------------------------------------------------------------------


def _send_error_traces(base_url: str, workspace: str, experiment_id: str, n_traces: int) -> list[str]:
    endpoint = _intake_url(base_url, workspace, "/ingest/otlp/v1/traces")
    provider = TracerProvider(resource=Resource.create({"service.name": "intake-error-fixtures"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    tracer = provider.get_tracer("nmp.intake.spans.error_fixtures")
    rng = random.Random(f"errors:{experiment_id}")

    session_ids: list[str] = []
    for i in range(n_traces):
        scenario = SCENARIOS[i % len(SCENARIOS)]
        run_id = f"run-{i // len(SCENARIOS):02d}"
        test_case_id = f"case-{i:04d}"
        session_id = f"{experiment_id}-{run_id}-{test_case_id}"
        session_ids.append(session_id)
        _emit_trace(tracer, rng, scenario, experiment_id, run_id, test_case_id, session_id)

    provider.force_flush()
    provider.shutdown()
    print(f"[otlp] sent {n_traces} error traces to {endpoint}")
    return session_ids


def _emit_trace(
    tracer: trace.Tracer,
    rng: random.Random,
    scenario: ErrorScenario,
    experiment_id: str,
    run_id: str,
    test_case_id: str,
    session_id: str,
) -> None:
    prompt_tokens = rng.randint(200, 1200)
    completion_tokens = rng.randint(40, 400)
    cost = round((prompt_tokens * 1e-6) + (completion_tokens * 4e-6), 6)

    # Root span carries the experiment tie. Intake's trace_index MV reads the nemo.*-namespaced
    # keys from the span attribute catalog (nemo.experiment.id / nemo.experiment.run_id /
    # nemo.test_case.id), per migration ch_trace_index_0004_nemo_keys. Using the old un-namespaced
    # keys leaves trace_index.experiment_id empty, so traces never link to the experiment.
    with tracer.start_as_current_span("agent-run", kind=OtelSpanKind.SERVER) as root:
        root.set_attribute("openinference.span.kind", "AGENT")
        root.set_attribute("gen_ai.conversation.id", session_id)
        root.set_attribute("nemo.experiment.id", experiment_id)
        root.set_attribute("nemo.experiment.run_id", run_id)
        root.set_attribute("nemo.test_case.id", test_case_id)
        root.set_attribute("project.name", "error-display-fixtures")
        root.set_attribute("gen_ai.agent.name", "fixtures-agent")
        root.set_attribute("input.value", f'{{"task":"{test_case_id}"}}')
        root.set_attribute("output.value", "" if scenario.root_error else '{"result":"ok"}')

        with tracer.start_as_current_span(scenario.child_kind.lower() + "-call") as child:
            child.set_attribute("openinference.span.kind", scenario.child_kind)
            child.set_attribute("gen_ai.conversation.id", session_id)
            if scenario.child_kind == "LLM":
                child.set_attribute("gen_ai.system", DEFAULT_PROVIDER)
                child.set_attribute("gen_ai.request.model", DEFAULT_MODEL)
                child.set_attribute("gen_ai.usage.input_tokens", prompt_tokens)
                child.set_attribute("gen_ai.usage.output_tokens", completion_tokens)
                child.set_attribute("gen_ai.usage.total_tokens", prompt_tokens + completion_tokens)
                child.set_attribute("gen_ai.usage.cost", cost)
                child.set_attribute("input.value", '{"messages":[{"role":"user","content":"..."}]}')
            else:  # TOOL
                child.set_attribute("gen_ai.tool.name", "web_search")
                child.set_attribute("gen_ai.tool.call.arguments", '{"query":"latest status"}')
            if scenario.child_error:
                _apply_error(child, scenario)

        if scenario.root_error:
            _apply_error(root, scenario)


def _apply_error(span: trace.Span, scenario: ErrorScenario) -> None:
    span.set_status(Status(StatusCode.ERROR, scenario.exception_message))
    if scenario.set_exception_attributes and scenario.exception_type is not None:
        span.set_attribute("exception.type", scenario.exception_type)
        span.set_attribute("exception.message", scenario.exception_message)
    if scenario.record_event:
        try:
            raise RuntimeError(scenario.exception_message)
        except RuntimeError as exc:
            span.record_exception(exc)


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def _verify(client: httpx.Client, base_url: str, workspace: str, experiment_id: str, sessions: list[str]) -> None:
    traces_url = _intake_url(base_url, workspace, "/traces")
    # The experiment tie filter was renamed evaluation_id -> experiment_id; try the
    # current name first and fall back so this works against older servers too.
    tie_field = _resolve_tie_field(client, traces_url, experiment_id)
    params = {f"filter[{tie_field}]": experiment_id, "mode": "detailed", "page_size": 1000}
    data: list[dict] = []
    for _ in range(20):
        response = client.get(traces_url, params=params)
        response.raise_for_status()
        data = response.json().get("data", []) or []
        if len(data) >= len(sessions):
            break
        time.sleep(0.5)

    status_errors = sum(1 for t in data if t.get("status") == "error")
    with_error_count = sum(1 for t in data if (t.get("error_count") or 0) > 0)
    print(
        f"[verify] traces tied via filter[{tie_field}]='{experiment_id}': {len(data)} found, "
        f"{status_errors} with status=error, {with_error_count} with error_count>0"
    )
    if data:
        sample = next((t for t in data if (t.get("error_count") or 0) > 0), data[0])
        print(f"[verify] sample trace status={sample.get('status')!r} error_count={sample.get('error_count')}")
        spans_url = _intake_url(base_url, workspace, "/spans")
        spans_resp = client.get(spans_url, params={"filter[session_id]": sample.get("session_id"), "page_size": 50})
        spans_resp.raise_for_status()
        for s in spans_resp.json().get("data", []):
            print(
                f"           span kind={s.get('kind')} status={s.get('status')} "
                f"error_type={_error_type(s)!r} error_message={_error_message(s)!r}"
            )


def _resolve_tie_field(client: httpx.Client, traces_url: str, experiment_id: str) -> str:
    """Return whichever experiment-tie filter the server accepts (newer first)."""
    for field in ("experiment_id", "evaluation_id"):
        probe = client.get(traces_url, params={f"filter[{field}]": experiment_id, "page_size": 1})
        if probe.status_code != 400:
            return field
    return "experiment_id"


def _error_type(span: dict) -> str | None:
    # Newer servers expose exception.* in the attribute bag; older ones promote
    # error_type/error_message to top-level span fields.
    return span.get("error_type") or (span.get("attributes_string", {}) or {}).get("exception.type")


def _error_message(span: dict) -> str | None:
    return span.get("error_message") or (span.get("attributes_string", {}) or {}).get("exception.message")


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
