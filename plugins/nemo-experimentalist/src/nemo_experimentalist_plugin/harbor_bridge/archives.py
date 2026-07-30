# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Archive transport that never follows links or accepts special files."""

from __future__ import annotations

import shutil
import stat
import tarfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

DEFAULT_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_ARCHIVE_FILES = 20_000
_IGNORED_PARTS = frozenset({".git", ".venv", "__pycache__"})


def _archive_paths(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in _IGNORED_PARTS for part in relative.parts):
            continue
        yield path


def _validate_source_path(path: Path, relative: Path) -> None:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ValueError(f"Archive source contains a symbolic link: {relative}")
    if stat.S_ISREG(mode) and path.stat().st_nlink > 1:
        raise ValueError(f"Archive source contains a hard-linked file: {relative}")
    if not stat.S_ISDIR(mode) and not stat.S_ISREG(mode):
        raise ValueError(f"Archive source contains a special file: {relative}")


def create_directory_archive(
    root: Path,
    destination: Path,
    *,
    max_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    max_files: int = DEFAULT_MAX_ARCHIVE_FILES,
) -> None:
    """Create a deterministic-safe tar archive without following links."""
    source = root.expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Archive source directory not found: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    entry_count = 0
    with tarfile.open(destination, mode="w:gz", dereference=False) as archive:
        for path in _archive_paths(source):
            relative = path.relative_to(source)
            _validate_source_path(path, relative)
            entry_count += 1
            if entry_count > max_files:
                raise ValueError(f"Archive source exceeds {max_files} entries")
            if path.is_file():
                total_bytes += path.stat().st_size
                if total_bytes > max_bytes:
                    raise ValueError(f"Archive source exceeds {max_bytes} uncompressed bytes")
            archive.add(path, arcname=relative.as_posix(), recursive=False)


def _validated_member_path(member: tarfile.TarInfo) -> PurePosixPath:
    path = PurePosixPath(member.name)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"Unsafe archive member path: {member.name!r}")
    if member.issym() or member.islnk() or member.isdev():
        raise ValueError(f"Unsupported archive member type: {member.name!r}")
    if not member.isdir() and not member.isfile():
        raise ValueError(f"Unsupported archive member type: {member.name!r}")
    return path


def extract_directory_archive(
    archive_path: Path,
    destination: Path,
    *,
    max_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    max_files: int = DEFAULT_MAX_ARCHIVE_FILES,
) -> None:
    """Extract a gzip tar after validating every path, type, count, and size."""
    if destination.exists():
        raise FileExistsError(f"Archive destination already exists: {destination}")
    destination.mkdir(parents=True)
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            if len(members) > max_files:
                raise ValueError(f"Archive exceeds {max_files} entries")
            normalized_names = [_validated_member_path(member).as_posix() for member in members]
            if len(set(normalized_names)) != len(normalized_names):
                raise ValueError("Archive contains duplicate member paths")
            total_bytes = sum(member.size for member in members if member.isfile())
            if total_bytes > max_bytes:
                raise ValueError(f"Archive exceeds {max_bytes} uncompressed bytes")

            for member in members:
                relative = _validated_member_path(member)
                target = destination.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    target.chmod(member.mode & 0o777)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(f"Archive file has no readable content: {member.name!r}")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(member.mode & 0o777)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
