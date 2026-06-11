# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval import AgentEvalAttempt, AgentEvalTask, AgentOutput
from nemo_evaluator_sdk.agent_eval.benchmarks import (
    AgentEvalBenchmarkBundle,
    resolve_agent_eval_benchmark,
)
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult


class _Metric:
    @property
    def type(self) -> str:
        return "test_metric"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("score")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        del input
        return MetricResult(outputs=[MetricOutput(name="score", value=1.0)])


def _task() -> AgentEvalTask:
    return AgentEvalTask(id="task-1", intent="Answer.", inputs={"prompt": "Question?"}, metrics=[_Metric()])


def _attempt() -> AgentEvalAttempt:
    return AgentEvalAttempt(id="attempt-1", task_id="task-1", output=AgentOutput(text="Answer."))


def test_benchmark_bundle_accepts_optional_attempts() -> None:
    bundle = AgentEvalBenchmarkBundle(tasks=[_task()], attempts=[_attempt()])

    assert bundle.attempts is not None
    assert bundle.attempts[0].id == "attempt-1"


def test_benchmark_bundle_requires_tasks() -> None:
    with pytest.raises(ValueError, match="benchmark bundles require at least one task"):
        AgentEvalBenchmarkBundle(
            tasks=[],
        )


def test_resolve_agent_eval_benchmark_accepts_instance_class_and_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = tmp_path / "custom_benchmarks.py"
    module_path.write_text(
        """
class InstanceBenchmark:
    name = "instance"
    def load(self, config):
        raise NotImplementedError

class ClassBenchmark:
    name = "class"
    def load(self, config):
        raise NotImplementedError

def benchmark_factory():
    return ClassBenchmark()

instance_benchmark = InstanceBenchmark()
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("custom_benchmarks", None)

    instance = resolve_agent_eval_benchmark("custom_benchmarks:instance_benchmark")
    class_instance = resolve_agent_eval_benchmark("custom_benchmarks:ClassBenchmark")
    factory_instance = resolve_agent_eval_benchmark("custom_benchmarks:benchmark_factory")

    assert instance.name == "instance"
    assert class_instance.name == "class"
    assert factory_instance.name == "class"


def test_resolve_agent_eval_benchmark_rejects_invalid_ref() -> None:
    with pytest.raises(ValueError, match="module:object"):
        resolve_agent_eval_benchmark("missing_separator")
