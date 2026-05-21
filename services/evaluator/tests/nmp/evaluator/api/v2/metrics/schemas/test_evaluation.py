# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_evaluator_sdk.values import DatasetRows, MetricOutput, Model, RowScore
from nmp.evaluator.api.v2.metrics.schemas.evaluation import (
    EvaluateDatasetRows,
    MetricEvaluationRequest,
    MetricEvaluationRowScore,
)
from nmp.evaluator.api.v2.metrics.schemas.metrics import (
    ExactMatchMetric,
    LLMJudgeMetric,
    StringCheckMetric,
)
from nmp.evaluator.app.values import MetricRef
from pydantic import ValidationError

ROW: dict[str, str] = {"question": "Q", "answer": "A"}


class TestEvaluateDatasetRows:
    """Tests for EvaluateDatasetRows validation constraints."""

    def test_valid_single_row(self):
        """EvaluateDatasetRows accepts exactly 1 row (minimum)."""
        dataset = EvaluateDatasetRows(rows=[{"key": "value"}])
        assert len(dataset.rows) == 1

    def test_valid_max_rows(self):
        """EvaluateDatasetRows accepts exactly 10 rows (maximum)."""
        rows = [{"key": f"value{i}"} for i in range(10)]
        dataset = EvaluateDatasetRows(rows=rows)
        assert len(dataset.rows) == 10

    def test_valid_middle_range(self):
        """EvaluateDatasetRows accepts rows within the valid range (1-10)."""
        rows = [{"key": f"value{i}"} for i in range(5)]
        dataset = EvaluateDatasetRows(rows=rows)
        assert len(dataset.rows) == 5

    def test_rejects_empty_rows(self):
        """EvaluateDatasetRows rejects empty rows list."""
        with pytest.raises(ValidationError) as exc_info:
            EvaluateDatasetRows(rows=[])

        err = exc_info.value
        assert len(err.errors()) == 1
        assert err.errors()[0]["loc"] == ("rows",)
        assert err.errors()[0]["type"] == "too_short"

    def test_rejects_more_than_10_rows(self):
        """EvaluateDatasetRows rejects more than 10 rows."""
        rows = [{"key": f"value{i}"} for i in range(11)]

        with pytest.raises(ValidationError) as exc_info:
            EvaluateDatasetRows(rows=rows)

        err = exc_info.value
        assert len(err.errors()) == 1
        assert err.errors()[0]["loc"] == ("rows",)
        assert err.errors()[0]["type"] == "too_long"

    def test_rejects_many_more_rows(self):
        """EvaluateDatasetRows rejects significantly more than 10 rows."""
        rows = [{"key": f"value{i}"} for i in range(100)]

        with pytest.raises(ValidationError) as exc_info:
            EvaluateDatasetRows(rows=rows)

        err = exc_info.value
        assert len(err.errors()) == 1
        assert err.errors()[0]["type"] == "too_long"


class TestEvaluateDatasetRowsVsDatasetRows:
    """Tests verifying EvaluateDatasetRows correctly overrides DatasetRows limits."""

    def test_base_inline_dataset_allows_more_than_10_rows(self):
        """DatasetRows (base class) allows more than 10 rows."""
        rows = [{"key": f"value{i}"} for i in range(50)]
        dataset = DatasetRows(rows=rows)
        assert len(dataset.rows) == 50

    def test_evaluate_inline_dataset_stricter_than_base(self):
        """EvaluateDatasetRows enforces stricter max_length than DatasetRows."""
        rows = [{"key": f"value{i}"} for i in range(11)]

        # Base class allows it
        base_dataset = DatasetRows(rows=rows)
        assert len(base_dataset.rows) == 11

        # Subclass rejects it
        with pytest.raises(ValidationError) as exc_info:
            EvaluateDatasetRows(rows=rows)

        err = exc_info.value
        assert err.errors()[0]["type"] == "too_long"

    def test_both_reject_empty_rows(self):
        """Both DatasetRows and EvaluateDatasetRows reject empty rows."""
        with pytest.raises(ValidationError):
            DatasetRows(rows=[])

        with pytest.raises(ValidationError):
            EvaluateDatasetRows(rows=[])


