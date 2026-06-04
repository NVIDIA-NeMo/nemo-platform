#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Raw driver for the memory-triage agreement primitive.

Same logic as ``nemo memory eval``, but with CLI flags instead
of a YAML spec and a stdout-friendly summary. Useful when iterating on
the metric definitions or scanning a disagreement set quickly. Does
NOT support fileset references; use local paths or pre-stage with
``nemo files download``.

Usage::

    uv run --frozen python plugins/nemo-memory/examples/triage/eval.py \\
        --baseline plugins/nemo-memory/src/nemo_memory_plugin/triage/phase1-smoke/baselines/baseline-sonnet-4-6-user.json \\
        --candidate /tmp/triage-omnistation/baseline-sonnet-4-6-user.json \\
        --output-dir /tmp/memory-eval-out \\
        --basename sonnet-vs-self-omnistation
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--baseline",
        required=True,
        type=Path,
        help="Path to the baseline triage artifact JSON.",
    )
    parser.add_argument(
        "--candidate",
        required=True,
        type=Path,
        help="Path to the candidate triage artifact JSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./memory-eval-output"),
        help="Where the report pair lands. Default: ./memory-eval-output.",
    )
    parser.add_argument(
        "--basename",
        default="memory-eval",
        help="Basename for the report pair ({basename}.json / {basename}.md).",
    )
    args = parser.parse_args(argv)

    from nemo_memory_plugin.triage.eval import compare_runs, write_report_artifacts

    report = compare_runs(args.baseline, args.candidate)
    json_path, md_path = write_report_artifacts(report, args.output_dir, basename=args.basename)

    # Compact stdout summary so you can pipe / eyeball without opening the
    # full artifact. Three headline rates plus a one-line confusion view.
    print(f"baseline:   {args.baseline}")
    print(f"            council={report.baseline_council} elapsed={report.baseline_elapsed_sec:.1f}s")
    print(f"candidate:  {args.candidate}")
    print(f"            council={report.candidate_council} elapsed={report.candidate_elapsed_sec:.1f}s")
    print()
    print(f"common entries:           {report.common_entries}")
    print(f"baseline-only entries:    {len(report.baseline_only_entries)}")
    print(f"candidate-only entries:   {len(report.candidate_only_entries)}")
    print()
    print(
        f"strict agreement:         {report.strict_agreements}/{report.common_entries} = {report.strict_rate * 100:.1f}%"
    )
    print(
        f"retain-vs-drop agreement: {report.retain_vs_drop_agreements}/{report.common_entries} = {report.retain_vs_drop_rate * 100:.1f}%"
    )
    print(
        f"promote-threshold agree:  {report.promote_threshold_agreements}/{report.common_entries} = {report.promote_threshold_rate * 100:.1f}%"
    )
    print(f"disagreements:            {len(report.deltas)}")
    print()
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
