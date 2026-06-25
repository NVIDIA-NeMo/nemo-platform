# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import sys
import types

import pytest
from nemo_evaluator_sdk.agent_eval.tasks import (
    AgentEvalTask,
    AgentEvalTasksetBundle,
    AgentEvalTasksetLoadConfig,
    SemanticReducer,
    SemanticView,
    ViewSignal,
    resolve_agent_eval_taskset,
)
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutputSpec, MetricResult


def test_taskset_bundle_requires_at_least_one_task() -> None:
    task = AgentEvalTask(id="t", intent="i", inputs={})
    assert AgentEvalTasksetBundle(tasks=[task]).tasks == [task]
    with pytest.raises(ValueError, match="taskset bundles require at least one task"):
        AgentEvalTasksetBundle(tasks=[])


def test_resolve_agent_eval_taskset(monkeypatch: pytest.MonkeyPatch) -> None:
    # Bad refs must use module:object syntax.
    with pytest.raises(ValueError, match="module:object syntax"):
        resolve_agent_eval_taskset("no_colon")

    # A resolved object that isn't a taskset is rejected.
    with pytest.raises(TypeError, match="does not implement AgentEvalTaskset"):
        resolve_agent_eval_taskset("math:pi")

    # Happy path: a class ref is instantiated and must satisfy the protocol.
    class _FakeTaskset:
        name = "fake"

        def load(self, config: AgentEvalTasksetLoadConfig) -> AgentEvalTasksetBundle:
            return AgentEvalTasksetBundle(tasks=[AgentEvalTask(id="t", intent="i", inputs={})])

    module = types.ModuleType("fake_taskset_mod")
    module.Fake = _FakeTaskset  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_taskset_mod", module)

    taskset = resolve_agent_eval_taskset("fake_taskset_mod:Fake")
    assert taskset.name == "fake"
    assert [task.id for task in taskset.load(AgentEvalTasksetLoadConfig()).tasks] == ["t"]


class _Metric:
    @property
    def type(self) -> str:
        return "example_metric"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("score")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        raise NotImplementedError


def test_task_serializes_metric_instances_as_descriptors() -> None:
    task = AgentEvalTask(
        id="task-1",
        intent="answer the prompt",
        inputs={"prompt": "Question?"},
        metrics=[_Metric()],
    )

    assert task.model_dump(mode="json")["metrics"] == [
        {
            "type": "example_metric",
            "outputs": [{"name": "score", "description": None, "value_schema": "ContinuousScore"}],
        }
    ]


def test_task_rejects_duplicate_metric_types() -> None:
    with pytest.raises(ValueError, match="duplicate task metric types"):
        AgentEvalTask(
            id="task-1",
            intent="answer the prompt",
            inputs={"prompt": "Question?"},
            metrics=[_Metric(), _Metric()],
        )


def test_task_validates_view_signals_against_metric_outputs() -> None:
    with pytest.raises(ValueError, match="unknown output"):
        AgentEvalTask(
            id="task-1",
            intent="answer the prompt",
            inputs={"prompt": "Question?"},
            metrics=[_Metric()],
            views={
                "outcome_correctness": SemanticView(
                    reducer=SemanticReducer.SINGLE,
                    signals=[ViewSignal(metric="example_metric", output="missing")],
                )
            },
        )
