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
REQUESTED_MODEL_NAME = "azure/openai/gpt-5.4"
REQUESTED_MODEL_URL_PREFIX = "https://inference-api.nvidia.com/v1"
SCRIPT_CONTAINER_PATH = "/logs/agent/nemo-evaluator-prof-bench.py"
CONFIG_CONTAINER_PATH = "/logs/agent/nemo-evaluator-config.json"
RESULTS_CONTAINER_PATH = "/logs/agent/nemo-evaluator-results.json"
LOG_CONTAINER_PATH = "/logs/agent/nemo-evaluator-logs.log"
TRAJECTORY_JSON = Path("/logs/agent/trajectory.json")
PYTHON_BIN = Path("/app/.venv/bin/python")
RUNNING_SESSION_RE = re.compile(r"Process running with session ID (?P<session_id>\d+)")
SCRIPT_EXEC_RE = re.compile(
    rf"(^|[;\n]\s*)(?:uv\s+run\s+)?(?:(?:/app/\.venv/bin/)?python(?:3)?\s+)?{re.escape(SCRIPT_CONTAINER_PATH)}"
)


def _entry() -> dict[str, Any]:
    entry_path = Path(os.environ.get("HARBOR_ENTRY_JSON", "/tests/entry.json"))
    return json.loads(entry_path.read_text(encoding="utf-8"))


def _is_target_case() -> bool:
    return _entry().get("id") == TASK_CASE_ID


def _script_path() -> Path:
    return Path(os.environ.get("NEMO_EVALUATOR_SCRIPT_PATH", SCRIPT_CONTAINER_PATH))


def _config_path() -> Path:
    return Path(os.environ.get("NEMO_EVALUATOR_CONFIG_PATH", CONFIG_CONTAINER_PATH))


def _results_path() -> Path:
    return Path(os.environ.get("NEMO_EVALUATOR_RESULTS_PATH", RESULTS_CONTAINER_PATH))


def _log_path() -> Path:
    return Path(os.environ.get("NEMO_EVALUATOR_LOG_PATH", LOG_CONTAINER_PATH))


def _python_bin() -> Path:
    return Path(os.environ.get("NEMO_EVALUATOR_PYTHON_BIN", str(PYTHON_BIN)))


def _trajectory() -> dict[str, Any]:
    trajectory_path = Path(os.environ.get("HARBOR_TRAJECTORY_JSON", str(TRAJECTORY_JSON)))
    return json.loads(trajectory_path.read_text(encoding="utf-8"))


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"Expected {path!s} to contain a JSON object"
    return data


def _json_path(path: list[str | int]) -> str:
    result = "$"
    for part in path:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}"
    return result


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def _compact_preview(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)[:500]


def _result_error_messages(value: Any, path: list[str | int] | None = None) -> list[str]:
    path = path or []
    messages: list[str] = []

    if isinstance(value, dict):
        error = value.get("error")
        attempt = value.get("attempt")

        if path == [] and _has_value(error):
            message = f"{_json_path(['error'])}: {error}"
            if attempt is not None:
                message += f" (attempt: {attempt})"
            messages.append(message)

        if value.get("status") == "error":
            reason = error if _has_value(error) else _compact_preview(value)
            message = f"{_json_path([*path, 'status'])}: status == error; reason: {reason}"
            if attempt is not None:
                message += f" (attempt: {attempt})"
            messages.append(message)

        for key, item in value.items():
            messages.extend(_result_error_messages(item, [*path, key]))
        return messages

    if isinstance(value, list):
        for index, item in enumerate(value):
            messages.extend(_result_error_messages(item, [*path, index]))

    return messages


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
    """Collect terminal output from trajectory steps that run the saved evaluator script.

    Matches exec_command calls that execute SCRIPT_CONTAINER_PATH, records their
    observations, and follows write_stdin calls for those background sessions so
    long-running script output is included in the returned text fragments.
    """
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
        "dataset",
        REQUESTED_MODEL_NAME,
        REQUESTED_MODEL_URL_PREFIX,
        CONFIG_CONTAINER_PATH,
        RESULTS_CONTAINER_PATH,
        LOG_CONTAINER_PATH,
    ]
    missing = [fragment for fragment in expected_fragments if fragment not in source]

    assert not missing, f"Saved script {script_path!s} is missing expected fragments: {missing}"
    assert "run_sync" in source or ".run(" in source, (
        f"Expected saved script {script_path!s} to call Evaluator().run_sync() or await Evaluator().run()."
    )


def test_execution_artifacts_exist() -> None:
    """The script should write the requested config, results, and INFO log artifacts."""
    if not _is_target_case():
        return

    for path in (_config_path(), _results_path(), _log_path()):
        assert path.exists(), f"Expected execution artifact at {path!s}"
        assert path.is_file(), f"Expected execution artifact path to be a file: {path!s}"
        assert path.stat().st_size > 0, f"Expected execution artifact to be non-empty: {path!s}"


def test_results_file_has_no_errors() -> None:
    """The persisted evaluation results should not contain execution errors."""
    if not _is_target_case():
        return

    results = _read_json(_results_path())
    error_messages = _result_error_messages(results)

    assert not error_messages, (
        f"Expected {_results_path()!s} to contain no evaluator execution errors. "
        f"Observed:\n" + "\n".join(f"- {message}" for message in error_messages)
    )


def test_trajectory_runs_saved_script() -> None:
    """The trajectory should show a real Python execution of the saved script."""
    if not _is_target_case():
        return

    commands = _tool_commands(_trajectory())

    assert any(_script_run_command(command) for command in commands), (
        f"Expected a Python execution command for {SCRIPT_CONTAINER_PATH}. Observed commands: {commands}"
    )


def test_trajectory_saved_script_run_completed() -> None:
    """The saved script run should finish, even when the persisted results contain handled errors."""
    if not _is_target_case():
        return

    texts = _script_run_observation_texts(_trajectory())
    combined = "\n".join(texts)

    assert texts, f"Expected trajectory observations for running {SCRIPT_CONTAINER_PATH}"
    assert any("Process exited with code" in text for text in texts), (
        f"Expected saved script execution to finish. Observed output:\n{combined}"
    )
