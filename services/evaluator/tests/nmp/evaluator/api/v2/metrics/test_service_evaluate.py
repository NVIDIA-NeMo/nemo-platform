# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from builtins import ExceptionGroup
from typing import Generator
from unittest.mock import AsyncMock, patch

import nmp.evaluator.entities as entities
import pytest
from nemo_evaluator_sdk import LLMJudgeMetric, StringCheckMetric
from nemo_evaluator_sdk.enums import ModelFormat
from nemo_evaluator_sdk.metrics.ragas import TopicAdherenceMetric
from nemo_evaluator_sdk.values import (
    AggregatedMetricResult,
    DatasetRows,
    EvaluationResult,
    MetricOutput,
    MetricResult,
    Model,
    RangeScore,
    RowScore,
)
from nmp.common.entities import EntityClient
from nmp.evaluator.api.v2.metrics.manager import (
    MetricEvaluationError,
    MetricRetrievalError,
    MetricsManager,
)
from nmp.evaluator.api.v2.metrics.schemas import metrics as schemas
from nmp.evaluator.api.v2.metrics.schemas import metrics_resp
from nmp.evaluator.api.v2.metrics.schemas.evaluation import MetricEvaluationResponse, MetricEvaluationRowScore
from nmp.evaluator.app.values import MetricRef, ModelRef
from nmp.testing import create_test_client


@pytest.fixture
def mock_entity_client() -> Generator[EntityClient, None, None]:
    """Real EntityClient backed by in-memory storage."""
    workspaces = ["default", "test-workspace", "system"]
    with create_test_client(client_type=EntityClient, workspaces=workspaces) as client:
        yield client


# mock_sdk fixture is now provided by conftest.py


@pytest.fixture
def metrics_service(mock_entity_client, mock_sdk) -> MetricsManager:
    """MetricsManager instance with mocked EntityClient."""
    return MetricsManager(mock_entity_client)


@pytest.fixture
def sample_metric() -> entities.StringCheckMetric:
    """Create a sample string-check metric for testing."""
    return entities.StringCheckMetric(
        name="test-metric",
        workspace="test-workspace",
        operation="equals",
        left_template="{{expected}}",
        right_template="{{output}}",
    )


class TestGetMetric:
    """Tests for MetricsManager.get_metric method."""

    @pytest.mark.asyncio
    async def test_get_metric_by_urn(self, metrics_service, sample_metric, mock_sdk):
        """Test resolving a metric by URN."""
        # First create the metric
        await metrics_service.create(sample_metric, sdk=mock_sdk)

        # Resolve by ref
        ref = MetricRef(root="test-workspace/test-metric")
        resolved = await metrics_service.get_metric(ref)

        assert resolved.type == sample_metric.type
        assert isinstance(resolved, StringCheckMetric)
        assert resolved.left_template == sample_metric.left_template
        assert resolved.right_template == sample_metric.right_template
        assert resolved.operation == sample_metric.operation

    @pytest.mark.asyncio
    async def test_get_metric_by_urn_not_found(self, metrics_service):
        """Test that resolving a non-existent URN raises MetricRetrievalError."""
        ref = MetricRef(root="nonexistent/metric")

        with pytest.raises(MetricRetrievalError) as exc_info:
            await metrics_service.get_metric(ref)

        err = exc_info.value
        assert err.error_code == "METRIC_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_inline_metric(self, metrics_service, sample_metric, mock_sdk):
        """Test resolving an inline metric definition (entity-based with workspace)."""
        # First create the metric
        await metrics_service.create(sample_metric, sdk=mock_sdk)

        resolved = await metrics_service.get_by_name(sample_metric.workspace, sample_metric.name)

        assert resolved.type == sample_metric.type
        assert isinstance(resolved, metrics_resp.StringCheckMetricResponse), type(resolved)
        assert resolved.left_template == sample_metric.left_template
        assert resolved.right_template == sample_metric.right_template
        assert resolved.operation == sample_metric.operation

    @pytest.mark.asyncio
    async def test_get_metric_resolves_model_refs(self, metrics_service):
        """Test that get_metric resolves ModelRef fields to Model before returning.

        When an inline metric contains ModelRef strings (e.g. judge_model: "workspace/model"),
        get_metric must resolve them to Model instances so the app layer receives
        only concrete Model objects.
        """
        # Create an API-layer metric with a ModelRef for judge_model
        inline_metric = schemas.TopicAdherenceMetric(
            judge_model=ModelRef("test-workspace/my-judge-model"),
            metric_mode="f1",
        )

        # The resolved Model that should replace the ModelRef
        resolved_model = Model(
            url="http://resolved-gateway:8000/v1",
            name="my-judge-model",
            format=ModelFormat.NVIDIA_NIM,
        )

        # Mock resolve_model to return the resolved model
        with patch(
            "nmp.evaluator.api.v2.metrics.manager.resolve_model",
            new_callable=AsyncMock,
            return_value=resolved_model,
        ) as mock_resolve:
            result = await metrics_service.get_metric(inline_metric)

        # resolve_model should have been called with the ModelRef
        mock_resolve.assert_called_once()
        call_arg = mock_resolve.call_args[0][0]
        assert isinstance(call_arg, ModelRef)
        assert call_arg.root == "test-workspace/my-judge-model"

        # The returned app-layer metric should have judge_model as a resolved Model
        assert isinstance(result, TopicAdherenceMetric)
        assert isinstance(result.judge_model, Model)
        assert result.judge_model.url == "http://resolved-gateway:8000/v1"
        assert result.judge_model.name == "my-judge-model"


