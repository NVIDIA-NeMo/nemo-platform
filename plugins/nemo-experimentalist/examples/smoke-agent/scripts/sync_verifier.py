# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Copy dataset/_shared/test.sh into every task's tests/ directory.

Harbor copies each task's tests/ into the container at verify time alongside that
task's own expected.txt, so the verifier is necessarily duplicated per task even
though it is identical everywhere. This is the one place that duplication is
produced; test_smoke_agent_assets.py keeps it honest.

The Dockerfile and records file are *not* copied. Tasks reference the prebuilt
image by tag instead — see scripts/build_image.py.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def sync(dataset_dir: Path) -> list[Path]:
    """Copy the canonical verifier into every task; return the paths written."""
    canonical = dataset_dir / "_shared" / "test.sh"
    written: list[Path] = []
    for task_toml in sorted((dataset_dir / "groups").rglob("task.toml")):
        target = task_toml.parent / "tests" / "test.sh"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(canonical, target)
        target.chmod(0o755)
        written.append(target)
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
