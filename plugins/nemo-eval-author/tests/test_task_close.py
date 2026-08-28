# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_PLUGIN = Path(__file__).resolve().parents[1]
_SCRIPT = _PLUGIN / "skills" / "eval-author-task-close" / "scripts" / "task_close.py"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Invoke ``task_close.py`` with ``args`` and return the completed process."""
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _input_report(*, run_id: str, covered: list[str]) -> dict[str, Any]:
    """Build one aggregate ``input_reports`` entry for task-close tests."""
    return {
        "path": f".eval-author/task-measurements/run={run_id}/tool_calls/coverage.json",
        "method": "tool_calls",
        "item_kind": "tool",
        "subject": {
            "trace": f".eval-author/task-runs/cover-read/{run_id}/agent/trajectory.json",
            "trace_format": "atif",
            "task_id": "cover-read",
            "run_id": run_id,
        },
        "covered": covered,
        "covered_count": len(covered),
    }


def _write_before_report(path: Path, *, target: str = "read") -> None:
    """Write a minimal before report with one actionable uncovered tool."""
    payload = {
        "covered": ["write"],
        "uncovered": [target],
        "uncovered_items": [
            {
                "name": target,
                "kind": "tool",
                "reason": "not_covered_by_any_input_report",
                "description": f"Use {target}.",
                "generation": {
                    "focus": f"Exercise {target}.",
                    "needed_tools": [target],
                    "evidence_required": [{"kind": "tool_call", "tool": target}],
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_after_report(path: Path, *, covered: list[str], uncovered: list[str], run_id: str) -> None:
    """Write a minimal aggregate after report."""
    payload = {
        "covered": covered,
        "uncovered": uncovered,
        "uncovered_items": [],
        "input_reports": [_input_report(run_id=run_id, covered=covered)],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_ready_draft(path: Path, *, verifier: str | None = None) -> None:
    """Write a generated Harbor task draft with substantive files."""
    (path / "environment").mkdir(parents=True)
    (path / "tests").mkdir()
    (path / "solution").mkdir()
    (path / "instruction.md").write_text("Read /app/data/input.txt and write the answer.\n", encoding="utf-8")
    (path / "task.toml").write_text(
        'version = "1.0"\n'
        "\n[task]\n"
        'name = "example/cover-read"\n'
        'authors = ["NVIDIA"]\n'
        'keywords = ["read", "file"]\n'
        "\n[verifier]\n"
        "timeout_sec = 60.0\n"
        "\n[agent]\n"
        "timeout_sec = 120.0\n"
        "\n[environment]\n"
        "cpus = 1\n"
        "memory_mb = 1024\n",
        encoding="utf-8",
    )
    (path / "environment" / "Dockerfile").write_text("FROM ubuntu:24.04\nRUN mkdir -p /app/data\n", encoding="utf-8")
    (path / "tests" / "test.sh").write_text(
        verifier
        or "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "reward=0\n"
        "if [ -f /app/answer.txt ]; then\n"
        "  if grep -qx expected /app/answer.txt; then reward=1; fi\n"
        "fi\n"
        "mkdir -p /logs/verifier\n"
        "printf '%s\\n' \"$reward\" > /logs/verifier/reward.txt\n",
        encoding="utf-8",
    )
    (path / "solution" / "solve.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nprintf 'expected\\n' > /app/answer.txt\n",
        encoding="utf-8",
    )


def _write_executable(path: Path, text: str) -> None:
    """Write an executable script used by preflight tests."""
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def test_preflight_reports_blocked_no_docker(tmp_path: Path) -> None:
    """Preflight distinguishes Docker daemon problems from task or verifier failures."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "harbor",
        '#!/usr/bin/env bash\nif [ "$1" = trial ] && [ "$2" = start ] && [ "$3" = --help ]; then exit 0; fi\nexit 2\n',
    )
    _write_executable(bin_dir / "docker", "#!/usr/bin/env bash\nexit 1\n")
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    result = _run("preflight", "--require-docker", env=env)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked_no_docker"
    assert payload["valid"] is False


