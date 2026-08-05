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


def _top_dir(path: str) -> str | None:
    """The partition directory for a file: its first path segment, else None for a root-level file.

    A split-named top-level directory (``train/``, ``test/``) is deliberately *not* a partition
    dimension. Grouping on it would split one dataset's train and test into unrelated partitions,
    each deriving its own schema and classification — the exact structure `splits` exists to model.
    Those files fall through to the same partition and are separated by :mod:`splits` instead.
    """
    parts = PurePosixPath(path).parts
    if len(parts) <= 1 or is_split_directory(parts[0]):
        return None
    return parts[0]


def group_partitions(entries: list[FileEntry]) -> list[tuple[str | None, list[FileEntry]]]:
    """Group files into (source_dir, files) partitions by top-level directory.

    Returns the *directory*, not a label — ``None`` for files at the fileset root. The label is the
    caller's to derive, because the two are not the same thing: a lone group under ``data/`` labels
    as "default" while its identity stays ``"data"``, and root-level files are a different partition
    from a directory literally named ``default`` even though both label the same way. Collapsing
    those into one string is what let a partition collide with another, and what let an unrelated
    file rename one out of existence.

    Files whose top-level directory is a split name (``train/``, ``test/``) group under ``None``
    alongside root-level files: those are one dataset's splits, not separate partitions.
    """
    by_dir: dict[str | None, list[FileEntry]] = {}
    for entry in entries:
        by_dir.setdefault(_top_dir(entry.path), []).append(entry)

    if len(by_dir) == 1:
        # A single group is one partition holding everything, whatever its directory happened to be.
        return [(next(iter(by_dir)), list(entries))]

    return sorted(by_dir.items(), key=lambda item: (item[0] is None, item[0] or ""))
