# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Split resolution from file paths.

Given the files in one partition, group them into splits by inferring each file's split from its
name. A declared split map from a dataset card would take precedence over this inference, but card
parsing is not wired up yet, so path inference is the only source today.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from nemo_datasets_plugin.profiler.file_source import FileEntry

# Strips a shard suffix like "-00000" or "-00000-of-00003" from a file stem.
_SHARD_SUFFIX = re.compile(r"-\d{2,}(?:-of-\d{2,})?$")

# Common on-disk split words -> the canonical concept they normalize to.
_CANONICAL_ALIASES = {
    "train": "train",
    "test": "test",
    "validation": "validation",
    "valid": "validation",
    "val": "validation",
    "dev": "validation",
}


@dataclass(frozen=True)
class ResolvedSplit:
    """A split and the files that belong to it."""

    name: str  # the on-disk split name, e.g. "train" or "train_prefs"
    canonical: str | None  # normalized concept (train | validation | test), or None
    entries: list[FileEntry]


def _split_name(path: str) -> str:
    """The shard-stripped file stem, e.g. train-00000-of-00003.parquet -> "train"."""
    stem = PurePosixPath(path).name.split(".")[0]
    return _SHARD_SUFFIX.sub("", stem)


def _canonical_for(split_name: str) -> str | None:
    """Map a split name to its canonical concept, tolerating variant suffixes (train_prefs -> train)."""
    lowered = split_name.lower()
    for alias, canonical in _CANONICAL_ALIASES.items():
        if lowered == alias or lowered.startswith(f"{alias}_") or lowered.startswith(f"{alias}-"):
            return canonical
    return None


def resolve_splits(entries: list[FileEntry]) -> list[ResolvedSplit]:
    """Group files into splits by path inference.

    Each file's split name is its shard-stripped stem; the canonical concept is matched against
    common aliases (val/valid/dev -> validation). When no file carries a recognizable split, every
    file lands in one "default" split.
    """
    grouped: dict[str, list[FileEntry]] = {}
    for entry in entries:
        grouped.setdefault(_split_name(entry.path), []).append(entry)

    canonicals = {name: _canonical_for(name) for name in grouped}
    if not any(canonicals.values()):
        return [ResolvedSplit(name="default", canonical=None, entries=list(entries))]

    return [ResolvedSplit(name=name, canonical=canonicals[name], entries=grouped[name]) for name in sorted(grouped)]
