# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Focused tests for MetricInput/MetricOutput execution plumbing."""

from __future__ import annotations

import math

import pytest
from nemo_evaluator_sdk.execution.benchmark_execution import evaluate_benchmark
from nemo_evaluator_sdk.execution.scoring import finalize_evaluation_result, score_row
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values import (
    RunConfig,
)


class _OutputMetric:
    @property
    def type(self) -> str:
        return "test-output-metric"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [
            MetricOutputSpec.continuous_score("score"),
            MetricOutputSpec.boolean("passed"),
            MetricOutputSpec.label("reason"),
        ]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        assert input.row.row_index is not None
        assert input.row.data["expected"] == "yes"
        assert input.candidate.output_text in {"yes", "no", None}
        passed = input.candidate.output_text == input.row.data["expected"]
        return MetricResult(
            outputs=[
                MetricOutput(name="score", value=1.0 if passed else 0.0),
                MetricOutput(name="passed", value=passed),
                MetricOutput(name="reason", value="matched" if passed else "mismatched"),
            ]
        )


class _RaisingMetric(_OutputMetric):
    async def compute_scores(self, input: MetricInput) -> MetricResult:
        del input
        raise RuntimeError("metric failed")


@pytest.mark.asyncio
async def test_score_row_stores_outputs_and_aggregates_score_like_specs() -> None:
    metric = _OutputMetric()
    completed = [
        await score_row(
            metric=metric,
            row={"expected": "yes"},
            sample={"output_text": "yes", "response": {"id": "ok"}},
            index=0,
            metric_key="metric",
            fail_fast=True,
            generation_requests=[],
        )
    ]

    result = await finalize_evaluation_result(metric, completed)

    row = result.row_scores[0]
    assert [output.name for output in row.metrics["metric"]] == ["score", "passed", "reason"]
    assert result.to_records()[0]["output.score"] == 1.0
    assert result.to_records()[0]["output.reason"] == "matched"
    assert [score.name for score in result.aggregate_scores.scores] == ["score", "passed"]
    assert [score.mean for score in result.aggregate_scores.scores] == [1.0, 1.0]


@pytest.mark.asyncio
async def test_lenient_score_row_creates_nan_outputs_for_aggregateable_specs() -> None:
    metric = _RaisingMetric()

    _, metric_result, row = await score_row(
        metric=metric,
        row={"expected": "yes"},
        sample={"output_text": "no"},
        index=0,
        metric_key="metric",
        fail_fast=False,
        generation_requests=[],
    )

    assert metric_result is not None
    assert [output.name for output in metric_result.outputs] == ["score", "passed"]
    assert all(math.isnan(output.value) for output in metric_result.outputs)
    assert [output.name for output in row.metrics["metric"]] == ["score", "passed"]
    assert row.metric_errors == {"metric": "metric failed"}

    result = await finalize_evaluation_result(metric, [(0, metric_result, row)])

    assert [(score.name, score.count, score.nan_count) for score in result.aggregate_scores.scores] == [
        ("score", 0, 1),
        ("passed", 0, 1),
    ]


@pytest.mark.asyncio
async def test_benchmark_namespaces_output_rows_and_aggregates() -> None:
    rows = [{"expected": "yes"}, {"expected": "yes"}]

    result = await evaluate_benchmark(
        metrics=[("custom", _OutputMetric())],
        rows=rows,
        target=None,
        params=RunConfig(parallelism=1),
    )

    assert result.row_scores[0].metrics["custom"][0] == MetricOutput(name="score", value=0.0)
    assert result.to_records()[0]["output.custom.reason"] == "mismatched"
    assert [score.name for score in result.aggregate_scores.scores] == ["custom.score", "custom.passed"]
