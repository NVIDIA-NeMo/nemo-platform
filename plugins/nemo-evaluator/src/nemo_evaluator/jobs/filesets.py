# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fileset helpers for evaluator plugin datasets."""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

import fsspec.asyn
from nemo_evaluator.sdk.types import FilesetRef
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform.filesets import FilesetFileSystem

_GLOB_CHARS = {"*", "?", "["}


def is_fileset_glob_pattern(pattern: str) -> bool:
    """Return True when a fileset fragment contains glob wildcards."""
    return any(char in pattern for char in _GLOB_CHARS)


def _match_path_parts(path_parts: tuple[str, ...], pattern_parts: tuple[str, ...]) -> bool:
    if not pattern_parts:
        return not path_parts

    pattern_part = pattern_parts[0]
    remaining_pattern = pattern_parts[1:]
    if pattern_part == "**":
        return _match_path_parts(path_parts, remaining_pattern) or (
            bool(path_parts) and _match_path_parts(path_parts[1:], pattern_parts)
        )

    if not path_parts:
        return False
    return fnmatchcase(path_parts[0], pattern_part) and _match_path_parts(path_parts[1:], remaining_pattern)


def matches_fileset_glob(filepath: str, pattern: str) -> bool:
    """Return True when a fileset-relative path matches a root-anchored glob pattern."""
    normalized_path = filepath.strip("/")
    normalized_pattern = pattern.strip("/")
    if not normalized_path or not normalized_pattern:
        return False
    return _match_path_parts(tuple(normalized_path.split("/")), tuple(normalized_pattern.split("/")))


def fileset_glob_prefix_dir(pattern: str) -> str:
    """Return the stable directory prefix before the first glob wildcard."""
    pattern = pattern.lstrip("/")
    if not pattern or not is_fileset_glob_pattern(pattern):
        return pattern

    first_wildcard = min(index for index, char in enumerate(pattern) if char in _GLOB_CHARS)
    prefix = pattern[:first_wildcard]
    if "/" not in prefix:
        return ""
    return prefix.rsplit("/", 1)[0]


def normalize_fileset_path(path: str) -> str:
    """Normalize a fileset reference with an optional fragment for local paths."""
    if "#" not in path:
        return path

    base, fragment = path.split("#", 1)
    fragment = fragment.lstrip("/")
    if not fragment:
        return base
    if is_fileset_glob_pattern(fragment):
        dir_prefix = fileset_glob_prefix_dir(fragment)
        return f"{base}/{dir_prefix}" if dir_prefix else base
    return f"{base}/{fragment}"


async def dataset_exists(
    sdk: AsyncNeMoPlatform,
    dataset: FilesetRef,
) -> bool:
    """Return whether the FilesetRef exists, including optional fragments."""
    fs = FilesetFileSystem(sdk=sdk)
    ref = dataset.root

    if "#" not in ref:
        return await fs._exists(ref)

    base_path, pattern = ref.split("#", 1)
    pattern = pattern.lstrip("/")
    if not await fs._exists(base_path):
        return False
    if not pattern:
        return True
    if is_fileset_glob_pattern(pattern):
        prefix_dir = fileset_glob_prefix_dir(pattern)
        if prefix_dir:
            return await fs._exists(f"{base_path}/{prefix_dir}")
        return True
    return await fs._exists(f"{base_path}/{pattern}")


async def _download_fileset_ref(
    sdk: AsyncNeMoPlatform,
    dataset: FilesetRef,
    destination: str,
    recursive: bool = True,
) -> Path:
    fs = FilesetFileSystem(sdk=sdk)
    ref = dataset.root

    if "#" not in ref:
        dest = Path(destination) / normalize_fileset_path(ref)
        source = ref.rstrip("/") + "/"
        await fs._get(source, str(dest), recursive=recursive)
        return dest

    base_path, pattern = ref.split("#", 1)
    pattern = pattern.lstrip("/")
    if not pattern:
        return await _download_fileset_ref(sdk, FilesetRef(root=base_path), destination, recursive=recursive)

    base_dest = Path(destination) / base_path
    base_dest.mkdir(parents=True, exist_ok=True)
    if is_fileset_glob_pattern(pattern):
        all_files = await fs._find(base_path)
        for file_path in all_files:
            relative_path = (
                file_path.split("#", 1)[1] if "#" in file_path else file_path.replace(base_path + "/", "", 1)
            )
            if matches_fileset_glob(relative_path, pattern):
                file_dest = base_dest / relative_path
                file_dest.parent.mkdir(parents=True, exist_ok=True)
                await fs._get_file(file_path, str(file_dest))
        return base_dest

    full_remote_path = f"{base_path}/{pattern}"
    file_dest = base_dest / pattern
    file_dest.parent.mkdir(parents=True, exist_ok=True)
    await fs._get_file(full_remote_path, str(file_dest))
    return file_dest


def _download_fileset_ref_sync(
    sdk: NeMoPlatform,
    dataset: FilesetRef,
    destination: str,
    recursive: bool = True,
) -> Path:
    fs = FilesetFileSystem(sdk=sdk)

    async def _impl() -> Path:
        try:
            return await _download_fileset_ref(fs._sdk, dataset, destination, recursive=recursive)
        finally:
            await fs._sdk.close()

    return fsspec.asyn.sync(fs.loop, _impl)


async def download_dataset(
    sdk: AsyncNeMoPlatform,
    dataset: FilesetRef,
    destination: str,
    recursive: bool = True,
) -> Path:
    """Download a persisted fileset dataset to a local directory."""
    return await _download_fileset_ref(sdk, dataset, destination, recursive=recursive)


def download_dataset_sync(
    sdk: NeMoPlatform,
    dataset: FilesetRef,
    destination: str,
    recursive: bool = True,
) -> Path:
    """Download a persisted fileset dataset using the sync platform SDK."""
    return _download_fileset_ref_sync(sdk, dataset, destination, recursive=recursive)
