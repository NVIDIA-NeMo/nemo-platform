# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backend protocol for completed-result evaluator execution."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from nemo_platform.beta.evaluator.inference import PostprocessResponse, PreprocessRequest
from nemo_platform.beta.evaluator.metrics.protocol import Metric
from nemo_platform.beta.evaluator.values import (
    Agent,
    DatasetInput,
    FieldMapping,
    Model,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from nemo_platform.beta.evaluator.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_platform.beta.evaluator.values.results import AggregateFieldName, EvaluationResult

BackendParams = RunConfig | RunConfigOnline | RunConfigOnlineModel


class EvaluationBackend(Protocol):
    async def evaluate(
        self,
        *,
        metric: Metric,
        dataset: DatasetInput | str | Path,
        params: BackendParams,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
    ) -> EvaluationResult:
        """Evaluate one metric directly and return the completed result.

        Args:
            metric: Metric to prepare and execute.
            dataset: Inline dataset rows, a dataset file, or a dataset directory/glob path.
            params: Validated run configuration for the selected target mode.
            target: Optional model or agent used to generate candidate responses before scoring.
            field_mapping: Optional mapping from canonical evaluator fields to dataset columns.
            prompt_template: Optional prompt template for online target generation.
            aggregate_fields: Optional aggregate score fields to keep in the returned result.
            preprocess_hooks: Optional request preprocess hooks for online execution.
            postprocess_hooks: Optional response postprocess hooks for online execution.

        Returns:
            The completed single-metric evaluation result.
        """
        ...

    async def evaluate_benchmark(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        params: BackendParams,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
    ) -> BenchmarkEvaluationResult:
        """Evaluate multiple metrics directly and return the completed result.

        Args:
            metrics: Metrics to prepare and execute together.
            dataset: Inline dataset rows, a dataset file, or a dataset directory/glob path.
            params: Validated run configuration for the selected target mode.
            target: Optional model or agent used to generate candidate responses before scoring.
            field_mapping: Optional mapping from canonical evaluator fields to dataset columns.
            prompt_template: Optional prompt template for online target generation.
            aggregate_fields: Optional aggregate score fields to keep in the returned result.
            preprocess_hooks: Optional request preprocess hooks for online execution.
            postprocess_hooks: Optional response postprocess hooks for online execution.

        Returns:
            The completed multi-metric evaluation result.
        """
        ...


class SyncEvaluationBackend(Protocol):
    def evaluate(
        self,
        *,
        metric: Metric,
        dataset: DatasetInput | str | Path,
        params: BackendParams,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
    ) -> EvaluationResult:
        """Evaluate one metric directly and return the completed result.

        Args:
            metric: Metric to prepare and execute.
            dataset: Inline dataset rows, a dataset file, or a dataset directory/glob path.
            params: Validated run configuration for the selected target mode.
            target: Optional model or agent used to generate candidate responses before scoring.
            field_mapping: Optional mapping from canonical evaluator fields to dataset columns.
            prompt_template: Optional prompt template for online target generation.
            aggregate_fields: Optional aggregate score fields to keep in the returned result.
            preprocess_hooks: Optional request preprocess hooks for online execution.
            postprocess_hooks: Optional response postprocess hooks for online execution.

        Returns:
            The completed single-metric evaluation result.
        """
        ...

    def evaluate_benchmark(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        params: BackendParams,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
    ) -> BenchmarkEvaluationResult:
        """Evaluate multiple metrics directly and return the completed result.

        Args:
            metrics: Metrics to prepare and execute together.
            dataset: Inline dataset rows, a dataset file, or a dataset directory/glob path.
            params: Validated run configuration for the selected target mode.
            target: Optional model or agent used to generate candidate responses before scoring.
            field_mapping: Optional mapping from canonical evaluator fields to dataset columns.
            prompt_template: Optional prompt template for online target generation.
            aggregate_fields: Optional aggregate score fields to keep in the returned result.
            preprocess_hooks: Optional request preprocess hooks for online execution.
            postprocess_hooks: Optional response postprocess hooks for online execution.

        Returns:
            The completed multi-metric result.
        """
        ...
