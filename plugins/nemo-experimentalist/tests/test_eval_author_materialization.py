# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for persisted Eval Author insight suites."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from nemo_experimentalist_plugin.eval_author import materialization as materialization_module
from nemo_experimentalist_plugin.eval_author.materialization import InsightSuite
from nemo_experimentalist_plugin.experimentalist.components.evaluator import Task
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborDataset
from nemo_platform import AsyncNeMoPlatform


@dataclass(frozen=True, slots=True)
class _FakeFileset:
    id: str
    name: str
    workspace: str


@dataclass(frozen=True, slots=True)
class _FakeRemoteFile:
    path: str
    size: int


@dataclass(frozen=True, slots=True)
class _FakeFileList:
    data: list[_FakeRemoteFile]


class _FakeFilesets:
    def __init__(self, files: _FakeFiles) -> None:
        self._files = files
        self.created: list[str] = []
        self.deleted: list[str] = []

    async def create(self, *, workspace: str, name: str, **_: Any) -> _FakeFileset:
        fileset = _FakeFileset(id=f"fileset-id-{len(self.created) + 1}", name=name, workspace=workspace)
        self.created.append(name)
        self._files.contents[name] = {}
        return fileset

    async def delete(self, name: str, *, workspace: str) -> _FakeFileset:
        self.deleted.append(name)
        self._files.contents.pop(name)
        return _FakeFileset(id="deleted", name=name, workspace=workspace)


class _FakeFiles:
    def __init__(self) -> None:
        self.contents: dict[str, dict[str, int]] = {}
        self.fail_upload = False
        self.omit_from_listing: str | None = None
        self.filesets = _FakeFilesets(self)

    async def upload(self, *, local_path: str, fileset: str, **_: Any) -> _FakeFileset:
        if self.fail_upload:
            raise RuntimeError("upload failed")
        root = Path(local_path)
        self.contents[fileset] = {
            path.relative_to(root).as_posix(): path.stat().st_size for path in root.rglob("*") if path.is_file()
        }
        return _FakeFileset(id="uploaded", name=fileset, workspace="workspace-a")

    async def list(self, *, fileset: str, **_: Any) -> _FakeFileList:
        return _FakeFileList(
            data=[
                _FakeRemoteFile(path=path, size=size)
                for path, size in self.contents[fileset].items()
                if path != self.omit_from_listing
            ]
        )


class _FakeClient:
    def __init__(self) -> None:
        self.files = _FakeFiles()


def _write_template(root: Path) -> Task:
    root.mkdir(parents=True)
    (root / "task.toml").write_text(
        """
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

schema_version = "1.1"

[task]
name = "example/template__placeholder"

[metadata]
difficulty = "easy"

[environment]
build_timeout_sec = 60.0
""".lstrip(),
        encoding="utf-8",
    )
    (root / "instruction.md").write_text("{{ instruction }}\n", encoding="utf-8")
    environment = root / "environment"
    environment.mkdir()
    (environment / "Dockerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test.sh").write_text("#!/bin/sh\nmkdir -p /logs/verifier\necho 1 > /logs/verifier/reward.txt\n")
    return Task(id="task-template", uri=root.as_uri())