class TestEvaluate:
    """Tests for MetricsManager.evaluate method."""

    @pytest.mark.asyncio
    async def test_evaluate_with_inline_metric(self, metrics_service, mock_sdk):
        """Test evaluation with an inline metric definition (entity-based)."""
        metric = entities.StringCheckMetric(
            name="string-equals",
            workspace="test-workspace",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )

        dataset = DatasetRows(
            rows=[
                {"expected": "hello", "output": "hello"},  # Match
                {"expected": "world", "output": "world"},  # Match
                {"expected": "foo", "output": "bar"},  # No match
            ],
        )

        result = await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        assert isinstance(result, MetricEvaluationResponse)
        # Response contains the full metric definition
        assert len(result.row_scores) == 3

        # Check individual results have correct indices and scores
        # All rows should have scores (no errors expected for this simple metric)
        assert result.row_scores[0].index == 0
        assert result.row_scores[0].scores["string-check"] == 1.0
        assert result.row_scores[0].error is None
        assert result.row_scores[1].index == 1
        assert result.row_scores[1].scores["string-check"] == 1.0
        assert result.row_scores[1].error is None
        assert result.row_scores[2].index == 2
        assert result.row_scores[2].scores["string-check"] == 0.0
        assert result.row_scores[2].error is None

        # Aggregate should be mean: (1 + 1 + 0) / 3 = 0.666...
        assert abs(result.aggregate_scores[0].mean - 2 / 3) < 0.01

    @pytest.mark.asyncio
    async def test_evaluate_with_inline_metric_no_workspace_name(self, metrics_service, mock_sdk):
        """Test evaluation with InlineMetric that doesn't have workspace/name.

        This is the primary use case for the /evaluate endpoint: users can define
        a metric inline without needing to specify workspace or name.
        """
        # StringCheckMetric doesn't require workspace or name
        metric = StringCheckMetric(
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )

        dataset = DatasetRows(
            rows=[
                {"expected": "hello", "output": "hello"},  # Match
                {"expected": "foo", "output": "bar"},  # No match
            ],
        )

        # Workspace is provided by the endpoint, not the metric
        result = await metrics_service.evaluate("my-workspace", metric, dataset, sdk=mock_sdk)

        assert isinstance(result, MetricEvaluationResponse)
        # Response contains the inline metric definition (no workspace/name)
        assert result.metric.model_dump(exclude_none=True) == metric.model_dump(exclude_none=True)
        assert result.metric.type == "string-check"
        assert len(result.row_scores) == 2
        assert result.row_scores[0].scores["string-check"] == 1.0
        assert result.row_scores[1].scores["string-check"] == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_with_stored_metric(self, metrics_service, sample_metric, mock_sdk):
        """Test evaluation with a stored metric referenced by URN."""
        # Store the metric first
        await metrics_service.create(sample_metric, sdk=mock_sdk)

        # Reference by URN
        ref = MetricRef(root="test-workspace/test-metric")
        dataset = DatasetRows(
            rows=[{"expected": "match", "output": "match"}],
        )

        result = await metrics_service.evaluate("test-workspace", ref, dataset, sdk=mock_sdk)

        # Response contains the resolved metric definition
        assert len(result.row_scores) == 1
        assert result.row_scores[0].scores["string-check"] == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_metric_not_found(self, metrics_service, mock_sdk):
        """Test that referencing a non-existent metric raises error."""
        ref = MetricRef(root="nonexistent/metric")
        dataset = DatasetRows(rows=[{"input": "test", "output": "test"}])

        with pytest.raises(MetricRetrievalError) as exc_info:
            await metrics_service.evaluate("test-workspace", ref, dataset, sdk=mock_sdk)

        err = exc_info.value
        assert err.error_code == "METRIC_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_evaluate_fails_fast_by_default(self, metrics_service, mock_sdk):
        """Test that evaluation fails fast (raises on first error) by default.

        Non-LLM metrics don't have ignore_request_failure, so they should fail fast.
        """
        # Use a metric that will fail due to invalid template
        metric = entities.StringCheckMetric(
            name="bad-metric",
            workspace="test-workspace",
            operation="equals",
            left_template="{{nonexistent_field}}",
            right_template="{{output}}",
        )

        dataset = DatasetRows(
            rows=[
                {"input": "test1", "output": "test1"},  # Will fail
                {"input": "test2", "output": "test2"},  # Won't be reached
            ],
        )

        with pytest.raises(MetricEvaluationError) as exc_info:
            await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        # Should fail fast with an error mentioning a row index
        err = exc_info.value
        assert "Evaluation failed at row" in err.detail
        assert "nonexistent_field" in err.detail

    @pytest.mark.asyncio
    async def test_evaluate_respects_limit_samples(self, metrics_service, sample_metric, mock_sdk):
        """Test that limit_samples limits evaluation."""
        dataset = DatasetRows(
            rows=[{"expected": f"val{i}", "output": f"val{i}"} for i in range(50)],
        )

        result = await metrics_service.evaluate("test-workspace", sample_metric, dataset, limit_samples=5, sdk=mock_sdk)

        assert len(result.row_scores) == 5

    @pytest.mark.asyncio
    async def test_evaluate_aggregate_fields_default(self, metrics_service, sample_metric, mock_sdk):
        """Test that default aggregate fields are returned."""
        dataset = DatasetRows(
            rows=[{"expected": "hello", "output": "hello"}],
        )

        result = await metrics_service.evaluate("test-workspace", sample_metric, dataset, sdk=mock_sdk)

        # Serialize the aggregate score to check fields
        agg_dict = result.aggregate_scores[0].model_dump()

        # Required fields should always be present
        assert "name" in agg_dict
        assert "count" in agg_dict

        # Default optional fields should be present
        assert "nan_count" in agg_dict
        assert "sum" in agg_dict
        assert "mean" in agg_dict
        assert "min" in agg_dict
        assert "max" in agg_dict

        # Extended fields should NOT be present by default
        assert "std_dev" not in agg_dict
        assert "variance" not in agg_dict
        assert "percentiles" not in agg_dict
        assert "histogram" not in agg_dict

    @pytest.mark.asyncio
    async def test_evaluate_aggregate_fields_custom(self, metrics_service, sample_metric, mock_sdk):
        """Test that custom aggregate fields can be requested."""
        dataset = DatasetRows(
            rows=[{"expected": "hello", "output": "hello"}],
        )

        # Request only mean, std_dev, and percentiles
        custom_fields = frozenset({"mean", "std_dev", "percentiles"})
        result = await metrics_service.evaluate(
            "test-workspace", sample_metric, dataset, aggregate_fields=custom_fields, sdk=mock_sdk
        )

        # Serialize the aggregate score to check fields
        agg_dict = result.aggregate_scores[0].model_dump()

        # Required fields are ALWAYS present (name, count)
        assert "name" in agg_dict
        assert "count" in agg_dict

        # Requested fields should be present
        assert "mean" in agg_dict
        assert "std_dev" in agg_dict
        assert "percentiles" in agg_dict

        # Non-requested optional fields should NOT be present
        assert "sum" not in agg_dict
        assert "nan_count" not in agg_dict
        assert "histogram" not in agg_dict

    @pytest.mark.asyncio
    async def test_evaluate_ignored_failures_do_not_leak_synthetic_metric_scores(
        self,
        metrics_service,
        mock_sdk,
        mocker,
    ):
        """Ignored failures should keep failed rows out of API scores and aggregates."""
        metric = entities.LLMJudgeMetric(
            name="judge-metric",
            workspace="test-workspace",
            description="Test judge metric",
            model=Model(
                url="https://api.openai.com/v1",
                name="gpt-4o",
                format=ModelFormat.OPEN_AI,
            ),
            prompt_template="Rate the response: {output}",
            scores=[
                RangeScore(
                    name="quality",
                    description="Quality score",
                    minimum=0.0,
                    maximum=1.0,
                )
            ],
            ignore_request_failure=True,
        )
        runtime_metric = LLMJudgeMetric(
            model=metric.model,
            prompt_template=metric.prompt_template,
            scores=metric.scores,
            ignore_request_failure=metric.ignore_request_failure,
        )
        dataset = DatasetRows(rows=[{"output": "good"}, {"output": "bad"}])

        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.new_metric",
            new_callable=AsyncMock,
            return_value=runtime_metric,
        )
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.run_generated_sample_scoring_pipeline",
            new_callable=AsyncMock,
            return_value=[
                (
                    0,
                    MetricResult(outputs=[MetricOutput(name="quality", value=0.8)]),
                    RowScore(
                        row_index=0,
                        item={"output": "good"},
                        sample={},
                        metrics={"quality": [MetricOutput(name="quality", value=0.8)]},
                        requests=[],
                    ),
                ),
                (
                    1,
                    MetricResult(outputs=[MetricOutput(name="llm-judge", value=float("nan"))]),
                    RowScore(
                        row_index=1,
                        item={"output": "bad"},
                        sample={},
                        metrics={"llm-judge": [MetricOutput(name="llm-judge", value=float("nan"))]},
                        requests=[],
                        metric_errors={"llm-judge": "request timed out"},
                    ),
                ),
            ],
        )

        result = await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        assert result.row_scores[0].scores == {"quality": 0.8}
        assert result.row_scores[0].error is None
        assert result.row_scores[1].scores is None
        assert result.row_scores[1].error == "llm-judge: request timed out"
        assert [score.name for score in result.aggregate_scores] == ["quality"]