def test_inspect_accepts_substantive_generated_draft(tmp_path: Path) -> None:
    """A filled generated draft is ready for Oracle, not accepted as closed."""
    draft = tmp_path / ".eval-author" / "task-drafts" / "cover-read"
    before = tmp_path / ".eval-author" / "audit-coverage-report.json"
    before.parent.mkdir()
    _write_ready_draft(draft)
    _write_before_report(before)
    out = tmp_path / ".eval-author" / "task-closures" / "cover-read" / "inspection.json"

    result = _run("inspect", "--draft", str(draft), "--target", "read", "--before", str(before), "--out", str(out))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready_for_oracle"
    assert payload["valid"] is True
    assert out.is_file()


def test_inspect_rejects_unconditional_reward_verifier(tmp_path: Path) -> None:
    """A verifier that only writes reward 1 still needs repair."""
    draft = tmp_path / ".eval-author" / "task-drafts" / "cover-read"
    _write_ready_draft(
        draft,
        verifier="#!/usr/bin/env bash\nmkdir -p /logs/verifier\necho 1 > /logs/verifier/reward.txt\n",
    )

    result = _run("inspect", "--draft", str(draft), "--target", "read")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "needs_repair"
    failed = {check["name"] for check in payload["checks"] if not check["passed"]}
    assert "verifier:has_failure_path" in failed
    assert "verifier:not_unconditional_reward" in failed


def test_report_accepts_coverage_closure_even_when_agent_failed_reward(tmp_path: Path) -> None:
    """A generated eval can be accepted and still expose a real-agent task failure."""
    before = tmp_path / "before.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_before_report(before)
    _write_after_report(first, covered=["read"], uncovered=[], run_id="repeat-1")
    _write_after_report(second, covered=["read"], uncovered=[], run_id="repeat-2")

    result = _run(
        "report",
        "--before",
        str(before),
        "--after",
        str(first),
        "--after",
        str(second),
        "--target",
        "read",
        "--oracle-reward",
        "1.0",
        "--agent-reward",
        "0.0",
        "--agent-reward",
        "0.0",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "closed"
    assert payload["accepted"] is True
    assert payload["coverage"]["closed"] is True
    assert payload["real_agent"]["passed_task"] is False


def test_report_classifies_agent_solved_without_target_tool(tmp_path: Path) -> None:
    """A passing task reward is not coverage closure if the target tool is absent."""
    before = tmp_path / "before.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_before_report(before)
    _write_after_report(first, covered=[], uncovered=["read"], run_id="repeat-1")
    _write_after_report(second, covered=[], uncovered=["read"], run_id="repeat-2")

    result = _run(
        "report",
        "--before",
        str(before),
        "--after",
        str(first),
        "--after",
        str(second),
        "--target",
        "read",
        "--oracle-reward",
        "1.0",
        "--agent-reward",
        "1.0",
        "--agent-reward",
        "1.0",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "agent_solved_without_target_tool"
    assert payload["accepted"] is False
    assert payload["coverage"]["closed"] is False
    assert payload["real_agent"]["passed_task"] is True


def test_report_requires_distinct_after_run_ids(tmp_path: Path) -> None:
    """Copied after reports do not count as independent closure evidence."""
    before = tmp_path / "before.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_before_report(before)
    _write_after_report(first, covered=["read"], uncovered=[], run_id="repeat-1")
    _write_after_report(second, covered=["read"], uncovered=[], run_id="repeat-1")

    result = _run(
        "report",
        "--before",
        str(before),
        "--after",
        str(first),
        "--after",
        str(second),
        "--target",
        "read",
        "--oracle-reward",
        "1.0",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "trajectory_invalid"
    assert "distinct ATIF subject.run_id" in payload["coverage"]["error"]


def test_report_classifies_missing_second_repeat_as_coverage_unproven(tmp_path: Path) -> None:
    """A single measured repeat is not enough evidence to accept or reject closure."""
    before = tmp_path / "before.json"
    first = tmp_path / "first.json"
    _write_before_report(before)
    _write_after_report(first, covered=["read"], uncovered=[], run_id="repeat-1")

    result = _run(
        "report",
        "--before",
        str(before),
        "--after",
        str(first),
        "--target",
        "read",
        "--oracle-reward",
        "1.0",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "coverage_unproven"
    assert payload["failure_reason"] == "coverage_unproven"
