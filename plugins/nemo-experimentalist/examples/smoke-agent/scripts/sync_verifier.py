# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Copy the shared verifier into every task, and the records into the task template.

Harbor copies each task's tests/ into the container at verify time alongside that
task's own expected.txt, so the verifier is necessarily duplicated per task even
though it is identical everywhere. This is the one place that duplication is
produced; test_smoke_agent_assets.py keeps it honest.

The task template is included. It was scoped out once, and quietly went stale.

The records file is copied to the template *only*. Insight mode has Eval Author
write a task from a production trace, and a trace cannot supply the answer key: it
holds the question and the agent's wrong answer, never the right one. Left to infer
it, Eval Author writes nothing and `<EXPECTED>` survives into a task that then
scores 0 for every agent, repaired or not. With the records beside the template the
answer is computable, which is the assumption worth making generally -- an agent's
evaluator should be able to see what the agent sees.

Real tasks do not get a copy: they already have their answers committed, and their
container reads the same records from the prebuilt image at /app/data/records.json.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def sync(dataset_dir: Path) -> list[Path]:
    """Copy the canonical verifier into every task and the records into the template.

    Returns every path written.
    """
    canonical = dataset_dir / "_shared" / "test.sh"
    written: list[Path] = []
    for task_toml in sorted(dataset_dir.rglob("task.toml")):
        target = task_toml.parent / "tests" / "test.sh"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(canonical, target)
        target.chmod(0o755)
        written.append(target)

    template = dataset_dir / "task-template"
    if template.is_dir():
        records = template / "records.json"
        shutil.copyfile(dataset_dir / "_shared" / "records.json", records)
        written.append(records)
    return written


def main() -> None:
    """Sync the verifier from the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dataset",
    )
    args = parser.parse_args()
    for path in sync(args.dataset_dir):
        print(path)


if __name__ == "__main__":
    main()
