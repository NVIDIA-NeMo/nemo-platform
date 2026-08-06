# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Finalize verifier files authored explicitly for reuse."""

import hashlib
import json
import os
from pathlib import Path

from nemo_eval_author_plugin.eval_author.models import ArtifactDescriptor
from nemo_experimentalist_plugin.entities import Dataset, DatasetValidationError, local_path_from_uri

_SCHEMA_VERSION = 1


class VerifierBundleValidationError(DatasetValidationError):
    """The authored verifier bundle is missing or inconsistent with its tasks."""


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _bundle_files(bundle_root: Path) -> tuple[tuple[str, bytes], ...]:
    files_root = bundle_root / "files"
    if not files_root.is_dir():
        raise VerifierBundleValidationError("authored verifier bundle contains no files")

    files: list[tuple[str, bytes]] = []
    for path in sorted(files_root.rglob("*")):
        if path.is_symlink():
            raise VerifierBundleValidationError(
                f"authored verifier bundle contains a symbolic link: {path.relative_to(files_root).as_posix()}"
            )
        if path.is_file():
            files.append((path.relative_to(files_root).as_posix(), path.read_bytes()))
    if not files:
        raise VerifierBundleValidationError("authored verifier bundle contains no files")
    return tuple(files)


def _manifest(metric_keys: tuple[str, ...], files: tuple[tuple[str, bytes], ...]) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "metric_keys": list(metric_keys),
        "files": [{"path": path, "sha256": _sha256(content)} for path, content in files],
    }


def _identity(metric_keys: tuple[str, ...], files: tuple[tuple[str, bytes], ...]) -> str:
    manifest = json.dumps(
        _manifest(metric_keys, files),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(manifest)
    for _, content in files:
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def finalize_verifier_bundle(
    bundle_root: Path,
    dataset: Dataset,
    *,
    metric_keys: tuple[str, ...],
) -> ArtifactDescriptor:
    """Validate the directly authored bundle against every task and write its manifest."""
    files = _bundle_files(bundle_root)
    tasks = dataset.list_tasks()
    if not tasks:
        raise VerifierBundleValidationError("cannot finalize a verifier bundle for an empty task set")

    for task in tasks:
        if not task.uri:
            raise VerifierBundleValidationError(f"generated task {task.id!r} has no URI")
        tests_dir = local_path_from_uri(task.uri, context=f"generated task {task.id!r}").resolve() / "tests"
        for relative_path, expected in files:
            installed = tests_dir / relative_path
            if installed.is_symlink() or not installed.is_file() or installed.read_bytes() != expected:
                raise VerifierBundleValidationError(
                    f"generated task {task.id!r} does not contain verifier bundle file {relative_path!r}"
                )

    identity = _identity(metric_keys, files)
    manifest_path = bundle_root / "manifest.json"
    pending_path = bundle_root / "manifest.json.pending"
    pending_path.write_text(
        json.dumps(
            {
                **_manifest(metric_keys, files),
                "identity": identity,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(pending_path, manifest_path)
    return ArtifactDescriptor(uri=bundle_root.resolve().as_uri(), identity=identity)