class TestMetricEvaluationRequestMetricUnion:
    """Tests for MetricEvaluationRequest handling of MetricRef | InlineMetric union.

    This tests the discriminated union pattern that allows the 'metric' field to accept
    either a string reference (MetricRef) or an inline metric definition (InlineMetric).

    Regression tests for: union discrimination between RootModel[str] and discriminated
    union of BaseModel subclasses.
    """

    def test_metric_field_uses_tagged_union_with_callable_discriminator(self):
        """CRITICAL: The metric field MUST use a tagged-union with callable discriminator.

        Without a callable discriminator, the union of MetricRef (string) and InlineMetric
        (discriminated union with 'type' field) can cause validation errors in certain
        contexts (e.g., FastAPI request parsing) where Pydantic tries to apply the nested
        'type' discriminator at the wrong level.

        This test verifies the fix is in place by checking the Pydantic core schema.
        """
        from pydantic import TypeAdapter

        adapter = TypeAdapter(MetricEvaluationRequest)
        core_schema = adapter.core_schema

        # Navigate to the metric field schema
        # Path: .schema.schema.fields.metric.schema
        request_schema = core_schema.get("schema", {})
        assert isinstance(request_schema, dict)
        model_schema = request_schema.get("schema", {})
        assert isinstance(model_schema, dict)
        fields = model_schema.get("fields", {})
        assert isinstance(fields, dict)
        metric_field = fields.get("metric", {})
        assert isinstance(metric_field, dict)
        metric_schema = metric_field.get("schema", {})
        assert isinstance(metric_schema, dict)

        # CRITICAL ASSERTION: The metric union MUST be a 'tagged-union', not 'union'
        schema_type = metric_schema.get("type")
        assert schema_type == "tagged-union", (
            f"Expected metric field to use 'tagged-union' schema type, got '{schema_type}'. "
            "This indicates the callable discriminator fix is missing. "
            "Without the fix, validation may fail with 'Unable to extract tag using discriminator' errors."
        )

        # CRITICAL ASSERTION: The discriminator MUST be a callable function
        discriminator = metric_schema.get("discriminator")
        assert callable(discriminator), (
            f"Expected metric field discriminator to be a callable function, got {type(discriminator)}. "
            "The discriminator must be a function that returns 'ref' for strings and 'inline' for dicts."
        )

    def test_accepts_metric_ref_string(self):
        """MetricEvaluationRequest accepts a string metric reference."""
        request = MetricEvaluationRequest.model_validate(
            {
                "metric": "my-workspace/my-metric",
                "dataset": {"rows": [{"input": "test"}]},
            }
        )

        assert isinstance(request.metric, MetricRef)
        assert request.metric.root == "my-workspace/my-metric"

    def test_accepts_metric_ref_system_workspace(self):
        """MetricEvaluationRequest accepts system workspace metric references."""
        request = MetricEvaluationRequest.model_validate(
            {
                "metric": "system/exact-match",
                "dataset": {"rows": [{"input": "test"}]},
            }
        )

        assert isinstance(request.metric, MetricRef)
        assert request.metric.root == "system/exact-match"

    def test_accepts_inline_string_check_metric(self):
        """MetricEvaluationRequest accepts inline string-check metric definition."""
        request = MetricEvaluationRequest.model_validate(
            {
                "metric": {
                    "type": "string-check",
                    "operation": "equals",
                    "left_template": "{{item.output}}",
                    "right_template": "{{item.expected}}",
                },
                "dataset": {"rows": [{"output": "hello", "expected": "hello"}]},
            }
        )

        assert isinstance(request.metric, StringCheckMetric)
        assert request.metric.operation == "equals"

    def test_accepts_inline_exact_match_metric(self):
        """MetricEvaluationRequest accepts inline exact-match metric definition."""
        request = MetricEvaluationRequest.model_validate(
            {
                "metric": {
                    "type": "exact-match",
                    "reference": "{{item.expected}}",
                },
                "dataset": {"rows": [{"output": "test", "expected": "test"}]},
            }
        )

        assert isinstance(request.metric, ExactMatchMetric)
        assert request.metric.reference == "{{item.expected}}"

    def test_accepts_inline_llm_judge_metric(self):
        """MetricEvaluationRequest accepts inline llm-judge metric definition."""
        request = MetricEvaluationRequest.model_validate(
            {
                "metric": {
                    "type": "llm-judge",
                    "model": {
                        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
                        "name": "meta/llama-3.1-8b-instruct",
                        "api_key_secret": "my-api-key",
                    },
                    "scores": [{"name": "quality", "minimum": 1, "maximum": 5}],
                },
                "dataset": {"rows": [{"input": "test"}]},
            }
        )

        assert isinstance(request.metric, LLMJudgeMetric)
        assert isinstance(request.metric.model, Model)
        assert request.metric.model.name == "meta/llama-3.1-8b-instruct"

    def test_rejects_invalid_metric_ref_format(self):
        """MetricEvaluationRequest rejects invalid metric reference format."""
        with pytest.raises(ValidationError) as exc_info:
            MetricEvaluationRequest.model_validate(
                {
                    "metric": "invalid-no-slash",
                    "dataset": {"rows": [{"input": "test"}]},
                }
            )

        err = exc_info.value
        # Should fail on the MetricRef pattern validation
        assert any("metric" in str(e["loc"]) for e in err.errors())

    def test_rejects_inline_metric_missing_type(self):
        """MetricEvaluationRequest rejects inline metric without type field."""
        with pytest.raises(ValidationError) as exc_info:
            MetricEvaluationRequest.model_validate(
                {
                    "metric": {
                        "operation": "equals",
                        "left_template": "{{item.output}}",
                        "right_template": "{{item.expected}}",
                    },
                    "dataset": {"rows": [{"input": "test"}]},
                }
            )

        err = exc_info.value
        assert len(err.errors()) >= 1

    def test_rejects_inline_metric_invalid_type(self):
        """MetricEvaluationRequest rejects inline metric with unknown type."""
        with pytest.raises(ValidationError) as exc_info:
            MetricEvaluationRequest.model_validate(
                {
                    "metric": {
                        "type": "unknown-metric-type",
                        "some_field": "value",
                    },
                    "dataset": {"rows": [{"input": "test"}]},
                }
            )

        err = exc_info.value
        assert len(err.errors()) >= 1

    def test_rejects_non_string_non_dict_metric(self):
        """MetricEvaluationRequest rejects metric that is neither string nor dict."""
        with pytest.raises(ValidationError) as exc_info:
            MetricEvaluationRequest.model_validate(
                {
                    "metric": 12345,
                    "dataset": {"rows": [{"input": "test"}]},
                }
            )

        err = exc_info.value
        assert len(err.errors()) >= 1

    def test_rejects_list_as_metric(self):
        """MetricEvaluationRequest rejects list as metric value."""
        with pytest.raises(ValidationError) as exc_info:
            MetricEvaluationRequest.model_validate(
                {
                    "metric": ["not", "a", "metric"],
                    "dataset": {"rows": [{"input": "test"}]},
                }
            )

        err = exc_info.value
        assert len(err.errors()) >= 1

    def test_serialization_round_trip_metric_ref(self):
        """MetricEvaluationRequest with MetricRef survives serialization round-trip."""
        original = MetricEvaluationRequest.model_validate(
            {
                "metric": "my-workspace/my-metric",
                "dataset": {"rows": [{"input": "test"}]},
            }
        )

        serialized = original.model_dump()
        restored = MetricEvaluationRequest.model_validate(serialized)

        assert isinstance(restored.metric, MetricRef)
        assert restored.metric.root == "my-workspace/my-metric"

    def test_serialization_round_trip_inline_metric(self):
        """MetricEvaluationRequest with InlineMetric survives serialization round-trip."""
        original = MetricEvaluationRequest.model_validate(
            {
                "metric": {
                    "type": "string-check",
                    "operation": "contains",
                    "left_template": "{{item.output}}",
                    "right_template": "{{item.expected}}",
                },
                "dataset": {"rows": [{"input": "test"}]},
            }
        )

        serialized = original.model_dump()
        restored = MetricEvaluationRequest.model_validate(serialized)

        assert isinstance(restored.metric, StringCheckMetric)
        assert restored.metric.operation == "contains"


