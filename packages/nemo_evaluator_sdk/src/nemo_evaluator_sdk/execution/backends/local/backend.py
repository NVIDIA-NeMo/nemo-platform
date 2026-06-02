# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local backend implementation for completed-result evaluator execution."""

from __future__ import annotations

from collections.abc import Sequence
from logging import getLogger
from typing import Any

from nemo_evaluator_sdk.dataset_schemas.compatibility import apply_column_mapping_to_row
from nemo_evaluator_sdk.datasets.loader import prepare_dataset_rows
from nemo_evaluator_sdk.execution.benchmark_execution import evaluate_benchmark as sdk_evaluate_benchmark
from nemo_evaluator_sdk.execution.config import EvaluationRequest
from nemo_evaluator_sdk.execution.metric_execution import _merge_online_hooks, evaluate_metric
from nemo_evaluator_sdk.execution.utils import prepare_metric_for_execution, unique_metric_keys
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.metrics.utils import metric_type_name
from nemo_evaluator_sdk.resolvers import LocalModelResolver, LocalSecretResolver
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult, namespace_result
from nemo_evaluator_sdk.values.results import EvaluationResult

log = getLogger(__name__)


def _prepare_request_rows(request: EvaluationRequest) -> list[dict[str, Any]]:
    """Load request rows and apply any canonical field mapping."""
    rows = prepare_dataset_rows(
        request.dataset,
        request.dataset_glob_pattern,
        request.params.limit_samples if request.params else None,
    )
    if request.field_mapping is None:
        return rows
    return [apply_column_mapping_to_row(row, request.field_mapping) for row in rows]


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
        request: EvaluationRequest,
        rows: list[dict[str, Any]],
    ) -> EvaluationResult:
        """Prepare one metric and execute it through the local runtime.

        Args:
            metric: Metric to execute.
            metric_key: Public metric key used to namespace the result.
            request: Normalized evaluator request for the backend.
            rows: Precomputed dataset rows shared across metrics in the request.

        Returns:
            A namespaced single-metric evaluation result.
        """
        prepared_metric = await prepare_metric_for_execution(
            metric,
            params=request.params,
            model_resolver=self.model_resolver,
            secret_resolver=self.secret_resolver,
        )

        result = await evaluate_metric(
            metric=prepared_metric,
            target=request.target,
            rows=rows,
            prompt_template=request.prompt_template,
            params=request.params,
            preprocess_hooks=request.preprocess_hooks,
            postprocess_hooks=request.postprocess_hooks,
        )

        return namespace_result(metric_key, result, request.aggregate_fields)

    async def evaluate(
        self,
        *,
        metric: Metric,
        request: EvaluationRequest,
    ) -> EvaluationResult:
        """Execute one metric locally and return the completed result.

        Args:
            metric: Metric to execute.
            request: Normalized evaluator request for the backend.

        Returns:
            A namespaced single-metric result.
        """
        rows = _prepare_request_rows(request)
        return await self._evaluate_one(
            metric=metric,
            metric_key=metric_type_name(metric),
            request=request,
            rows=rows,
        )

    async def evaluate_benchmark(
        self,
        *,
        metrics: Sequence[Metric],
        request: EvaluationRequest,
    ) -> BenchmarkEvaluationResult:
        """Execute multiple metrics locally using the shared streaming pipeline.

        Delegates to :func:`sdk_evaluate_benchmark` so that each dataset row runs
        target inference exactly once, regardless of metric count.

        Args:
            metrics: Metrics to execute.
            request: Normalized evaluator request for the backend.

        Returns:
            A completed multi-metric result.
        """
        rows = _prepare_request_rows(request)
        metric_keys = unique_metric_keys(metrics)
        prepared_metrics = [
            await prepare_metric_for_execution(
                metric,
                params=request.params,
                model_resolver=self.model_resolver,
                secret_resolver=self.secret_resolver,
            )
            for metric in metrics
        ]
        metrics_built: list[tuple[str, Metric]] = list(zip(metric_keys, prepared_metrics, strict=True))
        if request.target is not None:
            preprocess_hooks, postprocess_hooks = _merge_online_hooks(
                params=request.params,
                target=request.target,
                preprocess_hooks=request.preprocess_hooks,
                postprocess_hooks=request.postprocess_hooks,
            )
        else:
            preprocess_hooks = tuple(request.preprocess_hooks or ())
            postprocess_hooks = tuple(request.postprocess_hooks or ())
        return await sdk_evaluate_benchmark(
            metrics=metrics_built,
            rows=rows,
            target=request.target,
            params=request.params,
            prompt_template=request.prompt_template,
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
            aggregate_fields=request.aggregate_fields,
            logger=log,
        )
