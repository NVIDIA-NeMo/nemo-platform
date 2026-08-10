# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import shutil
from pathlib import Path

HELD_OUT_SPLITS = frozenset({"validation"})
HELD_OUT_STORAGE_DIR = ".aad-heldout"

# Path tokens GuardedShellTools refuses: a tripwire for direct shell access while a
# split is briefly restored for scoring. Relocation is the main obfuscation layer.
DEFAULT_BLOCKED_PATHS: tuple[str, ...] = (
    HELD_OUT_STORAGE_DIR,
    *(f"dataset/{s}" for s in sorted(HELD_OUT_SPLITS)),
)

BLOCKED_MESSAGE = (
    "blocked: the validation split is held out for scoring only. "
    "Its contents are off-limits; diagnose and fix using the train split."
)


class HeldOutAccessError(PermissionError):
    """Raised when held-out split contents or debugging artifacts are requested."""


def heldout_storage_root(workspace: Path) -> Path:
    """Return the workspace-local directory used to store held-out splits.

    Args:
        workspace: absolute path to the eval-and-optimize workspace root.

    Returns:
        Path: the hidden storage directory for held-out splits.

    """
    workspace = Path(workspace).resolve()
    return workspace / HELD_OUT_STORAGE_DIR


def _split_paths(workspace: Path, split: str) -> tuple[Path, Path]:
    """Return the ``(visible, hidden)`` locations for ``split``."""
    workspace = Path(workspace).resolve()
    return workspace / "dataset" / split, heldout_storage_root(workspace) / split


def _move(src: Path, dst: Path, split: str) -> None:
    """Delete any existing ``dst``, then rename ``src`` to ``dst``."""
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)


def ensure_heldout_hidden(workspace: Path, *, splits: frozenset[str] = HELD_OUT_SPLITS) -> None:
    """Move any visible held-out splits into hidden storage.

    Idempotent — safe to call before every optimizer phase.

    Args:
        workspace: absolute path to the eval-and-optimize workspace root.
        splits: set of split names to hide; defaults to ``HELD_OUT_SPLITS``.

    """
    for split in splits:
        visible, hidden = _split_paths(workspace, split)
        if visible.exists():
            _move(visible, hidden, split)


def restore_heldout_splits(workspace: Path, *, splits: frozenset[str] = HELD_OUT_SPLITS) -> None:
    """Restore hidden held-out splits back into ``dataset/``.

    Args:
        workspace: absolute path to the eval-and-optimize workspace root.
        splits: set of split names to restore; defaults to ``HELD_OUT_SPLITS``.

    """
    for split in splits:
        visible, hidden = _split_paths(workspace, split)
        if hidden.exists():
            _move(hidden, visible, split)
    _prune_empty_storage(workspace)


def _prune_empty_storage(workspace: Path) -> None:
    """Remove the hidden storage dir if empty."""
    root = heldout_storage_root(workspace)
    try:
        root.rmdir()
    except OSError:
        pass
