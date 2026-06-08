# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ATIF trajectory loading and summary helpers."""

from pathlib import Path

from evaluator_agent_eval.schemas import TrajectorySummary


def load_atif_trajectory(path: str | Path):
    """Load and validate an ATIF trajectory using ``nvidia-nat-atif`` models."""
    try:
        from nat.atif import ATIFTrajectory
    except ModuleNotFoundError as exc:
        raise RuntimeError("ATIF trajectory support requires the nvidia-nat-atif package") from exc

    try:
        return ATIFTrajectory.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"Invalid ATIF trajectory at {path}: {exc}") from exc


def summarize_atif_trajectory(path: str | Path) -> TrajectorySummary:
    """Validate an ATIF trajectory file and derive trajectory metric inputs."""
    trajectory = load_atif_trajectory(path)
    tool_call_count = 0
    failed_command_count = 0
    recovery_event_count = 0

    for step in trajectory.steps:
        if step.tool_calls:
            tool_call_count += len(step.tool_calls)
        step_text = _step_text(step)
        if _has_error_evidence(_observation_text(step)):
            failed_command_count += 1
        if _has_recovery_evidence(step_text):
            recovery_event_count += 1

    return TrajectorySummary(
        tool_call_count=tool_call_count,
        failed_command_count=failed_command_count,
        recovery_event_count=recovery_event_count,
    )


def _step_text(step) -> str:
    parts: list[str] = []
    if isinstance(step.message, str):
        parts.append(step.message)
    if step.reasoning_content:
        parts.append(step.reasoning_content)
    if step.observation:
        for result in step.observation.results:
            if isinstance(result.content, str):
                parts.append(result.content)
    return "\n".join(parts).lower()


def _observation_text(step) -> str:
    if not step.observation:
        return ""
    parts = [result.content for result in step.observation.results if isinstance(result.content, str)]
    return "\n".join(parts).lower()


def _has_error_evidence(text: str) -> bool:
    return any(marker in text for marker in ("error", "failed", "traceback", "exception", "exit code"))


def _has_recovery_evidence(text: str) -> bool:
    return any(marker in text for marker in ("retry", "recover", "fixed", "corrected", "try again"))
