# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public evaluator entrypoint for completed-result execution."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypeGuard, overload

import nemo_platform.beta.evaluator.inference as inference
from nemo_platform.beta.evaluator.execution.metric_execution import run_sync
from nemo_platform.beta.evaluator.metrics.protocol import Metric
from nemo_platform.beta.evaluator.values.agents import Agent
from nemo_platform.beta.evaluator.values.dataset_schemas import FieldMapping
from nemo_platform.beta.evaluator.values.datasets import DatasetInput
from nemo_platform.beta.evaluator.values.models import Model
from nemo_platform.beta.evaluator.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_platform.beta.evaluator.values.params import RunConfig
from nemo_platform.beta.evaluator.values.results import AggregateFieldName, EvaluationResult

from .backends.base import EvaluationBackend, SyncEvaluationBackend
from .backends.local.backend import LocalBackend
from .config import EvaluationRequest, normalize_params

BackendClient = EvaluationBackend | SyncEvaluationBackend


def _validate_backend_client(client: BackendClient) -> None:
    """Validate that a backend client exposes callable evaluator methods.

    Do not use runtime-checkable protocols for this check. ``EvaluationBackend``
    and ``SyncEvaluationBackend`` share method names, and runtime protocol
    checks cannot distinguish async methods from sync methods.

    Args:
        client: Backend client to validate.

    Raises:
        TypeError: If the backend client does not expose the evaluator backend methods.
    """
    missing = [
        method_name
        for method_name in ("evaluate", "evaluate_benchmark")
        if not callable(getattr(client, method_name, None))
    ]
    if missing:
        raise TypeError(
            f"client must provide callable evaluate and evaluate_benchmark methods; missing: {', '.join(missing)}"
        )


def _is_async_backend(client: BackendClient) -> TypeGuard[EvaluationBackend]:
    """Return whether the validated backend client exposes async evaluator methods."""
    return inspect.iscoroutinefunction(client.evaluate) and inspect.iscoroutinefunction(client.evaluate_benchmark)


def _is_sync_backend(client: BackendClient) -> TypeGuard[SyncEvaluationBackend]:
    """Return whether the validated backend client exposes sync evaluator methods."""
    return not inspect.iscoroutinefunction(client.evaluate) and not inspect.iscoroutinefunction(
        client.evaluate_benchmark
    )


class _SyncBackendAdapter:
    """Expose a sync evaluator backend through the async backend contract."""

    def __init__(self, backend: SyncEvaluationBackend) -> None:
        """Store the sync backend to execute off the event loop."""
        self._backend = backend

    async def evaluate(
        self,
        *,
        metric: Metric,
        request: EvaluationRequest,
    ) -> EvaluationResult:
        """Evaluate one metric by running the sync backend in a worker thread."""
        return await asyncio.to_thread(self._backend.evaluate, metric=metric, request=request)

    async def evaluate_benchmark(
        self,
        *,
        metrics: Sequence[Metric],
        request: EvaluationRequest,
    ) -> BenchmarkEvaluationResult:
        """Evaluate multiple metrics by running the sync backend in a worker thread."""
        return await asyncio.to_thread(self._backend.evaluate_benchmark, metrics=metrics, request=request)