class TestEvaluateRowScoresFormat:
    """Tests for row_scores structure (combined success/error items)."""

    @pytest.mark.asyncio
    async def test_successful_row_has_scores_no_error(self, metrics_service, sample_metric, mock_sdk):
        """Test that successful rows have scores and null error."""
        dataset = DatasetRows(
            rows=[{"expected": "hello", "output": "hello"}],
        )

        result = await metrics_service.evaluate("test-workspace", sample_metric, dataset, sdk=mock_sdk)

        row_score = result.row_scores[0]
        assert row_score.scores is not None
        assert "string-check" in row_score.scores
        assert row_score.error is None

    @pytest.mark.asyncio
    async def test_row_includes_original_data(self, metrics_service, sample_metric, mock_sdk):
        """Test that row_scores include the original row data."""
        original_row = {"expected": "hello", "output": "hello", "extra_field": "extra_value"}
        dataset = DatasetRows(rows=[original_row])

        result = await metrics_service.evaluate("test-workspace", sample_metric, dataset, sdk=mock_sdk)

        assert result.row_scores[0].row == original_row

    def test_row_scores_serializes_non_finite_values_as_null(self):
        """Non-finite per-row scores should be exposed as null for JSON-compliant responses."""
        row_score = RowScore(
            row_index=0,
            item={"expected": "x", "output": "x"},
            sample={},
            metrics={"string-check": [MetricOutput(name="string-check", value=float("nan"))]},
            requests=[],
        )

        result = MetricEvaluationRowScore.from_row_score(
            row_score,
            row={"expected": "x", "output": "x"},
            index=0,
        )

        assert result.scores == {"string-check": None}

    def test_failed_row_scores_remain_null_when_pipeline_includes_placeholder_metrics(self):
        """Failed rows should keep `scores=null` even if the pipeline attached NaN placeholders."""
        row_score = RowScore(
            row_index=1,
            item={"expected": "x", "output": "x"},
            sample={},
            metrics={"llm-judge": [MetricOutput(name="llm-judge", value=float("nan"))]},
            requests=[],
            metric_errors={"llm-judge": "request timed out"},
        )

        result = MetricEvaluationRowScore.from_row_score(
            row_score,
            row={"expected": "x", "output": "x"},
            index=1,
        )

        assert result.scores is None
        assert result.error == "llm-judge: request timed out"

    @pytest.mark.asyncio
    async def test_evaluate_raises_on_out_of_bounds_row_index(self, metrics_service, mock_sdk, mocker):
        """Pipeline returning an out-of-bounds row_index should raise MetricEvaluationError."""
        metric = entities.StringCheckMetric(
            name="sc-metric",
            workspace="test-workspace",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        runtime_metric = StringCheckMetric(
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        dataset = DatasetRows(rows=[{"expected": "a", "output": "a"}])

        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.new_metric",
            new_callable=AsyncMock,
            return_value=runtime_metric,
        )
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.run_generated_sample_scoring_pipeline",
            new_callable=AsyncMock,
            return_value=[
                (
                    0,
                    MetricResult(outputs=[MetricOutput(name="string-check", value=1.0)]),
                    RowScore(
                        row_index=999,  # out-of-bounds for a 1-row dataset
                        item={"expected": "a", "output": "a"},
                        sample={},
                        metrics={"string-check": [MetricOutput(name="string-check", value=1.0)]},
                        requests=[],
                    ),
                ),
            ],
        )

        with pytest.raises(MetricEvaluationError) as exc_info:
            await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        assert exc_info.value.detail == "Pipeline returned out-of-bounds row_index=999 for 1 rows"

    def test_row_scores_fall_back_to_list_position_when_sdk_row_index_is_missing(self):
        """Missing SDK row_index values should still produce a concrete API index."""
        row_score = RowScore(
            row_index=None,
            item={"expected": "x", "output": "x"},
            sample={},
            metrics={"string-check": [MetricOutput(name="string-check", value=1.0)]},
            requests=[],
        )

        result = MetricEvaluationRowScore.from_row_score(
            row_score,
            row={"expected": "x", "output": "x"},
            index=3,
        )

        assert result.index == 3
        assert result.scores == {"string-check": 1.0}


