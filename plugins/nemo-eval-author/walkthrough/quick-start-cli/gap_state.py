# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Filesystem-derived gap progress for the walkthrough quick-start CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harbor_progress import GapPhase, HarborProgressUpdate, infer_gap_phase


@dataclass(slots=True)
class GapProgress:
    """Live status for one selected tool gap."""

    tool: str
    task_slug: str
    phase: GapPhase = GapPhase.WAITING
    detail: str = "waiting for draft"
    completed: int = 0
    total: int = 0
    attempt: int = 1
    trial_index: int = 0
    accepted: bool | None = None
    error: str | None = None
    error_log: str | None = None

    @classmethod
    def from_update(cls, tool: str, task_slug: str, update: HarborProgressUpdate) -> GapProgress:
        return cls(
            tool=tool,
            task_slug=task_slug,
            phase=update.phase,
            detail=update.detail,
            completed=update.completed,
            total=update.total,
            attempt=update.attempt,
            trial_index=update.trial_index,
        )


def draft_is_ready(workspace: Path, task_slug: str) -> bool:
    """Return True when a Harbor draft looks complete enough for oracle runs."""
    draft = workspace / ".eval-author" / "task-drafts" / task_slug
    required = (
        draft / "instruction.md",
        draft / "solution" / "solve.sh",
        draft / "tests" / "test.sh",
        draft / "task.toml",
    )
    return draft.is_dir() and all(path.is_file() for path in required)


def infer_gap_progress(workspace: Path, tool: str, task_slug: str) -> GapProgress:
    """Return filesystem-derived gap progress for sequential agent mode."""
    return GapProgress.from_update(tool, task_slug, infer_gap_phase(workspace, tool, task_slug))
