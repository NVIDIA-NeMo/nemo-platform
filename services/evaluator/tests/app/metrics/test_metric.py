# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import math
from typing import cast

import nmp.evaluator.entities as entities
import pytest
from nemo_evaluator_sdk.metrics.aggregation import aggregate_metrics
from nemo_evaluator_sdk.metrics.bleu import BLEUMetric
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.f1 import F1Metric
from nemo_evaluator_sdk.metrics.rouge import ROUGEMetric
from nemo_evaluator_sdk.metrics.string_check import StringCheckMetric
from nemo_evaluator_sdk.metrics.tool_calling import ToolCallingMetric
from nemo_evaluator_sdk.values import (
    AggregateRangeScore,
    MetricOutput,
    MetricOutputSpec,
    MetricResult,
)
from nmp.evaluator.app.metrics.metric import new_metric
from nmp.evaluator.app.values.metrics import Metric as MetricParams


def _metric_result(name: str, value: float | int | bool) -> MetricResult:
    return MetricResult(outputs=[MetricOutput(name=name, value=value)])


def _output_specs(*names: str) -> list[MetricOutputSpec]:
    return [MetricOutputSpec.continuous_score(name) for name in names]


async def _new_metric(params: object):
    return await new_metric(cast(MetricParams, params))


def test_aggregate_metrics():
    """Test basic aggregation computes all statistics correctly."""
    metric_results = [
        _metric_result("my-score", 0),
        _metric_result("my-score", 2),
        _metric_result("my-score", 5),
        _metric_result("my-score", 15),
    ]
    # Expected: sum=22, mean=5.5, min=0, max=15, variance=33.25, stddev=5.766...
    results = aggregate_metrics(metric_results, _output_specs("my-score"))

    assert len(results.scores) == 1
    score = results.scores[0]
    assert isinstance(score, AggregateRangeScore)
    assert score.name == "my-score"
    assert score.mean == 5.5
    assert score.count == 4
    assert score.sum == 22.0
    assert score.min == 0.0
    assert score.max == 15.0
    assert score.variance is not None
    assert score.std_dev is not None
    assert math.isclose(score.variance, 33.25)  # population variance
    assert math.isclose(score.std_dev, 5.766281297335398)
    assert score.nan_count == 0


def test_aggregate_metrics_nan():
    """Test that NaN values are excluded from statistics but counted."""
    metric_results = [
        _metric_result("my-score", 0),
        _metric_result("my-score", float("nan")),
        _metric_result("my-score", 2),
        _metric_result("my-score", 5),
        _metric_result("my-score", float("nan")),
        _metric_result("my-score", 15),
    ]
    results = aggregate_metrics(metric_results, _output_specs("my-score"))

    assert len(results.scores) == 1
    score = results.scores[0]
    assert isinstance(score, AggregateRangeScore)
    assert score.name == "my-score"
    assert score.mean == 5.5
    assert score.count == 4  # NaN values excluded from count
    assert score.nan_count == 2  # But tracked separately
    assert score.sum == 22.0
    assert score.min == 0.0
    assert score.max == 15.0


def test_aggregate_metrics_all_nan_returns_null_aggregates():
    metric_results = [
        _metric_result("my-score", float("nan")),
        _metric_result("my-score", float("nan")),
    ]

    results = aggregate_metrics(metric_results, _output_specs("my-score"))

    assert len(results.scores) == 1
    score = results.scores[0]
    assert isinstance(score, AggregateRangeScore)
    assert score.name == "my-score"
    assert score.count == 0
    assert score.nan_count == 2
    assert score.sum is None
    assert score.mean is None
    assert score.min is None
    assert score.max is None
    assert score.variance is None
    assert score.std_dev is None
    assert score.percentiles is None


