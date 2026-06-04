# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval import (
    AgentEvalAttempt,
    AgentEvalMetricSpec,
    AgentEvalRunConfig,
    AgentEvalTask,
    AgentEvaluator,
    AgentOutput,
    ProfBenchCriterion,
    ProfBenchJudgeDecision,
)
from nemo_evaluator_sdk.agent_eval.profbench import PROFBENCH_METRIC_ID, PROFBENCH_METRIC_TYPE
from nemo_evaluator_sdk.enums import AgentFormat, ModelFormat
from nemo_evaluator_sdk.values import Agent, Model, RunConfigOnline, RunConfigOnlineModel


class _FakeJudge:
    async def judge(self, request: Any) -> ProfBenchJudgeDecision:
        fulfilled = request.criterion_id.endswith("criterion-1")
        return ProfBenchJudgeDecision(fulfilled=fulfilled, reason=f"fake judge for {request.criterion_id}")


def _profbench_task() -> AgentEvalTask:
    criterion_1 = ProfBenchCriterion(
        id="task-1:criterion-1",
        description="States the core answer.",
        weight_name="Critical",
        points=4,
        criterion_type="Correctness",
        source_uri="/tmp/profbench.jsonl",
        line_number=12,
        json_path="$.rubrics[0]",
    )
    criterion_2 = ProfBenchCriterion(
        id="task-1:criterion-2",
        description="Includes the caveat.",
        weight_name="Minor",
        points=2,
        criterion_type="Completeness",
        source_uri="/tmp/profbench.jsonl",
        line_number=12,
        json_path="$.rubrics[1]",
    )
    return AgentEvalTask(
        id="task-1",
        intent="Answer a professional benchmark prompt.",
        inputs={"prompt": "What is the answer?", "domain": "Finance MBA"},
        metrics=[
            AgentEvalMetricSpec(
                id=PROFBENCH_METRIC_ID,
                type=PROFBENCH_METRIC_TYPE,
                config={"rubrics": [criterion_1.model_dump(mode="json"), criterion_2.model_dump(mode="json")]},
            )
        ],
        metadata={"benchmark": "ProfBench", "domain": "Finance MBA"},
    )


def _candidate_attempt() -> AgentEvalAttempt:
    return AgentEvalAttempt(
        id="attempt-1",
        task_id="task-1",
        output=AgentOutput(output_text="Candidate answer"),
        metadata={"model_id": "candidate"},
    )


def test_run_rejects_attempts_and_target_together() -> None:
    model = Model(url="https://model.test/v1/chat/completions", name="target", format=ModelFormat.OPEN_AI)

    with pytest.raises(ValueError, match="provide exactly one"):
        AgentEvaluator().run_sync(
            tasks=[_profbench_task()],
            attempts=[_candidate_attempt()],
            target=model,
            config=AgentEvalRunConfig(judge=_FakeJudge()),
        )


@pytest.mark.asyncio
async def test_scores_imported_attempts_with_fake_judge_and_artifacts(tmp_path: Path) -> None:
    result = await AgentEvaluator().run(
        tasks=[_profbench_task()],
        attempts=[_candidate_attempt()],
        config=AgentEvalRunConfig(judge=_FakeJudge(), output_dir=tmp_path, parallelism=1),
    )

    assert result.summary.overall_score == 4 / 6
    assert result.dashboard_path == tmp_path / "report.html"
    assert (tmp_path / "run.json").exists()
    assert (tmp_path / "results.jsonl").exists()
    assert result.results[0].deductions[0].evidence[1].kind == "judge"
    assert Path(result.results[0].deductions[0].evidence[1].uri).exists()


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
        tasks=[_profbench_task()],
        target=model,
        config=AgentEvalRunConfig(
            judge=_FakeJudge(),
            model_inference_fn=fake_model_inference,
            params=RunConfigOnlineModel(parallelism=1),
        ),
    )

    assert result.attempts[0].metadata["model_id"] == "target-model"
    assert result.attempts[0].output is not None
    assert result.attempts[0].output.output_text == "Generated model answer"
    assert result.summary.overall_score == 4 / 6


@pytest.mark.asyncio
async def test_live_agent_generation_preserves_trace_evidence() -> None:
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
        tasks=[_profbench_task()],
        target=agent,
        config=AgentEvalRunConfig(
            judge=_FakeJudge(),
            agent_inference_fn=fake_agent_inference,
            params=RunConfigOnline(parallelism=1),
        ),
    )

    assert result.attempts[0].output is not None
    assert result.attempts[0].output.evidence is not None
    assert result.attempts[0].output.evidence.trace is not None
    assert result.attempts[0].output.evidence.trace.kind == "trace"
    assert result.attempts[0].output.output_text == "Generated agent answer"
