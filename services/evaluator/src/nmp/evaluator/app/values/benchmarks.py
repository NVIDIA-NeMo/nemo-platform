# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nemo_evaluator_sdk.values import FieldMapping
from nmp.evaluator.app.values.common import FilesetRef, MetricRef
from nmp.evaluator.app.values.metrics import Metric
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self


class BenchmarkMetric(BaseModel):
    """Benchmark metric with stable reference identity."""

    metric_ref: MetricRef = Field(description="Reference to the metric (format: workspace/metric_name).")
    metric: Metric = Field(description="Resolved metric definition.")


class Benchmark(BaseModel):
    """Inline custom benchmark for grouping metrics."""

    name: str = Field(description="Benchmark name")
    description: str | None = Field(default=None, description="Human-readable description of the benchmark.")
    metrics: list[BenchmarkMetric] = Field(min_length=1, description="List of metrics that comprise this benchmark.")
    dataset: FilesetRef = Field(
        description="Reference to a Fileset in the Files API (format: workspace/fileset-name). The fileset contains the test cases for this benchmark."
    )
    field_mapping: FieldMapping | None = Field(
        default=None,
        description="Maps canonical evaluator fields such as 'input' and 'output' to dataset column paths for this benchmark.",
    )
    labels: dict[str, str] = Field(
        default_factory=dict, description="Labels are key-value pairs that can be used for grouping and filtering."
    )

    @model_validator(mode="after")
    def unique_metric_refs(self) -> Self:
        if type(self) is not Benchmark:
            return self
        refs = [metric.metric_ref.root for metric in self.metrics]
        if len(refs) != len(set(refs)):
            raise ValueError("benchmark metric references must be unique")
        return self
