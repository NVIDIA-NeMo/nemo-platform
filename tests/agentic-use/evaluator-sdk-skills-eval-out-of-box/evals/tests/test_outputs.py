# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Domain pytest checks for the nemo-evaluator SDK skill eval."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

TASK_CASE_ID = "nemo-evaluator-001"
SCRIPT_CONTAINER_PATH = "/logs/agent/nemo-evaluator-001.py"
TRAJECTORY_JSON = Path("/logs/agent/trajectory.json")
PYTHON_BIN = Path("/app/.venv/bin/python")
TY_BIN = Path("/app/.venv/bin/ty")
RUNNING_SESSION_RE = re.compile(r"Process running with session ID (?P<session_id>\d+)")
SCRIPT_EXEC_RE = re.compile(
    rf"(^|[;\n]\s*)(?:uv\s+run\s+)?(?:/app/\.venv/bin/)?python(?:3)?\s+{re.escape(SCRIPT_CONTAINER_PATH)}"
)


def _entry() -> dict[str, Any]:
    entry_path = Path(os.environ.get("HARBOR_ENTRY_JSON", "/tests/entry.json"))
    return json.loads(entry_path.read_text(encoding="utf-8"))


def _is_target_case() -> bool:
    return _entry().get("id") == TASK_CASE_ID


def _script_path() -> Path:
    return Path(os.environ.get("NEMO_EVALUATOR_SCRIPT_PATH", SCRIPT_CONTAINER_PATH))


def _python_bin() -> Path:
    return Path(os.environ.get("NEMO_EVALUATOR_PYTHON_BIN", str(PYTHON_BIN)))


def _ty_bin() -> Path:
    return Path(os.environ.get("NEMO_EVALUATOR_TY_BIN", str(TY_BIN)))


def _trajectory() -> dict[str, Any]:
    trajectory_path = Path(os.environ.get("HARBOR_TRAJECTORY_JSON", str(TRAJECTORY_JSON)))
    return json.loads(trajectory_path.read_text(encoding="utf-8"))


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for item in value.values():
            strings.extend(_string_values(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_string_values(item))
        return strings
    return []


def _tool_commands(trajectory: dict[str, Any]) -> list[str]:
    commands: list[str] = []
    for step in trajectory.get("steps", []):
        if not isinstance(step, dict):
            continue
        for tool_call in step.get("tool_calls", []):
            if not isinstance(tool_call, dict):
                continue
            if tool_call.get("function_name") != "exec_command":
                continue

            arguments = tool_call.get("arguments", {})
            if isinstance(arguments, dict):
                command = arguments.get("cmd") or arguments.get("command")
                if isinstance(command, str):
                    commands.append(command)
            elif isinstance(arguments, str):
                commands.append(arguments)
    return commands


def _observation_text(step: dict[str, Any]) -> str:
    return "\n".join(_string_values(step.get("observation", {})))


def _script_run_command(command: str) -> bool:
    if "pgrep -af" in command or command.lstrip().startswith("ps "):
        return False
    return SCRIPT_EXEC_RE.search(command) is not None


def _script_run_observation_texts(trajectory: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    session_ids: set[int] = set()

    for step in trajectory.get("steps", []):
        if not isinstance(step, dict):
            continue

        for tool_call in step.get("tool_calls", []):
            if not isinstance(tool_call, dict):
                continue

            function_name = tool_call.get("function_name")
            arguments = tool_call.get("arguments", {})

            if function_name == "exec_command":
                command = ""
                if isinstance(arguments, dict):
                    command = str(arguments.get("cmd") or arguments.get("command") or "")
                elif isinstance(arguments, str):
                    command = arguments
                if not _script_run_command(command):
                    continue

                text = _observation_text(step)
                texts.append(text)
                for match in RUNNING_SESSION_RE.finditer(text):
                    session_ids.add(int(match.group("session_id")))
                continue

            if function_name == "write_stdin" and isinstance(arguments, dict):
                session_id = arguments.get("session_id")
                if isinstance(session_id, int) and session_id in session_ids:
                    texts.append(_observation_text(step))

    return texts


def test_saved_script_exists() -> None:
    """The agent should save the requested Python script under /logs/agent."""
    if not _is_target_case():
        return

    script_path = _script_path()

    assert script_path.exists(), f"Expected saved script at {script_path!s}"
    assert script_path.is_file(), f"Expected saved script path to be a file: {script_path!s}"
    assert script_path.stat().st_size > 0, f"Expected saved script to be non-empty: {script_path!s}"


def test_saved_script_is_valid_python() -> None:
    """The saved script should parse and compile without executing model calls."""
    if not _is_target_case():
        return

    script_path = _script_path()
    source = script_path.read_text(encoding="utf-8")

    ast.parse(source, filename=str(script_path))
    result = subprocess.run(
        [str(_python_bin()), "-m", "py_compile", str(script_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"Expected py_compile to pass for {script_path!s}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_saved_script_passes_ty_check() -> None:
    """The saved script should satisfy the type checker installed in /app/.venv."""
    if not _is_target_case():
        return

    script_path = _script_path()
    ty_bin = _ty_bin()

    assert ty_bin.exists(), f"Expected ty binary to exist at {ty_bin!s}"

    result = subprocess.run(
        [str(ty_bin), "check", str(script_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"Expected ty check to pass for {script_path!s}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_saved_script_contains_expected_sdk_eval_contract() -> None:
    """The saved script should encode the requested SDK, dataset, model, and rubric setup."""
    if not _is_target_case():
        return

    script_path = _script_path()
    source = script_path.read_text(encoding="utf-8")

    expected_fragments = [
        "Evaluator",
        "LLMJudgeMetric",
        "nvidia/ProfBench",
        "rubrics",
        "test[:3]",
        "limit_samples=3",
        "nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "https://integrate.api.nvidia.com/v1",
    ]
    missing = [fragment for fragment in expected_fragments if fragment not in source]

    assert not missing, f"Saved script {script_path!s} is missing expected fragments: {missing}"
    assert "run_sync" in source or ".run(" in source, (
        f"Expected saved script {script_path!s} to call Evaluator().run_sync() or await Evaluator().run()."
    )


def test_trajectory_runs_saved_script() -> None:
    """The trajectory should show a real Python execution of the saved script."""
    if not _is_target_case():
        return

    commands = _tool_commands(_trajectory())

    assert any(_script_run_command(command) for command in commands), (
        f"Expected a Python execution command for {SCRIPT_CONTAINER_PATH}. Observed commands: {commands}"
    )


def test_trajectory_saved_script_run_completed_with_results() -> None:
    """The saved script run should finish and print config, summary, aggregate, and row scores."""
    if not _is_target_case():
        return

    texts = _script_run_observation_texts(_trajectory())
    combined = "\n".join(texts)

    assert texts, f"Expected trajectory observations for running {SCRIPT_CONTAINER_PATH}"
    assert any("Process exited with code 0" in text for text in texts), (
        f"Expected saved script execution to exit successfully. Observed output:\n{combined}"
    )

    expected_markers = ["FULL SDK CONFIG", "SUMMARY", "AGGREGATE SCORES", "ROW SCORES"]
    missing = [marker for marker in expected_markers if marker not in combined]

    assert not missing, (
        f"Expected saved script output to include completed result markers {expected_markers}. "
        f"Missing: {missing}\nObserved output:\n{combined}"
    )
