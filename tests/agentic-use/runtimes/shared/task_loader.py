# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Map agentic-use task directories to AgentEvalTask values."""

from __future__ import annotations

import tomllib
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.types import AgentEvalTask
from nemo_evaluator_sdk.metrics.protocol import Metric

from runtimes.shared.constants import AGENTIC_USE_DIR
from runtimes.shared.metrics import AgentPhaseSuccessMetric


def load_task_toml(task_dir: Path) -> dict[str, object]:
    task_toml = task_dir / "task.toml"
    if not task_toml.exists():
        return {}
    try:
        with task_toml.open("rb") as handle:
            data = tomllib.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def task_agent_timeout_sec(task_dir: Path) -> int | None:
    data = load_task_toml(task_dir)
    agent = data.get("agent")
    if not isinstance(agent, dict):
        return None
    timeout_value = agent.get("timeout_sec")
    if isinstance(timeout_value, (int, float)) and timeout_value > 0:
        return int(timeout_value)
    return None


def agentic_task_from_dir(
    task_dir: str | Path,
    *,
    tasks_root: Path | None = None,
    metrics: list[Metric] | None = None,
) -> AgentEvalTask:
    """Build an :class:`AgentEvalTask` from an agentic-use task directory.

    ``inputs`` carries only agent-facing material (``instruction``) per the SDK
    design doc; runtime materialization details such as ``task_dir`` live in
    ``metadata`` so they cannot leak into metric scoring rows. Metrics are
    authored *on the task* (defaulting to :class:`AgentPhaseSuccessMetric`); the
    orchestrator only appends compatibility metrics, it does not own the set.
    """
    root = Path(tasks_root or AGENTIC_USE_DIR)
    task_path = Path(task_dir)
    if not task_path.is_absolute():
        task_path = (root / task_path).resolve()

    instruction_path = task_path / "instruction.md"
    if not instruction_path.exists():
        raise FileNotFoundError(f"instruction.md not found in {task_path}")

    instruction = instruction_path.read_text(encoding="utf-8")
    task_toml = load_task_toml(task_path)

    return AgentEvalTask(
        id=task_path.name,
        intent=instruction,
        inputs={
            "instruction": instruction,
        },
        metrics=metrics if metrics is not None else [AgentPhaseSuccessMetric()],
        metadata={
            "benchmark": "agentic-use",
            "task_toml": task_toml,
            "instruction_path": str(instruction_path),
            "task_dir": str(task_path),
        },
    )
