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


def _glob_matches(pattern: str, path: str) -> bool:
    """Match ``path`` against ``pattern`` where ``*`` spans any run of characters except ``/``.

    Deliberately the narrowest dialect rather than the most expressive one. This single reading of
    ``*`` is shared by shell globs, Python's :mod:`glob`, fsspec and HF ``data_files``, so a pattern
    emitted here means the same thing wherever a consumer pastes it. ``**`` is not produced at all:
    its semantics differ between those tools, and a pattern that silently selects a different set of
    files in the reader than it did in the profiler is worse than no pattern.
    """
    return re.fullmatch("[^/]*".join(re.escape(part) for part in pattern.split("*")), path) is not None


def infer_data_files(split_name: str, entries: list[FileEntry], all_paths: list[str]) -> str | None:
    """A glob selecting exactly ``entries`` out of ``all_paths``, or None if no single one does.

    This is the inverse of the split resolution above: splits are read *off* the paths, so the
    pattern is rebuilt from the same evidence — the directory the files share, and the split name
    their filenames start with. It restores addressability of a split's files without restoring the
    per-file manifest that was removed for scaling: one pattern per split, whatever the shard count.

    Candidates run most specific first, because the general ones over-match. In ``helpsteer2/`` a
    ``train`` split wants ``helpsteer2/train*.parquet``; ``helpsteer2/*.parquet`` would swallow the
    validation shards too, and only the ordering distinguishes them. The ``data/train/0000.parquet``
    layout is the other way round — no filename starts with "train", so the name-anchored candidates
    are skipped and the directory-wide one is exactly right.

    Every candidate is matched back against *every* file the source listed, not just this split's or
    even just this partition's, and the first that reproduces the split exactly wins. Nothing is
    emitted on a near miss. A glob is an instruction to go read files, so an approximate one is not
    a smaller version of the right answer -- it quietly pulls a README, or another split's shards,
    into a training set. None says "these files are not expressible as one pattern", which is a
    thing a consumer can handle; a wrong pattern is not.
    """
    paths = [entry.path for entry in entries]
    directories = {PurePosixPath(path).parent.as_posix() for path in paths}
    if len(directories) != 1:
        # Shards spread across subdirectories. Covering them needs `**`, whose meaning is not shared
        # across glob implementations, so this reports no pattern rather than an ambiguous one.
        return None
    directory = directories.pop()
    prefix = "" if directory == "." else f"{directory}/"
    names = [PurePosixPath(path).name for path in paths]
    suffixes = {PurePosixPath(path).suffix for path in paths}
    # A partition may hold more than one format; only a single shared suffix can go in the pattern.
    suffix = suffixes.pop() if len(suffixes) == 1 else None

    # Stems to anchor on: the bare split name first, then the same name keeping the separator that
    # follows it. Plain `train*` is what a person would write and is tried first for that reason;
    # the separator variants exist only for the sibling collision, where `train` sits beside
    # `train_prefs` in one directory and `train*` swallows both. Verification is what demotes the
    # simple form there, so the narrower `train-*` is reached only when it is actually needed. Each
    # stem is offered only when every filename in the split carries it, so one can never exclude a
    # file it ought to match.
    stems = [split_name] + [f"{split_name}{sep}" for sep in ("-", ".", "_")] if split_name else []
    candidates: list[str] = []
    for stem in stems:
        if not all(name.startswith(stem) for name in names):
            continue
        if suffix:
            candidates.append(f"{prefix}{stem}*{suffix}")
        candidates.append(f"{prefix}{stem}*")
    if suffix:
        candidates.append(f"{prefix}*{suffix}")
    candidates.append(f"{prefix}*")

    target = set(paths)
    for candidate in candidates:
        if {path for path in all_paths if _glob_matches(candidate, path)} == target:
            return candidate
    return None


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
