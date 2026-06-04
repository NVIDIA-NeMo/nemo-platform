# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval import (
    AgentEvalAttempt,
    AgentEvalRunConfig,
    AgentEvalTask,
    AgentEvaluator,
    AgentOutput,
)
from nemo_evaluator_sdk.enums import AgentFormat, ModelFormat
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values import Agent, Model, RunConfigOnline, RunConfigOnlineModel


class _ConstantMetric:
    @property
    def type(self) -> str:
        return "constant_metric"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("score")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        return MetricResult(outputs=[MetricOutput(name="score", value=0.75)])


class _EvidenceMetric:
    def __init__(self) -> None:
        self.inputs: list[MetricInput] = []

    @property
    def type(self) -> str:
        return "evidence_metric"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("score")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        self.inputs.append(input)
        return MetricResult(outputs=[MetricOutput(name="score", value=1.0)])


def _task(metric: Any | None = None) -> AgentEvalTask:
    return AgentEvalTask(
        id="task-1",
        intent="Answer a professional benchmark prompt.",
        inputs={"prompt": "What is the answer?", "domain": "Finance MBA"},
        metrics=[metric or _ConstantMetric()],
        metadata={"benchmark": "Example", "domain": "Finance MBA"},
    )


def _candidate_attempt() -> AgentEvalAttempt:
    return AgentEvalAttempt(
        id="attempt-1",
        task_id="task-1",
        output=AgentOutput(text="Candidate answer"),
        metadata={"model_id": "candidate"},
    )


class _AttemptRuntime:
    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalAttempt]:
        del config
        return [
            AgentEvalAttempt(
                id=f"{task.id}:runtime",
                task_id=task.id,
                output=AgentOutput(text="Runtime answer"),
                metadata={"model_id": "runtime"},
            )
            for task in tasks
        ]


def test_run_rejects_attempts_and_target_together() -> None:
    model = Model(url="https://model.test/v1/chat/completions", name="target", format=ModelFormat.OPEN_AI)

    with pytest.raises(ValueError, match="provide exactly one"):
        AgentEvaluator().run_sync(
            tasks=[_task()],
            attempts=[_candidate_attempt()],
            target=model,
        )


@pytest.mark.asyncio
async def test_scores_imported_attempts_with_metric_and_persists_bundle(tmp_path: Path) -> None:
    result = await AgentEvaluator().run(
        tasks=[_task()],
        attempts=[_candidate_attempt()],
        config=AgentEvalRunConfig(output_dir=tmp_path, parallelism=1),
    )

    assert result.summary.overall_score == 0.75
    assert result.summary.metric_scores == {"constant_metric": {"score": 0.75}}
    assert result.dashboard_path == tmp_path / "report.html"
    assert (tmp_path / "run.json").exists()
    assert (tmp_path / "results.jsonl").exists()
    assert result.results[0].metric_type == "constant_metric"
    assert result.results[0].outputs[0].value == 0.75


@pytest.mark.asyncio
async def test_scores_partial_attempts() -> None:
    result = await AgentEvaluator().run(
        tasks=[_task()],
        attempts=[
            AgentEvalAttempt(
                id="attempt-1",
                task_id="task-1",
                status="partial",
                output=AgentOutput(text="Partial answer"),
            )
        ],
    )

    assert result.summary.overall_score == 0.75


@pytest.mark.asyncio
async def test_target_runtime_produces_attempts_before_scoring() -> None:
    result = await AgentEvaluator().run(
        tasks=[_task()],
        target=_AttemptRuntime(),
    )

    assert result.attempts[0].id == "task-1:runtime"
    assert result.summary.overall_score == 0.75


@pytest.mark.asyncio
async def test_live_model_generation_with_mocked_inference() -> None:
    async def fake_model_inference(
        model: Model,
        request: dict[str, Any],
        max_retries: int | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del model, max_retries, kwargs
        assert request["messages"][0]["content"] == "What is the answer?"
        assert "prompt" not in request
        return {"choices": [{"message": {"role": "assistant", "content": "Generated model answer"}}]}

    model = Model(url="https://model.test/v1/chat/completions", name="target-model", format=ModelFormat.OPEN_AI)
    result = await AgentEvaluator().run(
        tasks=[_task()],
        target=model,
        config=AgentEvalRunConfig(
            model_inference_fn=fake_model_inference,
            params=RunConfigOnlineModel(parallelism=1),
        ),
    )

    assert result.attempts[0].metadata["model_id"] == "target-model"
    assert result.attempts[0].output is not None
    assert result.attempts[0].output.output_text == "Generated model answer"
    assert result.summary.overall_score == 0.75


@pytest.mark.asyncio
async def test_live_agent_generation_preserves_trace_evidence_for_metrics() -> None:
    metric = _EvidenceMetric()

    async def fake_agent_inference(
        agent: Agent,
        request: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        del agent, kwargs
        assert request["messages"][0]["content"] == "What is the answer?"
        return {
            "choices": [{"message": {"role": "assistant", "content": "Generated agent answer"}}],
            "trajectory": [{"tool": "search", "line": 3}],
        }

    agent = Agent(
        url="https://agent.test",
        name="target-agent",
        format=AgentFormat.GENERIC,
        body={"input": "{{ messages[-1].content }}"},
        response_path="$.answer",
    )
    result = await AgentEvaluator().run(
        tasks=[_task(metric)],
        target=agent,
        config=AgentEvalRunConfig(
            agent_inference_fn=fake_agent_inference,
            params=RunConfigOnline(parallelism=1),
        ),
    )

    assert result.attempts[0].evidence is not None
    assert result.attempts[0].evidence.require("trace").kind == "trace"
    assert result.attempts[0].output is not None
    assert result.attempts[0].output.output_text == "Generated agent answer"
    assert metric.inputs[0].candidate.evidence == result.attempts[0].evidence
