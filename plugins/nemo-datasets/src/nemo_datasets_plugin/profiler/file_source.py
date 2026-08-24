# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The file-source seam.

The profiler core reads dataset files only through a :class:`FileSource`, so it never touches a
storage API directly. :class:`LocalFileSource` covers a directory on disk; a ranged-read source over
the Files storage API is a later drop-in behind the same two methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class FileEntry:
    """A file's identity — everything the profiler needs before it reads the contents."""

    path: str  # POSIX-style path relative to the source root
    size_bytes: int


class FileSource(Protocol):
    """Read-only access to a set of dataset files."""

    def list_files(self) -> list[FileEntry]:
        """Every file in the source, in a stable order."""
        ...

    def open(self, path: str) -> BinaryIO:
        """A binary, seekable stream for one file (``path`` as returned by :meth:`list_files`)."""
        ...


class LocalFileSource:
    """A directory of dataset files on the local filesystem."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        if not self._root.is_dir():
            raise NotADirectoryError(f"{self._root} is not a directory")

    def list_files(self) -> list[FileEntry]:
        entries = [
            FileEntry(path=path.relative_to(self._root).as_posix(), size_bytes=path.stat().st_size)
            for path in sorted(self._root.rglob("*"))
            if path.is_file()
        ]
        return entries

    def open(self, path: str) -> BinaryIO:
        return open(self._root / path, "rb")
