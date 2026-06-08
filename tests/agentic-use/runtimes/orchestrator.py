# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Orchestrate BUILD + AgentEvaluator + VERIFY for agentic-use tasks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nemo_evaluator_sdk.agent_eval import AgentEvalRunConfig, AgentEvaluator
from nemo_evaluator_sdk.agent_eval.types import AgentAttemptRuntime, AgentEvalRunResult
from nemo_evaluator_sdk.metrics.protocol import Metric

from runtimes.shared.docker import docker_image_exists
from runtimes.shared.environment_spec import execute_build_plan, plan_task_build
from runtimes.shared.layout import task_image_tag
from runtimes.shared.metrics import AgentPhaseSuccessMetric, VerifierRewardMetric
from runtimes.shared.reporting import GateThresholds, evaluate_gate, load_baseline_summary, write_gate_report
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
        task = task.model_copy(update={"metrics": self._task_metrics()})
        image_tag = task_image_tag(task.id)
        self._ensure_task_image(task.inputs["task_dir"], image_tag)

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

        if self.config.write_gate and result.output_dir is not None:
            baseline = (
                load_baseline_summary(self.config.baseline_summary_path)
                if self.config.baseline_summary_path is not None
                else None
            )
            report = evaluate_gate(
                result,
                thresholds=self.config.gate_thresholds,
                baseline_summary=baseline,
            )
            write_gate_report(report, result.output_dir)

        return result

    def _task_metrics(self) -> list[Metric]:
        """Attach the verifier compatibility metric when verify is enabled."""
        metrics: list[Metric] = [AgentPhaseSuccessMetric()]
        if self._verify_enabled():
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
