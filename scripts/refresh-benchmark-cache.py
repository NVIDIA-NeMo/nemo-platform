#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
refresh-benchmark-cache.py

Pulls current scores from BFCL (tool-calling) and LMSYS Chatbot Arena
Elo (head-to-head human preference), enriches each model entry with
plain-English capability descriptions, and writes a JSON cache the
nemo-model-selection skill reads.

The skill uses this cache to recommend models in plain English first
and benchmark numbers second.

Usage:
    python scripts/refresh-benchmark-cache.py
    python scripts/refresh-benchmark-cache.py --output path/to/cache.json
    python scripts/refresh-benchmark-cache.py --dry-run

Stdlib only. No third-party dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict


class BenchmarkEntry(TypedDict):
    """One row in BENCHMARK_REGISTRY: what a leaderboard measures, in plain English."""
    full_name: str
    url: str
    what_it_measures: str
    what_it_predicts: str
    does_not_predict: str
    scale: str
    primary_signal_for: list[str]


class ModelProfile(TypedDict):
    """One row in NIM_MODEL_PROFILES: a model's architectural strengths and caveats."""
    aliases: list[str]
    architecture_note: str
    strong_at: list[str]
    watch_out_for: list[str]
    best_deployment: str
    primary_benchmarks: list[str]


class BfclScore(TypedDict):
    raw: float
    percent: str  # raw formatted as e.g. "48%" for direct display
    tier: str
    plain: str


class ArenaEloScore(TypedDict):
    """One per-category Elo rating: raw points, tier band, plain-English gloss."""
    raw: int
    tier: str
    plain: str


class ModelScores(TypedDict, total=False):
    """Scores attached to a cached model — each key only present if the upstream matched.

    `arena_elo` is keyed by Arena category (e.g. "overall", "coding",
    "hard_prompts", "instruction_following"). The skill picks the category
    that matches the user's profile question 2 answer.
    """
    bfcl_v4: BfclScore
    arena_elo: dict[str, ArenaEloScore]


class CacheModelEntry(TypedDict):
    """One model entry as it appears in the written cache."""
    nim_model: str
    architecture_note: str
    strong_at: list[str]
    watch_out_for: list[str]
    best_deployment: str
    primary_benchmarks: list[str]
    scores: ModelScores


class CacheSources(TypedDict):
    bfcl: str
    arena_elo: str


class Cache(TypedDict):
    """Top-level shape written to benchmark_cache.json."""
    generated_at: str
    schema_version: str
    sources: CacheSources
    benchmarks: dict[str, BenchmarkEntry]
    models: list[CacheModelEntry]

# ---------------------------------------------------------------------------
# Upstream data sources
# ---------------------------------------------------------------------------

BFCL_CSV_URL = "https://gorilla.cs.berkeley.edu/data_overall.csv"

# LMSYS Chatbot Arena Elo is published daily as a Hugging Face dataset.
# The "text" config / "latest" split holds the most recent leaderboard snapshot,
# broken down across ~22 categories (overall, coding, hard_prompts,
# instruction_following, creative_writing, industry verticals, language-specific,
# etc.). We page through the whole split so the cache can carry per-category Elo
# for each NIM model — that's what lets the skill differentiate models by the
# capability the user actually cares about, not just the headline number.
ARENA_ELO_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=lmarena-ai%2Fleaderboard-dataset&config=text&split=latest"
)
ARENA_ELO_PAGE_SIZE = 100  # HF datasets-server caps page size at 100
ARENA_ELO_MAX_PAGES = 100  # ~360 models × 22 categories ≈ 79 pages today; ceiling for safety
ARENA_ELO_SLEEP_S = 0.5    # baseline polite delay; _fetch_text retries with backoff on 429
HTTP_429_BACKOFF_S = (30.0, 60.0, 120.0)  # backoff schedule per 429 retry

DEFAULT_CACHE_PATH = Path(
    "packages/nemo_platform_ext/src/nemo_platform_ext/skills/"
    "nemo-model-selection/references/benchmark_cache.json"
)