class Evaluator:
    """Evaluator convenience API for backends that return completed results.

    ``Evaluator`` evaluates metrics locally by default. When constructed with an
    evaluator backend object, it delegates completed-result execution to that
    backend. Sync backends are adapted to the async backend contract.

    Examples:
        Local evaluation uses `run` directly:

        ```python
        evaluator = Evaluator()
        result = await evaluator.run(
            metrics=ExactMatchMetric(reference="{{item.reference}}"),
            dataset=[{"reference": "Paris", "output_text": "Paris"}],
        )
        ```
    """

    def __init__(self, client: BackendClient | None = None) -> None:
        """Create an evaluator for completed-result backends.

        Args:
            client: Optional evaluator backend. Async backends are used directly;
                sync backends are adapted to the async backend contract. When
                omitted, the evaluator runs metrics in-process via ``LocalBackend``.
        """
        if client is None:
            self._backend: EvaluationBackend = LocalBackend()
            return

        _validate_backend_client(client)

        if _is_async_backend(client):
            self._backend = client
        elif _is_sync_backend(client):
            self._backend = _SyncBackendAdapter(client)
        else:
            raise TypeError(
                "client must implement either async evaluate/evaluate_benchmark "
                "or sync evaluate/evaluate_benchmark; "
                "mixed sync/async clients are not supported"
            )

    @overload
    async def run(
        self,
        metrics: Metric,
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | None = None,
        target: Model | Agent | None = None,
        dataset_glob_pattern: str | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult: ...

    @overload
    async def run(
        self,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | None = None,
        target: Model | Agent | None = None,
        dataset_glob_pattern: str | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> BenchmarkEvaluationResult: ...

    async def run(
        self,
        metrics: Metric | Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | None = None,
        target: Model | Agent | None = None,
        dataset_glob_pattern: str | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult | BenchmarkEvaluationResult:
        """Evaluate metrics and return the finished result.

        Args:
            metrics: One metric or a sequence of metrics to execute.
            dataset: Dataset input for the configured backend.
            config: Optional run-level execution configuration.
            model: Optional model used for online generation.
            dataset_glob_pattern: Optional file selector within the provided dataset path.
            field_mapping: Optional mapping from canonical evaluator fields to dataset columns.
            prompt_template: Optional prompt template to use for online model generation.
            aggregate_fields: Optional aggregate score fields to keep in the returned result.
            preprocess_hooks: Optional request preprocess hooks for online execution.
            postprocess_hooks: Optional response postprocess hooks for online execution.

        Returns:
            A single-metric or multi-metric result, matching the input metric
            shape.
        """
        eval_request = EvaluationRequest(
            dataset=dataset,
            params=normalize_params(config, target),
            target=target,
            dataset_glob_pattern=dataset_glob_pattern,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            aggregate_fields=aggregate_fields,
            preprocess_hooks=tuple(preprocess_hooks) if preprocess_hooks is not None else None,
            postprocess_hooks=tuple(postprocess_hooks) if postprocess_hooks is not None else None,
        )
        if isinstance(metrics, Sequence):
            return await self._backend.evaluate_benchmark(
                metrics=list(metrics),
                request=eval_request,
            )
        return await self._backend.evaluate(
            metric=metrics,
            request=eval_request,
        )

    @overload
    def run_sync(
        self,
        metrics: Metric,
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | None = None,
        target: Model | Agent | None = None,
        dataset_glob_pattern: str | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult: ...

    @overload
    def run_sync(
        self,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | None = None,
        target: Model | Agent | None = None,
        dataset_glob_pattern: str | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> BenchmarkEvaluationResult: ...

    def run_sync(
        self,
        metrics: Metric | Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | None = None,
        target: Model | Agent | None = None,
        dataset_glob_pattern: str | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult | BenchmarkEvaluationResult:
        """Synchronously evaluate metrics and return the finished result.

        Args:
            metrics: One metric or a sequence of metrics to execute.
            dataset: Dataset input for the configured backend.
            config: Optional run-level execution configuration.
            model: Optional model used for online generation.
            dataset_glob_pattern: Optional file selector within the provided dataset path.
            field_mapping: Optional mapping from canonical evaluator fields to dataset columns.
            prompt_template: Optional prompt template for online execution.
            aggregate_fields: Optional aggregate score fields to keep in the returned result.
            preprocess_hooks: Optional request preprocess hooks for online execution.
            postprocess_hooks: Optional response postprocess hooks for online execution.

        Returns:
            A single-metric or multi-metric result, matching the input metric
            shape.
        """
        return run_sync(
            lambda: self.run(
                metrics=metrics,
                dataset=dataset,
                config=config,
                target=target,
                dataset_glob_pattern=dataset_glob_pattern,
                field_mapping=field_mapping,
                prompt_template=prompt_template,
                aggregate_fields=aggregate_fields,
                preprocess_hooks=preprocess_hooks,
                postprocess_hooks=postprocess_hooks,
            )
        )
