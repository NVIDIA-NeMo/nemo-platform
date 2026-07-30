# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Security contract tests that do not require Docker or OpenShell."""

from __future__ import annotations

import io
import os
import shutil
import tarfile
from pathlib import Path
from typing import cast

import pytest
from nemo_experimentalist_plugin.harbor_bridge.archives import (
    create_directory_archive,
    extract_directory_archive,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    EnvelopeTask,
    EvaluationSubmission,
)
from nemo_experimentalist_plugin.harbor_bridge.envelopes import (
    ENVELOPE_DESCRIPTOR_FILENAME,
    TrustedEnvelopeCatalog,
    create_overlay_directory,
    register_dataset_envelope,
    resolve_envelope_task,
    tree_digest,
)
from pydantic import ValidationError

_DIGEST = f"sha256:{'0' * 64}"


def _metadata() -> dict[str, object]:
    return {
        "schema_version": 1,
        "request_id": "candidate-004-validation",
        "envelope": {
            "id": "fixture-0123456789abcdef",
            "digest": _DIGEST,
            "tasks": [{"task_id": "generated-trace-004", "base_task_id": "base-task"}],
        },
        "candidate": {"digest": _DIGEST},
        "overlay": {"digest": _DIGEST},
        "run_profile": "smoke",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("image", "attacker/image:latest"),
        ("mounts", ["/Users/ryan:/host"]),
        ("env", {"NVIDIA_API_KEY": "something-else"}),
        ("agent_import_path", "candidate.module:Agent"),
        ("verifier_mode", "shared"),
        ("docker", {"privileged": True}),
    ],
)
def test_submission_rejects_unknown_authority(field: str, value: object) -> None:
    payload = _metadata()
    payload[field] = value
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvaluationSubmission.model_validate(payload)


def test_submission_rejects_nested_unknown_fields() -> None:
    payload = _metadata()
    envelope = cast(dict[str, object], payload["envelope"])
    envelope["image"] = "attacker/image:latest"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvaluationSubmission.model_validate(payload)