# ---------------------------------------------------------------------------
# Benchmark registry
#
# Each benchmark entry answers three questions a non-expert can reason about:
#   what_it_measures      one sentence, no acronyms, describes the test
#   what_it_predicts      what good or bad scores mean for the user's agent
#   does_not_predict      common misreadings to guard against
#   scale                 how to interpret the raw number
# ---------------------------------------------------------------------------

BENCHMARK_REGISTRY: dict[str, BenchmarkEntry] = {
    "bfcl_v4": {
        "full_name": "Berkeley Function Calling Leaderboard v4",
        "url": "https://gorilla.cs.berkeley.edu/leaderboard.html",
        "what_it_measures": (
            "Whether a model can correctly decide which tool to call, with what "
            "arguments, and when not to call any tool at all — tested across "
            "single calls, parallel calls, multi-step sequences, and situations "
            "where calling a tool would be the wrong answer."
        ),
        "what_it_predicts": (
            "How reliably your agent will invoke tools without hallucinating "
            "function names, fabricating arguments, or calling the wrong tool "
            "when the user's intent is ambiguous. A high score here means fewer "
            "silent failures in production where the agent confidently calls "
            "something that doesn't exist."
        ),
        "does_not_predict": (
            "General reasoning quality or how well the model writes prose. "
            "A model can score poorly here and still be excellent at open-ended "
            "tasks that don't involve structured tool calls."
        ),
        "scale": (
            "Reported as a percentage 0–100%, higher is better. Current "
            "leaderboard top is ~77% (Claude Opus 4.5). This script buckets "
            "scores as top ≥70%, strong ≥55%, mid ≥35%, weak below that — "
            "editorial bands calibrated against the live distribution, not "
            "published by Berkeley."
        ),
        "primary_signal_for": ["tool_calling", "mcp_tools", "api_agents"],
    },
    "swe_bench_verified": {
        "full_name": "SWE-bench Verified",
        "url": "https://www.swebench.com",
        "what_it_measures": (
            "Whether a model can read a real GitHub issue, understand an "
            "existing codebase it has never seen before, write a patch that "
            "fixes the issue, and pass the repo's existing test suite — all "
            "without human guidance."
        ),
        "what_it_predicts": (
            "How well your agent will handle multi-step software tasks: reading "
            "unfamiliar code, making targeted edits, and not breaking things "
            "that were already working. Good signal for agents that interact "
            "with codebases rather than just generating isolated snippets."
        ),
        "does_not_predict": (
            "Performance on short code-generation prompts, or on tasks outside "
            "software engineering. Also does not predict tool-calling accuracy."
        ),
        "scale": "% of issues resolved, higher is better. Top OSS models reach 40–55%.",
        "primary_signal_for": ["code_agents", "software_tasks", "repo_interaction"],
    },
    "arena_elo": {
        "full_name": "LMSYS Chatbot Arena Elo (overall)",
        "url": "https://lmarena.ai",
        "what_it_measures": (
            "How often real users, shown two anonymous model responses side by "
            "side, prefer one model over the other — aggregated across millions "
            "of head-to-head votes covering every topic imaginable."
        ),
        "what_it_predicts": (
            "Whether the model will feel good to interact with in practice: "
            "clear writing, appropriate length, not over-hedging, following "
            "instructions without being obtuse. Good proxy for general-purpose "
            "agents whose output is prose the user will read directly."
        ),
        "does_not_predict": (
            "Structured output quality, tool-calling accuracy, or correctness "
            "on any specific domain. Human preference can favor confident-sounding "
            "wrong answers over correct but uncertain ones."
        ),
        "scale": (
            "Elo points, similar to chess ratings. Current leaderboard top is "
            "~1500. This script buckets ratings as top ≥1450, strong ≥1350, "
            "mid ≥1250, weak below that — editorial bands calibrated against "
            "the live distribution, not published by LMSYS."
        ),
        "primary_signal_for": ["general_purpose", "conversational", "instruction_following"],
    },
    "gpqa_diamond": {
        "full_name": "Graduate-Level Google-Proof Q&A (Diamond set)",
        "url": "https://arxiv.org/abs/2311.12022",
        "what_it_measures": (
            "Whether a model can answer questions that were written by PhD "
            "researchers to be hard enough that other experts in adjacent fields "
            "get them wrong — covering biology, chemistry, and physics. The "
            "'Diamond' subset is the hardest tier."
        ),
        "what_it_predicts": (
            "Deep multi-step reasoning and the ability to synthesize complex "
            "information without shortcuts. Relevant for agents that need to "
            "draw real conclusions from dense technical or scientific content, "
            "not just retrieve and reformat it."
        ),
        "does_not_predict": (
            "Performance on everyday tasks, instruction following, or anything "
            "involving tool use. Overkill as a signal for most business agents."
        ),
        "scale": "% correct, higher is better. Human expert baseline is ~70%; top models reach 75–80%.",
        "primary_signal_for": ["reasoning", "scientific_analysis", "technical_depth"],
    },
    "ruler": {
        "full_name": "RULER (Realistic and Unbiased Long-context Evaluation)",
        "url": "https://arxiv.org/abs/2404.06654",
        "what_it_measures": (
            "Whether a model can actually find and use information buried deep "
            "in a long document — not just claim it supports a large context "
            "window. Tests retrieval, tracking multiple entities, and "
            "aggregating information across a long input."
        ),
        "what_it_predicts": (
            "How much of the model's advertised context window you can actually "
            "rely on. A model claiming 128K context might only reliably use "
            "50–70K. Critical for agents that process long documents, codebases, "
            "or conversation histories."
        ),
        "does_not_predict": (
            "Quality on short inputs. A model can be excellent at short tasks "
            "and lose the thread badly at 60K tokens."
        ),
        "scale": "Score 0–100; also reported as effective context length vs advertised length.",
        "primary_signal_for": ["long_context", "document_analysis", "rag"],
    },
}

