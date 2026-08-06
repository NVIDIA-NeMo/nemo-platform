# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A directly authored verifier bundle, without snapshot or diff machinery."""

import json
import shutil
from pathlib import Path

import pytest
from nemo_eval_author_plugin.eval_author.verifier_bundle import (
    VerifierBundleValidationError,
    finalize_verifier_bundle,
)
from nemo_experimentalist_plugin.entities import Dataset, Task


def _task(root: Path, task_id: str, files: dict[str, bytes]) -> Task:
    task_dir = root / task_id
    tests_dir = task_dir / "tests"
    tests_dir.mkdir(parents=True)
    for relative_path, content in files.items():
        destination = tests_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    return Task(id=task_id, uri=task_dir.as_uri())


def _bundle(root: Path, files: dict[str, bytes]) -> Path:
    bundle_root = root / "verifier-bundle"
    for relative_path, content in files.items():
        destination = bundle_root / "files" / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    return bundle_root


def test_finalizes_directly_authored_bundle(tmp_path: Path) -> None:
    files = {
        "check_tool.py": b"METRIC_KEY = 'uses_correct_tool'\n",
        "merge_metrics.py": b"# merge metric outputs\n",
    }
    dataset = Dataset(
        id="insight",
        tasks=[
            _task(tmp_path / "tasks", "task-a", files),
            _task(tmp_path / "tasks", "task-b", files),
        ],
    )
    bundle_root = _bundle(tmp_path, files)

    descriptor = finalize_verifier_bundle(
        bundle_root,
        dataset,
        metric_keys=("uses_correct_tool",),
    )
    manifest = json.loads((bundle_root / "manifest.json").read_text(encoding="utf-8"))

    assert descriptor.uri == bundle_root.resolve().as_uri()
    assert descriptor.identity == manifest["identity"]
    assert manifest["schema_version"] == 1
    assert manifest["metric_keys"] == ["uses_correct_tool"]
    assert [entry["path"] for entry in manifest["files"]] == [
        "check_tool.py",
        "merge_metrics.py",
    ]
    assert str(tmp_path) not in json.dumps(manifest)


def test_bundle_identity_ignores_task_order_and_absolute_root(tmp_path: Path) -> None:
    files = {"check.py": b"METRIC_KEY = 'policy_adherence'\n"}

    def finalize(root: Path, *, reverse: bool) -> str:
        tasks = [
            _task(root / "tasks", "task-a", files),
            _task(root / "tasks", "task-b", files),
        ]
        descriptor = finalize_verifier_bundle(
            _bundle(root, files),
            Dataset(id="insight", tasks=list(reversed(tasks)) if reverse else tasks),
            metric_keys=("policy_adherence",),
        )
        return descriptor.identity

    assert finalize(tmp_path / "first", reverse=False) == finalize(tmp_path / "second", reverse=True)


def test_rejects_bundle_not_installed_identically_in_every_task(tmp_path: Path) -> None:
    files = {"check.py": b"METRIC_KEY = 'policy_adherence'\n"}
    first = _task(tmp_path / "tasks", "task-a", files)
    second = _task(tmp_path / "tasks", "task-b", {"check.py": b"different\n"})

    with pytest.raises(VerifierBundleValidationError, match="task-b.*check.py"):
        finalize_verifier_bundle(
            _bundle(tmp_path, files),
            Dataset(id="insight", tasks=[first, second]),
            metric_keys=("policy_adherence",),
        )


def test_rejects_empty_or_symlinked_bundle(tmp_path: Path) -> None:
    task = _task(tmp_path / "tasks", "task-a", {})
    empty_bundle = _bundle(tmp_path / "empty", {})
    with pytest.raises(VerifierBundleValidationError, match="no files"):
        finalize_verifier_bundle(
            empty_bundle,
            Dataset(id="insight", tasks=[task]),
            metric_keys=("policy_adherence",),
        )

    bundle_root = _bundle(tmp_path / "linked", {})
    source = tmp_path / "source.py"
    source.write_text("metric = 1\n", encoding="utf-8")
    (bundle_root / "files").mkdir(parents=True)
    (bundle_root / "files" / "check.py").symlink_to(source)
    linked_task = _task(tmp_path / "linked-tasks", "task-a", {"check.py": source.read_bytes()})
    with pytest.raises(VerifierBundleValidationError, match="symbolic link"):
        finalize_verifier_bundle(
            bundle_root,
            Dataset(id="insight", tasks=[linked_task]),
            metric_keys=("policy_adherence",),
        )


def test_replaces_stale_manifest_only_after_success(tmp_path: Path) -> None:
    files = {"check.py": b"METRIC_KEY = 'policy_adherence'\n"}
    bundle_root = _bundle(tmp_path, files)
    manifest_path = bundle_root / "manifest.json"
    manifest_path.write_text('{"stale": true}\n', encoding="utf-8")
    task = _task(tmp_path / "tasks", "task-a", {"check.py": b"different\n"})

    with pytest.raises(VerifierBundleValidationError):
        finalize_verifier_bundle(
            bundle_root,
            Dataset(id="insight", tasks=[task]),
            metric_keys=("policy_adherence",),
        )
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == {"stale": True}

    shutil.copyfile(bundle_root / "files" / "check.py", tmp_path / "tasks" / "task-a" / "tests" / "check.py")
    finalize_verifier_bundle(
        bundle_root,
        Dataset(id="insight", tasks=[task]),
        metric_keys=("policy_adherence",),
    )
    assert "identity" in json.loads(manifest_path.read_text(encoding="utf-8"))
