# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Domain pytest checks for the evaluator-plugin ACES custom metric."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from nemo_platform import NeMoPlatform

WORKSPACE = "default"
EXACT_MATCH_CASE_ID = "evaluator-plugin-001"
DURABLE_JOB_CASE_ID = "evaluator-plugin-002"
EXACT_MATCH_SPEC_PATH = (
    "plugins/nemo-evaluator/src/nemo_evaluator/skills/evaluator-plugin/assets/specs/exact_match_metric.json"
)
TRAJECTORY_JSON = Path("/logs/agent/trajectory.json")
FILE_URL_RE = re.compile(r"\"artifact_url\"\s*:\s*\"(?P<url>file://[^\"]+)\"|(?P<fallback>file://[^\s\"']+)")


def _entry() -> dict[str, Any]:
    entry_path = Path(os.environ.get("HARBOR_ENTRY_JSON", "/tests/entry.json"))
    return json.loads(entry_path.read_text(encoding="utf-8"))


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


def _observation_text(trajectory: dict[str, Any]) -> str:
    observations = []
    for step in trajectory.get("steps", []):
        if isinstance(step, dict) and "observation" in step:
            observations.extend(_string_values(step["observation"]))
    return "\n".join(observations)


def _artifact_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in FILE_URL_RE.finditer(text):
        url = match.group("url") or match.group("fallback")
        if url and url not in urls:
            urls.append(url.rstrip(".,;"))
    return urls


def _path_from_file_url(url: str) -> Path:
    parsed = urlparse(url)
    assert parsed.scheme == "file", f"Expected a file:// artifact URL, found {url!r}"
    return Path(unquote(parsed.path))


def _job_names() -> list[str]:
    nmp_base_url = os.environ.get("NMP_BASE_URL", "http://localhost:8080")
    client = NeMoPlatform(base_url=nmp_base_url)
    response = client.jobs.list(workspace=WORKSPACE)
    return [job.name for job in response.data]


def test_exact_match_spec_file_command_was_run() -> None:
    """The exact-match case should run the documented spec-file command."""
    entry = _entry()
    if entry.get("id") != EXACT_MATCH_CASE_ID:
        return

    commands = _tool_commands(_trajectory())

    assert any(
        "nemo evaluator evaluate run" in command
        and "--spec-file" in command
        and EXACT_MATCH_SPEC_PATH in command
        for command in commands
    ), (
        "Expected the exact-match case to run "
        f"`nemo evaluator evaluate run --spec-file {EXACT_MATCH_SPEC_PATH}`. "
        f"Observed commands: {commands}"
    )


def test_exact_match_run_reported_completed_artifact() -> None:
    """The exact-match case should report a completed evaluation-results artifact."""
    entry = _entry()
    if entry.get("id") != EXACT_MATCH_CASE_ID:
        return

    text = _observation_text(_trajectory())
    normalized = re.sub(r"\s+", "", text).lower()

    assert "evaluation-results" in text, f"Expected evaluation-results artifact in trajectory output:\n{text}"
    assert '"status":"completed"' in normalized, f"Expected completed status in trajectory output:\n{text}"
    assert "artifact_url" in text, f"Expected artifact_url in trajectory output:\n{text}"


def test_exact_match_result_artifact_file_exists() -> None:
    """The exact-match artifact URL should point to a file visible to the verifier."""
    entry = _entry()
    if entry.get("id") != EXACT_MATCH_CASE_ID:
        return

    text = _observation_text(_trajectory())
    artifact_urls = [url for url in _artifact_urls(text) if "evaluation-results" in url]

    assert artifact_urls, f"Expected file:// evaluation-results artifact URL in trajectory output:\n{text}"

    artifact_path = _path_from_file_url(artifact_urls[-1])
    assert artifact_path.exists(), (
        f"Expected artifact file from URL {artifact_urls[-1]!r} to exist at {artifact_path!s}. "
        f"All parsed artifact URLs: {artifact_urls}"
    )
    assert artifact_path.is_file(), (
        f"Expected artifact URL {artifact_urls[-1]!r} to resolve to a file at {artifact_path!s}. "
        f"All parsed artifact URLs: {artifact_urls}"
    )


def test_expected_durable_job_count() -> None:
    """The submit case should create exactly one durable platform job."""
    entry = _entry()
    if entry.get("id") != DURABLE_JOB_CASE_ID:
        return

    job_names = _job_names()

    assert len(job_names) == 1, (
        f"Expected 1 durable platform job in workspace {WORKSPACE!r} "
        f"for eval case {entry.get('id')!r}, found {len(job_names)}: {job_names}"
    )