class TestFromRowScore:
    """Tests for MetricEvaluationRowScore.from_row_score edge cases."""

    def test_multiple_metrics_flattened(self):
        """Multiple metric keys should be flattened into a single scores dict."""
        row_score = RowScore(
            row_index=0,
            item={},
            sample={},
            metrics={
                "precision": [MetricOutput(name="precision", value=0.9)],
                "recall": [MetricOutput(name="recall", value=0.8)],
            },
            requests=[],
        )

        result = MetricEvaluationRowScore.from_row_score(row_score, row={"k": "v"}, index=0)

        assert result.scores == {"precision": 0.9, "recall": 0.8}
        assert result.error is None

    def test_all_nan_scores_become_all_null(self):
        """If every score is NaN the dict should contain only None values."""
        row_score = RowScore(
            row_index=0,
            item={},
            sample={},
            metrics={"m": [MetricOutput(name="m", value=float("nan"))]},
            requests=[],
        )

        result = MetricEvaluationRowScore.from_row_score(row_score, row={}, index=0)

        assert result.scores == {"m": None}

    def test_inf_score_becomes_null(self):
        """Positive and negative infinity should be serialized as null."""
        row_score = RowScore(
            row_index=0,
            item={},
            sample={},
            metrics={
                "pos": [MetricOutput(name="pos", value=float("inf"))],
                "neg": [MetricOutput(name="neg", value=float("-inf"))],
            },
            requests=[],
        )

        result = MetricEvaluationRowScore.from_row_score(row_score, row={}, index=0)

        assert result.scores == {"pos": None, "neg": None}

    def test_empty_metrics_dict_yields_empty_scores(self):
        """Successful rows with no score entries should yield scores={}.

        Restores the pre-refactor ``/metric-evaluate`` contract where any row
        with a ``MetricResult`` emitted ``scores={}`` (rather than ``None``).
        Only rows with an ``error`` should serialize with ``scores=null``.
        """
        row_score = RowScore(
            row_index=0,
            item={},
            sample={},
            metrics={},
            requests=[],
        )

        result = MetricEvaluationRowScore.from_row_score(row_score, row={}, index=0)

        assert result.scores == {}
        assert result.error is None

    def test_empty_per_metric_score_list_yields_empty_scores(self):
        """A metrics dict with empty score lists should still yield scores={}."""
        row_score = RowScore(
            row_index=0,
            item={},
            sample={},
            metrics={"m": []},
            requests=[],
        )

        result = MetricEvaluationRowScore.from_row_score(row_score, row={}, index=0)

        assert result.scores == {}
        assert result.error is None

    def test_error_with_multiple_metric_errors(self):
        """Multiple metric_errors should be joined in the error string."""
        row_score = RowScore(
            row_index=0,
            item={},
            sample={},
            metrics={"a": [MetricOutput(name="a", value=float("nan"))]},
            requests=[],
            metric_errors={"a": "timeout", "b": "rate limited"},
        )

        result = MetricEvaluationRowScore.from_row_score(row_score, row={}, index=0)

        assert result.scores is None
        assert result.error is not None
        assert "a: timeout" in result.error
        assert "b: rate limited" in result.error


