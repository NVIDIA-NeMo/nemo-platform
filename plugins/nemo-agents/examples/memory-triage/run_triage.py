# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Memory triage smoke / baseline / candidate runner.

Drives the council orchestration described in
``plugins/nemo-agents/src/nemo_agents_plugin/improvement/memory/DESIGN.md``
against a real memory store. Talks to whatever models the local NeMo
Platform IGW exposes via its OpenAI-compatible endpoint (no direct
provider credentials needed).

Three intended modes:

1. **Baseline lock.** Run with ``--judge azure-anthropic-claude-sonnet-4-6``
   (single judge) and ``--basename baseline-sonnet-4-6-user`` to produce
   the gold reference artifact future tuned-model runs diff against.
2. **Candidate eval.** Run with ``--judge <candidate-model>`` against the
   same corpus, produce a comparable artifact, then run
   ``eval_triage.py`` (Phase 2) to compute agreement / confusion.
3. **Multi-judge research smoke.** Pass ``--judge`` repeatedly to bring
   up an N-judge council. Useful for the "is this candidate worth
   tuning?" question before committing to a fine-tune run.

This is the Phase 1 / 1.5 driver. Phase 2 turns this into a proper
``nemo agents triage-memory`` NemoJob with ``run / submit / explain``
verbs; the CLI surface and config schema will replace this script.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import openai
from nemo_agents_plugin.improvement.memory.adapters.pi_hermes import PiHermesMemoryStore
from nemo_agents_plugin.improvement.memory.judges import OpenAICompatibleJudge
from nemo_agents_plugin.improvement.memory.report import write_artifacts
from nemo_agents_plugin.improvement.memory.triage import run_triage

DEFAULT_CORPUS = Path.home() / ".pi/agent/claude-session-replays/CONSOLIDATED/USER.md"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "output"
DEFAULT_STORE_NAME = "pi-hermes:CONSOLIDATED:user"


def get_igw_url() -> str:
    """Resolve the local IGW base URL via the ``nemo`` CLI.

    Falls back to the ``NEMO_INFERENCE_URL`` env var when ``nemo`` is
    unavailable (e.g. when this script is exec'd outside a repo
    checkout). Raises if neither path works so the caller sees a real
    error rather than a confusing 404 later.
    """
    env_override = os.environ.get("NEMO_INFERENCE_URL")
    if env_override:
        return env_override
    try:
        out = subprocess.run(
            ["nemo", "inference", "get-url"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip().splitlines()[-1]
    except (FileNotFoundError, subprocess.CalledProcessError) as err:
        raise RuntimeError(
            "could not resolve IGW URL; set NEMO_INFERENCE_URL or run from a checkout with `nemo` on PATH"
        ) from err


async def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run the memory-triage council against a pi-hermes corpus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--judge",
        action="append",
        required=True,
        metavar="MODEL",
        help=(
            "Judge model id (as exposed by `nemo models list`). Repeat to add multiple judges. "
            "First --judge is treated as the reference model used by the aggregator for "
            "supporting-field selection."
        ),
    )
    ap.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help=f"Path to the consolidated USER.md / MEMORY.md / failures.md (default: {DEFAULT_CORPUS}).",
    )
    ap.add_argument(
        "--store-name",
        default=DEFAULT_STORE_NAME,
        help=f"Store name recorded on every emitted proposal (default: {DEFAULT_STORE_NAME!r}).",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Where to write triage.json + triage.md (default: {DEFAULT_OUTPUT}).",
    )
    ap.add_argument(
        "--basename",
        default="triage",
        help='Basename for the JSON + Markdown pair (default: "triage").',
    )
    ap.add_argument(
        "--max-tokens",
        type=int,
        default=4096,
        help="Per-call max_tokens budget. Reasoning models need >=2048; 4096 is the safe default.",
    )
    ap.add_argument(
        "--max-entries",
        type=int,
        default=None,
        help="Cap entries processed (useful for pilot runs before committing the full budget).",
    )
    ap.add_argument(
        "--api-key",
        default="not-needed",
        help='API key for the IGW. Default "not-needed" because IGW handles upstream auth.',
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=180,
        help="Per-request timeout in seconds.",
    )
    args = ap.parse_args()

    if not args.corpus.exists():
        print(f"ERROR: corpus not found at {args.corpus}", file=sys.stderr)
        print(
            "Set --corpus to the path of a pi-hermes Markdown corpus (USER.md / MEMORY.md / failures.md).",
            file=sys.stderr,
        )
        return 2

    url = get_igw_url()
    print(f"IGW: {url}")
    print(f"Corpus: {args.corpus}")
    print(f"Judges: {args.judge}")
    print(f"Output: {args.output_dir / (args.basename + '.{json,md}')}")
    print()

    client = openai.AsyncOpenAI(api_key=args.api_key, base_url=url, timeout=args.timeout)
    judges = [OpenAICompatibleJudge(client=client, model=model, max_tokens=args.max_tokens) for model in args.judge]

    store = PiHermesMemoryStore(path=args.corpus, name=args.store_name)
    entries_by_id = {e.id: e.content for e in store.list_entries()}
    print(f"Loaded {len(entries_by_id)} entries from corpus.")
    if args.max_entries:
        print(f"Capped to first {args.max_entries} entries.")

    def progress(done: int, total: int) -> None:
        print(f"  [{done}/{total}] done", file=sys.stderr, flush=True)

    run = await run_triage(
        store,
        judges,
        reference_model=args.judge[0],
        max_entries=args.max_entries,
        progress=progress,
    )

    print()
    print(
        f"Done in {run.elapsed_sec:.1f}s. "
        f"proposals={len(run.proposals)} errors={len(run.errors)} skipped={len(run.skipped_entries)}"
    )
    print(f"verdict counts: {run.verdict_counts}")

    # Per-judge calibration breakdown for quick eyeballing.
    from collections import Counter

    for model in args.judge:
        counts: Counter[str] = Counter()
        for p in run.proposals:
            vote = p.judge_votes.get(model)
            if vote:
                counts[vote.verdict.value] += 1
        total = sum(counts.values())
        if total:
            shape = ", ".join(
                f"{v}={counts[v]} ({100 * counts[v] / total:.0f}%)"
                for v in ("keep", "promote_to_prompt", "refine", "merge", "drop")
                if counts.get(v)
            )
            print(f"  {model}: {shape}")

    json_path, md_path = write_artifacts(
        run,
        args.output_dir,
        entries_by_id=entries_by_id,
        basename=args.basename,
    )
    print()
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
