# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval import AgentEvalAttempt, AgentEvalTask, AgentOutput
from nemo_evaluator_sdk.agent_eval.benchmarks import (
    AgentEvalBenchmarkBundle,
    AgentEvalBenchmarkEvaluationKind,
    AgentEvalBenchmarkReports,
)
from nemo_evaluator_sdk.agent_eval.runner import benchmark_report_paths, run_benchmark_bundle
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


class _Target:
    async def run_tasks(self, tasks: list[AgentEvalTask], config: Any | None = None) -> list[AgentEvalAttempt]:
        del config
        return [
            AgentEvalAttempt(id=f"{task.id}:target", task_id=task.id, output=AgentOutput(text="Generated answer."))
            for task in tasks
        ]


def _task() -> AgentEvalTask:
    return AgentEvalTask(id="task-1", intent="Answer.", inputs={"prompt": "Question?"}, metrics=[_Metric()])


def _attempt() -> AgentEvalAttempt:
    return AgentEvalAttempt(id="attempt-1", task_id="task-1", output=AgentOutput(text="Recorded answer."))


@pytest.mark.asyncio
async def test_run_benchmark_bundle_scores_stored_attempts_and_writes_reports(tmp_path: Path) -> None:
    class FakeReportWriter:
        def write_reports(self, result: Any, output_dir: Path) -> AgentEvalBenchmarkReports:
            assert result.summary.task_count == 1
            path = output_dir / "custom-report.html"
            path.write_text("custom", encoding="utf-8")
            return AgentEvalBenchmarkReports(paths=[path])

    bundle = AgentEvalBenchmarkBundle(
        evaluation_kind=AgentEvalBenchmarkEvaluationKind.STORED_ATTEMPTS,
        tasks=[_task()],
        attempts=[_attempt()],
        metadata={"benchmark": "test"},
    )

    result, reports = await run_benchmark_bundle(
        bundle=bundle,
        output_dir=tmp_path / "run",
        run_id="run-1",
        report_writer=FakeReportWriter(),
    )

    assert result.summary.attempt_count == 1
    assert [path.name for path in reports.paths] == ["custom-report.html"]


@pytest.mark.asyncio
async def test_run_benchmark_bundle_rejects_stored_attempts_with_target(tmp_path: Path) -> None:
    bundle = AgentEvalBenchmarkBundle(
        evaluation_kind=AgentEvalBenchmarkEvaluationKind.STORED_ATTEMPTS,
        tasks=[_task()],
        attempts=[_attempt()],
    )

    with pytest.raises(ValueError, match="stored_attempts benchmark bundles must not be run with a target"):
        await run_benchmark_bundle(
            bundle=bundle,
            output_dir=tmp_path / "run",
            run_id="run-1",
            target=_Target(),
        )


@pytest.mark.asyncio
async def test_run_benchmark_bundle_rejects_stored_attempts_without_attempts(tmp_path: Path) -> None:
    bundle = AgentEvalBenchmarkBundle.model_construct(
        evaluation_kind=AgentEvalBenchmarkEvaluationKind.STORED_ATTEMPTS,
        tasks=[_task()],
        attempts=None,
        metadata={},
    )

    with pytest.raises(ValueError, match="stored_attempts benchmark bundles require attempts"):
        await run_benchmark_bundle(
            bundle=bundle,
            output_dir=tmp_path / "run",
            run_id="run-1",
        )


@pytest.mark.asyncio
async def test_run_benchmark_bundle_runs_live_target(tmp_path: Path) -> None:
    bundle = AgentEvalBenchmarkBundle(
        evaluation_kind=AgentEvalBenchmarkEvaluationKind.LIVE_TARGET,
        tasks=[_task()],
        metadata={"benchmark": "test"},
    )

    result, reports = await run_benchmark_bundle(
        bundle=bundle,
        output_dir=tmp_path / "run",
        run_id="run-1",
        target=_Target(),
    )

    assert result.summary.attempt_count == 1
    assert result.attempts[0].id == "task-1:target"
    assert [path.name for path in reports.paths] == ["report.html"]


@pytest.mark.asyncio
async def test_run_benchmark_bundle_rejects_live_target_without_target(tmp_path: Path) -> None:
    bundle = AgentEvalBenchmarkBundle(
        evaluation_kind=AgentEvalBenchmarkEvaluationKind.LIVE_TARGET,
        tasks=[_task()],
    )

    with pytest.raises(ValueError, match="live_target benchmark bundles require a target"):
        await run_benchmark_bundle(
            bundle=bundle,
            output_dir=tmp_path / "run",
            run_id="run-1",
        )


@pytest.mark.asyncio
async def test_run_benchmark_bundle_rejects_live_target_with_attempts(tmp_path: Path) -> None:
    bundle = AgentEvalBenchmarkBundle.model_construct(
        evaluation_kind=AgentEvalBenchmarkEvaluationKind.LIVE_TARGET,
        tasks=[_task()],
        attempts=[_attempt()],
        metadata={},
    )

    with pytest.raises(ValueError, match="live_target benchmark bundles must not include attempts"):
        await run_benchmark_bundle(
            bundle=bundle,
            output_dir=tmp_path / "run",
            run_id="run-1",
            target=_Target(),
        )


def test_benchmark_report_paths_reuses_single_sdk_report_path() -> None:
    path = Path("report.html")

    assert benchmark_report_paths(AgentEvalBenchmarkReports(paths=[path])) == (path, path)
