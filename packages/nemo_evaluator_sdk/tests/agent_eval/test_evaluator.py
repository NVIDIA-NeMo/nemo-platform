# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.results import AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalScoreStatus, AgentEvalTaskScore
from nemo_evaluator_sdk.agent_eval.tasks import (
    AgentEvalRunConfig,
    AgentEvalTask,
    SemanticReducer,
    SemanticView,
    ViewSignal,
)
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.enums import AgentFormat, ModelFormat
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values import Agent, Model, RunConfigOnline, RunConfigOnlineModel
from nemo_evaluator_sdk.values.results import AggregateScore


def _score(summary: AgentEvalSummary, name: str) -> AggregateScore:
    for aggregate in summary.scores.scores:
        if aggregate.name == name:
            return aggregate
    raise KeyError(name)


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


def _candidate_trial() -> AgentEvalTrial:
    return AgentEvalTrial(
        id="trial-1",
        task_id="task-1",
        status=AgentEvalTrialStatus.COMPLETED,
        output=AgentOutput(output_text="Candidate answer"),
        metadata={"model_id": "candidate"},
    )


def _task_score(
    run_id: str,
    task_id: str,
    trial_id: str,
    metric_type: str,
    output_name: str,
    output_value: float,
) -> AgentEvalTaskScore:
    return AgentEvalTaskScore(
        id=f"{run_id}:{task_id}:{trial_id}:{metric_type}",
        run_id=run_id,
        task_id=task_id,
        trial_id=trial_id,
        metric_type=metric_type,
        status=AgentEvalScoreStatus.COMPLETED,
        outputs=[MetricOutput(name=output_name, value=output_value)],
    )


class _TaskRunner:
    def __init__(self) -> None:
        self.config: AgentEvalRunConfig | None = None

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalTrial]:
        self.config = config
        return [
            AgentEvalTrial(
                id=f"{task.id}:runtime",
                task_id=task.id,
                status=AgentEvalTrialStatus.COMPLETED,
                output=AgentOutput(output_text="Runtime answer"),
                metadata={"model_id": "runtime"},
            )
            for task in tasks
        ]


def test_run_rejects_trials_and_target_together() -> None:
    model = Model(url="https://model.test/v1/chat/completions", name="target", format=ModelFormat.OPEN_AI)

    with pytest.raises(ValueError, match="provide exactly one"):
        AgentEvaluator().run_sync(
            tasks=[_task()],
            trials=[_candidate_trial()],
            target=model,
        )