def test_aggregate_metrics_returns_distribution():
    """Test that aggregate_metrics returns percentiles and histogram for range scores."""
    metric_results = [_metric_result("my-score", i) for i in range(10)]  # values 0-9

    result = aggregate_metrics(metric_results, _output_specs("my-score"))

    assert len(result.scores) == 1
    agg_score = result.scores[0]
    assert isinstance(agg_score, AggregateRangeScore)
    assert agg_score.name == "my-score"
    assert agg_score.count == 10
    assert agg_score.mean == 4.5  # (0+1+...+9)/10 = 45/10 = 4.5
    assert agg_score.min == 0.0
    assert agg_score.max == 9.0

    # Check percentiles (approximate for 10 values)
    assert agg_score.percentiles is not None
    assert agg_score.percentiles.p50 == 4.5  # median
    assert agg_score.percentiles.p100 == 9.0  # max

    # Check histogram has bins
    assert agg_score.histogram is not None
    assert len(agg_score.histogram.bins) == 10  # default 10 bins


class TestNewMetricBLEU:
    """Tests for new_metric factory function with BLEU."""

    @pytest.mark.asyncio
    async def test_new_metric_creates_bleu_metric(self):
        """Test that new_metric creates BLEUMetric from config."""
        params = entities.BLEUMetric(
            name="test-bleu-metric",
            workspace="default",
            references=["{{item.reference}}"],
        )

        metric = await _new_metric(params)

        assert isinstance(metric, BLEUMetric)
        assert metric.references == ["{{item.reference}}"]
        assert metric.type.value == "bleu"


class TestNewMetricExactMatch:
    """Tests for new_metric factory function with ExactMatch."""

    @pytest.mark.asyncio
    async def test_new_metric_creates_exact_match_metric(self):
        """Test that new_metric creates ExactMatchMetric from config."""
        params = entities.ExactMatchMetric(
            name="test-exact-match-metric",
            workspace="default",
            reference="{{item.reference}}",
        )

        metric = await _new_metric(params)

        assert isinstance(metric, ExactMatchMetric)
        assert metric.reference == "{{item.reference}}"
        assert metric.type.value == "exact-match"


class TestNewMetricF1:
    """Tests for new_metric factory function with F1."""

    @pytest.mark.asyncio
    async def test_new_metric_creates_f1_metric(self):
        """Test that new_metric creates F1Metric from config."""
        params = entities.F1Metric(
            name="test-f1-metric",
            workspace="default",
            reference="{{item.reference}}",
        )

        metric = await _new_metric(params)

        assert isinstance(metric, F1Metric)
        assert metric.reference == "{{item.reference}}"
        assert metric.type.value == "f1"


class TestNewMetricROUGE:
    """Tests for new_metric factory function with ROUGE."""

    @pytest.mark.asyncio
    async def test_new_metric_creates_rouge_metric(self):
        """Test that new_metric creates ROUGEMetric from config."""
        params = entities.ROUGEMetric(
            name="test-rouge-metric",
            workspace="default",
            reference="{{item.reference}}",
        )

        metric = await _new_metric(params)

        assert isinstance(metric, ROUGEMetric)
        assert metric.reference == "{{item.reference}}"
        assert metric.type.value == "rouge"


class TestNewMetricStringCheck:
    """Tests for new_metric factory function with StringCheck."""

    @pytest.mark.asyncio
    async def test_new_metric_creates_string_check_metric(self):
        """Test that new_metric creates StringCheckMetric from config."""
        params = entities.StringCheckMetric(
            name="test-string-check-metric",
            workspace="default",
            operation="equals",
            left_template="{{item.expected}}",
            right_template="{{sample.output_text}}",
        )

        metric = await _new_metric(params)

        assert isinstance(metric, StringCheckMetric)
        assert metric.operation == "equals"
        assert metric.type.value == "string-check"


class TestNewMetricToolCalling:
    """Tests for new_metric factory function with ToolCalling."""

    @pytest.mark.asyncio
    async def test_new_metric_creates_tool_calling_metric(self):
        """Test that new_metric creates ToolCallingMetric from config."""
        params = entities.ToolCallingMetric(
            name="test-tool-calling-metric",
            workspace="default",
            reference="{{item.expected_tool_calls}}",
        )

        metric = await _new_metric(params)

        assert isinstance(metric, ToolCallingMetric)
        assert metric.reference == "{{item.expected_tool_calls}}"
        assert metric.type.value == "tool-calling"
