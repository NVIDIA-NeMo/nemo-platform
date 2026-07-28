# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validated archive transport for Harbor bridge inputs and results."""

from __future__ import annotations

import shutil
import tarfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Mapping
from urllib.parse import quote, unquote, urlparse

from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    EvaluationResult,
    ResourceRef,
)

BRIDGE_ARTIFACT_SCHEME = "nemo-harbor-bridge"
DEFAULT_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_ARCHIVE_FILES = 20_000
_IGNORED_PARTS = frozenset({".git", ".venv", "__pycache__"})


def _archive_paths(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in _IGNORED_PARTS for part in relative.parts):
            continue
        yield path


def create_directory_archive(
    root: Path,
    destination: Path,
    *,
    max_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    max_files: int = DEFAULT_MAX_ARCHIVE_FILES,
) -> None:
    """Archive one directory without following links or special files."""
    source = root.expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Archive source directory not found: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    entry_count = 0
    with tarfile.open(destination, mode="w:gz", dereference=False) as archive:
        for path in _archive_paths(source):
            relative = path.relative_to(source)
            entry_count += 1
            if entry_count > max_files:
                raise ValueError(f"Archive source exceeds {max_files} entries")
            if path.is_symlink():
                raise ValueError(f"Archive source contains a symbolic link: {relative}")
            if path.is_dir():
                archive.add(path, arcname=relative.as_posix(), recursive=False)
                continue
            if not path.is_file():
                raise ValueError(f"Archive source contains a special file: {relative}")
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
    """Extract a gzip tar after validating paths, types, counts, and sizes."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, mode="r:gz") as archive:
        members = archive.getmembers()
        if len(members) > max_files:
            raise ValueError(f"Archive exceeds {max_files} entries")
        member_names = [member.name for member in members]
        if len(set(member_names)) != len(member_names):
            raise ValueError("Archive contains duplicate member paths")
        files = [member for member in members if member.isfile()]
        total_bytes = sum(member.size for member in files)
        if total_bytes > max_bytes:
            raise ValueError(f"Archive exceeds {max_bytes} uncompressed bytes")

        for member in members:
            relative = _validated_member_path(member)
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"Archive file has no readable content: {member.name!r}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777)


def _result_resource_refs(result: EvaluationResult) -> Iterator[ResourceRef]:
    for trial in result.trials:
        if trial.trace is not None:
            yield trial.trace
        yield from trial.resources.values()
        for output in trial.outputs.values():
            if isinstance(output, ResourceRef):
                yield output
        for metric in trial.metrics.values():
            if metric.spec is not None and metric.spec.ref is not None:
                yield metric.spec.ref


def _bridge_uri(relative: Path) -> str:
    return f"{BRIDGE_ARTIFACT_SCHEME}:///{quote(relative.as_posix())}"


def _copy_external_resource(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ValueError(f"Evaluation resource is a symbolic link: {source}")
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True)
    elif source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    else:
        raise ValueError(f"Evaluation resource does not exist or is a special file: {source}")


def _rewrite_result_for_transport(
    result: EvaluationResult,
    artifact_root: Path,
    additional_resource_roots: Mapping[str, Path],
) -> EvaluationResult:
    transported = EvaluationResult.model_validate_json(result.model_dump_json())
    root = artifact_root.resolve()
    allowed_roots = {label: path.expanduser().resolve() for label, path in additional_resource_roots.items()}
    for resource in _result_resource_refs(transported):
        parsed = urlparse(resource.uri)
        if parsed.scheme not in ("", "file"):
            continue
        raw_path = unquote(parsed.path) if parsed.scheme == "file" else resource.uri
        path = Path(raw_path).expanduser().resolve()
        try:
            relative = path.relative_to(root)
        except ValueError:
            for label, allowed_root in allowed_roots.items():
                try:
                    external_relative = path.relative_to(allowed_root)
                except ValueError:
                    continue
                relative = Path("_bridge_resources") / label / external_relative
                _copy_external_resource(path, root / relative)
                break
            else:
                raise ValueError(f"Evaluation resource escapes the bridge artifact roots: {path}") from None
        resource.uri = _bridge_uri(relative)
    return transported


def create_result_archive(
    result: EvaluationResult,
    artifact_root: Path,
    destination: Path,
    *,
    additional_resource_roots: Mapping[str, Path] | None = None,
    max_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    max_files: int = DEFAULT_MAX_ARCHIVE_FILES,
) -> None:
    """Bundle an evaluation result and every referenced Harbor artifact."""
    root = artifact_root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Bridge artifact root not found: {root}")
    transported = _rewrite_result_for_transport(result, root, additional_resource_roots or {})
    destination.parent.mkdir(parents=True, exist_ok=True)
    result_path = destination.with_name(f"{destination.name}.result.json")
    result_path.write_text(transported.model_dump_json(indent=2), encoding="utf-8")
    try:
        total_bytes = result_path.stat().st_size
        entry_count = 1
        if total_bytes > max_bytes:
            raise ValueError(f"Bridge result exceeds {max_bytes} uncompressed bytes")
        with tarfile.open(destination, mode="w:gz", dereference=False) as archive:
            for path in _archive_paths(root):
                relative = path.relative_to(root)
                entry_count += 1
                if entry_count > max_files:
                    raise ValueError(f"Bridge result exceeds {max_files} entries")
                if path.is_symlink():
                    raise ValueError(f"Bridge artifact contains a symbolic link: {relative}")
                if not path.is_dir() and not path.is_file():
                    raise ValueError(f"Bridge artifact contains a special file: {relative}")
                if path.is_file():
                    total_bytes += path.stat().st_size
                    if total_bytes > max_bytes:
                        raise ValueError(f"Bridge result exceeds {max_bytes} uncompressed bytes")
                archive.add(path, arcname=relative.as_posix(), recursive=False)
            archive.add(result_path, arcname="result.json", recursive=False)
    finally:
        result_path.unlink(missing_ok=True)


def materialize_result_archive(archive_path: Path, destination: Path) -> EvaluationResult:
    """Extract a bridge result and rewrite artifact URIs to local file URIs."""
    extract_directory_archive(archive_path, destination)
    result_path = destination / "result.json"
    if not result_path.is_file():
        raise ValueError("Harbor bridge response does not contain result.json")
    result = EvaluationResult.model_validate_json(result_path.read_text(encoding="utf-8"))
    root = destination.resolve()
    for resource in _result_resource_refs(result):
        parsed = urlparse(resource.uri)
        if parsed.scheme != BRIDGE_ARTIFACT_SCHEME:
            continue
        if parsed.netloc:
            raise ValueError(f"Bridge artifact URI must not contain an authority: {resource.uri}")
        relative = PurePosixPath(unquote(parsed.path).lstrip("/"))
        if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
            raise ValueError(f"Unsafe bridge artifact URI: {resource.uri}")
        local_path = root.joinpath(*relative.parts).resolve()
        try:
            local_path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Bridge artifact URI escapes the result directory: {resource.uri}") from exc
        resource.uri = local_path.as_uri()
    result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result
