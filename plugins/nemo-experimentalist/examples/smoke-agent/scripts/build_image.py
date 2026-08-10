# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build the shared task image and stamp its tag into every task.toml.

The tag is a content hash of the Dockerfile and the records file, so a change to
either produces a new tag. Tasks reference the tag rather than carrying their own
Dockerfile, and a test asserts every task references the current one -- which is
what turns "forgot to rebuild" into a failing test instead of a container quietly
running against stale data.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path

HASHED_FILES = ("Dockerfile", "records.json")
IMAGE_NAME = "smoke-agent-env"
_DOCKER_IMAGE_RE = re.compile(r'^(docker_image\s*=\s*)"[^"]*"', re.MULTILINE)


def image_tag(shared_dir: Path) -> str:
    """Return the content-addressed tag for the current shared assets."""
    digest = hashlib.sha256()
    for name in HASHED_FILES:
        digest.update((shared_dir / name).read_bytes())
    return f"{IMAGE_NAME}:sha-{digest.hexdigest()[:12]}"


def build(shared_dir: Path, tag: str) -> None:
    """Build the image. Docker layer caching makes a no-op rebuild cheap."""
    subprocess.run(["docker", "build", "-t", tag, str(shared_dir)], check=True)


def ensure_environment_dirs(dataset_dir: Path) -> list[Path]:
    """Create the empty environment/ every task needs; return the ones created.

    Harbor's ``TaskModel.is_valid_dir`` requires ``environment/`` to *exist* before
    it will even parse a task; ``[environment].docker_image`` only makes the
    Dockerfile inside it optional. A task without the directory is silently not a
    task -- the dataset loads with zero tasks rather than erroring. The directory
    stays empty apart from a .gitkeep, since a Dockerfile there would shadow the
    prebuilt image.
    """
    created: list[Path] = []
    for task_toml in sorted((dataset_dir / "groups").rglob("task.toml")):
        keep = task_toml.parent / "environment" / ".gitkeep"
        if not keep.exists():
            keep.parent.mkdir(parents=True, exist_ok=True)
            keep.touch()
            created.append(keep)
    return created


def stamp_tasks(dataset_dir: Path, tag: str) -> list[Path]:
    """Rewrite every task.toml's docker_image to *tag*; return the ones changed."""
    changed: list[Path] = []
    for task_toml in sorted((dataset_dir / "groups").rglob("task.toml")):
        text = task_toml.read_text(encoding="utf-8")
        updated = _DOCKER_IMAGE_RE.sub(rf'\1"{tag}"', text)
        if updated != text:
            task_toml.write_text(updated, encoding="utf-8")
            changed.append(task_toml)
    return changed


def main() -> None:
    """Build the shared image and stamp its tag into every task."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dataset",
    )
    parser.add_argument("--skip-build", action="store_true", help="stamp tags without invoking docker")
    args = parser.parse_args()

    tag = image_tag(args.dataset_dir / "_shared")
    if not args.skip_build:
        build(args.dataset_dir / "_shared", tag)
    for path in ensure_environment_dirs(args.dataset_dir):
        print(f"created {path}")
    for path in stamp_tasks(args.dataset_dir, tag):
        print(f"stamped {path}")
    print(tag)


if __name__ == "__main__":
    main()
