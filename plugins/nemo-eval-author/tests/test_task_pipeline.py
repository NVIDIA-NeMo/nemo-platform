# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[1]
_SCRIPT = _PLUGIN / "skills" / "eval-author-task-create" / "scripts" / "task_pipeline.py"
_needs_harbor = pytest.mark.skipif(shutil.which("harbor") is None, reason="Harbor is not installed")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _write_report(path: Path, *, covered: list[str], uncovered: list[str]) -> None:
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
    path.write_text(
        json.dumps({"covered": covered, "uncovered": uncovered, "uncovered_items": items}),
        encoding="utf-8",
    )


def test_select_returns_only_actionable_tool_gaps(tmp_path: Path) -> None:
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
            "reason": "not_covered_by_any_input_report",
        }
    ]


@_needs_harbor
def test_scaffold_uses_harbor_native_task_layout(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    _write_report(report, covered=["write"], uncovered=["read"])
    instruction = tmp_path / "read-instruction.md"
    instruction.write_text("Read seed.txt and report its content.\n", encoding="utf-8")
    draft = tmp_path / ".eval-author" / "task-drafts" / "read-file"

    result = _run(
        "scaffold",
        "--report",
        str(report),
        "--target",
        "read",
        "--out",
        str(draft),
        "--task-name",
        "example/read-file",
        "--description",
        "Read a fixture file.",
        "--author",
        "Test Author",
        "--instruction-file",
        str(instruction),
    )
    assert result.returncode == 0, result.stdout
    assert (draft / "instruction.md").read_text(encoding="utf-8") == instruction.read_text(encoding="utf-8")
    task_toml = (draft / "task.toml").read_text(encoding="utf-8")
    assert 'schema_version = "1.3"' in task_toml
    assert 'name = "example/read-file"' in task_toml
    assert (draft / "environment" / "Dockerfile").is_file()
    assert (draft / "solution" / "solve.sh").is_file()
    assert (draft / "tests" / "test.sh").is_file()


def test_verify_requires_every_repeat_to_cover_target(tmp_path: Path) -> None:
    before = tmp_path / "before.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_report(before, covered=["write"], uncovered=["read"])
    _write_report(first, covered=["read"], uncovered=[])
    _write_report(second, covered=["read"], uncovered=[])

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

    _write_report(second, covered=[], uncovered=["read"])
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
