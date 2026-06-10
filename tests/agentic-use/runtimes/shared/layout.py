# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Output directory layout for agentic-use runtime runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.types import AgentEvalRunConfig, AgentEvalTask

from runtimes.shared.config import AgenticSharedConfig


@dataclass(frozen=True)
class AgenticRunLayout:
    """Filesystem layout for one task run."""

    run_dir: Path
    agent_log_dir: Path
    workspace_dir: Path
    state_dir: Path
    instruction_path: Path


def default_jobs_dir(shared: AgenticSharedConfig) -> Path:
    if shared.jobs_dir is not None:
        return shared.jobs_dir
    return shared.repo_root / "nat-jobs"


def new_run_dir(jobs_dir: Path, task_id: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = jobs_dir / f"{timestamp}-{task_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def resolve_run_layout(
    task: AgentEvalTask,
    shared: AgenticSharedConfig,
    config: AgentEvalRunConfig | None = None,
) -> AgenticRunLayout:
    """Resolve or create the on-disk layout for one task attempt."""
    if config is not None and config.output_dir is not None:
        run_subdir = task.metadata.get("agentic_use_run_subdir")
        if isinstance(run_subdir, str) and run_subdir:
            base = Path(config.output_dir).resolve()
            candidate = (base / run_subdir).resolve()
            if not candidate.is_relative_to(base):
                raise ValueError(f"Invalid run_subdir escapes output_dir: {run_subdir!r}")
            run_dir = candidate
        else:
            run_dir = Path(config.output_dir)
    else:
        run_dir = new_run_dir(default_jobs_dir(shared), task.id)

    agent_log_dir = run_dir / "agent"
    workspace_dir = run_dir / "workspace"
    state_dir = run_dir / "state"
    agent_log_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    instruction_path = agent_log_dir / "instruction.md"
    instruction_path.write_text(task.intent, encoding="utf-8")

    return AgenticRunLayout(
        run_dir=run_dir,
        agent_log_dir=agent_log_dir,
        workspace_dir=workspace_dir,
        state_dir=state_dir,
        instruction_path=instruction_path,
    )


def task_image_tag(task_id: str) -> str:
    return f"nmp-nat-{task_id}:latest"