def test_insight_suite_publishes_discoverable_tasks_with_provenance(tmp_path: Path) -> None:
    template = _write_template(tmp_path / "template")
    refs = ["intake/traces/unsafe ref", "intake/traces/unsafe ref"]
    suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight/unsafe id", task_template=template)

    staged = suite.stage(refs)
    for index, task in enumerate(staged, start=1):
        (task.path / "instruction.md").write_text(f"Reproduce production scenario {index}.\n", encoding="utf-8")
        suite.validate(task)
    dataset = suite.promote_local(refs, staged)

    assert suite.suite_dir == next((tmp_path / "eval-and-optimize" / "eval_author").iterdir()) / "insight-suite"
    assert [task.id for task in dataset.list_tasks()] == [task.slug for task in staged]
    assert len(HarborDataset.from_path(suite.suite_dir).list_tasks()) == 2
    names: list[str] = []
    for trace_ref, task in zip(refs, dataset.list_tasks(), strict=True):
        task_dir = Path(task.uri.removeprefix("file://"))
        config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
        task_toml = (task_dir / "task.toml").read_text(encoding="utf-8")
        names.append(config["task"]["name"])
        assert "# SPDX-License-Identifier: Apache-2.0" in task_toml
        assert config["metadata"]["nemo_experimentalist"] == {
            "source_trace_ref": trace_ref,
            "insight_id": "insight/unsafe id",
        }
        assert (task_dir / "instruction.md").read_text(encoding="utf-8").strip()
        assert (task_dir / "environment").is_dir()
        assert (task_dir / "tests").is_dir()
    assert len(set(names)) == 2
    assert all(name.startswith("example/template__") for name in names)

    manifest = json.loads((suite.suite_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["insight_id"] == "insight/unsafe id"
    assert manifest["trace_refs"] == refs
    assert manifest["task_template"] == {"uri": template.uri}
    assert [task["source_trace_ref"] for task in manifest["tasks"]] == refs


@pytest.mark.asyncio
async def test_insight_suite_uploads_complete_suite_to_fresh_filesets(tmp_path: Path) -> None:
    template = _write_template(tmp_path / "template")
    suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight/unsafe id", task_template=template)
    staged = suite.stage(["trace-1"])
    (staged[0].path / "instruction.md").write_text("Generated instruction.\n", encoding="utf-8")
    suite.validate(staged[0])
    suite.promote_local(["trace-1"], staged)
    client = _FakeClient()

    first_ref = await suite.publish_fileset(cast(AsyncNeMoPlatform, client), "workspace-a")
    second_ref = await suite.publish_fileset(cast(AsyncNeMoPlatform, client), "workspace-a")

    assert first_ref.uri.startswith("fileset://workspace-a/nemo-experimentalist-insight-insight-unsafe-id-")
    assert second_ref.uri.startswith("fileset://workspace-a/nemo-experimentalist-insight-insight-unsafe-id-")
    assert first_ref.uri != second_ref.uri
    assert first_ref.metadata["insight_id"] == "insight/unsafe id"
    assert first_ref.metadata["fileset_id"] == "fileset-id-1"
    assert first_ref.metadata["workspace"] == "workspace-a"
    first_name = cast(str, first_ref.metadata["fileset_name"])
    assert "manifest.json" in client.files.contents[first_name]
    assert any(path.endswith("/task.toml") for path in client.files.contents[first_name])
    assert client.files.filesets.deleted == []


@pytest.mark.asyncio
async def test_failed_fileset_upload_removes_only_incomplete_artifact(tmp_path: Path) -> None:
    template = _write_template(tmp_path / "template")
    suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    staged = suite.stage(["trace-1"])
    (staged[0].path / "instruction.md").write_text("Generated instruction.\n", encoding="utf-8")
    suite.validate(staged[0])
    suite.promote_local(["trace-1"], staged)
    client = _FakeClient()
    published_ref = await suite.publish_fileset(cast(AsyncNeMoPlatform, client), "workspace-a")
    published_name = cast(str, published_ref.metadata["fileset_name"])
    published_contents = dict(client.files.contents[published_name])
    client.files.fail_upload = True

    with pytest.raises(RuntimeError, match="upload failed"):
        await suite.publish_fileset(cast(AsyncNeMoPlatform, client), "workspace-a")

    failed_name = client.files.filesets.created[-1]
    assert client.files.filesets.deleted == [failed_name]
    assert failed_name not in client.files.contents
    assert client.files.contents[published_name] == published_contents


@pytest.mark.asyncio
async def test_fileset_inventory_mismatch_fails_and_removes_incomplete_artifact(tmp_path: Path) -> None:
    template = _write_template(tmp_path / "template")
    suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    staged = suite.stage(["trace-1"])
    (staged[0].path / "instruction.md").write_text("Generated instruction.\n", encoding="utf-8")
    suite.validate(staged[0])
    suite.promote_local(["trace-1"], staged)
    client = _FakeClient()
    client.files.omit_from_listing = "manifest.json"

    with pytest.raises(RuntimeError, match="does not match the validated local suite"):
        await suite.publish_fileset(cast(AsyncNeMoPlatform, client), "workspace-a")

    failed_name = client.files.filesets.created[-1]
    assert client.files.filesets.deleted == [failed_name]
    assert failed_name not in client.files.contents


def test_insight_suite_second_publication_replaces_first_at_stable_path(tmp_path: Path) -> None:
    template = _write_template(tmp_path / "template")
    refs = ["trace-1"]
    first_suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    first_staged = first_suite.stage(refs)
    (first_staged[0].path / "instruction.md").write_text("First generated instruction.\n", encoding="utf-8")
    first_suite.validate(first_staged[0])
    first_suite.promote_local(refs, first_staged)
    published_path = first_suite.suite_dir

    second_suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    second_staged = second_suite.stage(refs)
    (second_staged[0].path / "instruction.md").write_text("Second generated instruction.\n", encoding="utf-8")
    second_suite.validate(second_staged[0])
    second_suite.promote_local(refs, second_staged)

    assert second_suite.suite_dir == published_path
    task = list(HarborDataset.from_path(published_path).list_tasks())[0]
    task_dir = Path(task.uri.removeprefix("file://"))
    assert (task_dir / "instruction.md").read_text(encoding="utf-8") == "Second generated instruction.\n"


def test_failed_rebuild_preserves_previous_published_suite(tmp_path: Path) -> None:
    template = _write_template(tmp_path / "template")
    refs = ["trace-1"]
    first_suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    first_staged = first_suite.stage(refs)
    (first_staged[0].path / "instruction.md").write_text("Valid published instruction.\n", encoding="utf-8")
    first_suite.validate(first_staged[0])
    first_suite.promote_local(refs, first_staged)

    failed_suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    failed_staged = failed_suite.stage(refs)
    (failed_staged[0].path / "instruction.md").write_text("\n", encoding="utf-8")

    with pytest.raises(ValueError, match="instruction is missing or empty"):
        failed_suite.validate(failed_staged[0])

    task = list(HarborDataset.from_path(first_suite.suite_dir).list_tasks())[0]
    task_dir = Path(task.uri.removeprefix("file://"))
    assert (task_dir / "instruction.md").read_text(encoding="utf-8") == "Valid published instruction.\n"


def test_post_promotion_validation_failure_restores_previous_suite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = _write_template(tmp_path / "template")
    refs = ["trace-1"]
    first_suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    first_staged = first_suite.stage(refs)
    (first_staged[0].path / "instruction.md").write_text("Previously published.\n", encoding="utf-8")
    first_suite.validate(first_staged[0])
    first_suite.promote_local(refs, first_staged)

    failed_suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    failed_staged = failed_suite.stage(refs)
    (failed_staged[0].path / "instruction.md").write_text("Broken promotion.\n", encoding="utf-8")
    failed_suite.validate(failed_staged[0])

    def fail_post_promotion_validation(_: Path) -> None:
        raise RuntimeError("post-promotion validation failed")

    monkeypatch.setattr(materialization_module, "HarborTask", fail_post_promotion_validation)

    with pytest.raises(RuntimeError, match="post-promotion validation failed"):
        failed_suite.promote_local(refs, failed_staged)

    task = list(HarborDataset.from_path(first_suite.suite_dir).list_tasks())[0]
    task_dir = Path(task.uri.removeprefix("file://"))
    assert (task_dir / "instruction.md").read_text(encoding="utf-8") == "Previously published.\n"
    assert list(first_suite.root.glob(".insight-suite-backup-*")) == []


def test_insight_suite_rejects_empty_instruction_before_publication(tmp_path: Path) -> None:
    template = _write_template(tmp_path / "template")
    suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    staged = suite.stage(["trace-1"])
    (staged[0].path / "instruction.md").write_text("\n", encoding="utf-8")

    with pytest.raises(ValueError, match="instruction is missing or empty"):
        suite.validate(staged[0])

    assert not suite.suite_dir.exists()


def test_discard_removes_candidate_and_allows_restaging(tmp_path: Path) -> None:
    template = _write_template(tmp_path / "template")
    suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    staged = suite.stage(["trace-1"])
    candidate_root = staged[0].path.parent.parent

    suite.discard()

    assert not candidate_root.exists()
    restaged = suite.stage(["trace-2"])
    assert len(restaged) == 1
    suite.discard()
    assert not restaged[0].path.exists()


def test_insight_suite_records_analysis_without_removing_failed_tasks(tmp_path: Path) -> None:
    template = _write_template(tmp_path / "template")
    suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    staged = suite.stage(["trace-good", "trace-bad"])
    for task in staged:
        (task.path / "instruction.md").write_text(f"Run {task.trace_ref}.\n", encoding="utf-8")
        suite.validate(task)
    suite.promote_local([task.trace_ref for task in staged], staged)

    suite.record_analysis(
        {
            staged[0].slug: ("completed", None),
            staged[1].slug: ("failed", "analysis failed"),
        }
    )

    manifest = json.loads((suite.suite_dir / "manifest.json").read_text(encoding="utf-8"))
    assert [task["analysis"] for task in manifest["tasks"]] == [
        {"status": "completed"},
        {"error": "analysis failed", "status": "failed"},
    ]
    assert len(HarborDataset.from_path(suite.suite_dir).list_tasks()) == 2
