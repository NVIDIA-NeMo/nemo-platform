# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the generic agent-eval orchestrator (online + offline paths)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.common_metrics import AgentPhaseSuccessMetric
from nemo_evaluator_sdk.agent_eval.orchestrator import AgentEvalOrchestrator, OrchestratorConfig
from nemo_evaluator_sdk.agent_eval.types import (
    AgentEvalAttempt,
    AgentEvalRunConfig,
    AgentEvalTask,
    AgentOutput,
)
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult


class _ExtraMetric:
    @property
    def type(self) -> str:
        return "extra"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("extra")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        return MetricResult(outputs=[MetricOutput(name="extra", value=1.0)])


class _FakeRuntime:
    def __init__(self) -> None:
        self.prepared_ids: list[str] = []

    async def run_tasks(
        self, tasks: Sequence[AgentEvalTask], config: AgentEvalRunConfig | None = None
    ) -> Sequence[AgentEvalAttempt]:
        return [
            AgentEvalAttempt(
                id=f"{task.id}:fake",
                task_id=task.id,
                status="completed",
                output=AgentOutput(text="ok"),
                metadata={"agent_ok": True},
            )
            for task in tasks
        ]


def _task() -> AgentEvalTask:
    return AgentEvalTask(id="demo", intent="do it", inputs={}, metrics=[AgentPhaseSuccessMetric()])


@pytest.mark.asyncio
async def test_run_tasks_appends_extra_metrics_and_runs_prepare_hook(tmp_path: Path) -> None:
    runtime = _FakeRuntime()
    seen: list[str] = []
    orch = AgentEvalOrchestrator(
        config=OrchestratorConfig(write_dashboard=False, write_gate=True),
        extra_metrics=[_ExtraMetric()],
    )

    result = await orch.run_tasks(
        [_task()],
        target=runtime,
        benchmark={"benchmark": "demo"},
        output_dir=tmp_path,
        run_id="run-1",
        prepare_task=lambda task: seen.append(task.id),
    )

    assert seen == ["demo"]
    assert {m.type for m in result.tasks[0].metrics} == {"agent_phase_success", "extra"}
    assert result.attempts[0].status == "completed"
    # Gate is written next to the run bundle.
    assert (tmp_path / "gate.json").exists()


@pytest.mark.asyncio
async def test_score_attempts_offline_does_not_invoke_runtime() -> None:
    orch = AgentEvalOrchestrator(config=OrchestratorConfig(write_dashboard=False, write_gate=False))
    attempt = AgentEvalAttempt(
        id="demo:stored",
        task_id="demo",
        status="completed",
        output=AgentOutput(text="ok"),
        metadata={"agent_ok": True},
    )
    result = await orch.score_attempts([_task()], attempts=[attempt])
    assert [m.type for m in result.tasks[0].metrics] == ["agent_phase_success"]
    assert any(r.metric_type == "agent_phase_success" for r in result.results)


@pytest.mark.asyncio
async def test_extra_metrics_deduplicated_by_type() -> None:
    task = AgentEvalTask(id="demo", intent="i", inputs={}, metrics=[AgentPhaseSuccessMetric(), _ExtraMetric()])
    orch = AgentEvalOrchestrator(
        config=OrchestratorConfig(write_dashboard=False, write_gate=False),
        extra_metrics=[_ExtraMetric()],
    )
    attempt = AgentEvalAttempt(id="demo:s", task_id="demo", status="completed", output=AgentOutput(text="ok"))
    result = await orch.score_attempts([task], attempts=[attempt])
    types = [m.type for m in result.tasks[0].metrics]
    assert types.count("extra") == 1


def test_result_dir_attempt_source_protocol_shape(tmp_path: Path) -> None:
    # A minimal AgentAttemptSource implementation satisfies the protocol.
    from nemo_evaluator_sdk.agent_eval.types import AgentAttemptSource

    class _Source:
        def load_attempt(self, source: str | Path, *, task: AgentEvalTask) -> AgentEvalAttempt:
            payload = json.loads(Path(source).read_text(encoding="utf-8"))
            return AgentEvalAttempt(
                id=f"{task.id}:stored",
                task_id=task.id,
                status="completed",
                output=AgentOutput(text=payload["agent"]),
            )

    src_path = tmp_path / "result.json"
    src_path.write_text(json.dumps({"agent": "ok"}), encoding="utf-8")
    source: AgentAttemptSource = _Source()
    assert isinstance(source, AgentAttemptSource)
    attempt = source.load_attempt(src_path, task=_task())
    assert attempt.task_id == "demo"
