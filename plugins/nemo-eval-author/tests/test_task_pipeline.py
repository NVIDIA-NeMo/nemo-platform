# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_PLUGIN = Path(__file__).resolve().parents[1]
_SCRIPT = _PLUGIN / "skills" / "eval-author-task-create" / "scripts" / "task_pipeline.py"
_needs_harbor = pytest.mark.skipif(shutil.which("harbor") is None, reason="Harbor is not installed")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke ``task_pipeline.py`` with ``args`` and return the completed process."""
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _coverage_input_report(*, run_id: str, covered: list[str]) -> dict[str, Any]:
    """Build one aggregate ``input_reports`` entry for verify tests."""
    return {
        "path": f".eval-author/task-measurements/run={run_id}/tool_calls/coverage.json",
        "method": "tool_calls",
        "item_kind": "tool",
        "item_kind_count": max(len(covered), 1),
        "subject": {
            "trace": f".harbor/runs/trial/{run_id}/agent/trajectory.json",
            "trace_format": "atif",
            "task_id": "cover-read",
            "run_id": run_id,
        },
        "covered": covered,
        "covered_count": len(covered),
    }


def _write_report(
    path: Path,
    *,
    covered: list[str],
    uncovered: list[str],
    run_id: str | None = None,
) -> None:
    """Write a minimal aggregate coverage report JSON file for tests."""
    items = [
        {
            "name": name,
            "kind": "tool",
            "reason": "not_covered_by_any_input_report",
            "description": f"Use {name}.",
            "generation": {
                "focus": f"Exercise {name}.",
                "needed_tools": [name],
                "evidence_required": [{"kind": "tool_call", "tool": name}],
            },
        }
        for name in uncovered
    ]
    _write_report_with_items(path, covered=covered, uncovered_items=items, run_id=run_id)


def _write_report_with_items(
    path: Path,
    *,
    covered: list[str],
    uncovered_items: list[dict[str, Any]],
    run_id: str | None = None,
) -> None:
    """Write an aggregate coverage report with explicit ``uncovered_items`` entries."""
    uncovered = [str(item["name"]) for item in uncovered_items]
    payload: dict[str, Any] = {"covered": covered, "uncovered": uncovered, "uncovered_items": uncovered_items}
    if run_id is not None:
        payload["input_reports"] = [_coverage_input_report(run_id=run_id, covered=covered)]
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_task_slug_for_tool_is_deterministic() -> None:
    """Base slugs are stable for common runtime tool names."""
    sys.path.insert(0, str(_SCRIPT.parent))
    try:
        from task_pipeline import task_slug_for_tool
    finally:
        sys.path.pop(0)

    assert task_slug_for_tool("read") == "cover-read"
    assert task_slug_for_tool("customer.lookup") == "cover-customer-lookup"


def test_select_returns_task_slug_and_paths(tmp_path: Path) -> None:
    """Select attaches canonical artifact paths for one actionable tool gap."""
    report = tmp_path / "report.json"
    _write_report(report, covered=["write"], uncovered=["read"])
    payload = json.loads(_run("select", "--report", str(report)).stdout)
    assert payload["valid"] is True
    assert payload["actionable_tools"] == [
        {
            "description": "Use read.",
            "evidence_required": [{"kind": "tool_call", "tool": "read"}],
            "focus": "Exercise read.",
            "kind": "tool",
            "name": "read",
            "needed_tools": ["read"],
            "paths": {
                "draft": ".eval-author/task-drafts/cover-read",
                "measurements": ".eval-author/task-measurements/cover-read",
                "proposal": ".eval-author/proposals/cover-read-instruction.md",
                "task_id": "cover-read",
            },
            "reason": "not_covered_by_any_input_report",
            "task_slug": "cover-read",
        }
    ]


def test_select_assigns_deduped_slugs_for_colliding_tool_names(tmp_path: Path) -> None:
    """Colliding base and final slugs receive deterministic ``-2``, ``-3``, ... suffixes."""
    report = tmp_path / "report.json"
    _write_report(report, covered=[], uncovered=["server:foo", "server.foo"])
    payload = json.loads(_run("select", "--report", str(report)).stdout)
    slugs = {gap["name"]: gap["task_slug"] for gap in payload["actionable_tools"]}
    assert slugs == {
        "server.foo": "cover-server-foo",
        "server:foo": "cover-server-foo-2",
    }

    report_three = tmp_path / "report-three.json"
    _write_report(report_three, covered=[], uncovered=["server:foo", "server.foo-2", "server.foo"])
    payload_three = json.loads(_run("select", "--report", str(report_three)).stdout)
    slugs_three = {gap["name"]: gap["task_slug"] for gap in payload_three["actionable_tools"]}
    assert slugs_three == {
        "server.foo": "cover-server-foo",
        "server.foo-2": "cover-server-foo-2",
        "server:foo": "cover-server-foo-3",
    }


@_needs_harbor
def test_scaffold_uses_harbor_native_task_layout(tmp_path: Path) -> None:
    """Scaffold installs the proposal into a Harbor-native task draft layout."""
    report = tmp_path / "report.json"
    _write_report(report, covered=["write"], uncovered=["read"])
    proposals = tmp_path / ".eval-author" / "proposals"
    proposals.mkdir(parents=True)
    instruction = proposals / "cover-read-instruction.md"
    instruction.write_text("Read seed.txt and report its content.\n", encoding="utf-8")
    draft = tmp_path / ".eval-author" / "task-drafts" / "cover-read"

    result = _run(
        "scaffold",
        "--report",
        str(report),
        "--target",
        "read",
        "--out",
        str(draft),
        "--task-name",
        "example/cover-read",
        "--description",
        "Read a fixture file.",
        "--author",
        "Test Author",
        "--instruction-file",
        str(instruction),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["task_slug"] == "cover-read"
    assert payload["paths"]["proposal"] == ".eval-author/proposals/cover-read-instruction.md"
    assert (draft / "instruction.md").read_text(encoding="utf-8") == instruction.read_text(encoding="utf-8")
    task_toml = (draft / "task.toml").read_text(encoding="utf-8")
    assert 'schema_version = "1.3"' in task_toml
    assert 'name = "example/cover-read"' in task_toml
    assert (draft / "environment" / "Dockerfile").is_file()
    assert (draft / "solution" / "solve.sh").is_file()
    assert (draft / "tests" / "test.sh").is_file()


def test_scaffold_rejects_mismatched_proposal_filename(tmp_path: Path) -> None:
    """Scaffold rejects proposal filenames that do not match the assigned task slug."""
    report = tmp_path / "report.json"
    _write_report(report, covered=["write"], uncovered=["read"])
    proposals = tmp_path / ".eval-author" / "proposals"
    proposals.mkdir(parents=True)
    instruction = proposals / "read-file-instruction.md"
    instruction.write_text("Read seed.txt and report its content.\n", encoding="utf-8")
    draft = tmp_path / ".eval-author" / "task-drafts" / "cover-read"

    result = _run(
        "scaffold",
        "--report",
        str(report),
        "--target",
        "read",
        "--out",
        str(draft),
        "--task-name",
        "example/cover-read",
        "--description",
        "Read a fixture file.",
        "--author",
        "Test Author",
        "--instruction-file",
        str(instruction),
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["valid"] is False
    assert "cover-read-instruction.md" in payload["error"]


def test_verify_rejects_single_after_report(tmp_path: Path) -> None:
    """Verify requires at least two after-reports."""
    before = tmp_path / "before.json"
    first = tmp_path / "first.json"
    _write_report(before, covered=["write"], uncovered=["read"])
    _write_report(first, covered=["read"], uncovered=[])

    result = _run(
        "verify",
        "--before",
        str(before),
        "--after",
        str(first),
        "--target",
        "read",
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["valid"] is False
    assert "at least 2 --after reports are required" in payload["error"]


def test_verify_rejects_duplicate_after_reports(tmp_path: Path) -> None:
    """Verify rejects duplicate after-report paths."""
    before = tmp_path / "before.json"
    first = tmp_path / "first.json"
    _write_report(before, covered=["write"], uncovered=["read"])
    _write_report(first, covered=["read"], uncovered=[])

    result = _run(
        "verify",
        "--before",
        str(before),
        "--after",
        str(first),
        "--after",
        str(first),
        "--target",
        "read",
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["valid"] is False
    assert "distinct" in payload["error"]


def test_verify_rejects_copied_after_reports_with_same_run_id(tmp_path: Path) -> None:
    """Verify rejects two paths that record the same ATIF subject.run_id."""
    before = tmp_path / "before.json"
    first = tmp_path / "repeat-1-report.json"
    second = tmp_path / "repeat-1-copy-report.json"
    _write_report(before, covered=["write"], uncovered=["read"])
    _write_report(first, covered=["read"], uncovered=[], run_id="repeat-1")
    second.write_text(first.read_text(encoding="utf-8"), encoding="utf-8")

    result = _run(
        "verify",
        "--before",
        str(before),
        "--after",
        str(first),
        "--after",
        str(second),
        "--target",
        "read",
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["valid"] is False
    assert "distinct ATIF subject.run_id" in payload["error"]


def test_verify_rejects_non_actionable_uncovered_item(tmp_path: Path) -> None:
    """Verify rejects targets that are uncovered but not actionable tool gaps."""
    before = tmp_path / "before.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_report_with_items(
        before,
        covered=["write"],
        uncovered_items=[
            {
                "name": "read",
                "kind": "tool",
                "reason": "not_covered_by_any_input_report",
                "description": "Use read.",
                "generation": {
                    "focus": "Exercise read.",
                    "needed_tools": ["read"],
                    "evidence_required": [{"kind": "tool_call", "tool": "read"}],
                },
            },
            {
                "name": "account_recovery",
                "kind": "capability",
                "reason": "not_measured_by_any_method",
                "description": "Recover account access.",
                "generation": {
                    "focus": "Exercise capability account_recovery.",
                    "needed_tools": ["read"],
                    "evidence_required": [],
                },
            },
        ],
    )
    _write_report(first, covered=["read"], uncovered=[], run_id="repeat-1")
    _write_report(second, covered=["read"], uncovered=[], run_id="repeat-1")

    result = _run(
        "verify",
        "--before",
        str(before),
        "--after",
        str(first),
        "--after",
        str(second),
        "--target",
        "account_recovery",
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["valid"] is False
    assert "not an actionable uncovered tool" in payload["error"]


def test_verify_requires_every_repeat_to_cover_target(tmp_path: Path) -> None:
    """Verify accepts only when every distinct after-report covers the target tool."""
    before = tmp_path / "before.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_report(before, covered=["write"], uncovered=["read"])
    _write_report(first, covered=["read"], uncovered=[], run_id="repeat-1")
    _write_report(second, covered=["read"], uncovered=[], run_id="repeat-2")

    result = _run(
        "verify",
        "--before",
        str(before),
        "--after",
        str(first),
        "--after",
        str(second),
        "--target",
        "read",
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["accepted"] is True
    assert payload["repeat_count"] == 2

    _write_report(second, covered=[], uncovered=["read"], run_id="repeat-2")
    failed = _run(
        "verify",
        "--before",
        str(before),
        "--after",
        str(first),
        "--after",
        str(second),
        "--target",
        "read",
    )
    assert failed.returncode == 1
    assert json.loads(failed.stdout)["accepted"] is False