@pytest.mark.asyncio
async def test_scores_imported_trials_with_metric_and_persists_bundle(tmp_path: Path) -> None:
    result = await AgentEvaluator().run(
        tasks=[_task()],
        trials=[_candidate_trial()],
        config=AgentEvalRunConfig(output_dir=tmp_path, parallelism=1),
    )

    assert _score(result.summary, "constant_metric.score").mean == 0.75
    assert result.dashboard_path == tmp_path / "report.html"
    assert (tmp_path / "run.json").exists()
    assert (tmp_path / "scores.jsonl").exists()
    assert "run_id" not in json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))

    score_payload = json.loads((tmp_path / "scores.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert score_payload["id"] == f"{result.run_id}:task-1:trial-1:constant_metric"
    assert score_payload["run_id"] == result.run_id
    assert score_payload["status"] == "completed"
    assert score_payload["diagnostics"] == []

    run_payload = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert run_payload == {
        "artifacts": {
            "benchmark": "benchmark.json",
            "scores": "scores.jsonl",
            "summary": "summary.json",
            "tasks": "tasks.jsonl",
            "trials": "trials.jsonl",
        },
        "dashboard_path": str(tmp_path / "report.html"),
        "output_dir": str(tmp_path),
        "run_id": result.run_id,
    }
    assert result.scores[0].metric_type == "constant_metric"
    assert result.scores[0].outputs[0].value == 0.75


@pytest.mark.asyncio
async def test_scores_partial_trials() -> None:
    result = await AgentEvaluator().run(
        tasks=[_task()],
        trials=[
            AgentEvalTrial(
                id="trial-1",
                task_id="task-1",
                status=AgentEvalTrialStatus.PARTIAL,
                output=AgentOutput(output_text="Partial answer"),
            )
        ],
    )

    assert _score(result.summary, "constant_metric.score").mean == 0.75


@pytest.mark.asyncio
async def test_target_runtime_produces_trials_before_scoring() -> None:
    runtime = _TaskRunner()
    result = await AgentEvaluator().run(
        tasks=[_task()],
        target=runtime,
    )

    assert result.trials[0].id == "task-1:runtime"
    assert runtime.config is not None
    assert runtime.config.run_id == result.run_id
    assert _score(result.summary, "constant_metric.score").mean == 0.75


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
    result = await AgentEvaluator(inference_fn=fake_model_inference).run(
        tasks=[_task()],
        target=model,
        config=AgentEvalRunConfig(params=RunConfigOnlineModel(parallelism=1)),
    )

    assert result.trials[0].metadata["model_id"] == "target-model"
    assert result.trials[0].output is not None
    assert result.trials[0].output.output_text == "Generated model answer"
    assert _score(result.summary, "constant_metric.score").mean == 0.75


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

    await AgentEvaluator(inference_fn=fake_model_inference).run(
        tasks=[task],
        target=model,
        config=AgentEvalRunConfig(params=RunConfigOnlineModel(parallelism=1)),
    )


@pytest.mark.asyncio
async def test_metric_failure_records_failed_score_and_does_not_stop_other_metrics() -> None:
    task = _task(metric=_FailingMetric())
    other_task = AgentEvalTask(
        id="task-2",
        intent="Answer another prompt.",
        inputs={"prompt": "Another question?"},
        metrics=[_OtherMetric()],
    )
    trials = [
        _candidate_trial(),
        AgentEvalTrial(
            id="trial-2",
            task_id="task-2",
            status=AgentEvalTrialStatus.COMPLETED,
            output=AgentOutput(output_text="Other answer"),
        ),
    ]

    result = await AgentEvaluator().run(tasks=[task, other_task], trials=trials)

    failed = next(item for item in result.scores if item.metric_type == "failing_metric")
    completed = next(item for item in result.scores if item.metric_type == "other_metric")
    assert failed.status.value == "failed"
    assert failed.outputs == []
    assert failed.diagnostics[0].message == "missing final_state evidence"
    assert completed.status.value == "completed"
    assert completed.outputs[0].value == 0.25
    assert result.summary.metric_coverage["failing_metric"]["score"].failed == 1
    assert result.summary.metric_coverage["other_metric"]["quality"].scored == 1


@pytest.mark.asyncio
async def test_metric_failure_can_fail_fast_for_development() -> None:
    with pytest.raises(RuntimeError, match="missing final_state evidence"):
        await AgentEvaluator().run(
            tasks=[_task(metric=_FailingMetric())],
            trials=[_candidate_trial()],
            config=AgentEvalRunConfig(fail_fast=True),
        )


def test_summary_reports_coverage_and_merges_views_into_scores() -> None:
    task = AgentEvalTask(
        id="task-1",
        intent="Answer a prompt.",
        inputs={"prompt": "Question?"},
        metrics=[_ConstantMetric(), _OtherMetric()],
        views={
            "outcome_correctness": SemanticView(
                reducer=SemanticReducer.MEAN,
                signals=[
                    ViewSignal(metric="constant_metric", output="score"),
                    ViewSignal(metric="other_metric", output="quality"),
                ],
            )
        },
    )
    scores = [
        _task_score("run-1", "task-1", "trial-1", "constant_metric", "score", 1.0),
        _task_score("run-1", "task-1", "trial-1", "other_metric", "quality", 0.0),
    ]

    summary = AgentEvalSummary.from_scores(scores, tasks=[task])

    assert _score(summary, "constant_metric.score").mean == 1.0
    assert _score(summary, "other_metric.quality").mean == 0.0
    assert _score(summary, "view.outcome_correctness").mean == 0.5
    assert summary.metric_coverage["constant_metric"]["score"].total == 1
    assert summary.metric_coverage["constant_metric"]["score"].scored == 1


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
    result = await AgentEvaluator(inference_fn=fake_agent_inference).run(
        tasks=[_task(metric)],
        target=agent,
        config=AgentEvalRunConfig(params=RunConfigOnline(parallelism=1)),
    )

    assert result.trials[0].evidence is not None
    assert result.trials[0].evidence.require("trace").kind == "trace"
    assert result.trials[0].output is not None
    assert result.trials[0].output.output_text == "Generated agent answer"
    assert metric.inputs[0].candidate.evidence == result.trials[0].evidence


@pytest.mark.asyncio
async def test_live_generation_ignore_request_failure_records_failed_trial() -> None:
    async def failing_model_inference(
        model: Model,
        request: dict[str, Any],
        max_retries: int | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del model, request, max_retries, kwargs
        raise RuntimeError("inference boom")

    model = Model(url="https://model.test/v1/chat/completions", name="target-model", format=ModelFormat.OPEN_AI)

    result = await AgentEvaluator(inference_fn=failing_model_inference).run(
        tasks=[_task()],
        target=model,
        config=AgentEvalRunConfig(params=RunConfigOnlineModel(parallelism=1, ignore_request_failure=True)),
    )

    assert result.trials[0].status is AgentEvalTrialStatus.FAILED
    assert result.trials[0].output is None
    assert result.trials[0].metadata["error"] == "inference boom"
    assert result.scores[0].status is AgentEvalScoreStatus.FAILED
    assert result.summary.metric_coverage["constant_metric"]["score"].failed == 1

    # Without ignore_request_failure the run aborts on the first failed request.
    with pytest.raises(RuntimeError, match="inference boom"):
        await AgentEvaluator(inference_fn=failing_model_inference).run(
            tasks=[_task()],
            target=model,
            config=AgentEvalRunConfig(params=RunConfigOnlineModel(parallelism=1)),
        )


@pytest.mark.asyncio
async def test_run_rejects_tasks_without_trials() -> None:
    other_task = AgentEvalTask(
        id="task-2",
        intent="Answer another prompt.",
        inputs={"prompt": "Another question?"},
        metrics=[_OtherMetric()],
    )

    with pytest.raises(ValueError, match=r"no trials produced for tasks: \['task-2'\]"):
        await AgentEvaluator().run(tasks=[_task(), other_task], trials=[_candidate_trial()])
