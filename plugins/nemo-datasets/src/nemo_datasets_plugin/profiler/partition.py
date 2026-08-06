# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Partition grouping.

A partition is a group of files profiled as a unit. This stage groups by top-level directory; a
later stage refines partitions whose files turn out to disagree on column schema.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from nemo_datasets_plugin.profiler.file_source import FileEntry
from nemo_datasets_plugin.profiler.splits import is_split_directory


def _top_dir(path: str) -> str:
    """The partition a file belongs to: its first path segment, or ``""`` for a root-level file.

    Empty is a usable name precisely because no directory can be called it, so root-level files never
    collide with a directory literally named ``default``.

    A split-named top-level directory (``train/``, ``test/``) is deliberately *not* a partition
    dimension. Grouping on it would split one dataset's train and test into unrelated partitions,
    each deriving its own schema and classification — the exact structure `splits` exists to model.
    Those files fall through to the same partition and are separated by :mod:`splits` instead.
    """
    parts = PurePosixPath(path).parts
    if len(parts) <= 1 or is_split_directory(parts[0]):
        return ""
    return parts[0]


def group_partitions(entries: list[FileEntry]) -> list[tuple[str, list[FileEntry]]]:
    """Group files into (name, files) partitions by top-level directory, sorted by name.

    The name *is* the identity — the shared path prefix, not a display string derived from it. A lone
    group under ``data/`` is named ``"data"``, not ``"default"``: reporting the latter discarded the
    only thing identifying the partition, and left two partitions that could share a name.

    Files whose top-level directory is a split name (``train/``, ``test/``) group under ``""``
    alongside root-level files: those are one dataset's splits, not separate partitions.
    """
    by_dir: dict[str, list[FileEntry]] = {}
    for entry in entries:
        by_dir.setdefault(_top_dir(entry.path), []).append(entry)

    if len(by_dir) == 1:
        # A single group is one partition holding everything, keeping whatever directory it came from.
        return [(next(iter(by_dir)), list(entries))]

    return sorted(by_dir.items())
