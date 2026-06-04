#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Raw driver for the fine-tune corpus extractor.

Same logic as ``nemo agents export-finetune-corpus``, with CLI flags
instead of a YAML spec and a stdout summary. Does NOT support fileset
references; use local paths or pre-stage with ``nemo files download``.

Usage::

    uv run --frozen python plugins/nemo-agents/examples/memory-triage/export_finetune_corpus.py \\
        --triage-artifact plugins/nemo-agents/src/nemo_agents_plugin/improvement/memory/phase1-smoke/triage-user.json \\
        --corpus ~/.pi/agent/claude-session-replays/CONSOLIDATED/USER.md \\
        --reference-judge azure-anthropic-claude-sonnet-4-5 \\
        --candidate-judge nvidia-nvidia-nemotron-3-nano-30b-a3b \\
        --only-disagreements \\
        --output-dir /tmp/finetune-out \\
        --basename v1-sonnet45-vs-nano-disagreements
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--triage-artifact", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--reference-judge", required=True)
    parser.add_argument("--candidate-judge", default=None)
    parser.add_argument("--only-disagreements", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./finetune-corpus-output"),
    )
    parser.add_argument("--basename", default="finetune-corpus")
    args = parser.parse_args(argv)

    from nemo_agents_plugin.improvement.memory.finetune import (
        build_finetune_corpus,
        write_finetune_artifacts,
    )

    records, summary = build_finetune_corpus(
        args.triage_artifact,
        args.corpus,
        reference_judge=args.reference_judge,
        candidate_judge=args.candidate_judge,
        only_disagreements=args.only_disagreements,
    )
    paths = write_finetune_artifacts(records, summary, args.output_dir, basename=args.basename)

    print(f"source artifact:    {summary.source_artifact}")
    print(f"source corpus:      {summary.source_corpus}")
    print(f"reference judge:    {summary.reference_judge}")
    print(f"candidate judge:    {summary.candidate_judge or '(none)'}")
    print(f"filter:             {'only disagreements' if summary.only_disagreements else 'full labeled corpus'}")
    print()
    print(f"total records:      {summary.total_records}")
    if summary.candidate_judge:
        print(f"disagreement count: {summary.disagreement_count}")
    if summary.skipped_entries:
        print(f"skipped entries:    {len(summary.skipped_entries)}")
    print()
    print("reference label distribution:")
    for v in sorted(summary.label_verdict_counts):
        print(f"  {v:24s} {summary.label_verdict_counts[v]}")
    if summary.candidate_judge:
        print(f"candidate ({summary.candidate_judge}) label distribution:")
        for v in sorted(summary.candidate_verdict_counts):
            print(f"  {v:24s} {summary.candidate_verdict_counts[v]}")
    print()
    for kind, p in paths.items():
        print(f"wrote {kind:8s} {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
