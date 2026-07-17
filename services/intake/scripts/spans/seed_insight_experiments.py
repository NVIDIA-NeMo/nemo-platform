#!/usr/bin/env python
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Seed an insight-linked experiment group (two candidate fixes) into Intake.

Creates one ``ExperimentGroup`` wired to a specific Optimizer insight via
``insight_id``, with two experiments — each a candidate fix for the problem in
the insight's description — plus a handful of ATIF sessions (the "associated
traces") and evaluator scores per experiment.

Target insight: the one titled "Slow first token on cold cache" (support-bot),
resolved by title at runtime (its id is regenerated on every reseed). Pass
``--insight-id`` to target a specific insight instead. The kb_retriever runs fully
and synchronously before generation, so a cold cache dominates time-to-first-token.
The two experiments are two different fixes, each undertaken from a *different*
root-cause reading (captured in each experiment's ``description``).

Evaluator scores are illustrative (the request left the exact numbers open): both
fixes improve cold-start TTFT; streaming+router meets the TTFT SLA most often at
a small correctness cost, prefetch keeps correctness highest with a smaller TTFT
win. Tune ``EXPERIMENTS[*].evaluators`` to taste.

Also seeds one in-progress group (a single experiment, no changeset) for each currently-"open"
insight, so every open insight has an associated group + experiment.

Re-running is safe: each group + its experiments are deleted by name first, and ATIF session ids
are deterministic so ClickHouse de-dupes.

Usage::

    uv run services/intake/scripts/spans/seed_insight_experiments.py \\
        --base-url http://127.0.0.1:8080 --workspace default
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_WORKSPACE = "default"
# The insight this group is a fix for. Its server-assigned id changes on every reseed, so we resolve
# it by title at runtime (see _resolve_insight_id). DEFAULT_INSIGHT_ID is only a last-resort fallback
# when the lookup fails; pass --insight-id to override both.
DEFAULT_INSIGHT_TITLE = "Slow first token on cold cache"
DEFAULT_INSIGHT_ID = "insight-WR2UnG6FFi1sz9PiW4oAg3"

GROUP_NAME = "cold-cache-ttft-fixes"
GROUP_DESCRIPTION = (
    "Two candidate fixes for the 'Slow first token on cold cache' insight on the support-bot: "
    "warm the retriever cache vs. stop blocking generation on full retrieval. Each experiment is "
    "undertaken from a different root-cause reading of the same cold-start TTFT problem."
)
GROUP_SUMMARY = (
    "Both fixes cut cold-start time-to-first-token materially. Streaming retrieval with an FAQ "
    "router hits the TTFT SLA most often (~0.95) at a small correctness cost; session-start "
    "prefetch keeps correctness highest (~0.91) with a smaller TTFT win. Recommendation: ship "
    "streaming+router, keep prefetch as a fallback for uncommon queries."
)
DATASET_NAME = "support-faq-latency-bench"
DATASET_VERSION = "v1"
AGENT_NAME = "support-bot"


@dataclass
class ExperimentSpec:
    name: str
    # Human-readable description == the root-cause analysis of why this experiment was undertaken.
    description: str
    root_cause: str
    model_name: str
    n_sessions: int
    # Evaluator name -> mean score in [0, 1]; per-session scores are drawn around this mean.
    evaluators: dict[str, float]
    latency_mean_ms: int
    cost_mean_usd: float = 0.008
    agent_version: str = "2.3.0"
    metadata: dict[str, Any] = field(default_factory=dict)
    # Optional URL for the source experiment (rendered as a "Changeset" badge in Studio).
    source_link: str | None = None


@dataclass
class GroupSpec:
    """One experiment group linked to an insight, with its experiments."""

    # Insight this group is a fix for, resolved by title at runtime (ids regenerate on reseed).
    insight_title: str
    # Last-resort id if the title lookup fails (None -> fall back to DEFAULT_INSIGHT_ID).
    fallback_insight_id: str | None
    name: str
    description: str
    summary: str
    dataset_name: str
    dataset_version: str
    agent_name: str
    experiments: list[ExperimentSpec]


# Two fixes for the cold-cache TTFT problem, each from a distinct root-cause read.
EXPERIMENTS: list[ExperimentSpec] = [
    ExperimentSpec(
        name="session-start-cache-prefetch",
        description=(
            "Root-cause read: first-token latency is dominated by a COLD kb_retriever that lazily "
            "builds/loads its index on first use, so every new session pays the full cold-load cost "
            "before generation can start — the evidence trace showed ~5.2s inside the retriever "
            "before the ~1.6s LLM span even began. Experiment undertaken to test whether removing "
            "the cold-load from the critical path fixes TTFT without touching answer quality. Fix "
            "under test: on session open, kick off an async prefetch that warms the retriever "
            "index/embeddings for the user's likely topic, so the first real query lands on a warm "
            "cache. Generation still waits for retrieval, but retrieval is no longer cold."
        ),
        root_cause="Cold retriever index loaded lazily on first query; no warmup on session start.",
        model_name="openai/gpt-4o-mini",
        n_sessions=12,
        evaluators={"answer_correctness": 0.91, "groundedness": 0.90, "ttft_sla_met": 0.76},
        latency_mean_ms=2600,
        metadata={"fix": "async session-start prefetch/warmup of the kb_retriever cache"},
    ),
    ExperimentSpec(
        name="streaming-retrieval-faq-router",
        description=(
            "Root-cause read: retrieval runs FULLY and SYNCHRONOUSLY before generation begins, and "
            "common FAQs (e.g. 'how do I reset my password?') do not need the heavy retriever at "
            "all — so time-to-first-token is gated by an unnecessary full-corpus fetch even when the "
            "answer is a canned KB article. Experiment undertaken to test whether unblocking the "
            "token stream and adding a fast path for hot intents beats simply warming the cache. Fix "
            "under test: stream top-k chunks into generation as they arrive instead of blocking on "
            "the whole retrieval, and route high-frequency FAQ intents to a small fast router model "
            "that answers directly, bypassing retrieval on the hot path."
        ),
        root_cause="Synchronous full retrieval blocks the token stream; no fast path for common FAQs.",
        model_name="openai/gpt-4o-mini",
        n_sessions=12,
        evaluators={"answer_correctness": 0.88, "groundedness": 0.86, "ttft_sla_met": 0.95},
        latency_mean_ms=1500,
        metadata={
            "fix": "streaming retrieval + small FAQ router model on the hot path",
            "router_model": "openai/gpt-4o-nano",
        },
        # Best performer for the resolved insight (highest TTFT SLA, the ship recommendation),
        # so it carries the source changeset that landed the fix.
        source_link="https://github.com/nvidia/support-bot/pull/482",
    ),
]

# One in-progress candidate fix per currently-"open" insight. These have no changeset yet
# (source_link=None) — the fix hasn't landed — which also exercises the empty-Changeset cell.
RETRY_EXPERIMENTS: list[ExperimentSpec] = [
    ExperimentSpec(
        name="exponential-backoff-jitter",
        description=(
            "Root-cause read: the wiki-agent retries a failed web_search with byte-identical "
            "arguments and no delay, so a transient upstream timeout turns into three back-to-back "
            "failures and a guaranteed give-up. Experiment undertaken to test whether spacing out "
            "retries and mutating the query between attempts recovers the answer instead of burning "
            "the attempt budget. Fix under test: exponential backoff with jitter between attempts, "
            "plus a query-rephrase step so the second and third calls differ from the first."
        ),
        root_cause="Fixed-count retries with identical args, no backoff/jitter, no query mutation.",
        model_name="openai/gpt-4o-mini",
        n_sessions=10,
        evaluators={"task_success": 0.84, "answer_correctness": 0.86, "tool_efficiency": 0.79},
        latency_mean_ms=3200,
        agent_version="1.4.0",
        metadata={"fix": "exponential backoff + jitter + query mutation between retries"},
    ),
]

REASONING_EXPERIMENTS: list[ExperimentSpec] = [
    ExperimentSpec(
        name="strict-output-template-trim",
        description=(
            "Root-cause read: final-answer extraction strips only a fixed preamble and misses "
            "free-form 'let me think / therefore' narration, so chain-of-thought leaks into "
            "user-facing answers whenever the model reasons out loud. Experiment undertaken to test "
            "whether a stricter output contract plus a post-generation trim removes the scaffolding "
            "without hurting correctness. Fix under test: enforce a strict output template and run a "
            "post-generation trim pass that drops reasoning markers before returning output.value."
        ),
        root_cause="Final-answer extraction misses free-form reasoning; no post-generation trim step.",
        model_name="openai/gpt-4o-mini",
        n_sessions=10,
        evaluators={"answer_conciseness": 0.93, "format_compliance": 0.95, "answer_correctness": 0.90},
        latency_mean_ms=1800,
        agent_version="1.4.0",
        metadata={"fix": "strict output template + post-generation trim pass"},
    ),
]

# All groups to seed: the resolved cold-cache group (2 fixes, one with a changeset) plus one
# in-progress group per open insight (1 experiment each).
GROUPS: list[GroupSpec] = [
    GroupSpec(
        insight_title=DEFAULT_INSIGHT_TITLE,
        fallback_insight_id=DEFAULT_INSIGHT_ID,
        name=GROUP_NAME,
        description=GROUP_DESCRIPTION,
        summary=GROUP_SUMMARY,
        dataset_name=DATASET_NAME,
        dataset_version=DATASET_VERSION,
        agent_name=AGENT_NAME,
        experiments=EXPERIMENTS,
    ),
    GroupSpec(
        insight_title="Agent retries failed tool calls without backoff",
        fallback_insight_id=None,
        name="retry-backoff-fix",
        description=(
            "A candidate fix for the 'Agent retries failed tool calls without backoff' insight on "
            "the wiki-agent: replace fixed-count identical retries with exponential backoff, jitter, "
            "and a query rephrase between attempts."
        ),
        summary=(
            "Early results: spacing out retries and rephrasing the query between attempts recovers "
            "answers that previously hit the give-up path, at a modest latency cost. Still "
            "validating on a wider query set before recommending a rollout."
        ),
        dataset_name="wiki-qa-retry-bench",
        dataset_version="v1",
        agent_name="wiki-agent",
        experiments=RETRY_EXPERIMENTS,
    ),
    GroupSpec(
        insight_title="Verbose system reasoning leaks into final answers",
        fallback_insight_id=None,
        name="reasoning-leak-trim",
        description=(
            "A candidate fix for the 'Verbose system reasoning leaks into final answers' insight on "
            "the wiki-agent: enforce a strict output template and add a post-generation trim pass "
            "that strips reasoning scaffolding from the final answer."
        ),
        summary=(
            "Early results: the strict template + trim pass removes 'let me think / therefore' "
            "narration from final answers with no measurable correctness regression. Validating on "
            "longer completions where the leakage was worst."
        ),
        dataset_name="wiki-qa-format-bench",
        dataset_version="v1",
        agent_name="wiki-agent",
        experiments=REASONING_EXPERIMENTS,
    ),
]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument(
        "--insight-id",
        default=None,
        help=f"Target insight id. If omitted, resolved by title ('{DEFAULT_INSIGHT_TITLE}').",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    workspace = args.workspace
    _preflight(base_url)

    base_started_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=6)
    with httpx.Client(timeout=15.0) as client:
        total_groups = 0
        total_experiments = 0
        total_sessions = 0
        for group in GROUPS:
            # --insight-id only overrides the primary (resolved) group; the rest resolve by title.
            override = args.insight_id if group.insight_title == DEFAULT_INSIGHT_TITLE else None
            insight_id = _resolve_insight_id(client, base_url, workspace, group, override)
            _check_insight(client, base_url, workspace, insight_id)
            _cleanup(client, base_url, workspace, group)
            group_id = _create_group(client, base_url, workspace, group, insight_id)
            print(f"[group] {group.name} -> {group_id} (insight_id={insight_id})")

            for spec in group.experiments:
                _create_experiment(client, base_url, workspace, group, spec, group_id)
                print(f"  [experiment] {spec.name}  n_sessions={spec.n_sessions}  evaluators={spec.evaluators}")
                _seed_sessions(client, base_url, workspace, group, spec, base_started_at)
                total_sessions += spec.n_sessions
            total_groups += 1
            total_experiments += len(group.experiments)

        print(
            f"\n=== Done. {total_groups} groups, {total_experiments} experiments, "
            f"{total_sessions} sessions seeded. ==="
        )


def _resolve_insight_id(
    client: httpx.Client, base_url: str, workspace: str, group: GroupSpec, override: str | None
) -> str:
    """Resolve a group's target insight id: honor an override, else look it up by title.

    Insight ids are server-assigned and regenerated on every reseed, so groups must be relinked each
    time. Looking the insight up by its (stable) title keeps a plain re-run correct. Falls back to the
    group's fallback id (then DEFAULT_INSIGHT_ID) only if the lookup fails or finds no match.
    """
    if override:
        return override
    fallback = group.fallback_insight_id or DEFAULT_INSIGHT_ID
    url = f"{base_url}/apis/optimizer/v2/workspaces/{workspace}/insights"
    try:
        resp = client.get(url, params={"page_size": 100})
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: could not list insights to resolve '{group.insight_title}': {exc}")
        print(f"Falling back to id {fallback}.")
        return fallback
    body = resp.json()
    rows = body.get("data", []) if isinstance(body, dict) else body
    for row in rows:
        if row.get("title") == group.insight_title:
            print(f"resolved insight '{group.insight_title}' -> {row.get('id')}")
            return row["id"]
    print(f"WARNING: no insight titled '{group.insight_title}' found; falling back to id {fallback}.")
    return fallback


# ---------------------------------------------------------------------------
# Create / seed
# ---------------------------------------------------------------------------


def _check_insight(client: httpx.Client, base_url: str, workspace: str, insight_id: str) -> None:
    """Warn (don't fail) if the referenced insight is missing — insight_id is a free-form ref."""
    url = f"{base_url}/apis/optimizer/v2/workspaces/{workspace}/insights/{insight_id}"
    try:
        resp = client.get(url)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: could not verify insight {insight_id}: {exc}")
        return
    if resp.status_code == 200:
        print(f"insight OK: '{resp.json().get('title')}'")
    else:
        print(f"WARNING: insight {insight_id} not found ({resp.status_code}); seeding group anyway.")


def _cleanup(client: httpx.Client, base_url: str, workspace: str, group: GroupSpec) -> None:
    """Delete a group's experiments and the group itself by name so re-runs stay clean."""
    for spec in group.experiments:
        _delete(client, base_url, workspace, f"/evaluations/{spec.name}")
    _delete(client, base_url, workspace, f"/experiment-groups/{group.name}")


def _create_group(
    client: httpx.Client, base_url: str, workspace: str, group: GroupSpec, insight_id: str
) -> str:
    body = {
        "name": group.name,
        "description": group.description,
        "insight_id": insight_id,
        "summary": group.summary,
        "metadata": {"seeded_by": "services/intake/scripts/spans/seed_insight_experiments.py"},
    }
    resp = client.post(_intake_url(base_url, workspace, "/experiment-groups"), json=body)
    resp.raise_for_status()
    return resp.json()["id"]


def _create_experiment(
    client: httpx.Client,
    base_url: str,
    workspace: str,
    group: GroupSpec,
    spec: ExperimentSpec,
    group_id: str,
) -> None:
    body = {
        "name": spec.name,
        "experiment_group_id": group_id,
        "dataset_name": group.dataset_name,
        "dataset_version": group.dataset_version,
        "description": spec.description,
        "root_cause": spec.root_cause,
        "metadata": {
            "seeded_by": "services/intake/scripts/spans/seed_insight_experiments.py",
            "model_name": spec.model_name,
            **spec.metadata,
        },
    }
    if spec.source_link:
        body["source_link"] = spec.source_link
    resp = client.post(_intake_url(base_url, workspace, "/evaluations"), json=body)
    resp.raise_for_status()


def _seed_sessions(
    client: httpx.Client,
    base_url: str,
    workspace: str,
    group: GroupSpec,
    spec: ExperimentSpec,
    base_started_at: datetime,
) -> None:
    """Ingest N ATIF sessions (the experiment's traces) + per-evaluator scores."""
    rng = random.Random(f"seed:{spec.name}")
    atif_url = _intake_url(base_url, workspace, "/ingest/atif")
    eval_url = _intake_url(base_url, workspace, "/evaluator-results")

    for i in range(spec.n_sessions):
        cost_usd = max(0.0005, rng.gauss(spec.cost_mean_usd, spec.cost_mean_usd * 0.4))
        latency_ms = max(100, int(rng.gauss(spec.latency_mean_ms, spec.latency_mean_ms * 0.25)))
        prompt_tokens = max(10, int(rng.gauss(700, 150)))
        completion_tokens = max(5, int(rng.gauss(160, 50)))
        test_case_id = f"case-{i:04d}"
        run_id = f"run-{i // 6:02d}"
        offset_seconds = (i / max(1, spec.n_sessions)) * 5.5 * 3600

        atif_body = _atif_body(
            base_started_at=base_started_at,
            experiment_id=spec.name,
            run_id=run_id,
            test_case_id=test_case_id,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            offset_seconds=offset_seconds,
            agent_name=group.agent_name,
            agent_version=spec.agent_version,
            model_name=spec.model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        client.post(atif_url, json=atif_body).raise_for_status()

        session_id = atif_body["session_id"]
        synthetic_span_id = f"{session_id}-root"
        for eval_name, mean in spec.evaluators.items():
            score = _clip(rng.gauss(mean, 0.06))
            client.post(
                eval_url,
                json={
                    "span_id": synthetic_span_id,
                    "session_id": session_id,
                    "name": eval_name,
                    "value": score,
                    "data_type": "NUMERIC",
                },
            ).raise_for_status()


def _atif_body(
    *,
    base_started_at: datetime,
    experiment_id: str,
    run_id: str,
    test_case_id: str,
    cost_usd: float,
    latency_ms: int,
    offset_seconds: float,
    agent_name: str,
    agent_version: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> dict[str, Any]:
    started_at = base_started_at + timedelta(seconds=offset_seconds)
    finished_at = started_at + timedelta(milliseconds=latency_ms)
    session_id = f"{experiment_id}-{run_id}-{test_case_id}"
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": session_id,
        "experiment_context": {"experiment_id": experiment_id, "test_case_id": test_case_id},
        "extra": {
            "task_id": test_case_id,
            "task_name": test_case_id,
            "verifier": {"started_at": _iso(started_at), "finished_at": _iso(finished_at)},
        },
        "agent": {"name": agent_name, "version": agent_version, "model_name": model_name},
        "steps": [
            {
                "step_id": 1,
                "timestamp": _iso(started_at),
                "source": "user",
                "message": f"support query: {test_case_id}",
            },
            {
                "step_id": 2,
                "timestamp": _iso(finished_at),
                "source": "agent",
                "model_name": model_name,
                "message": f"answered {test_case_id}",
                "metrics": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost_usd": cost_usd,
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _delete(client: httpx.Client, base_url: str, workspace: str, suffix: str) -> None:
    resp = client.delete(_intake_url(base_url, workspace, suffix))
    if resp.status_code not in (200, 204, 404):
        resp.raise_for_status()


def _clip(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _preflight(base_url: str) -> None:
    try:
        httpx.get(_replace_path(base_url, "/openapi.json"), timeout=3.0).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Cannot reach NeMo Platform at {base_url}: {exc}") from exc


def _intake_url(base_url: str, workspace: str, suffix: str) -> str:
    return f"{base_url}/apis/intake/v2/workspaces/{workspace}{suffix}"


def _replace_path(base_url: str, path: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
