#!/usr/bin/env python
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Seed Optimizer insights together with the Intake traces they are derived from.

Replaces the earlier ad-hoc ``curl`` insight seeding. Each insight now points at
real Intake traces (via ``trace_refs``) so the insight detail page can render the
evidence traces in the same table the Intake section uses.

Flow per run:

1. Emit a handful of OTLP/OpenInference traces per insight into Intake
   (``/apis/intake/v2/workspaces/{ws}/ingest/otlp/v1/traces``). Trace/span ids are
   deterministic (seeded), so re-runs are idempotent — ClickHouse de-dupes spans.
2. Capture each trace's 32-hex trace id from the root span context.
3. Create the Optimizer insights (``/apis/optimizer/v2/workspaces/{ws}/insights``)
   with ``trace_refs`` set to those trace ids. Existing insights whose title
   matches a seed title are deleted first so re-runs stay clean (use ``--keep``
   to skip the cleanup).

Usage::

    uv run services/intake/scripts/spans/seed_optimizer_insights.py \\
        --base-url http://127.0.0.1:8080 --workspace default

The target workspace must already exist. The "new"-status insight requires the
Optimizer plugin's InsightStatus enum to include ``new`` (restart the backend
after updating ``entities.py`` if you see a 422 on status).
"""

from __future__ import annotations

import argparse
import hashlib
import time
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit

import httpx
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.id_generator import IdGenerator
from opentelemetry.trace import Span, Status, StatusCode

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_WORKSPACE = "default"
SERVICE_NAME = "optimizer-insight-seed"
PROJECT = "optimizer-insights"
MS = 1_000_000  # nanoseconds per millisecond


# ---------------------------------------------------------------------------
# Deterministic ids so re-runs are idempotent (ClickHouse de-dupes on span id).
# ---------------------------------------------------------------------------


class DeterministicIdGenerator(IdGenerator):
    """Stable ids from a seed + creation order (see seed_span_type_showcase.py)."""

    def __init__(self, seed: str) -> None:
        self._seed = seed
        self._trace_n = 0
        self._span_n = 0

    def generate_span_id(self) -> int:
        self._span_n += 1
        return self._digest_int(f"span:{self._span_n}", 8)

    def generate_trace_id(self) -> int:
        self._trace_n += 1
        return self._digest_int(f"trace:{self._trace_n}", 16)

    def _digest_int(self, label: str, num_bytes: int) -> int:
        digest = hashlib.sha256(f"{self._seed}:{label}".encode()).digest()
        return int.from_bytes(digest[:num_bytes], "big") or 1


# ---------------------------------------------------------------------------
# Span emission
# ---------------------------------------------------------------------------


class Seeder:
    """Emits spans on a shared clock anchored ~1h in the past."""

    def __init__(self, tracer: trace.Tracer) -> None:
        self._tracer = tracer
        self._base_ns = time.time_ns() - 3_600 * 1_000_000_000

    @contextmanager
    def span(
        self,
        name: str,
        *,
        kind: str,
        session_id: str,
        start_ms: int,
        duration_ms: int,
        attributes: dict[str, Any] | None = None,
        status: str = "success",
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> Iterator[Span]:
        start_ns = self._base_ns + start_ms * MS
        cm = self._tracer.start_as_current_span(
            name, start_time=start_ns, end_on_exit=False, record_exception=False
        )
        with cm as span:
            span.set_attribute("openinference.span.kind", kind)
            span.set_attribute("gen_ai.conversation.id", session_id)
            span.set_attribute("project.name", PROJECT)
            for key, value in (attributes or {}).items():
                span.set_attribute(key, value)
            if error_type is not None:
                span.set_attribute("exception.type", error_type)
            if error_message is not None:
                span.set_attribute("exception.message", error_message)
            if status == "error":
                span.set_status(Status(StatusCode.ERROR, error_message or "error"))
            else:
                span.set_status(Status(StatusCode.OK))
            try:
                yield span
            finally:
                span.end(end_time=start_ns + duration_ms * MS)

    def emit_trace(
        self,
        *,
        session_id: str,
        agent: str,
        prompt: str,
        answer: str,
        duration_ms: int,
        children: list[dict[str, Any]],
    ) -> str:
        """Emit one AGENT-rooted trace with children; return the 32-hex trace id."""
        with self.span(
            f"{agent}-run",
            kind="AGENT",
            session_id=session_id,
            start_ms=0,
            duration_ms=duration_ms,
            attributes={
                "gen_ai.agent.name": agent,
                "input.value": prompt,
                "output.value": answer,
            },
        ) as root:
            trace_id = format(root.get_span_context().trace_id, "032x")
            offset = 40
            for child in children:
                child_duration = int(child["duration_ms"])
                with self.span(
                    child["name"],
                    kind=child["kind"],
                    session_id=session_id,
                    start_ms=offset,
                    duration_ms=child_duration,
                    attributes=child.get("attributes"),
                    status=child.get("status", "success"),
                    error_type=child.get("error_type"),
                    error_message=child.get("error_message"),
                ):
                    pass
                offset += child_duration + 20
        return trace_id


def _llm(
    name: str,
    *,
    duration_ms: int,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "LLM",
        "duration_ms": duration_ms,
        "attributes": {
            "llm.model_name": model,
            "gen_ai.request.model": model,
            "gen_ai.usage.input_tokens": input_tokens,
            "gen_ai.usage.output_tokens": output_tokens,
            "gen_ai.usage.total_tokens": input_tokens + output_tokens,
            "gen_ai.usage.cost": cost,
        },
    }


def _tool(
    name: str,
    *,
    duration_ms: int,
    tool_name: str,
    status: str = "success",
    error_type: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "TOOL",
        "duration_ms": duration_ms,
        "status": status,
        "error_type": error_type,
        "error_message": error_message,
        "attributes": {"tool.name": tool_name, "gen_ai.tool.name": tool_name},
    }


# ---------------------------------------------------------------------------
# Insight scenarios: each produces its evidence traces and the insight body.
# ---------------------------------------------------------------------------


def build_insights(seeder: Seeder) -> list[dict[str, Any]]:
    """Emit traces and return insight bodies with trace_refs wired to them."""

    # 1. Retries without backoff (open) — two traces hammering a failing tool.
    retry_refs = [
        seeder.emit_trace(
            session_id=f"retry-loop-{i}",
            agent="wiki-agent",
            prompt="Who won the 1998 World Cup and where was the final?",
            answer="I was unable to retrieve the result after several attempts.",
            duration_ms=9200,
            children=[
                _llm("plan", duration_ms=700, model="gpt-4o", input_tokens=820, output_tokens=90, cost=0.004),
                _tool("search #1", duration_ms=1500, tool_name="web_search", status="error",
                      error_type="TimeoutError", error_message="upstream timed out"),
                _tool("search #2", duration_ms=1500, tool_name="web_search", status="error",
                      error_type="TimeoutError", error_message="upstream timed out"),
                _tool("search #3", duration_ms=1500, tool_name="web_search", status="error",
                      error_type="TimeoutError", error_message="upstream timed out"),
                _llm("give up", duration_ms=600, model="gpt-4o", input_tokens=1400, output_tokens=40, cost=0.007),
            ],
        )
        for i in (1, 2)
    ]

    # 2. Verbose reasoning leaks into answers (open) — one long LLM span.
    verbose_refs = [
        seeder.emit_trace(
            session_id="verbose-reasoning-1",
            agent="wiki-agent",
            prompt="Explain why the sky is blue in one sentence.",
            answer="Let me think step by step. First, sunlight... Therefore the sky is blue.",
            duration_ms=4200,
            children=[
                _llm("answer", duration_ms=3800, model="gpt-4o", input_tokens=180, output_tokens=520, cost=0.011),
            ],
        )
    ]

    # 3. Slow first token on cold cache (resolved) — slow retriever then LLM.
    cold_cache_refs = [
        seeder.emit_trace(
            session_id="cold-cache-1",
            agent="support-bot",
            prompt="How do I reset my password?",
            answer="Go to Settings > Security > Reset password and follow the emailed link.",
            duration_ms=7300,
            children=[
                _tool("retrieve (cold)", duration_ms=5200, tool_name="kb_retriever"),
                _llm("answer", duration_ms=1600, model="gpt-4o-mini", input_tokens=2400, output_tokens=120, cost=0.002),
            ],
        )
    ]

    # 4. Tool schema drift -> silent argument drop (NEW) — three evidence traces.
    drift_refs = [
        seeder.emit_trace(
            session_id=f"schema-drift-{i}",
            agent="wiki-agent",
            prompt="Book a table for four at 7pm.",
            answer="Your reservation is confirmed.",
            duration_ms=5100,
            children=[
                _llm("plan call", duration_ms=800, model="gpt-4o", input_tokens=640, output_tokens=110, cost=0.005),
                _tool("reserve", duration_ms=900, tool_name="reservations.create"),
                _llm("confirm", duration_ms=700, model="gpt-4o", input_tokens=900, output_tokens=60, cost=0.005),
            ],
        )
        for i in (1, 2, 3)
    ]

    # 5. Unredacted PII forwarded to an external tool (NEW).
    pii_leak_refs = [
        seeder.emit_trace(
            session_id="pii-leak-1",
            agent="support-bot",
            prompt="My email is jane.doe@example.com and my number is 415-555-0132 — where's my receipt?",
            answer="I looked into your account and re-sent the receipt to your email.",
            duration_ms=4300,
            children=[
                _llm("plan", duration_ms=600, model="gpt-4o-mini", input_tokens=560, output_tokens=80, cost=0.002),
                _tool("search", duration_ms=1500, tool_name="web_search"),
                _llm("answer", duration_ms=1600, model="gpt-4o-mini", input_tokens=1900, output_tokens=120, cost=0.002),
            ],
        )
    ]

    # 6. Redundant retriever calls within one turn (NEW).
    redundant_refs = [
        seeder.emit_trace(
            session_id="redundant-retrieval-1",
            agent="support-bot",
            prompt="What are your hours, and what are your hours on holidays?",
            answer="We're open 9-5 on weekdays and closed on public holidays.",
            duration_ms=6100,
            children=[
                _tool("retrieve #1", duration_ms=1800, tool_name="kb_retriever"),
                _tool("retrieve #2", duration_ms=1800, tool_name="kb_retriever"),
                _llm("answer", duration_ms=1300, model="gpt-4o-mini", input_tokens=2200, output_tokens=130, cost=0.002),
            ],
        )
    ]

    # 7. Fabricated source citations (NEW) — two evidence traces.
    fabricated_cite_refs = [
        seeder.emit_trace(
            session_id=f"fabricated-cite-{i}",
            agent="wiki-agent",
            prompt="What year was the Eiffel Tower completed? Include a source link.",
            answer="It was completed in 1889 (source: https://en.wikipedia.org/wiki/Eiffel_Tower_completion_facts).",
            duration_ms=3700,
            children=[
                _tool("search", duration_ms=1200, tool_name="web_search"),
                _llm("answer", duration_ms=1700, model="gpt-4o", input_tokens=1400, output_tokens=150, cost=0.008),
            ],
        )
        for i in (1, 2)
    ]

    return [
        {
            "title": "Agent retries failed tool calls without backoff",
            "agent": "wiki-agent",
            "description": (
                "The wiki-agent re-invokes the same failing web_search call immediately after a "
                "timeout, with identical arguments and no backoff, until it exhausts its attempt "
                "budget and gives up — burning tokens and wall-clock while returning nothing "
                "useful. Examples: (a) asked 'Who won the 1998 World Cup and where was the "
                "final?' the agent fired three back-to-back web_search calls that each returned "
                "TimeoutError ('upstream timed out') within ~1.5s of one another, then produced "
                "'I was unable to retrieve the result after several attempts' instead of trying a "
                "narrower query or an alternate source; (b) the retry payloads are byte-identical "
                "across attempts, so the second and third calls could never have succeeded where "
                "the first failed. A separate session that rephrased the query after the first "
                "failure returned the correct answer, confirming the loop is wasteful rather than "
                "load-driven. Affects: the tool-invocation/retry policy and the web_search error "
                "handler. Hypothesis: retries are wired as a fixed count with no exponential "
                "backoff, no jitter, and no query mutation between attempts, so transient upstream "
                "timeouts turn into 3x cost with a guaranteed give-up."
            ),
            "status": "open",
            "trace_refs": retry_refs,
        },
        {
            "title": "Verbose system reasoning leaks into final answers",
            "agent": "wiki-agent",
            "description": (
                "The wiki-agent frequently emits its internal planning scaffolding into the "
                "user-facing answer instead of the final response only, so short factual "
                "questions come back wrapped in step-by-step narration the reply contract is "
                "supposed to strip. Examples: (a) asked 'Explain why the sky is blue in one "
                "sentence,' the agent replied 'Let me think step by step. First, sunlight... "
                "Therefore the sky is blue.' — a single ~520-token completion where the 'Let me "
                "think step by step / First / Therefore' framing is model reasoning, not answer "
                "content, and directly violates the one-sentence instruction; (b) the leak scales "
                "with output length: the longer the completion, the more scaffolding survives "
                "into output.value, suggesting no post-generation trim step runs. A separate "
                "session on the same prompt with a stricter output template returned just the "
                "final sentence, confirming this is contract enforcement, not model capability. "
                "Affects: reply_to_user text generation and the output formatting/trim pass. "
                "Hypothesis: final-answer extraction strips only a fixed preamble token and misses "
                "free-form 'let me think / therefore' reasoning, so chain-of-thought passes "
                "through whenever the model narrates."
            ),
            "status": "open",
            "trace_refs": verbose_refs,
        },
        {
            "title": "Slow first token on cold cache",
            "agent": "support-bot",
            "description": (
                "When the retrieval cache is cold, the support-bot's first-token latency spikes "
                "because the kb_retriever tool blocks the entire turn before the model starts "
                "generating, so users wait on an empty screen for several seconds on the first "
                "question of a session. Examples: (a) asked 'How do I reset my password?', the "
                "retriever took ~5.2s on a cold cache before the ~1.6s LLM answer even began, so "
                "time-to-first-token was dominated by retrieval rather than generation; the answer "
                "itself ('Go to Settings > Security > Reset password and follow the emailed link') "
                "was correct and cheap once the data was in hand; (b) the same query on a warm "
                "cache returns in a fraction of the time, confirming the spike is cache-state "
                "driven, not query difficulty. Affects: the retrieval path and the turn's "
                "token-streaming start. Hypothesis: retrieval runs synchronously and fully before "
                "generation with no cache warmup, no streaming of partial context, and no smaller "
                "router model for common FAQs, so every cold session pays the full retriever "
                "latency up front."
            ),
            "status": "resolved",
            "trace_refs": cold_cache_refs,
        },
        {
            "title": "Tool schema drift causes silent argument drops",
            "agent": "wiki-agent",
            "description": (
                "A newer version of the reservations.create tool renamed one of its parameters, "
                "but the wiki-agent still sends the old key, so the call returns success while the "
                "renamed argument is silently dropped — producing confident, plausible-looking "
                "confirmations that do not reflect what was actually booked. Examples: (a) asked "
                "'Book a table for four at 7pm,' the agent planned the call, invoked "
                "reservations.create, and replied 'Your reservation is confirmed,' but the "
                "party-size/time argument went under the deprecated key and was ignored by the "
                "tool, so the confirmation asserts a state the backend never recorded; (b) because "
                "the tool returns 200 regardless of the unknown field, there is no error span to "
                "trip the reply-guard — the failure is invisible in status and only detectable by "
                "diffing sent arguments against the current schema. This reproduced across three "
                "separate booking sessions with identical symptoms. Affects: tool argument "
                "construction and the tool-schema binding step. Hypothesis: the agent is pinned to "
                "a stale tool signature and the tool ignores unknown keys instead of rejecting "
                "them, so schema drift degrades correctness with zero error signal."
            ),
            "status": "new",
            "trace_refs": drift_refs,
        },
        {
            "title": "Unredacted PII forwarded to external search tool",
            "agent": "support-bot",
            "description": (
                "The support-bot passes user-provided PII (email address, phone number) straight "
                "into the web_search tool query without redaction, so personal data leaves the trust "
                "boundary and lands in an external service's logs. Examples: (a) a user wrote 'my "
                "email is jane.doe@example.com and my number is 415-555-0132 — where's my receipt?' "
                "and the agent issued a web_search whose query string embedded both the email and "
                "phone verbatim; (b) the pattern repeats whenever a user includes contact details, "
                "because the tool argument is built by concatenating the raw user turn. Affects: the "
                "tool-argument construction step and the web_search boundary. Hypothesis: there is no "
                "PII detection/redaction pass between user input and outbound tool calls, so any "
                "contact detail in the prompt is forwarded as-is."
            ),
            "status": "new",
            "trace_refs": pii_leak_refs,
        },
        {
            "title": "Redundant retriever calls within a single turn",
            "agent": "support-bot",
            "description": (
                "For multi-part questions the support-bot fires the kb_retriever more than once with "
                "near-identical queries in the same turn, doubling retrieval latency and cost for no "
                "new information. Examples: (a) asked 'what are your hours, and what are your hours on "
                "holidays?' the agent ran two back-to-back kb_retriever calls (~1.8s each) that "
                "returned overlapping chunks before a single answer; (b) the second call's query is a "
                "paraphrase of the first, so its results are a strict subset already in context. "
                "Affects: the retrieval planning step and the turn's latency/cost budget. Hypothesis: "
                "each sub-question is planned independently with no dedup of retrieval intents, so "
                "compound questions pay N retrievals where one would do."
            ),
            "status": "new",
            "trace_refs": redundant_refs,
        },
        {
            "title": "Fabricated source links in cited answers",
            "agent": "wiki-agent",
            "description": (
                "When asked to cite a source the wiki-agent sometimes emits a plausible-looking URL "
                "that does not appear in any retrieved chunk and does not resolve, presenting a "
                "confident answer with an invented citation. Examples: (a) asked 'what year was the "
                "Eiffel Tower completed? include a source link' the agent answered '1889 (source: "
                "https://en.wikipedia.org/wiki/Eiffel_Tower_completion_facts)' — a path that 404s and "
                "was never in the search results; (b) the fabricated links follow the shape of real "
                "domains, so they pass a naive format check while pointing nowhere. Affects: answer "
                "synthesis and the citation-grounding step. Hypothesis: citations are generated from "
                "the model's parametric memory rather than constrained to URLs present in retrieved "
                "context, so the grounding check never runs against real sources."
            ),
            "status": "new",
            "trace_refs": fabricated_cite_refs,
        },
    ]


# ---------------------------------------------------------------------------
# Optimizer insight REST helpers
# ---------------------------------------------------------------------------


def _insights_url(base_url: str, workspace: str, suffix: str = "") -> str:
    return f"{base_url}/apis/optimizer/v2/workspaces/{workspace}/insights{suffix}"


def cleanup_existing(client: httpx.Client, base_url: str, workspace: str, titles: set[str]) -> None:
    """Delete existing insights whose title matches a seed title (idempotent re-runs)."""
    page = 1
    deleted = 0
    while True:
        resp = client.get(_insights_url(base_url, workspace), params={"page": page, "page_size": 100})
        resp.raise_for_status()
        body = resp.json()
        rows = body.get("data", [])
        for row in rows:
            if row.get("title") in titles:
                del_resp = client.delete(_insights_url(base_url, workspace, f"/{row['id']}"))
                if del_resp.status_code < 300:
                    deleted += 1
        pagination = body.get("pagination", {})
        if page >= (pagination.get("total_pages") or 1) or not rows:
            break
        page += 1
    print(f"cleanup: deleted {deleted} existing seed insight(s)")


def create_insights(
    client: httpx.Client, base_url: str, workspace: str, insights: list[dict[str, Any]]
) -> None:
    for body in insights:
        resp = client.post(_insights_url(base_url, workspace), json=body)
        if resp.status_code == 422 and body["status"] == "new":
            raise SystemExit(
                f"Backend rejected status 'new' for '{body['title']}'.\n"
                "The Optimizer plugin's InsightStatus enum does not include 'new' yet — "
                "update entities.py and restart the backend, then re-run."
            )
        resp.raise_for_status()
        created = resp.json()
        print(
            f"created insight '{created['title']}' "
            f"(status={created['status']}, trace_refs={len(body['trace_refs'])})"
        )


# ---------------------------------------------------------------------------
# Preflight / verify
# ---------------------------------------------------------------------------


def _replace_path(base_url: str, path: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _preflight(base_url: str, workspace: str) -> None:
    try:
        httpx.get(_replace_path(base_url, "/health/ready"), timeout=3.0).raise_for_status()
    except Exception as exc:
        raise SystemExit(f"Cannot reach NeMo Platform at {base_url}: {exc}") from exc
    probe = httpx.get(
        f"{base_url}/apis/intake/v2/workspaces/{workspace}/traces", params={"page_size": 1}, timeout=5.0
    )
    if probe.status_code == 404:
        raise SystemExit(
            f"Workspace '{workspace}' not found. Create it first, e.g.\n"
            f"  curl -s -X POST {base_url}/apis/entities/v2/workspaces "
            f'-H "content-type: application/json" -d \'{{"name":"{workspace}"}}\''
        )
    probe.raise_for_status()
    opt = httpx.get(_insights_url(base_url, workspace), params={"page_size": 1}, timeout=5.0)
    if opt.status_code == 404:
        raise SystemExit(
            "Optimizer routes not found — is the nemo-optimizer-plugin installed and the "
            "backend restarted? Expected 200 from "
            f"{_insights_url(base_url, workspace)}"
        )
    opt.raise_for_status()


def _verify_traces(base_url: str, workspace: str, expected_trace_ids: set[str]) -> None:
    """Confirm each seeded trace id is queryable in Intake by its detail endpoint.

    Intake exposes the trace identifier as ``id`` (32-hex, == the OTLP trace id we
    captured). Verify by fetching each trace directly rather than scanning the
    (large, paginated) list. Non-fatal: warns but lets insight creation proceed.
    """
    for attempt in range(5):
        missing = {
            trace_id
            for trace_id in expected_trace_ids
            if httpx.get(
                f"{base_url}/apis/intake/v2/workspaces/{workspace}/traces/{trace_id}",
                timeout=10.0,
            ).status_code
            != 200
        }
        if not missing:
            print(f"verified {len(expected_trace_ids)} seeded trace(s) visible in Intake")
            return
        time.sleep(1.0 + attempt)
    print(
        f"WARNING: {len(missing)} seeded trace id(s) not visible in Intake yet "
        f"(ingest lag?): {', '.join(sorted(missing))}. Creating insights anyway."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument(
        "--keep", action="store_true", help="Do not delete existing insights with matching titles."
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    workspace = args.workspace
    otlp_endpoint = f"{base_url}/apis/intake/v2/workspaces/{workspace}/ingest/otlp/v1/traces"

    _preflight(base_url, workspace)

    provider = TracerProvider(
        resource=Resource.create({"service.name": SERVICE_NAME, "project.name": PROJECT}),
        id_generator=DeterministicIdGenerator(seed=f"optimizer-insights:{workspace}"),
    )
    provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
    seeder = Seeder(provider.get_tracer(SERVICE_NAME))

    print(f"=== Seeding optimizer insights + traces into workspace '{workspace}' ===")
    insights = build_insights(seeder)
    provider.force_flush()

    all_refs = {ref for insight in insights for ref in insight["trace_refs"]}
    print(f"emitted {len(all_refs)} trace(s) over OTLP for {len(insights)} insight(s)")
    _verify_traces(base_url, workspace, all_refs)

    with httpx.Client(timeout=10.0) as client:
        if not args.keep:
            cleanup_existing(client, base_url, workspace, {i["title"] for i in insights})
        create_insights(client, base_url, workspace, insights)

    print("done.")


if __name__ == "__main__":
    main()
