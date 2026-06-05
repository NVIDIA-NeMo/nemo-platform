# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval import (
    AgentEvalAttempt,
    AgentEvalRunConfig,
    AgentEvalSummary,
    AgentEvalTask,
    AgentEvalTaskResult,
    AgentEvaluator,
    AgentOutput,
    SemanticView,
    ViewSignal,
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


class _OtherMetric:
    @property
    def type(self) -> str:
        return "other_metric"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("quality")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        return MetricResult(outputs=[MetricOutput(name="quality", value=0.25)])


class _FailingMetric:
    @property
    def type(self) -> str:
        return "failing_metric"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("score")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        raise RuntimeError("missing final_state evidence")


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


def _agent_eval_result(
    run_id: str,
    task_id: str,
    attempt_id: str,
    metric_type: str,
    output_name: str,
    output_value: float,
) -> AgentEvalTaskResult:
    return AgentEvalTaskResult(
        id=f"{run_id}:{task_id}:{attempt_id}:{metric_type}",
        run_id=run_id,
        task_id=task_id,
        attempt_id=attempt_id,
        metric_type=metric_type,
        outputs=[MetricOutput(name=output_name, value=output_value)],
    )


class _AttemptRuntime:
    def __init__(self) -> None:
        self.config: AgentEvalRunConfig | None = None

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalAttempt]:
        self.config = config
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
    assert "run_id" not in json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))

    result_payload = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert result_payload["id"] == f"{result.run_id}:task-1:attempt-1:constant_metric"
    assert result_payload["run_id"] == result.run_id
    assert result_payload["status"] == "completed"
    assert result_payload["diagnostics"] == []

    run_payload = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert run_payload == {
        "artifacts": {
            "attempts": "attempts.jsonl",
            "benchmark": "benchmark.json",
            "results": "results.jsonl",
            "summary": "summary.json",
            "tasks": "tasks.jsonl",
        },
        "dashboard_path": str(tmp_path / "report.html"),
        "output_dir": str(tmp_path),
        "run_id": result.run_id,
    }
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
    runtime = _AttemptRuntime()
    result = await AgentEvaluator().run(
        tasks=[_task()],
        target=runtime,
    )

    assert result.attempts[0].id == "task-1:runtime"
    assert runtime.config is not None
    assert runtime.config.run_id == result.run_id
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
async def test_live_model_generation_uses_instruction_when_prompt_is_absent() -> None:
    async def fake_model_inference(
        model: Model,
        request: dict[str, Any],
        max_retries: int | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del model, max_retries, kwargs
        assert request["messages"][0]["content"] == "Use the task instruction."
        return {"choices": [{"message": {"role": "assistant", "content": "Generated model answer"}}]}

    task = AgentEvalTask(
        id="task-1",
        intent="Fallback intent.",
        inputs={"instruction": "Use the task instruction."},
        metrics=[_ConstantMetric()],
    )
    model = Model(url="https://model.test/v1/chat/completions", name="target-model", format=ModelFormat.OPEN_AI)

    await AgentEvaluator().run(
        tasks=[task],
        target=model,
        config=AgentEvalRunConfig(
            model_inference_fn=fake_model_inference,
            params=RunConfigOnlineModel(parallelism=1),
        ),
    )


@pytest.mark.asyncio
async def test_metric_failure_records_failed_result_and_does_not_stop_other_metrics() -> None:
    task = _task(metric=_FailingMetric())
    other_task = AgentEvalTask(
        id="task-2",
        intent="Answer another prompt.",
        inputs={"prompt": "Another question?"},
        metrics=[_OtherMetric()],
    )
    attempts = [
        _candidate_attempt(),
        AgentEvalAttempt(id="attempt-2", task_id="task-2", output=AgentOutput(text="Other answer")),
    ]

    result = await AgentEvaluator().run(tasks=[task, other_task], attempts=attempts)

    failed = next(item for item in result.results if item.metric_type == "failing_metric")
    completed = next(item for item in result.results if item.metric_type == "other_metric")
    assert failed.status == "failed"
    assert failed.outputs == []
    assert failed.diagnostics[0].message == "missing final_state evidence"
    assert completed.status == "completed"
    assert completed.outputs[0].value == 0.25
    assert result.summary.metric_coverage["failing_metric"]["score"].failed == 1
    assert result.summary.metric_coverage["other_metric"]["quality"].scored == 1


@pytest.mark.asyncio
async def test_metric_failure_can_fail_fast_for_development() -> None:
    with pytest.raises(RuntimeError, match="missing final_state evidence"):
        await AgentEvaluator().run(
            tasks=[_task(metric=_FailingMetric())],
            attempts=[_candidate_attempt()],
            config=AgentEvalRunConfig(fail_fast=True),
        )


def test_summary_reports_coverage_and_avoids_cross_metric_overall_score() -> None:
    task = AgentEvalTask(
        id="task-1",
        intent="Answer a prompt.",
        inputs={"prompt": "Question?"},
        metrics=[_ConstantMetric(), _OtherMetric()],
        views={
            "outcome_correctness": SemanticView(
                reducer="mean",
                signals=[
                    ViewSignal(metric="constant_metric", output="score"),
                    ViewSignal(metric="other_metric", output="quality"),
                ],
            )
        },
    )
    results = [
        _agent_eval_result("run-1", "task-1", "attempt-1", "constant_metric", "score", 1.0),
        _agent_eval_result("run-1", "task-1", "attempt-1", "other_metric", "quality", 0.0),
    ]

    summary = AgentEvalSummary.from_results(results, tasks=[task])

    assert summary.overall_score is None
    assert summary.metric_scores == {"constant_metric": {"score": 1.0}, "other_metric": {"quality": 0.0}}
    assert summary.metric_coverage["constant_metric"]["score"].total == 1
    assert summary.metric_coverage["constant_metric"]["score"].scored == 1
    assert summary.semantic_view_scores == {"outcome_correctness": 0.5}


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
