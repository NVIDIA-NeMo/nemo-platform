# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from nemo_evaluator_sdk.agent_eval.evaluator import (
    AgentEvaluator,
    _metric_row,
    _new_run_id,
    _task_row,
    _trial_from_sample,
)
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
from nemo_evaluator_sdk.agent_inference import AgentInferenceContext, AgentInvocationResult, AgentInvocationStatus
from nemo_evaluator_sdk.enums import AgentFormat, ModelFormat
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values import (
    Agent,
    GenericAgent,
    Model,
    NemoAgentToolkitAgent,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor
from nemo_evaluator_sdk.values.results import AggregateScore


def test_trial_from_sample_falls_back_to_reasoning_content() -> None:
    task = AgentEvalTask(id="task-1", intent="Answer.", inputs={"instruction": "Q?"})
    target = Model(name="reasoning-model", url="https://example/v1/chat/completions")
    response = {"choices": [{"message": {"content": None, "reasoning_content": "the reasoned answer"}}]}

    # Empty content falls back to reasoning_content; explicit content wins when present.
    fallback = _trial_from_sample(task, target, {"output_text": "  ", "response": response})
    assert fallback.output is not None
    assert fallback.output.output_text == "the reasoned answer"

    explicit = _trial_from_sample(task, target, {"output_text": "final answer", "response": response})
    assert explicit.output is not None
    assert explicit.output.output_text == "final answer"


def test_trial_from_sample_fallback_trace_has_trace_kind() -> None:
    task = AgentEvalTask(id="task-1", intent="Answer.", inputs={"instruction": "Q?"})
    target = Model(name="target", url="https://example/v1/chat/completions")

    trial = _trial_from_sample(task, target, {"output_text": "answer"})

    assert trial.evidence is not None
    trace = trial.evidence.require("trace", kind="trace")
    assert trace.format == "json"


def test_trial_from_sample_preserves_typed_trace_and_canonical_metadata() -> None:
    task = AgentEvalTask(id="task-1", intent="Answer.", inputs={"instruction": "Q?"})
    target = Model(name="canonical-target", url="https://example/v1/chat/completions")
    typed_trace = {
        "schema_version": "ATIF-v1.7",
        "steps": [{"source": "user", "message": "Q?"}],
    }

    trial = _trial_from_sample(
        task,
        target,
        {
            "output_text": "answer",
            "trajectory": [{"legacy": True}],
            "evidence": CandidateEvidence(
                descriptors={
                    "trace": EvidenceDescriptor(
                        kind="trace",
                        format="atif",
                        data=typed_trace,
                    )
                }
            ),
            "invocation_metadata": {
                "endpoint": "/generate/stream",
                "model_id": "spoofed-model",
                "target_name": "spoofed-target",
                "generated": False,
            },
        },
    )

    assert trial.evidence is not None
    trace = trial.evidence.require("trace", kind="trace")
    assert trace.format == "atif"
    assert trace.data == typed_trace
    assert trial.metadata["endpoint"] == "/generate/stream"
    assert trial.metadata["model_id"] == "canonical-target"
    assert trial.metadata["target_name"] == "canonical-target"
    assert trial.metadata["generated"] is True


def test_generated_run_ids_are_unique_within_the_same_second() -> None:
    with patch("nemo_evaluator_sdk.agent_eval.evaluator.datetime") as mock_datetime:
        mock_datetime.now.return_value.strftime.return_value = "20260628120000"

        first = _new_run_id()
        second = _new_run_id()

    assert first != second
    assert first.startswith("agent-eval-20260628120000-")


def test_metric_row_exposes_reference_but_task_row_hides_it() -> None:
    # ``reference`` is grader-only held-out ground truth: metrics must see it, the agent (via the
    # generation ``_task_row``) must not.
    task = AgentEvalTask(
        id="task-1",
        intent="Fix the bug.",
        inputs={"instruction": "Fix calculator.py."},
        reference={"test_calculator.py": "def test_add(): assert add(2, 3) == 5"},
    )
    trial = _candidate_trial()

    metric_row = _metric_row(task, trial)
    assert metric_row["reference"] == {"test_calculator.py": "def test_add(): assert add(2, 3) == 5"}

    task_row = _task_row(task)
    assert "reference" not in task_row


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


def _task(metric: Any | None = None, *, task_id: str = "task-1") -> AgentEvalTask:
    return AgentEvalTask(
        id=task_id,
        intent="Answer a professional benchmark prompt.",
        inputs={"instruction": "What is the answer?", "domain": "Finance MBA"},
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
async def test_live_model_generation_completions_endpoint_prompts_with_instruction() -> None:
    # A bare /v1/completions endpoint uses the `{"prompt": ...}` request shape; the task instruction
    # is rendered into that wire field (there is no chat `messages` wrapper).
    async def fake_model_inference(
        model: Model,
        request: dict[str, Any],
        max_retries: int | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del model, max_retries, kwargs
        assert request["prompt"] == "Use the task instruction."
        assert "messages" not in request
        return {"choices": [{"text": "Generated model answer"}]}

    task = AgentEvalTask(
        id="task-1",
        intent="Answer the instruction.",
        inputs={"instruction": "Use the task instruction."},
        metrics=[_ConstantMetric()],
    )
    model = Model(url="https://model.test/v1/completions", name="target-model", format=ModelFormat.OPEN_AI)

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
        inputs={"instruction": "Another question?"},
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
        inputs={"instruction": "Question?"},
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
        # A generic HTTP agent receives the task row directly — no chat/completions wrapper — so its
        # `body` template can reference task inputs such as `{{ instruction }}`.
        assert "messages" not in request
        assert request["instruction"] == "What is the answer?"
        return {
            "choices": [{"message": {"role": "assistant", "content": "Generated agent answer"}}],
            "trajectory": [{"tool": "search", "line": 3}],
        }

    agent = GenericAgent(
        url="https://agent.test",
        name="target-agent",
        format=AgentFormat.GENERIC,
        body={"input": "{{ instruction }}"},
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
async def test_live_agent_typed_partial_invocation_preserves_non_trace_evidence() -> None:
    metric = _EvidenceMetric()

    async def fake_agent_inference(
        agent: Agent,
        request: dict[str, Any],
        **kwargs: Any,
    ) -> AgentInvocationResult:
        del agent, request, kwargs
        return AgentInvocationResult(
            status=AgentInvocationStatus.PARTIAL,
            response={"choices": [{"message": {"role": "assistant", "content": None}}]},
            evidence=CandidateEvidence(
                descriptors={
                    "stream_events": EvidenceDescriptor(
                        kind="agent_stream_events",
                        format="json",
                        data=[{"channel": "data", "payload": {"value": {"error": "auth required"}}}],
                    )
                }
            ),
            metadata={"stream_error": "auth required"},
        )

    agent = NemoAgentToolkitAgent(url="https://agent.test", name="target-agent", format=AgentFormat.NEMO_AGENT_TOOLKIT)
    result = await AgentEvaluator(inference_fn=fake_agent_inference).run(
        tasks=[_task(metric)],
        target=agent,
        config=AgentEvalRunConfig(params=RunConfigOnline(parallelism=1)),
    )

    trial = result.trials[0]
    assert trial.status is AgentEvalTrialStatus.PARTIAL
    assert trial.evidence is not None
    assert trial.evidence.require("stream_events").kind == "agent_stream_events"
    assert "trace" not in trial.evidence.names()
    assert metric.inputs[0].candidate.evidence == trial.evidence
    assert result.scores[0].status is AgentEvalScoreStatus.COMPLETED


@pytest.mark.asyncio
async def test_live_agent_typed_failed_invocation_retains_output_and_evidence() -> None:
    async def fake_agent_inference(
        agent: Agent,
        request: dict[str, Any],
        **kwargs: Any,
    ) -> AgentInvocationResult:
        del agent, request, kwargs
        return AgentInvocationResult(
            status=AgentInvocationStatus.FAILED,
            response={"choices": [{"message": {"role": "assistant", "content": "answer"}}]},
            output_text="answer",
            evidence=CandidateEvidence(
                descriptors={
                    "raw_stream": EvidenceDescriptor(
                        kind="agent_stream",
                        format="text",
                        data="data: answer\n",
                    ),
                    "translation_error": EvidenceDescriptor(
                        kind="error",
                        format="json",
                        data={"error": "invalid ATIF"},
                    ),
                }
            ),
        )

    agent = NemoAgentToolkitAgent(
        url="https://agent.test",
        name="target-agent",
        format=AgentFormat.NEMO_AGENT_TOOLKIT,
    )
    result = await AgentEvaluator(inference_fn=fake_agent_inference).run(
        tasks=[_task()],
        target=agent,
        config=AgentEvalRunConfig(params=RunConfigOnline(parallelism=1)),
    )

    trial = result.trials[0]
    assert trial.status is AgentEvalTrialStatus.FAILED
    assert trial.output is not None
    assert trial.output.output_text == "answer"
    assert trial.evidence is not None
    assert trial.evidence.require("raw_stream").data == "data: answer\n"
    assert trial.evidence.require("translation_error").kind == "error"


@pytest.mark.asyncio
async def test_generation_boundary_names_agent_eval_context() -> None:
    agent = NemoAgentToolkitAgent(url="https://agent.test", name="target-agent", format=AgentFormat.NEMO_AGENT_TOOLKIT)
    sample = {
        "output_text": "answer",
        "response": {"choices": [{"message": {"role": "assistant", "content": "answer"}}]},
    }

    with patch(
        "nemo_evaluator_sdk.agent_eval.evaluator._generate_sample",
        new_callable=AsyncMock,
        return_value=sample,
    ) as mock_generate:
        await AgentEvaluator(inference_fn=AsyncMock()).run(
            tasks=[_task()],
            target=agent,
            config=AgentEvalRunConfig(
                run_id="run-123",
                params=RunConfigOnline(parallelism=1),
                write_dashboard=False,
            ),
        )

    assert mock_generate.await_args is not None
    assert mock_generate.await_args.kwargs["agent_eval_context"] == {
        "run_id": "run-123",
        "task_id": "task-1",
        "invocation_id": "run-123:task-1:target-agent",
    }
    assert "template_context" not in mock_generate.await_args.kwargs


@pytest.mark.asyncio
async def test_default_agent_invocation_receives_run_context_and_evidence_dir(tmp_path: Path) -> None:
    invocation = AgentInvocationResult(
        status=AgentInvocationStatus.COMPLETED,
        response={"choices": [{"message": {"role": "assistant", "content": "answer"}}]},
        output_text="answer",
    )
    agent = NemoAgentToolkitAgent(url="https://agent.test", name="target-agent", format=AgentFormat.NEMO_AGENT_TOOLKIT)
    prompt_template = {
        "input_message": "{{ item.instruction }}",
        "conversation_id": ("{{ agent_eval.run_id }}-{{ agent_eval.task_id }}-{{ agent_eval.invocation_id }}"),
    }

    with patch(
        "nemo_evaluator_sdk.agent_inference.invoke_agent",
        new_callable=AsyncMock,
        return_value=invocation,
    ) as mock_invoke:
        await AgentEvaluator().run(
            tasks=[_task()],
            target=agent,
            config=AgentEvalRunConfig(
                run_id="run-123",
                output_dir=tmp_path,
                prompt_template=prompt_template,
                params=RunConfigOnline(parallelism=1),
                write_dashboard=False,
            ),
        )

    assert mock_invoke.await_args is not None
    assert mock_invoke.await_args.args[1] == {
        "input_message": "What is the answer?",
        "conversation_id": "run-123-task-1-run-123:task-1:target-agent",
    }
    assert mock_invoke.await_args.kwargs["evidence_dir"] == tmp_path / "evidence" / "000000-task-1"


@pytest.mark.asyncio
async def test_default_agent_evidence_dirs_are_confined_and_unique(tmp_path: Path) -> None:
    captured_dirs: list[Path] = []
    invocation = AgentInvocationResult(
        status=AgentInvocationStatus.COMPLETED,
        response={"choices": [{"message": {"role": "assistant", "content": "answer"}}]},
        output_text="answer",
    )

    async def fake_invoke(agent: Agent, request: dict[str, Any], **kwargs: Any) -> AgentInvocationResult:
        del agent, request
        evidence_dir = kwargs["evidence_dir"]
        assert isinstance(evidence_dir, Path)
        captured_dirs.append(evidence_dir)
        return invocation

    tasks = [
        _task(task_id=".."),
        _task(task_id="a/b"),
        _task(task_id="a?b"),
    ]
    agent = NemoAgentToolkitAgent(url="https://agent.test", name="target-agent", format=AgentFormat.NEMO_AGENT_TOOLKIT)

    with patch("nemo_evaluator_sdk.agent_inference.invoke_agent", side_effect=fake_invoke):
        await AgentEvaluator().run(
            tasks=tasks,
            target=agent,
            config=AgentEvalRunConfig(
                run_id="run-123",
                output_dir=tmp_path,
                params=RunConfigOnline(parallelism=1),
                write_dashboard=False,
            ),
        )

    evidence_root = (tmp_path / "evidence").resolve()
    assert {path.name for path in captured_dirs} == {
        "task-000000",
        "000001-a-b",
        "000002-a-b",
    }
    assert len({path.resolve() for path in captured_dirs}) == len(tasks)
    assert all(path.resolve().parent == evidence_root for path in captured_dirs)


@pytest.mark.asyncio
async def test_agent_inference_factory_receives_per_task_context(tmp_path: Path) -> None:
    invocation = AgentInvocationResult(
        status=AgentInvocationStatus.COMPLETED,
        response={"choices": [{"message": {"role": "assistant", "content": "answer"}}]},
        output_text="answer",
    )
    agent = NemoAgentToolkitAgent(url="https://agent.test", name="target-agent", format=AgentFormat.NEMO_AGENT_TOOLKIT)

    contexts: list[AgentInferenceContext] = []

    async def inference_fn(agent, request, **kwargs):
        del agent, request, kwargs
        return invocation

    def factory(context: AgentInferenceContext):
        contexts.append(context)
        return inference_fn

    await AgentEvaluator(agent_inference_fn_factory=factory).run(
        tasks=[_task()],
        target=agent,
        config=AgentEvalRunConfig(
            run_id="run-123",
            output_dir=tmp_path,
            params=RunConfigOnline(parallelism=1),
            write_dashboard=False,
        ),
    )

    assert len(contexts) == 1
    assert contexts[0].metadata == {
        "run_id": "run-123",
        "task_id": "task-1",
        "invocation_id": "run-123:task-1:target-agent",
    }
    assert contexts[0].evidence_dir == tmp_path / "evidence" / "000000-task-1"


def test_agent_evaluator_rejects_direct_inference_and_factory() -> None:
    async def inference_fn(agent, request, **kwargs):
        del agent, request, kwargs
        return {}

    invalid_kwargs: Any = {
        "inference_fn": inference_fn,
        "agent_inference_fn_factory": lambda context: inference_fn,
    }
    with pytest.raises(ValueError, match="inference_fn.*agent_inference_fn_factory"):
        # Deliberately bypass the overload contract to verify the runtime guard for
        # dynamically typed callers.
        AgentEvaluator(**invalid_kwargs)  # ty: ignore[no-matching-overload]


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
        inputs={"instruction": "Another question?"},
        metrics=[_OtherMetric()],
    )

    with pytest.raises(ValueError, match=r"no trials produced for tasks: \['task-2'\]"):
        await AgentEvaluator().run(tasks=[_task(), other_task], trials=[_candidate_trial()])