def _write_tar(path: Path, members: list[tarfile.TarInfo]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for member in members:
            content = io.BytesIO(b"x")
            if member.isfile():
                member.size = 1
                archive.addfile(member, content)
            else:
                archive.addfile(member)


@pytest.mark.parametrize(
    "member",
    [
        tarfile.TarInfo("../escape"),
        tarfile.TarInfo("/absolute"),
        tarfile.TarInfo("safe/../escape"),
        tarfile.TarInfo("safe-link"),
        tarfile.TarInfo("hard-link"),
    ],
)
def test_archive_rejects_traversal_and_links(tmp_path: Path, member: tarfile.TarInfo) -> None:
    if member.name == "safe-link":
        member.type = tarfile.SYMTYPE
        member.linkname = "target"
    elif member.name == "hard-link":
        member.type = tarfile.LNKTYPE
        member.linkname = "target"
    archive = tmp_path / "input.tar.gz"
    _write_tar(archive, [member])
    with pytest.raises(ValueError, match="Unsafe archive|Unsupported archive"):
        extract_directory_archive(archive, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_archive_rejects_duplicate_paths(tmp_path: Path) -> None:
    archive = tmp_path / "input.tar.gz"
    _write_tar(archive, [tarfile.TarInfo("same"), tarfile.TarInfo("same")])
    with pytest.raises(ValueError, match="duplicate"):
        extract_directory_archive(archive, tmp_path / "output")


def test_archive_source_rejects_hard_links(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    first = source / "first"
    first.write_text("content", encoding="utf-8")
    os.link(first, source / "second")
    with pytest.raises(ValueError, match="hard-linked"):
        create_directory_archive(source, tmp_path / "output.tar.gz")


def _task_dataset(tmp_path: Path) -> Path:
    dataset = tmp_path / "source"
    task = dataset / "base-task"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "task.toml").write_text(
        """
[task]
name = "fixture/base-task"

[environment]
type = "docker"

[verifier]
""".lstrip(),
        encoding="utf-8",
    )
    (task / "environment" / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (task / "instruction.md").write_text("trusted instruction\n", encoding="utf-8")
    (task / "data.json").write_text("{}\n", encoding="utf-8")
    (task / "tests" / "test.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (task / "nemo-task-envelope.json").write_text(
        """
{
  "schema_version": 1,
  "task_data": [
    {"path": "instruction.md", "media_type": "text/plain", "max_bytes": 65536},
    {"path": "data.json", "media_type": "application/json", "max_bytes": 1024}
  ],
  "verifier_paths": ["tests"]
}
""".lstrip(),
        encoding="utf-8",
    )
    return dataset


def test_catalog_materializes_only_declared_overlays(tmp_path: Path) -> None:
    source = _task_dataset(tmp_path)
    registered = register_dataset_envelope(source, catalog_root=tmp_path / "catalog", name="fixture")
    working = tmp_path / "working"
    shutil.copytree(registered.dataset_path, working)
    task = working / "base-task"
    (task / "instruction.md").write_text("generated instruction\n", encoding="utf-8")
    (task / "task.toml").write_text('[task]\nname = "attacker/replacement"\n', encoding="utf-8")

    binding = resolve_envelope_task(working, task, task_id="generated-task")
    overlay = tmp_path / "overlay"
    overlay_digest = create_overlay_directory([binding], overlay)
    assert overlay_digest is not None
    assert (overlay / "generated-task" / "instruction.md").read_text() == "generated instruction\n"
    assert not (overlay / "generated-task" / "task.toml").exists()

    materialized = tmp_path / "materialized"
    TrustedEnvelopeCatalog(tmp_path / "catalog").materialize(
        envelope_id=registered.manifest.envelope_id,
        envelope_digest=registered.manifest.envelope_digest,
        selections=[EnvelopeTask(task_id="generated-task", base_task_id="base-task")],
        destination=materialized,
        overlay_dir=overlay,
    )
    generated = materialized / "generated-task"
    assert (generated / "instruction.md").read_text() == "generated instruction\n"
    assert "fixture/base-task__generated-task" in (generated / "task.toml").read_text()
    assert not (generated / ENVELOPE_DESCRIPTOR_FILENAME).exists()


@pytest.mark.parametrize("path", ["task.toml", "Dockerfile", ".dockerignore", "compose.yaml"])
def test_catalog_rejects_runtime_control_overlays(tmp_path: Path, path: str) -> None:
    source = _task_dataset(tmp_path)
    registered = register_dataset_envelope(source, catalog_root=tmp_path / "catalog", name="fixture")
    overlay = tmp_path / "overlay" / "generated-task"
    overlay.mkdir(parents=True)
    (overlay / path).write_text("attacker-controlled\n", encoding="utf-8")

    with pytest.raises(ValueError, match="runtime-control|undeclared"):
        TrustedEnvelopeCatalog(tmp_path / "catalog").materialize(
            envelope_id=registered.manifest.envelope_id,
            envelope_digest=registered.manifest.envelope_digest,
            selections=[EnvelopeTask(task_id="generated-task", base_task_id="base-task")],
            destination=tmp_path / "materialized",
            overlay_dir=tmp_path / "overlay",
        )


def test_catalog_detects_tampering_before_materialization(tmp_path: Path) -> None:
    source = _task_dataset(tmp_path)
    registered = register_dataset_envelope(source, catalog_root=tmp_path / "catalog", name="fixture")
    (registered.dataset_path / "base-task" / "task.toml").write_text("[task]\nname='tampered/task'\n")
    with pytest.raises(ValueError, match="changed after registration"):
        TrustedEnvelopeCatalog(tmp_path / "catalog").load(
            registered.manifest.envelope_id,
            registered.manifest.envelope_digest,
        )


def test_digest_covers_file_modes(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    path = root / "script"
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o644)
    before = tree_digest(root)
    path.chmod(0o755)
    assert tree_digest(root) != before
