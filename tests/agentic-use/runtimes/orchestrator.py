# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Orchestrate BUILD + AgentEvaluator + VERIFY for agentic-use tasks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nemo_evaluator_sdk.agent_eval import AgentEvalRunConfig, AgentEvaluator
from nemo_evaluator_sdk.agent_eval.types import (
    AgentAttemptRuntime,
    AgentEvalRunResult,
    AgentEvalTask,
)
from nemo_evaluator_sdk.metrics.protocol import Metric

from runtimes.shared.docker import docker_image_exists
from runtimes.shared.environment_spec import execute_build_plan, plan_task_build
from runtimes.shared.layout import task_image_tag
from runtimes.shared.metrics import VerifierRewardMetric
from runtimes.shared.reporting import GateThresholds, evaluate_gate, load_baseline_summary, write_gate_report
from runtimes.shared.result_adapter import attempt_from_result_dir
from runtimes.shared.task_loader import agentic_task_from_dir


@dataclass(frozen=True)
class AgenticOrchestratorConfig:
    skip_build: bool = False
    skip_verify: bool = False
    write_dashboard: bool = True
    write_gate: bool = True
    gate_thresholds: GateThresholds | None = None
    baseline_summary_path: Path | None = None


class AgenticEvalOrchestrator:
    """Run agentic-use tasks through AgentEvaluator and optional verify phase."""

    def __init__(
        self,
        runtime: AgentAttemptRuntime,
        *,
        config: AgenticOrchestratorConfig | None = None,
    ) -> None:
        self.runtime = runtime
        self.config = config or AgenticOrchestratorConfig()

    async def run_agent_eval(
        self,
        task_name: str,
        *,
        output_dir: Path | None = None,
        run_id: str | None = None,
    ) -> AgentEvalRunResult:
        """Build the task image when needed, run the agent runtime, return SDK result."""
        task = agentic_task_from_dir(task_name)
        task = task.model_copy(update={"metrics": self._metrics_for_task(task)})
        image_tag = task_image_tag(task.id)
        self._ensure_task_image(task.metadata["task_dir"], image_tag)

        result = await AgentEvaluator().run(
            tasks=[task],
            target=self.runtime,
            config=AgentEvalRunConfig(
                output_dir=output_dir,
                run_id=run_id,
                parallelism=1,
                write_dashboard=self.config.write_dashboard,
                benchmark={"benchmark": "agentic-use", "task": task_name},
            ),
        )

        self._maybe_write_gate(result)
        return result

    async def score_captured_attempts(
        self,
        task_name: str,
        *,
        result_dirs: Sequence[str | Path],
        output_dir: Path | None = None,
        run_id: str | None = None,
    ) -> AgentEvalRunResult:
        """Score already-captured ``result.json`` runs without re-running the agent.

        This is the SDK's first-class *stored-attempt* path: it imports each
        ``nat_runner`` output directory via :func:`attempt_from_result_dir` and
        scores them through :class:`AgentEvaluator`, so metrics can be exercised
        (and runs rescored) with no Docker/agent execution.
        """
        task = agentic_task_from_dir(task_name)
        task = task.model_copy(update={"metrics": self._metrics_for_task(task)})
        attempts = [attempt_from_result_dir(result_dir, task=task) for result_dir in result_dirs]

        result = await AgentEvaluator().run(
            tasks=[task],
            attempts=attempts,
            config=AgentEvalRunConfig(
                output_dir=output_dir,
                run_id=run_id,
                parallelism=1,
                write_dashboard=self.config.write_dashboard,
                benchmark={"benchmark": "agentic-use", "task": task_name, "mode": "offline"},
            ),
        )

        self._maybe_write_gate(result)
        return result

    def _maybe_write_gate(self, result: AgentEvalRunResult) -> None:
        if not (self.config.write_gate and result.output_dir is not None):
            return
        baseline = (
            load_baseline_summary(self.config.baseline_summary_path)
            if self.config.baseline_summary_path is not None
            else None
        )
        report = evaluate_gate(result, thresholds=self.config.gate_thresholds, baseline_summary=baseline)
        write_gate_report(report, result.output_dir)

    def _metrics_for_task(self, task: AgentEvalTask) -> list[Metric]:
        """Honor task-authored metrics; only *append* a compatibility metric.

        Metrics originate on the task (see ``agentic_task_from_dir``). When the
        live verify phase is enabled we append :class:`VerifierRewardMetric` so
        the legacy pytest reward is scored too — but we never replace the task's
        own metric set, and we avoid duplicating a metric the task already
        declares (the SDK rejects duplicate metric types).
        """
        metrics: list[Metric] = list(task.metrics)
        if self._verify_enabled() and not any(isinstance(metric, VerifierRewardMetric) for metric in metrics):
            metrics.append(VerifierRewardMetric())
        return metrics

    def _verify_enabled(self) -> bool:
        runtime_config = getattr(self.runtime, "config", None)
        shared = getattr(runtime_config, "shared", None)
        return bool(getattr(shared, "run_verify", False))

    def _ensure_task_image(self, task_dir: str | Path, image_tag: str) -> None:
        if self.config.skip_build:
            if not docker_image_exists(image_tag):
                raise RuntimeError(
                    f"--skip-build requested but task image {image_tag!r} is not available locally. "
                    "Run without skip_build to build the task image first."
                )
            return
        execute_build_plan(plan_task_build(Path(task_dir), image_tag))


def runtime_for_backend(
    backend: str,
    *,
    shared_kwargs: dict[str, Any] | None = None,
    backend_kwargs: dict[str, Any] | None = None,
) -> AgentAttemptRuntime:
    """Select a concrete runtime by backend name (CLI helper only)."""
    from runtimes.aut.runtime import AutAgentAttemptRuntime
    from runtimes.claude_code.runtime import ClaudeCodeAgentAttemptRuntime
    from runtimes.codex.runtime import CodexAgentAttemptRuntime
    from runtimes.cursor_agent.runtime import CursorAgentAttemptRuntime
    from runtimes.shared.config import (
        AgenticSharedConfig,
        AutRuntimeConfig,
        ClaudeCodeRuntimeConfig,
        CodexRuntimeConfig,
        CursorAgentRuntimeConfig,
        WorkflowRuntimeConfig,
    )
    from runtimes.workflow.runtime import NatWorkflowAttemptRuntime

    shared = AgenticSharedConfig(**(shared_kwargs or {}))
    backend_kwargs = backend_kwargs or {}

    match backend:
        case "workflow":
            return NatWorkflowAttemptRuntime(WorkflowRuntimeConfig(shared=shared, **backend_kwargs))
        case "aut":
            return AutAgentAttemptRuntime(AutRuntimeConfig(shared=shared, **backend_kwargs))
        case "claude-code":
            return ClaudeCodeAgentAttemptRuntime(ClaudeCodeRuntimeConfig(shared=shared, **backend_kwargs))
        case "codex":
            return CodexAgentAttemptRuntime(CodexRuntimeConfig(shared=shared, **backend_kwargs))
        case "cursor-agent":
            return CursorAgentAttemptRuntime(CursorAgentRuntimeConfig(shared=shared, **backend_kwargs))
        case _:
            raise ValueError(f"Unsupported agent backend: {backend!r}")
