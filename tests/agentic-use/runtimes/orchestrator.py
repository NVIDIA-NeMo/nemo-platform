# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agentic-use adapter over the generic SDK orchestrator.

This is a thin NeMo-Platform factory: the generic run/score/gate loop lives in
:class:`nemo_evaluator_sdk.agent_eval.orchestrator.AgentEvalOrchestrator`. Here we
inject the platform specifics it deliberately does not know about — the agentic
task loader, the Docker image build (``prepare_task``), the ``run_verify``-derived
``VerifierRewardMetric``, and the ``result.json`` :class:`AgentAttemptSource`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nemo_evaluator_sdk.agent_eval.gating import GateThresholds
from nemo_evaluator_sdk.agent_eval.orchestrator import AgentEvalOrchestrator, OrchestratorConfig
from nemo_evaluator_sdk.agent_eval.runtimes.docker import docker_image_exists
from nemo_evaluator_sdk.agent_eval.runtimes.environment_spec import execute_build_plan, plan_task_build
from nemo_evaluator_sdk.agent_eval.types import (
    AgentAttemptRuntime,
    AgentEvalRunResult,
    AgentEvalTask,
)
from nemo_evaluator_sdk.metrics.protocol import Metric

from runtimes.shared.platform import (
    ResultDirAttemptSource,
    VerifierRewardMetric,
    agentic_task_from_dir,
    task_image_tag,
)


@dataclass(frozen=True)
class AgenticOrchestratorConfig:
    skip_build: bool = False
    skip_verify: bool = False
    write_dashboard: bool = True
    write_gate: bool = True
    gate_thresholds: GateThresholds | None = None
    baseline_summary_path: Path | None = None


class AgenticEvalOrchestrator:
    """Run agentic-use tasks through the generic orchestrator + optional verify metric."""

    def __init__(
        self,
        runtime: AgentAttemptRuntime,
        *,
        config: AgenticOrchestratorConfig | None = None,
    ) -> None:
        self.runtime = runtime
        self.config = config or AgenticOrchestratorConfig()
        self._orchestrator = AgentEvalOrchestrator(
            config=OrchestratorConfig(
                parallelism=1,
                write_dashboard=self.config.write_dashboard,
                write_gate=self.config.write_gate,
                gate_thresholds=self.config.gate_thresholds,
                baseline_summary_path=self.config.baseline_summary_path,
            ),
            extra_metrics=self._extra_metrics(),
        )

    async def run_agent_eval(
        self,
        task_name: str,
        *,
        output_dir: Path | None = None,
        run_id: str | None = None,
    ) -> AgentEvalRunResult:
        """Build the task image when needed, run the agent runtime, return SDK result."""
        task = agentic_task_from_dir(task_name)
        return await self._orchestrator.run_tasks(
            [task],
            target=self.runtime,
            benchmark={"benchmark": "agentic-use", "task": task_name},
            output_dir=output_dir,
            run_id=run_id,
            prepare_task=self._ensure_task_image,
        )

    async def score_captured_attempts(
        self,
        task_name: str,
        *,
        result_dirs: Sequence[str | Path],
        output_dir: Path | None = None,
        run_id: str | None = None,
    ) -> AgentEvalRunResult:
        """Score already-captured ``result.json`` runs without re-running the agent.

        The SDK's first-class *stored-attempt* path: each ``nat_runner`` output
        dir is adapted via :class:`ResultDirAttemptSource` and scored through the
        generic orchestrator, so metrics can be exercised (and runs rescored) with
        no Docker/agent execution.
        """
        task = agentic_task_from_dir(task_name)
        source = ResultDirAttemptSource()
        attempts = [source.load_attempt(result_dir, task=task) for result_dir in result_dirs]
        return await self._orchestrator.score_attempts(
            [task],
            attempts=attempts,
            benchmark={"benchmark": "agentic-use", "task": task_name, "mode": "offline"},
            output_dir=output_dir,
            run_id=run_id,
        )

    def _extra_metrics(self) -> list[Metric]:
        """Append :class:`VerifierRewardMetric` only when the runtime runs verify.

        The verify-enable decision stays in the adapter (it knows its own runtime
        config); the generic orchestrator never introspects the runtime.
        """
        return [VerifierRewardMetric()] if self._verify_enabled() else []

    def _verify_enabled(self) -> bool:
        runtime_config = getattr(self.runtime, "config", None)
        shared = getattr(runtime_config, "shared", None)
        return bool(getattr(shared, "run_verify", False))

    def _ensure_task_image(self, task: AgentEvalTask) -> None:
        image_tag = task_image_tag(task.id)
        task_dir = task.metadata["task_dir"]
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
