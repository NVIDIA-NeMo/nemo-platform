# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the generic agent-eval pipeline (online + offline paths)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.common_metrics import AgentPhaseSuccessMetric
from nemo_evaluator_sdk.agent_eval.pipeline import AgentEvalPipeline, PipelineConfig
from nemo_evaluator_sdk.agent_eval.types import (
    AgentAttemptSerde,
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
    pipeline = AgentEvalPipeline(
        config=PipelineConfig(write_dashboard=False, write_gate=True),
        extra_metrics=[_ExtraMetric()],
    )

    result = await pipeline.run_tasks(
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
    pipeline = AgentEvalPipeline(config=PipelineConfig(write_dashboard=False, write_gate=False))
    attempt = AgentEvalAttempt(
        id="demo:stored",
        task_id="demo",
        status="completed",
        output=AgentOutput(text="ok"),
        metadata={"agent_ok": True},
    )
    result = await pipeline.score_attempts([_task()], attempts=[attempt])
    assert [m.type for m in result.tasks[0].metrics] == ["agent_phase_success"]
    assert any(r.metric_type == "agent_phase_success" for r in result.results)


@pytest.mark.asyncio
async def test_extra_metrics_deduplicated_by_type() -> None:
    task = AgentEvalTask(id="demo", intent="i", inputs={}, metrics=[AgentPhaseSuccessMetric(), _ExtraMetric()])
    pipeline = AgentEvalPipeline(
        config=PipelineConfig(write_dashboard=False, write_gate=False),
        extra_metrics=[_ExtraMetric()],
    )
    attempt = AgentEvalAttempt(id="demo:s", task_id="demo", status="completed", output=AgentOutput(text="ok"))
    result = await pipeline.score_attempts([task], attempts=[attempt])
    types = [m.type for m in result.tasks[0].metrics]
    assert types.count("extra") == 1


def test_attempt_serde_round_trips_through_one_codec(tmp_path: Path) -> None:
    # A directory-bound serde satisfies the symmetric read/write protocol.
    class _DirSerde:
        def __init__(self, path: str | Path, *, task: AgentEvalTask) -> None:
            self._path = Path(path)
            self._task = task

        def read(self) -> AgentEvalAttempt:
            payload = json.loads((self._path / "attempt.json").read_text(encoding="utf-8"))
            return AgentEvalAttempt(
                id=f"{self._task.id}:stored",
                task_id=self._task.id,
                status="completed",
                output=AgentOutput(text=payload["agent"]),
            )

        def write(self, attempt: AgentEvalAttempt) -> None:
            self._path.mkdir(parents=True, exist_ok=True)
            (self._path / "attempt.json").write_text(
                json.dumps({"agent": attempt.output.text if attempt.output else ""}), encoding="utf-8"
            )

    serde: AgentAttemptSerde = _DirSerde(tmp_path, task=_task())
    assert isinstance(serde, AgentAttemptSerde)
    serde.write(AgentEvalAttempt(id="demo:x", task_id="demo", status="completed", output=AgentOutput(text="ok")))
    attempt = serde.read()
    assert attempt.task_id == "demo" and attempt.output is not None and attempt.output.text == "ok"
