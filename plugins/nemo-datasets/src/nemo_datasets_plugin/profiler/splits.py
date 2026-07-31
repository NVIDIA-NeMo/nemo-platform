# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Split resolution from file paths.

Given the files in one partition, group them into splits by inferring each file's split from its
path — a split-named directory first, then the shard-stripped filename. A declared split map from a
dataset card would take precedence over this inference, but card parsing is not wired up yet, so
path inference is the only source today.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from nemo_datasets_plugin.profiler.file_source import FileEntry

# Strips a shard suffix like "-00000" or "-00000-of-00003" from a file stem. A bare trailing number
# must be zero-padded to count: `-\d{2,}` alone also matched years and versions, turning
# covid-19.jsonl into a "covid" split and data-2024.jsonl into "data".
_SHARD_SUFFIX = re.compile(r"-(?:\d{2,}-of-\d{2,}|0\d{3,})$")

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


def _canonical_for(split_name: str) -> str | None:
    """Map a split name to its canonical concept, tolerating variant suffixes (train_prefs -> train)."""
    lowered = split_name.lower()
    for alias, canonical in _CANONICAL_ALIASES.items():
        if lowered == alias or lowered.startswith(f"{alias}_") or lowered.startswith(f"{alias}-"):
            return canonical
    return None


def is_split_directory(name: str) -> bool:
    """Whether a directory name denotes a split rather than a partition.

    Partition grouping needs this to avoid turning ``train/`` and ``test/`` into two unrelated
    partitions, each with its own schema and classification, when they are two splits of one dataset.
    """
    return _canonical_for(name) is not None


def _split_name(path: str) -> str:
    """The split a file belongs to.

    A split-named directory anywhere on the path wins over the filename, because the ``data/train/``
    layout names its shards ``0000.parquet`` — reading only the stem would file every split's shards
    under the same meaningless name and collapse the whole dataset into one split. Nearest directory
    to the file wins. Failing that, the shard-stripped stem: train-00000-of-00003.parquet -> "train".
    """
    parts = PurePosixPath(path).parts
    for directory in reversed(parts[:-1]):
        if is_split_directory(directory):
            return directory
    return _SHARD_SUFFIX.sub("", parts[-1].split(".")[0])


def resolve_splits(entries: list[FileEntry]) -> list[ResolvedSplit]:
    """Group files into splits by path inference.

    Each file's split name comes from a split-named directory on its path, else its shard-stripped
    stem; the canonical concept is matched against common aliases (val/valid/dev -> validation). When
    no file carries a recognizable split, every file lands in one "default" split.
    """
    grouped: dict[str, list[FileEntry]] = {}
    for entry in entries:
        grouped.setdefault(_split_name(entry.path), []).append(entry)

    canonicals = {name: _canonical_for(name) for name in grouped}
    if not any(canonicals.values()):
        return [ResolvedSplit(name="default", canonical=None, entries=list(entries))]

    return [ResolvedSplit(name=name, canonical=canonicals[name], entries=grouped[name]) for name in sorted(grouped)]
