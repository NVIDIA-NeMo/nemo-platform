# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local backend implementation for completed-result evaluator execution."""

from __future__ import annotations

from collections.abc import Sequence
from logging import getLogger
from pathlib import Path
from typing import Any

from nemo_platform.beta.evaluator.dataset_schemas.compatibility import apply_column_mapping_to_row
from nemo_platform.beta.evaluator.datasets.loader import prepare_dataset_rows
from nemo_platform.beta.evaluator.execution.backends.base import BackendParams
from nemo_platform.beta.evaluator.execution.benchmark_execution import evaluate_benchmark as sdk_evaluate_benchmark
from nemo_platform.beta.evaluator.execution.metric_execution import _merge_online_hooks, evaluate_metric
from nemo_platform.beta.evaluator.execution.utils import prepare_metric_for_execution, unique_metric_keys
from nemo_platform.beta.evaluator.inference import PostprocessResponse, PreprocessRequest
from nemo_platform.beta.evaluator.metrics.protocol import Metric
from nemo_platform.beta.evaluator.metrics.utils import metric_type_name
from nemo_platform.beta.evaluator.resolvers import LocalModelResolver, LocalSecretResolver
from nemo_platform.beta.evaluator.values import Agent, DatasetInput, FieldMapping, Model
from nemo_platform.beta.evaluator.values.multi_metric_results import BenchmarkEvaluationResult, namespace_result
from nemo_platform.beta.evaluator.values.results import AggregateFieldName, EvaluationResult

log = getLogger(__name__)


def _prepare_rows(
    dataset: DatasetInput | str | Path,
    params: BackendParams,
    field_mapping: FieldMapping | None,
) -> list[dict[str, Any]]:
    """Load dataset rows, apply sampling limits, and project mapped fields."""
    rows = prepare_dataset_rows(
        dataset,
        None,
        params.limit_samples,
    )
    if field_mapping is None:
        return rows
    return [apply_column_mapping_to_row(row, field_mapping) for row in rows]


class LocalBackend:
    """Local backend that executes metrics in-process."""

    def __init__(self) -> None:
        """Create a local backend with local resolver defaults."""
        self.secret_resolver = LocalSecretResolver()
        self.model_resolver = LocalModelResolver()

    async def _evaluate_one(
        self,
        *,
        metric: Metric,
        metric_key: str,
        params: BackendParams,
        target: Model | Agent | None,
        prompt_template: str | dict[str, Any] | None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None,
        preprocess_hooks: tuple[PreprocessRequest, ...] | None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None,
        rows: list[dict[str, Any]],
    ) -> EvaluationResult:
        """Prepare one metric and execute it through the local runtime.

        Args:
            metric: Metric to execute.
            metric_key: Public metric key used to namespace the result.
            params: Validated run configuration for the selected target mode.
            target: Optional model or agent used to generate candidate responses before scoring.
            prompt_template: Optional prompt template for online target generation.
            aggregate_fields: Optional aggregate score fields to keep in the returned result.
            preprocess_hooks: Optional request preprocess hooks for online execution.
            postprocess_hooks: Optional response postprocess hooks for online execution.
            rows: Precomputed dataset rows shared across metrics in the request.

        Returns:
            A namespaced single-metric evaluation result.
        """
        prepared_metric = await prepare_metric_for_execution(
            metric,
            params=params,
            model_resolver=self.model_resolver,
            secret_resolver=self.secret_resolver,
        )

        result = await evaluate_metric(
            metric=prepared_metric,
            target=target,
            rows=rows,
            prompt_template=prompt_template,
            params=params,
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
        )

        return namespace_result(metric_key, result, aggregate_fields)

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
        """Execute one metric locally and return the completed result.

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
            A namespaced single-metric result.
        """
        rows = _prepare_rows(dataset, params, field_mapping)
        return await self._evaluate_one(
            metric=metric,
            metric_key=metric_type_name(metric),
            params=params,
            target=target,
            prompt_template=prompt_template,
            aggregate_fields=aggregate_fields,
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
            rows=rows,
        )

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
        """Execute multiple metrics locally using the shared streaming pipeline.

        Delegates to :func:`sdk_evaluate_benchmark` so that each dataset row runs
        target inference exactly once, regardless of metric count.

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
            A completed multi-metric result.
        """
        rows = _prepare_rows(dataset, params, field_mapping)
        metric_keys = unique_metric_keys(metrics)
        prepared_metrics = [
            await prepare_metric_for_execution(
                metric,
                params=params,
                model_resolver=self.model_resolver,
                secret_resolver=self.secret_resolver,
            )
            for metric in metrics
        ]
        metrics_built: list[tuple[str, Metric]] = list(zip(metric_keys, prepared_metrics, strict=True))
        if target is not None:
            merged_preprocess_hooks, merged_postprocess_hooks = _merge_online_hooks(
                params=params,
                target=target,
                preprocess_hooks=preprocess_hooks,
                postprocess_hooks=postprocess_hooks,
            )
        else:
            merged_preprocess_hooks = tuple(preprocess_hooks or ())
            merged_postprocess_hooks = tuple(postprocess_hooks or ())
        return await sdk_evaluate_benchmark(
            metrics=metrics_built,
            rows=rows,
            target=target,
            params=params,
            prompt_template=prompt_template,
            preprocess_hooks=merged_preprocess_hooks,
            postprocess_hooks=merged_postprocess_hooks,
            aggregate_fields=aggregate_fields,
            logger=log,
        )