# ---------------------------------------------------------------------------
# Model registry
#
# Static knowledge that doesn't come from upstream leaderboards:
# what each model is architecturally good at and what to watch out for.
# Scores are fetched at runtime; these descriptions persist across refreshes.
# ---------------------------------------------------------------------------

NIM_MODEL_PROFILES: dict[str, ModelProfile] = {
    "qwen/qwen3-235b-a22b": {
        "aliases": ["Qwen3-235B", "qwen3-235b"],
        "architecture_note": "235B sparse MoE, ~22B active parameters per forward pass",
        "strong_at": [
            "Calling multiple tools in a single turn without mixing up their arguments",
            "Parallel tool invocation where the order of calls matters",
            "Recovering gracefully when a tool returns an error instead of hallucinating a result",
        ],
        "watch_out_for": [
            "Requires significant VRAM for self-hosted deployment despite low active params",
            "Overkill for agents that only call one or two simple tools",
        ],
        "best_deployment": "cloud_api",
        "primary_benchmarks": ["bfcl_v4"],
    },
    "qwen/qwen3-30b-a3b": {
        "aliases": ["Qwen3-30B-A3B", "qwen3-30b-a3b"],
        "architecture_note": "30B sparse MoE, ~3B active parameters — very fast inference",
        "strong_at": [
            "Tool-calling tasks where speed and cost matter more than perfection",
            "High-throughput agents that run many short tool-calling loops per minute",
            "Good baseline for tool-heavy agents before you know if you need the larger model",
        ],
        "watch_out_for": [
            "Lower ceiling than the 235B for complex nested or parallel tool chains",
            "May struggle with ambiguous tool selection when multiple tools fit the query",
        ],
        "best_deployment": "cloud_api_cost_sensitive",
        "primary_benchmarks": ["bfcl_v4"],
    },
    "qwen/qwen3-coder-30b-a3b-instruct": {
        "aliases": ["Qwen3-Coder-30B", "qwen3-coder"],
        "architecture_note": "30B MoE fine-tuned specifically on software engineering tasks",
        "strong_at": [
            "Navigating unfamiliar codebases and making targeted edits",
            "Writing patches that don't break existing tests",
            "Agents that interact with git, CI, or code review workflows",
        ],
        "watch_out_for": [
            "Not the right choice for non-code tasks — general reasoning suffers from the specialization",
            "Tool-calling accuracy is good but not best-in-class; use qwen3-235b if tools matter more than code",
        ],
        "best_deployment": "cloud_api",
        "primary_benchmarks": ["swe_bench_verified"],
    },
    "nvidia/llama-3.1-nemotron-ultra-253b": {
        "aliases": ["Nemotron-Ultra", "nemotron-ultra-253b"],
        "architecture_note": "253B dense model, NVIDIA post-trained on Llama 3.1 for reasoning",
        "strong_at": [
            "Multi-step reasoning over long documents without losing the thread",
            "Technical and scientific analysis where intermediate reasoning steps matter",
            "Agents that need to synthesize information from many retrieved chunks",
        ],
        "watch_out_for": [
            "Very large model — cloud API is the practical deployment path for most teams",
            "Slower inference than MoE alternatives; not ideal for latency-sensitive loops",
        ],
        "best_deployment": "cloud_api",
        "primary_benchmarks": ["gpqa_diamond", "ruler"],
    },
    "nvidia/llama-3.3-nemotron-super-49b-v1": {
        "aliases": [
            "Nemotron-Super-49B",
            "nemotron-super-49b",
            "nvidia-llama-3-3-nemotron-super-49b-v1",
        ],
        "architecture_note": "49B dense model, NVIDIA post-trained on Llama 3.3; platform default for cloud agents",
        "strong_at": [
            "General-purpose agent work where you don't yet know the bottleneck",
            "Reasonable tool-calling accuracy plus solid prose — a balanced starting point",
            "The platform's curated default; well-tested across the agent build path",
        ],
        "watch_out_for": [
            "Not specialized — a tool-calling specialist will beat it on heavy tool chains",
            "Not the fastest — a smaller MoE wins on cost and latency for simple loops",
        ],
        "best_deployment": "cloud_api",
        "primary_benchmarks": ["arena_elo"],
    },
    "meta/llama-3.3-70b-instruct": {
        "aliases": ["Llama-3.3-70B", "llama-3.3-70b"],
        "architecture_note": "70B dense model, widely deployed and well-understood",
        "strong_at": [
            "General-purpose instruction following across a wide range of tasks",
            "Stable, predictable outputs — well-characterized by the community",
            "Good starting point for any agent before you know its bottlenecks",
        ],
        "watch_out_for": [
            "Not a specialist in any one area — if tool-calling or code quality is critical, use a specialist",
            "Human preference scores well but that doesn't translate directly to agentic reliability",
        ],
        "best_deployment": "cloud_api_or_self_hosted",
        "primary_benchmarks": ["arena_elo"],
    },
    "microsoft/phi-4-mini-instruct": {
        "aliases": ["Phi-4-Mini", "phi-4-mini"],
        "architecture_note": "Small dense model (~4B), optimized for quality-per-parameter",
        "strong_at": [
            "Fast, cheap inference for agents where latency is the bottleneck",
            "Single-tool or low-complexity tool-calling loops",
            "Edge or resource-constrained deployments",
        ],
        "watch_out_for": [
            "Ceiling is lower than larger models for complex multi-tool orchestration",
            "May miss subtle nuance in tool argument generation under ambiguous prompts",
        ],
        "best_deployment": "self_hosted_low_vram",
        "primary_benchmarks": ["arena_elo"],
    },
    "qwen/qwen3-8b": {
        "aliases": ["Qwen3-8B", "qwen3-8b"],
        "architecture_note": "8B dense model with strong BFCL performance for its size class",
        "strong_at": [
            "Tool-calling on a single consumer GPU (fits in 12–16 GB VRAM)",
            "Local development and prototyping before scaling to a larger model",
            "Agents where self-hosting is non-negotiable and tools are the primary task",
        ],
        "watch_out_for": [
            "Not competitive with larger models on complex reasoning chains",
            "Context window reliability drops faster than in larger models",
        ],
        "best_deployment": "self_hosted_local_gpu",
        "primary_benchmarks": ["bfcl_v4"],
    },
}

# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def _fetch_text(url: str, timeout: int = 15) -> str:
    """Fetch a URL with retry-on-429 backoff.

    HF's free-tier datasets-server enforces a per-IP rate limit that's stricter
    than its docs claim. When it returns 429, sleep for the next backoff
    interval and retry — up to len(HTTP_429_BACKOFF_S) attempts. Other HTTP
    errors propagate immediately.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": "nemo-platform-benchmark-refresh/1.0"}
    )
    last_exc: Exception | None = None
    for attempt in range(len(HTTP_429_BACKOFF_S) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt >= len(HTTP_429_BACKOFF_S):
                raise
            backoff = HTTP_429_BACKOFF_S[attempt]
            print(f"\n    429 from upstream — backing off {backoff:.0f}s...", flush=True)
            time.sleep(backoff)
            last_exc = exc
    # Unreachable in practice (the loop either returns or raises) but satisfies type checkers
    raise last_exc if last_exc else RuntimeError("fetch retry loop exited unexpectedly")


def fetch_bfcl_scores() -> dict[str, float]:
    """Pull the live BFCL `data_overall.csv` from gorilla.cs.berkeley.edu.

    Schema (as of 2026): columns include `Model` and `Overall Acc`; values are
    percent-formatted strings like `77.47%`. Normalize to 0–1 floats. Model
    names carry suffixes like ` (FC)` for the function-calling variant; strip
    those so substring matching against NIM aliases works.
    """
    print("  Fetching BFCL overall scores...", end=" ", flush=True)
    try:
        raw = _fetch_text(BFCL_CSV_URL)
    except Exception as exc:
        print(f"FAILED ({exc})")
        return {}

    scores: dict[str, float] = {}
    lines = raw.strip().splitlines()
    header = [h.strip().lower() for h in lines[0].split(",")]
    try:
        model_idx = header.index("model")
        score_idx = header.index("overall acc")
    except ValueError:
        print("FAILED (unexpected CSV header)")
        return {}

    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) <= max(model_idx, score_idx):
            continue
        model = parts[model_idx].strip().strip('"')
        # Strip " (FC)", " (Prompt)" and similar variant tags
        for tag in (" (FC)", " (Prompt)", " (Function Calling)"):
            if model.endswith(tag):
                model = model[: -len(tag)].rstrip()
        raw_score = parts[score_idx].strip().rstrip("%")
        try:
            score = float(raw_score) / 100.0
        except ValueError:
            continue
        scores[model] = score

    print(f"OK ({len(scores)} entries)")
    return scores


def fetch_arena_elo_scores() -> dict[str, dict[str, float]]:
    """Pull current Arena Elo ratings, broken down by category, from the LMSYS dataset.

    The dataset is updated daily and served as JSON via the HF datasets-server
    `/rows` endpoint — stdlib-friendly, no parquet decoding. We page through
    the full `latest` split (~360 models × ~22 categories), with a short sleep
    between requests to stay under HF's rate limit. Returns a nested dict:
    `{model_name: {category: rating}}`.
    """
    print("  Fetching Arena Elo scores (per-category)...", end=" ", flush=True)

    by_model: dict[str, dict[str, float]] = {}
    publish_date: str = ""
    categories_seen: set[str] = set()

    for page in range(ARENA_ELO_MAX_PAGES):
        if page > 0:
            time.sleep(ARENA_ELO_SLEEP_S)

        offset = page * ARENA_ELO_PAGE_SIZE
        url = f"{ARENA_ELO_ROWS_URL}&offset={offset}&length={ARENA_ELO_PAGE_SIZE}"
        try:
            raw = _fetch_text(url, timeout=20)
            payload = json.loads(raw)
        except Exception as exc:
            print(f"PARTIAL — failed page {page} ({exc})")
            break  # keep what we already collected

        rows = payload.get("rows", [])
        if not rows:
            break

        for entry in rows:
            row = entry.get("row", {})
            model = row.get("model_name")
            category = row.get("category")
            rating = row.get("rating")
            if not (isinstance(model, str) and isinstance(category, str)
                    and isinstance(rating, (int, float))):
                continue
            by_model.setdefault(model, {})[category] = float(rating)
            categories_seen.add(category)
            if not publish_date and isinstance(row.get("leaderboard_publish_date"), str):
                publish_date = row["leaderboard_publish_date"]

        if len(rows) < ARENA_ELO_PAGE_SIZE:
            break
    else:
        # Loop completed without break — we may have hit the page ceiling.
        print(f"NOTE — hit ARENA_ELO_MAX_PAGES={ARENA_ELO_MAX_PAGES} ceiling, dataset may be larger.")

    suffix = f" from {publish_date}" if publish_date else ""
    print(f"OK ({len(by_model)} models × {len(categories_seen)} categories{suffix})")
    return by_model


# ---------------------------------------------------------------------------
# Matching + cache assembly
# ---------------------------------------------------------------------------

def _match_score(nim_model: str, aliases: list[str], upstream: dict[str, float]) -> float | None:
    candidates = [nim_model] + aliases
    for cand in candidates:
        cand_lower = cand.lower()
        for key, val in upstream.items():
            if cand_lower in key.lower() or key.lower() in cand_lower:
                return val
    return None


def _match_arena_categories(
    nim_model: str, aliases: list[str], upstream: dict[str, dict[str, float]],
) -> dict[str, float] | None:
    """Same substring matching as `_match_score`, but returns the full per-category dict."""
    candidates = [nim_model] + aliases
    for cand in candidates:
        cand_lower = cand.lower()
        for key, val in upstream.items():
            if cand_lower in key.lower() or key.lower() in cand_lower:
                return val
    return None


# Tier thresholds are editorial buckets calibrated against the current BFCL
# distribution (top score ~77%). They are NOT published by Berkeley — they're
# this script's bucketing on top of the raw percentage. When the distribution
# shifts (a new frontier model raises the ceiling, or the benchmark is revised),
# revisit these.
def _bfcl_tier(score: float) -> str:
    if score >= 0.70:
        return "top"
    if score >= 0.55:
        return "strong"
    if score >= 0.35:
        return "mid"
    return "weak"


def _bfcl_plain(score: float) -> str:
    """Translate a BFCL score into a sentence a layperson can act on."""
    tier = _bfcl_tier(score)
    return {
        "top": (
            f"Correctly selects and calls tools in {score:.0%} of test cases, "
            "including tricky parallel and multi-step scenarios. At the frontier "
            "of what currently-public models can do on this benchmark."
        ),
        "strong": (
            f"Correctly handles tools in roughly {score:.0%} of cases. Competitive "
            "for production tool-calling agents; may occasionally mis-select a "
            "tool under ambiguous prompts."
        ),
        "mid": (
            f"Gets tool calls right about {score:.0%} of the time. Workable for "
            "single-tool or low-complexity agents; expect reliability issues "
            "with parallel calls or chained sequences."
        ),
        "weak": (
            f"Tool-calling accuracy around {score:.0%} — well behind current "
            "competitive models. Consider a stronger model if precise tool "
            "invocation is the main job."
        ),
    }[tier]


# Tier thresholds are editorial buckets calibrated against the current Arena
# distribution (top ~1500). They are NOT published by LMSYS — they're this
# script's bucketing on top of the raw Elo. Revisit when the ceiling shifts.
def _arena_elo_tier(score: float) -> str:
    if score >= 1450:
        return "top"
    if score >= 1350:
        return "strong"
    if score >= 1250:
        return "mid"
    return "weak"


def _category_label(category: str) -> str:
    """Human-readable name for an Arena category in plain-English sentences."""
    return {
        "overall": "overall head-to-head preference",
        "coding": "coding tasks",
        "hard_prompts": "hard prompts",
        "hard_prompts_english": "hard prompts (English)",
        "instruction_following": "instruction following",
        "creative_writing": "creative writing",
        "expert": "expert-level prompts",
        "english": "English prompts",
        "chinese": "Chinese prompts",
        "german": "German prompts",
        "french": "French prompts",
        "japanese": "Japanese prompts",
        "korean": "Korean prompts",
        "exclude_ties": "head-to-head preference (excluding ties)",
    }.get(category, category.replace("_", " "))


def _arena_elo_plain(score: float, category: str = "overall") -> str:
    """Translate an Arena Elo rating into a sentence a layperson can act on."""
    tier = _arena_elo_tier(score)
    rounded = int(round(score))
    label = _category_label(category)
    return {
        "top": (
            f"Rated {rounded} Elo on {label} in head-to-head matches with real "
            "users — at the frontier for this capability."
        ),
        "strong": (
            f"Rated {rounded} Elo on {label} — competitive, reliable across the "
            "kinds of prompts real users send in this category."
        ),
        "mid": (
            f"Rated {rounded} Elo on {label} — workable, but expect to lose "
            "preference comparisons against top models in this category."
        ),
        "weak": (
            f"Rated {rounded} Elo on {label} — well below current competitive "
            "models. Consider a stronger model if this capability is the main job."
        ),
    }[tier]


def build_cache(bfcl: dict[str, float], arena_elo: dict[str, dict[str, float]]) -> Cache:
    models: list[CacheModelEntry] = []

    for nim_id, profile in NIM_MODEL_PROFILES.items():
        aliases = profile["aliases"]

        bfcl_score = _match_score(nim_id, aliases, bfcl)
        arena_by_category = _match_arena_categories(nim_id, aliases, arena_elo)

        scores: ModelScores = {}
        if bfcl_score is not None:
            scores["bfcl_v4"] = {
                "raw": round(bfcl_score, 4),
                "percent": f"{bfcl_score:.0%}",
                "tier": _bfcl_tier(bfcl_score),
                "plain": _bfcl_plain(bfcl_score),
            }
        if arena_by_category:
            scores["arena_elo"] = {
                category: {
                    "raw": int(round(rating)),
                    "tier": _arena_elo_tier(rating),
                    "plain": _arena_elo_plain(rating, category),
                }
                for category, rating in sorted(arena_by_category.items())
            }

        models.append({
            "nim_model": nim_id,
            "architecture_note": profile["architecture_note"],
            "strong_at": profile["strong_at"],
            "watch_out_for": profile["watch_out_for"],
            "best_deployment": profile["best_deployment"],
            "primary_benchmarks": profile["primary_benchmarks"],
            "scores": scores,
        })

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "schema_version": "4",
        "sources": {
            "bfcl": BFCL_CSV_URL,
            "arena_elo": ARENA_ELO_ROWS_URL,
        },
        "benchmarks": BENCHMARK_REGISTRY,
        "models": models,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def load_existing_cache(path: Path) -> Cache | None:
    """Read the cache that's already on disk, or return None if there isn't one."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  Existing cache at {path} unreadable ({exc}); starting fresh.")
        return None
    return data