class TestEvaluateErrorPaths:
    """Tests for evaluate() error handling paths."""

    @pytest.mark.asyncio
    async def test_non_evaluation_error_is_wrapped_with_normalize(self, metrics_service, mock_sdk, mocker):
        """When pipeline raises a non-EvaluationError, it should be wrapped via normalize_evaluation_failure."""
        metric = entities.StringCheckMetric(
            name="sc-metric",
            workspace="test-workspace",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        dataset = DatasetRows(rows=[{"expected": "a", "output": "a"}])

        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.new_metric",
            new_callable=AsyncMock,
            return_value=metric,
        )
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.run_generated_sample_scoring_pipeline",
            new_callable=AsyncMock,
            side_effect=RuntimeError("internal pipeline failure"),
        )

        with pytest.raises(MetricEvaluationError) as exc_info:
            await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        assert exc_info.value.error_code == "EVALUATION_FAILED"
        assert "internal pipeline failure" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_exception_group_with_evaluation_error_extracts_row_detail(self, metrics_service, mock_sdk, mocker):
        """ExceptionGroup wrapping an EvaluationError should surface the row index and message."""
        from nemo_evaluator_sdk.execution.values import EvaluationError

        metric = entities.StringCheckMetric(
            name="sc-metric",
            workspace="test-workspace",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        dataset = DatasetRows(rows=[{"expected": "a", "output": "a"}])

        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.new_metric",
            new_callable=AsyncMock,
            return_value=metric,
        )
        inner = EvaluationError(index=3, message="'missing_field' is undefined")
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.run_generated_sample_scoring_pipeline",
            new_callable=AsyncMock,
            side_effect=ExceptionGroup("tasks", [inner]),
        )

        with pytest.raises(MetricEvaluationError) as exc_info:
            await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        assert "Evaluation failed at row 3" in exc_info.value.detail
        assert "missing_field" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_exception_group_with_non_leading_evaluation_error_extracts_row_detail(
        self, metrics_service, mock_sdk, mocker
    ):
        """A sibling EvaluationError past position [0] should still be surfaced."""
        from nemo_evaluator_sdk.execution.values import EvaluationError

        metric = entities.StringCheckMetric(
            name="sc-metric",
            workspace="test-workspace",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        dataset = DatasetRows(rows=[{"expected": "a", "output": "a"}])

        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.new_metric",
            new_callable=AsyncMock,
            return_value=metric,
        )
        inner = EvaluationError(index=2, message="'missing_field' is undefined")
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.run_generated_sample_scoring_pipeline",
            new_callable=AsyncMock,
            side_effect=ExceptionGroup(
                "tasks",
                [
                    RuntimeError("sibling before"),
                    inner,
                    RuntimeError("sibling after"),
                ],
            ),
        )

        with pytest.raises(MetricEvaluationError) as exc_info:
            await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        assert "Evaluation failed at row 2" in exc_info.value.detail
        assert "missing_field" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_nested_exception_group_with_evaluation_error_extracts_row_detail(
        self, metrics_service, mock_sdk, mocker
    ):
        """An EvaluationError nested inside an inner ExceptionGroup should still be surfaced."""
        from nemo_evaluator_sdk.execution.values import EvaluationError

        metric = entities.StringCheckMetric(
            name="sc-metric",
            workspace="test-workspace",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        dataset = DatasetRows(rows=[{"expected": "a", "output": "a"}])

        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.new_metric",
            new_callable=AsyncMock,
            return_value=metric,
        )
        inner = EvaluationError(index=5, message="nested cause")
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.run_generated_sample_scoring_pipeline",
            new_callable=AsyncMock,
            side_effect=ExceptionGroup(
                "outer",
                [
                    RuntimeError("sibling"),
                    ExceptionGroup("inner", [RuntimeError("noise"), inner]),
                ],
            ),
        )

        with pytest.raises(MetricEvaluationError) as exc_info:
            await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        assert "Evaluation failed at row 5" in exc_info.value.detail
        assert "nested cause" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_unexpected_error_is_logged(self, metrics_service, mock_sdk, mocker):
        """Non-EvaluationError exceptions should trigger a logger.exception call."""
        metric = entities.StringCheckMetric(
            name="sc-metric",
            workspace="test-workspace",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        dataset = DatasetRows(rows=[{"expected": "a", "output": "a"}])

        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.new_metric",
            new_callable=AsyncMock,
            return_value=metric,
        )
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.run_generated_sample_scoring_pipeline",
            new_callable=AsyncMock,
            side_effect=TypeError("unexpected bug"),
        )
        mock_logger = mocker.patch("nmp.evaluator.api.v2.metrics.manager._logger")

        with pytest.raises(MetricEvaluationError):
            await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        mock_logger.exception.assert_called_once()
        assert "Unexpected failure" in mock_logger.exception.call_args[0][0]

    @pytest.mark.asyncio
    async def test_post_pipeline_finalize_failure_is_wrapped(self, metrics_service, mock_sdk, mocker):
        """Unexpected finalize failures should be logged and wrapped as EVALUATION_FAILED."""
        metric = entities.StringCheckMetric(
            name="sc-metric",
            workspace="test-workspace",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        dataset = DatasetRows(rows=[{"expected": "a", "output": "a"}])

        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.new_metric",
            new_callable=AsyncMock,
            return_value=metric,
        )
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.run_generated_sample_scoring_pipeline",
            new_callable=AsyncMock,
            return_value=[],
        )
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.finalize_evaluation_result",
            new_callable=AsyncMock,
            side_effect=RuntimeError("post-pipeline finalize failure"),
        )
        mock_logger = mocker.patch("nmp.evaluator.api.v2.metrics.manager._logger")

        with pytest.raises(MetricEvaluationError) as exc_info:
            await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        assert exc_info.value.error_code == "EVALUATION_FAILED"
        assert exc_info.value.detail == "post-pipeline finalize failure"
        mock_logger.exception.assert_called_once()
        assert "post-pipeline" in mock_logger.exception.call_args[0][0]

    @pytest.mark.asyncio
    async def test_post_pipeline_from_row_score_failure_is_wrapped(self, metrics_service, mock_sdk, mocker):
        """Row-score conversion failures should be logged and wrapped as EVALUATION_FAILED."""
        metric = entities.StringCheckMetric(
            name="sc-metric",
            workspace="test-workspace",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        dataset = DatasetRows(rows=[{"expected": "a", "output": "a"}])
        evaluation_result = EvaluationResult(
            row_scores=[
                RowScore(
                    row_index=0,
                    item={"expected": "a", "output": "a"},
                    sample={},
                    metrics={"string-check": [MetricOutput(name="string-check", value=1.0)]},
                    requests=[],
                )
            ],
            aggregate_scores=AggregatedMetricResult(scores=[]),
        )

        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.new_metric",
            new_callable=AsyncMock,
            return_value=metric,
        )
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.run_generated_sample_scoring_pipeline",
            new_callable=AsyncMock,
            return_value=[],
        )
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.finalize_evaluation_result",
            new_callable=AsyncMock,
            return_value=evaluation_result,
        )
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.MetricEvaluationRowScore.from_row_score",
            side_effect=RuntimeError("row conversion blew up"),
        )
        mock_logger = mocker.patch("nmp.evaluator.api.v2.metrics.manager._logger")

        with pytest.raises(MetricEvaluationError) as exc_info:
            await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        assert exc_info.value.error_code == "EVALUATION_FAILED"
        assert exc_info.value.detail == "row conversion blew up"
        mock_logger.exception.assert_called_once()
        assert "post-pipeline" in mock_logger.exception.call_args[0][0]

    @pytest.mark.asyncio
    async def test_post_pipeline_metric_response_validation_failure_is_wrapped(self, metrics_service, mock_sdk, mocker):
        """Metric response validation failures should be logged and wrapped as EVALUATION_FAILED."""
        metric = entities.StringCheckMetric(
            name="sc-metric",
            workspace="test-workspace",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        dataset = DatasetRows(rows=[{"expected": "a", "output": "a"}])
        evaluation_result = EvaluationResult(
            row_scores=[],
            aggregate_scores=AggregatedMetricResult(scores=[]),
        )

        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.new_metric",
            new_callable=AsyncMock,
            return_value=metric,
        )
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.run_generated_sample_scoring_pipeline",
            new_callable=AsyncMock,
            return_value=[],
        )
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.finalize_evaluation_result",
            new_callable=AsyncMock,
            return_value=evaluation_result,
        )
        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.MetricResponseAdapter.validate_python",
            side_effect=ValueError("metric response validation failed"),
        )
        mock_logger = mocker.patch("nmp.evaluator.api.v2.metrics.manager._logger")

        with pytest.raises(MetricEvaluationError) as exc_info:
            await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        assert exc_info.value.error_code == "EVALUATION_FAILED"
        assert exc_info.value.detail == "metric response validation failed"
        mock_logger.exception.assert_called_once()
        assert "post-pipeline" in mock_logger.exception.call_args[0][0]

    @pytest.mark.asyncio
    async def test_metric_init_failure_raises_evaluation_error(self, metrics_service, mock_sdk, mocker):
        """ValueError during metric initialization should be wrapped in MetricEvaluationError."""
        metric = entities.StringCheckMetric(
            name="bad-init",
            workspace="test-workspace",
            operation="equals",
            left_template="{{x}}",
            right_template="{{y}}",
        )
        dataset = DatasetRows(rows=[{"x": "a", "y": "a"}])

        mocker.patch(
            "nmp.evaluator.api.v2.metrics.manager.new_metric",
            new_callable=AsyncMock,
            side_effect=ValueError("unsupported metric config"),
        )

        with pytest.raises(MetricEvaluationError) as exc_info:
            await metrics_service.evaluate("test-workspace", metric, dataset, sdk=mock_sdk)

        assert exc_info.value.error_code == "EVALUATION_FAILED"
        assert "Failed to initialize metric" in exc_info.value.detail
        assert "unsupported metric config" in exc_info.value.detail
