# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from typing import Annotated

import nmp.evaluator.app.values as app
import nmp.evaluator.entities as entities
from nemo_evaluator_sdk.values import DatasetRows
from nmp.common.api.common import Page
from nmp.common.entities.values import DatetimeFilter, Filter, StringFilter, map_entity_field
from nmp.evaluator.app.values import Fileset, FilesetRef, MetricRef
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

# =============================================================================
# Request input schemas
# =============================================================================


class BenchmarksListFilter(Filter):
    """Filter for list benchmarks query."""

    name: StringFilter | str | None = Field(default=None, description="Filter benchmarks by name.")
    description: StringFilter | str | None = Field(default=None, description="Filter benchmarks by description.")
    dataset: FilesetRef | None = Field(
        default=None,
        description="Filter custom benchmarks by dataset used for evaluation (format workspace/fileset-name).",
    )
    project: str | None = Field(default=None, description="Filter benchmarks by project name.")
    created_at: DatetimeFilter | None = Field(default=None, description="Filter benchmarks by creation date range.")
    updated_at: DatetimeFilter | None = Field(default=None, description="Filter benchmarks by last update date range.")
    labels: Annotated[dict[str, str] | None, map_entity_field("data.labels", namespace=True)] = Field(
        default=None,
        description="Filter by labels. Address an individual label as a sub-path, e.g. filter[labels.eval_category]=agentic.",
    )


class BenchmarkRequest(BaseModel):
    """Request schema for creating a benchmark. Workspace comes from route parameter."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="The name of the benchmark.")
    description: str | None = Field(description="The description of the benchmark.")
    metrics: list[MetricRef] = Field(
        description="The metrics that comprise this benchmark (format: workspace/metric_name)."
    )
    dataset: FilesetRef = Field(description="The Fileset containing test data (format: workspace/fileset-name).")
    field_mapping: app.FieldMapping | None = Field(
        default=None,
        description="Maps canonical evaluator fields such as 'input' and 'output' to dataset column paths for this benchmark.",
    )
    labels: dict[str, str] = Field(
        default_factory=dict, description="Labels are key-value pairs that can be used for grouping and filtering."
    )

    @model_validator(mode="after")
    def restrict_label_characters(self) -> Self:
        """Restrict label key/value strings from unsupported characters"""
        errs = []
        for k, v in self.labels.items():
            if not k.isalnum():
                errs.append(f"label {k}")
            if not v.isalnum():
                errs.append(f"label {k} value {v}")
        if errs:
            raise ValueError(f"labels must be alphanumeric: {errs}")
        return self

    @model_validator(mode="after")
    def unique_metric_refs(self) -> Self:
        metric_refs = [metric_ref.root for metric_ref in self.metrics]
        if len(metric_refs) != len(set(metric_refs)):
            raise ValueError("benchmark metric references must be unique")
        return self


# =============================================================================
# Response schemas
# Response objects must inherit from EntityBase to satisfy nmp.common.entities.client.ListResponse
# =============================================================================


class Benchmark(entities.Benchmark):
    """Benchmark response schema."""

    metrics: list[MetricRef] = Field(
        description="The metrics that comprise this benchmark (format: workspace/metric_name)."
    )


class ExtendedBenchmark(entities.Benchmark):
    """Extended benchmark response. Includes the metrics and dataset as entities."""

    metrics: list[entities.Metric] = Field(description="The fully defined metrics of the benchmark.")
    # TODO remove FilesetRef type when resolved before saving
    dataset: DatasetRows | Fileset | FilesetRef = Field(
        description="Dataset containing the test cases for this benchmark."
    )


class SystemBenchmark(entities.SystemBenchmark):
    """System Benchmark response schema."""

    ...


# This is needed to ensure the generated OAS has a better name than UnionsPage.
class BenchmarksListResponse(Page[Benchmark | ExtendedBenchmark | SystemBenchmark]): ...


# =============================================================================
# List Job Results
# =============================================================================


class BenchmarkJobResultsListFilter(Filter):
    """Filter for list benchmark job results."""

    name: StringFilter | str | None = Field(default=None, description="Filter job results by name.")
    benchmark: app.BenchmarkRef | None = Field(default=None, description="Filter results by benchmark reference.")
    metrics: str | None = Field(default=None, description="Filter results by metric reference.")
    dataset: app.FilesetRef | None = Field(
        default=None,
        description="Filter results by dataset if the benchmark job is configured with the fileset reference.",
    )
    model: app.ModelRef | None = Field(
        default=None, description="Filter results by model if the benchmark job is configured with the model reference."
    )
    created_at: DatetimeFilter | None = Field(default=None, description="Filter job results by creation date range.")


class BenchmarkJobResult(entities.BenchmarkJobResult):
    """Response type for benchmark job result."""

    pass


class BenchmarkJobResultsListResponse(Page[BenchmarkJobResult]): ...