def _row_score(
    *,
    index: int = 0,
    metrics: dict[str, list[MetricOutput]] | None = None,
    metric_errors: dict[str, str] | None = None,
) -> RowScore:
    """Build a minimal RowScore with only the fields `from_row_score` reads."""
    return RowScore(
        row_index=index,
        item=ROW,
        sample={},
        metrics=metrics or {},
        requests=[],
        metric_errors=metric_errors,
    )


class TestMetricEvaluationRowScoreFromRowScore:
    """Unit coverage for MetricEvaluationRowScore.from_row_score.

    Exercises the classmethod directly rather than through the /metric-evaluate
    route so edge cases (non-finite values, errored rows, empty metrics) are
    pinned at the schema layer.
    """

    def test_success_preserves_finite_scores(self) -> None:
        """Finite metric values pass through unchanged into the scores dict."""
        row_score = _row_score(
            index=3,
            metrics={"exact_match": [MetricOutput(name="score", value=1.0)]},
        )
        result = MetricEvaluationRowScore.from_row_score(row_score, row=ROW, index=3)

        assert result.index == 3
        assert result.row == ROW
        assert result.scores == {"score": 1.0}
        assert result.error is None

    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_scores_become_none(self, bad_value: float) -> None:
        """NaN and ±inf are serialized as None for JSON compatibility."""
        row_score = _row_score(
            metrics={"m": [MetricOutput(name="score", value=bad_value)]},
        )
        result = MetricEvaluationRowScore.from_row_score(row_score, row=ROW, index=0)

        assert result.scores == {"score": None}
        assert result.error is None

    def test_errored_row_emits_null_scores_and_error(self) -> None:
        """Rows with metric_errors surface error text and set scores to None."""
        row_score = _row_score(index=1, metric_errors={"m": "boom"})
        result = MetricEvaluationRowScore.from_row_score(row_score, row=ROW, index=1)

        assert result.scores is None
        assert result.error is not None
        assert "boom" in result.error

    def test_multiple_metrics_flatten_into_single_scores_dict(self) -> None:
        """All MetricOutput entries across metric keys flatten into one dict keyed by name."""
        row_score = _row_score(
            index=2,
            metrics={
                "a": [MetricOutput(name="precision", value=0.5)],
                "b": [MetricOutput(name="recall", value=0.75)],
            },
        )
        result = MetricEvaluationRowScore.from_row_score(row_score, row=ROW, index=2)

        assert result.scores == {"precision": 0.5, "recall": 0.75}

    def test_non_numeric_outputs_are_excluded_from_scores_dict(self) -> None:
        """Labels and structured outputs stay in row artifacts but not the live scores response."""
        row_score = _row_score(
            metrics={
                "judge": [
                    MetricOutput(name="quality", value=0.75),
                    MetricOutput(name="quality.label", value="good"),
                    MetricOutput(name="details", value={"rationale": "clear"}),
                ]
            },
        )
        result = MetricEvaluationRowScore.from_row_score(row_score, row=ROW, index=0)

        assert result.scores == {"quality": 0.75}

    def test_empty_metrics_emit_empty_scores_dict(self) -> None:
        """Successful rows with no metrics still emit a (possibly empty) scores dict."""
        row_score = _row_score(index=4)
        result = MetricEvaluationRowScore.from_row_score(row_score, row=ROW, index=4)

        assert result.scores == {}
        assert result.error is None
