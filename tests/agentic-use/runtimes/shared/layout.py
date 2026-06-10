# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Output directory layout for agentic-use runtime runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.runtimes.layout import prepare_run_layout, resolve_run_dir
from nemo_evaluator_sdk.agent_eval.types import AgentEvalRunConfig, AgentEvalTask

from runtimes.shared.config import AgenticSharedConfig


@dataclass(frozen=True)
class AgenticRunLayout:
    """Filesystem layout for one task run.

    Extends the SDK's generic ``RunLayout`` shape with a platform-specific
    ``state_dir`` (preserved platform/database state across agent + verifier).
    """

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
    output_dir = config.output_dir if config is not None else None
    run_dir = resolve_run_dir(output_dir, lambda: new_run_dir(default_jobs_dir(shared), task.id))

    # Generic agent/workspace dirs + written instruction come from the SDK helper.
    base = prepare_run_layout(run_dir, task.intent)

    # Platform extension: a preserved state dir for platform/db across phases.
    state_dir = base.run_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    return AgenticRunLayout(
        run_dir=base.run_dir,
        agent_log_dir=base.agent_log_dir,
        workspace_dir=base.workspace_dir,
        state_dir=state_dir,
        instruction_path=base.instruction_path,
    )


def task_image_tag(task_id: str) -> str:
    return f"nmp-nat-{task_id}:latest"
