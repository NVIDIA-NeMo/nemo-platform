# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Refresh the canonical files that task rendering copies from the template.

The records file is copied to the template *only*. Insight mode has Eval Author
write a task from a production trace, and a trace cannot supply the answer key: it
holds the question and the agent's wrong answer, never the right one. Left to infer
it, Eval Author writes nothing and `<EXPECTED>` survives into a task that then
scores 0 for every agent, repaired or not. With the records beside the template the
answer is computable, which is the assumption worth making generally -- an agent's
evaluator should be able to see what the agent sees.

Rendered tasks inherit the verifier from the template and their expected answers
from ``tasks.json``. Their container reads the same records from the prebuilt
image at /app/data/records.json.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def sync(dataset_dir: Path) -> list[Path]:
    """Copy the verifier and records into the task template."""
    canonical = dataset_dir / "_shared" / "test.sh"
    template = dataset_dir / "task-template"
    verifier = template / "tests" / "test.sh"
    records = template / "records.json"
    shutil.copyfile(canonical, verifier)
    verifier.chmod(0o755)
    shutil.copyfile(dataset_dir / "_shared" / "records.json", records)
    return [verifier, records]


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