def merge_cache(existing: Cache | None, fresh: Cache) -> Cache:
    """Overlay `fresh` onto `existing` — fresh wins per category, existing fills gaps.

    Each refresh may be cut short by rate limits and only capture a subset of the
    22 Arena categories. Without merge, every partial run wipes the richer cache
    from previous runs. With merge, multiple runs over time converge on full
    coverage; a single bad run can't make the cache worse.
    """
    if existing is None or existing.get("schema_version") != fresh["schema_version"]:
        return fresh

    existing_by_id = {m["nim_model"]: m for m in existing.get("models", [])}

    merged_models: list[CacheModelEntry] = []
    for fresh_m in fresh["models"]:
        nim_id = fresh_m["nim_model"]
        old_m = existing_by_id.get(nim_id)
        if old_m is None:
            merged_models.append(fresh_m)
            continue

        old_scores = old_m.get("scores", {})
        new_scores = fresh_m.get("scores", {})
        merged_scores: ModelScores = {}

        # BFCL is a single number per model — fresh wins if present, else keep old
        if "bfcl_v4" in new_scores:
            merged_scores["bfcl_v4"] = new_scores["bfcl_v4"]
        elif "bfcl_v4" in old_scores:
            merged_scores["bfcl_v4"] = old_scores["bfcl_v4"]

        # Arena Elo is per-category — overlay fresh categories onto cached ones
        merged_arena: dict[str, ArenaEloScore] = {}
        if "arena_elo" in old_scores:
            merged_arena.update(old_scores["arena_elo"])
        if "arena_elo" in new_scores:
            merged_arena.update(new_scores["arena_elo"])
        if merged_arena:
            merged_scores["arena_elo"] = merged_arena

        # Static descriptive fields always come from the current registry, not the cache
        merged_models.append({
            "nim_model": nim_id,
            "architecture_note": fresh_m["architecture_note"],
            "strong_at": fresh_m["strong_at"],
            "watch_out_for": fresh_m["watch_out_for"],
            "best_deployment": fresh_m["best_deployment"],
            "primary_benchmarks": fresh_m["primary_benchmarks"],
            "scores": merged_scores,
        })

    return {
        "generated_at": fresh["generated_at"],
        "schema_version": fresh["schema_version"],
        "sources": fresh["sources"],
        "benchmarks": fresh["benchmarks"],
        "models": merged_models,
    }


