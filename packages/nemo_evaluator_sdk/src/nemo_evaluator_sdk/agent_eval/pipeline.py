# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic agent-eval pipeline: agent/scoring run + deterministic gate.

Wraps :class:`~nemo_evaluator_sdk.agent_eval.evaluator.AgentEvaluator` with the
gate from :mod:`nemo_evaluator_sdk.agent_eval.gating`. It is intentionally lean —
the only collaborators are the tasks and a target (online) or attempts (offline).
Two seams keep it backend-agnostic:

* **verify-enable is inverted to data**: callers pass ``extra_metrics`` to append
  (e.g. a verifier-reward metric). The pipeline never introspects a runtime's
  config to decide what to score.
* **environment prep is an injected hook**: ``prepare_task`` (e.g. "build the task
  image") runs per task before execution, so Docker/build specifics live in the
  caller, not here.

The common Docker case stays a few lines via :meth:`AgentEvalPipeline`'s plain
constructor (config + optional ``extra_metrics``); richer wiring is opt-in.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.gating import (
    GateThresholds,
    evaluate_gate,
    load_baseline_summary,
    write_gate_report,
)
from nemo_evaluator_sdk.agent_eval.types import (
    AgentAttemptRuntime,
    AgentEvalAttempt,
    AgentEvalRunConfig,
    AgentEvalRunResult,
    AgentEvalTask,
)
from nemo_evaluator_sdk.metrics.protocol import Metric


@dataclass(frozen=True)
class PipelineConfig:
    """Run-level knobs shared by the online and offline paths."""

    parallelism: int = 1
    write_dashboard: bool = True
    write_gate: bool = True
    gate_thresholds: GateThresholds | None = None
    baseline_summary_path: Path | None = None


class AgentEvalPipeline:
    """Run tasks through ``AgentEvaluator`` (online or offline) and apply the gate."""

    def __init__(
        self,
        *,
        config: PipelineConfig | None = None,
        extra_metrics: Sequence[Metric] = (),
    ) -> None:
        self.config = config or PipelineConfig()
        self._extra_metrics = list(extra_metrics)

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        *,
        target: AgentAttemptRuntime,
        benchmark: dict[str, object] | None = None,
        output_dir: Path | None = None,
        run_id: str | None = None,
        prepare_task: Callable[[AgentEvalTask], None] | None = None,
    ) -> AgentEvalRunResult:
        """Online path: optionally prep each task, run the runtime, score, gate."""
        prepared = [self._with_extra_metrics(task) for task in tasks]
        if prepare_task is not None:
            for task in prepared:
                prepare_task(task)

        result = await AgentEvaluator().run(
            tasks=prepared,
            target=target,
            config=self._run_config(output_dir=output_dir, run_id=run_id, benchmark=benchmark),
        )
        self._maybe_write_gate(result)
        return result

    async def score_attempts(
        self,
        tasks: Sequence[AgentEvalTask],
        *,
        attempts: Sequence[AgentEvalAttempt],
        benchmark: dict[str, object] | None = None,
        output_dir: Path | None = None,
        run_id: str | None = None,
    ) -> AgentEvalRunResult:
        """Offline path: score already-captured attempts (no agent execution)."""
        prepared = [self._with_extra_metrics(task) for task in tasks]
        result = await AgentEvaluator().run(
            tasks=prepared,
            attempts=list(attempts),
            config=self._run_config(output_dir=output_dir, run_id=run_id, benchmark=benchmark),
        )
        self._maybe_write_gate(result)
        return result

    def _run_config(
        self,
        *,
        output_dir: Path | None,
        run_id: str | None,
        benchmark: dict[str, object] | None,
    ) -> AgentEvalRunConfig:
        return AgentEvalRunConfig(
            output_dir=output_dir,
            run_id=run_id,
            parallelism=self.config.parallelism,
            write_dashboard=self.config.write_dashboard,
            benchmark=dict(benchmark or {}),
        )

    def _with_extra_metrics(self, task: AgentEvalTask) -> AgentEvalTask:
        """Append injected metrics, honoring task-authored metrics and avoiding duplicate types."""
        if not self._extra_metrics:
            return task
        metrics: list[Metric] = list(task.metrics)
        existing_types = {type(metric) for metric in metrics}
        appended = [metric for metric in self._extra_metrics if type(metric) not in existing_types]
        if not appended:
            return task
        return task.model_copy(update={"metrics": metrics + appended})

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


__all__ = [
    "AgentEvalPipeline",
    "GateThresholds",
    "PipelineConfig",
]
