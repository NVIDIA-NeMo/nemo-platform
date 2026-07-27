# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for persisted Eval Author insight suites."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from nemo_experimentalist_plugin.eval_author import materialization as materialization_module
from nemo_experimentalist_plugin.eval_author.materialization import InsightSuite
from nemo_experimentalist_plugin.experimentalist.components.evaluator import Task
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborDataset


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


def test_insight_suite_materializes_discoverable_tasks_with_provenance(tmp_path: Path) -> None:
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


def test_insight_suite_second_materialization_replaces_first_at_stable_path(tmp_path: Path) -> None:
    template = _write_template(tmp_path / "template")
    refs = ["trace-1"]
    first_suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    first_staged = first_suite.stage(refs)
    (first_staged[0].path / "instruction.md").write_text("First generated instruction.\n", encoding="utf-8")
    first_suite.validate(first_staged[0])
    first_suite.promote_local(refs, first_staged)
    materialized_path = first_suite.suite_dir

    second_suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    second_staged = second_suite.stage(refs)
    (second_staged[0].path / "instruction.md").write_text("Second generated instruction.\n", encoding="utf-8")
    second_suite.validate(second_staged[0])
    second_suite.promote_local(refs, second_staged)

    assert second_suite.suite_dir == materialized_path
    task = list(HarborDataset.from_path(materialized_path).list_tasks())[0]
    task_dir = Path(task.uri.removeprefix("file://"))
    assert (task_dir / "instruction.md").read_text(encoding="utf-8") == "Second generated instruction.\n"


def test_failed_rebuild_preserves_previous_materialized_suite(tmp_path: Path) -> None:
    template = _write_template(tmp_path / "template")
    refs = ["trace-1"]
    first_suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    first_staged = first_suite.stage(refs)
    (first_staged[0].path / "instruction.md").write_text("Valid materialized instruction.\n", encoding="utf-8")
    first_suite.validate(first_staged[0])
    first_suite.promote_local(refs, first_staged)

    failed_suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    failed_staged = failed_suite.stage(refs)
    (failed_staged[0].path / "instruction.md").write_text("\n", encoding="utf-8")

    with pytest.raises(ValueError, match="instruction is missing or empty"):
        failed_suite.validate(failed_staged[0])

    task = list(HarborDataset.from_path(first_suite.suite_dir).list_tasks())[0]
    task_dir = Path(task.uri.removeprefix("file://"))
    assert (task_dir / "instruction.md").read_text(encoding="utf-8") == "Valid materialized instruction.\n"


def test_post_promotion_validation_failure_restores_previous_suite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = _write_template(tmp_path / "template")
    refs = ["trace-1"]
    first_suite = InsightSuite(experiment_dir=tmp_path, insight_id="insight-1", task_template=template)
    first_staged = first_suite.stage(refs)
    (first_staged[0].path / "instruction.md").write_text("Previously materialized.\n", encoding="utf-8")
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
    assert (task_dir / "instruction.md").read_text(encoding="utf-8") == "Previously materialized.\n"
    assert list(first_suite.root.glob(".insight-suite-backup-*")) == []


def test_insight_suite_rejects_empty_instruction_before_materialization(tmp_path: Path) -> None:
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
