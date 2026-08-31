# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Assemble `dataset/groups/_all/` from the groups listed in `source_groups`.

The loop takes one train/validation pair, so exercising several groups in a
single run means one combined dataset. Directory names collide -- every group has
a `lookup-ada` or `lookup-grace` control -- so each is prefixed with its group
key. The `[task] name` values inside were already unique.

Generated, not authored: rerun this after changing any group. A test asserts the
combined copy matches its sources, so a stale `_all/` fails rather than silently
running against old tasks.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

COMBINED = "_all"
SPLITS = ("train", "validation")

# Not part of the combined set. Both are held out because the combined scenario
# asserts that every task in it is reachable, and neither of these is.
#
# `g4-dispatch-order` backs the generalization scenario, which asserts the
# opposite outcome: there, retaining the baseline is a pass. One run cannot
# assert both.
#
# `g5-edge-cases` is reachable only when trajectory scoring is on, and the
# combined scenario runs with it off. Measured across runs made after the Ethos
# stated the sentinel, so the Ethos is not the variable:
#
#     goal tree off -> 0 of 13 candidates closed g5
#     goal tree on  -> 7 of 11 candidates closed g5
#
# The pattern is that the goal tree sharpens the analysis enough for the Coder to
# see both halves of the fix; without it the analysis names one half and the
# candidates fix one half, which scores nothing. Trajectory scoring is off here
# because it is not yet dependable -- it has silently skipped a candidate, and a
# rejected goal tree disables it for a whole run without saying so.
#
# PUT G5 BACK once trajectory scoring is dependable enough to leave on. It is the
# only group that exercises a fix needing several coordinated edits, so the
# combined scenario is weaker without it.
EXCLUDED_GROUPS = frozenset({"g4-dispatch-order", "g5-edge-cases"})


def group_key(group: str) -> str:
    """Return the short key a group's task names already use (``g1`` from ``g1-aggregation``)."""
    return group.split("-")[0]


def source_groups(dataset_dir: Path) -> list[str]:
    """Every group the combined set is built from, in a stable order."""
    groups = dataset_dir / "groups"
    return sorted(
        d.name for d in groups.iterdir() if d.is_dir() and d.name != COMBINED and d.name not in EXCLUDED_GROUPS
    )


def assemble(dataset_dir: Path) -> list[Path]:
    """Rebuild the combined group from its sources; return the task directories written."""
    target = dataset_dir / "groups" / COMBINED
    shutil.rmtree(target, ignore_errors=True)

    written: list[Path] = []
    for group in source_groups(dataset_dir):
        key = group_key(group)
        for split in SPLITS:
            for task in sorted((dataset_dir / "groups" / group / split).iterdir()):
                if not (task / "task.toml").is_file():
                    continue
                dest = target / split / f"{key}-{task.name}"
                shutil.copytree(task, dest)
                written.append(dest)
    return written


def main() -> None:
    """Assemble the combined group from the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dataset",
    )
    args = parser.parse_args()
    from render_tasks import render

    render(args.dataset_dir)
    written = assemble(args.dataset_dir)
    for path in written:
        print(path.relative_to(args.dataset_dir))
    print(f"{len(written)} tasks")


if __name__ == "__main__":
    main()