def write_cache(cache: Cache, path: Path, dry_run: bool) -> None:
    payload = json.dumps(cache, indent=2)
    if dry_run:
        print("\n--- DRY RUN OUTPUT ---")
        print(payload)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    print(f"\n  Cache written to {path}")


def print_summary(cache: Cache) -> None:
    print("\nModel capability summary (raw values; tier in parens):")
    print(f"  {'NIM model':<45} {'BFCL':<14} {'overall':<14} {'coding':<14} {'hard_prompts'}")
    print("  " + "-" * 102)
    for m in cache["models"]:
        bfcl = m["scores"].get("bfcl_v4")
        bfcl_cell = f"{bfcl['percent']} ({bfcl['tier']})" if bfcl else "—"
        arena = m["scores"].get("arena_elo", {})

        def _cell(cat: str) -> str:
            s = arena.get(cat)
            return f"{s['raw']} ({s['tier']})" if s else "—"

        print(
            f"  {m['nim_model']:<45} {bfcl_cell:<14} "
            f"{_cell('overall'):<14} {_cell('coding'):<14} {_cell('hard_prompts')}"
        )
        if m["strong_at"]:
            hint = m["strong_at"][0]
            print(f"    → {hint[:72]}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_CACHE_PATH,
        help=f"Cache output path (default: {DEFAULT_CACHE_PATH})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print cache JSON to stdout without writing",
    )
    args = parser.parse_args()

    print("Refreshing benchmark cache...")

    bfcl = fetch_bfcl_scores()
    arena_elo = fetch_arena_elo_scores()

    if not bfcl and not arena_elo:
        print("\nERROR: All upstream fetches failed. Check network access.", file=sys.stderr)
        print("The existing cache (if any) is unchanged.", file=sys.stderr)
        return 1

    fresh = build_cache(bfcl, arena_elo)
    existing = load_existing_cache(args.output)
    cache = merge_cache(existing, fresh)
    if existing is not None:
        # Quick diagnostic: how many arena categories landed across all models
        old_cats = sum(len(m.get("scores", {}).get("arena_elo", {})) for m in existing.get("models", []))
        new_cats = sum(len(m.get("scores", {}).get("arena_elo", {})) for m in cache["models"])
        print(f"  Cache merge: {old_cats} → {new_cats} category entries across all models.")
    write_cache(cache, args.output, dry_run=args.dry_run)
    print_summary(cache)

    missing = [
        m["nim_model"] for m in cache["models"]
        if "bfcl_v4" not in m["scores"] and "arena_elo" not in m["scores"]
    ]
    if missing:
        print(f"\n  NOTE: No upstream scores found for {len(missing)} model(s):")
        for m in missing:
            print(f"    - {m}")
        print("  Static capability descriptions are still available in the cache.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
