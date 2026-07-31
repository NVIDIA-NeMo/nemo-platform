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


def group_partitions(entries: list[FileEntry]) -> list[tuple[str, list[FileEntry]]]:
    """Group files into (name, files) partitions by top-level directory.

    A single top-level group — every file at the root, or all under one container like ``data/`` —
    is one "default" partition. Multiple top-level directories (e.g. ``main/`` and ``socratic/``)
    each become their own partition, named after the directory; root-level files fall under
    "default".
    """
    by_dir: dict[str | None, list[FileEntry]] = {}
    for entry in entries:
        by_dir.setdefault(_top_dir(entry.path), []).append(entry)

    if len(by_dir) == 1:
        return [("default", list(entries))]

    ordered = sorted(by_dir.items(), key=lambda item: (item[0] is None, item[0] or ""))
    return [("default" if directory is None else directory, files) for directory, files in ordered]
