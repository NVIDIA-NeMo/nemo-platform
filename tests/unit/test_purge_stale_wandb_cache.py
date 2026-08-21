# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for docker/scripts/purge-stale-wandb-cache.sh."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
SCRIPT = ROOT / "docker/scripts/purge-stale-wandb-cache.sh"


def _run(cache: Path, keep: str = "0.28.2") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), keep, str(cache)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_purge_script_is_executable() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_purge_removes_unpinned_wandb_artifacts(tmp_path: Path) -> None:
    archive = tmp_path / "archive-v0"
    stale_archive = archive / "hash-old"
    keep_archive = archive / "hash-new"
    stale_archive.mkdir(parents=True)
    keep_archive.mkdir(parents=True)
    (stale_archive / "wandb-0.28.1.dist-info").mkdir()
    (stale_archive / "wandb" / "bin").mkdir(parents=True)
    (stale_archive / "wandb" / "bin" / "wandb-core").write_text("old", encoding="utf-8")
    (keep_archive / "wandb-0.28.2.dist-info").mkdir()
    (keep_archive / "wandb" / "bin").mkdir(parents=True)
    (keep_archive / "wandb" / "bin" / "wandb-core").write_text("new", encoding="utf-8")

    wheels = tmp_path / "wheels-v3"
    wheels.mkdir()
    (wheels / "wandb-0.28.1-py3-none-manylinux_2_28_x86_64.whl").write_bytes(b"old")
    (wheels / "wandb-0.28.2-py3-none-manylinux_2_28_x86_64.whl").write_bytes(b"new")
    (tmp_path / "wandb-0.28.1.tar.gz").write_bytes(b"old-sdist")
    (tmp_path / "wandb-0.28.2.tar.gz").write_bytes(b"new-sdist")

    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr

    assert not stale_archive.exists()
    assert (keep_archive / "wandb-0.28.2.dist-info").is_dir()
    assert (keep_archive / "wandb" / "bin" / "wandb-core").read_text(encoding="utf-8") == "new"
    assert not (wheels / "wandb-0.28.1-py3-none-manylinux_2_28_x86_64.whl").exists()
    assert (wheels / "wandb-0.28.2-py3-none-manylinux_2_28_x86_64.whl").exists()
    assert not (tmp_path / "wandb-0.28.1.tar.gz").exists()
    assert (tmp_path / "wandb-0.28.2.tar.gz").exists()


def test_purge_fails_when_cache_missing(tmp_path: Path) -> None:
    result = _run(tmp_path / "missing")
    assert result.returncode == 1
    assert "does not exist" in result.stderr


def test_purge_requires_keep_version() -> None:
    result = subprocess.run(["bash", str(SCRIPT)], check=False, capture_output=True, text=True)
    assert result.returncode == 2
    assert "usage:" in result.stderr
