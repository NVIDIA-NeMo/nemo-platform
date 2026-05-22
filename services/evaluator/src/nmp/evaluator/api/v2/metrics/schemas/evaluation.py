# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import math
from typing import Annotated, Any, Self

import nmp.evaluator.app.values as app
from nemo_evaluator_sdk.values import AggregateScore, DatasetRows, RowScore
from nmp.evaluator.api.v2.metrics.schemas.metrics import Metric
from nmp.evaluator.api.v2.metrics.schemas.metrics_resp import MetricResponse
from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag


class EvaluateDatasetRows(DatasetRows):
    """Inline dataset for evaluation with a maximum of 10 rows."""

    model_config = ConfigDict(extra="forbid")

    rows: list[dict[str, Any]] = Field(
        min_length=1,
        max_length=10,
        description="Array of data rows. Each row can be any valid JSON value (object, string, array, etc.).",
    )


def _metric_discriminator(v: Any) -> str | None:
    """Discriminate between MetricRef (string) and app.Metric (dict).

    Returns 'ref' for string references, 'inline' for dict/object definitions,
    or None if the value type is not recognized.
    """
    if isinstance(v, str):
        return "ref"
    if isinstance(v, dict):
        return "inline"
    # Handle already-validated instances (used during serialization)
    if isinstance(v, app.MetricRef):
        return "ref"
    if hasattr(v, "type"):  # app.Metric has a 'type' field
        return "inline"
    return None


# Union type with callable discriminator to handle MetricRef (string) vs app.Metric (dict)
EvaluationMetric = Annotated[
    Annotated[app.MetricRef, Tag("ref")] | Annotated[Metric, Tag("inline")],
    Discriminator(_metric_discriminator),
]


class MetricEvaluationRequest(BaseModel):
    """Request body for metric evaluation."""

    model_config = ConfigDict(extra="forbid")

    metric: EvaluationMetric = Field(
        description="The metric to use for evaluation. Can be a reference (workspace/metric_name) or an inline metric definition."
    )
    dataset: EvaluateDatasetRows = Field(description="The dataset to evaluate with inline rows.")


class MetricEvaluationRowScore(BaseModel):
    """Result for a single evaluated row.

    Contains either scores (on success) or error (on failure), facilitating
    easy manipulation where each row represents one evaluation.
    """

    model_config = ConfigDict(extra="forbid")

    index: int = Field(description="Position of this row in the original input dataset (0-based).")
    row: dict[str, Any] = Field(description="The original dataset row.")
    scores: dict[str, float | None] | None = Field(
        default=None,
        description="Score name to value mapping for this row. Non-finite values are serialized as null. Null if evaluation failed.",
    )
    error: str | None = Field(
        default=None,
        description="Error message if evaluation failed. Null if evaluation succeeded.",
    )

    @classmethod
    def from_row_score(cls, row_score: RowScore, row: dict[str, Any], index: int) -> Self:
        """Convert an SDK ``RowScore`` into the API response model.

        Non-finite values (NaN, inf) become ``None`` for JSON serialization.
        Errored rows emit ``scores=null``; successful rows always emit a
        ``scores`` dict (possibly empty) — the ``/metric-evaluate`` contract.
        """
        if row_score.error is not None:
            return cls(index=index, row=row, scores=None, error=row_score.error)
        scores: dict[str, float | None] = {}
        for metric_outputs in row_score.metrics.values():
            for output in metric_outputs:
                if isinstance(output.value, bool):
                    scores[output.name] = 1.0 if output.value else 0.0
                elif isinstance(output.value, int | float):
                    scores[output.name] = float(output.value) if math.isfinite(output.value) else None
        return cls(index=index, row=row, scores=scores, error=None)


class MetricEvaluationResponse(BaseModel):
    """Response body for metric evaluation.

    Designed for easy loading into pandas DataFrames. See docs/evaluation-response-pandas.md
    for examples of how to load `aggregate_scores` and `row_scores` into DataFrames.
    """

    model_config = ConfigDict(extra="forbid")

    metric: MetricResponse = Field(description="The metric definition that was used for evaluation.")
    aggregate_scores: list[AggregateScore] = Field(description="Aggregated statistics per score.")
    row_scores: list[MetricEvaluationRowScore] = Field(description="Per-row evaluation results with scores or errors.")
