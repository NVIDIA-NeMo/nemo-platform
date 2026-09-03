# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public evaluator entrypoint for completed-result execution."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypeGuard, overload

import nemo_evaluator_sdk.inference as inference
from nemo_evaluator_sdk.execution.metric_execution import run_sync
from nemo_evaluator_sdk.execution.retrieval_execution import evaluate_retrieval
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.retrieval.beir import BeirDataset
from nemo_evaluator_sdk.values.agents import Agent
from nemo_evaluator_sdk.values.dataset_schemas import FieldMapping
from nemo_evaluator_sdk.values.datasets import DatasetInput
from nemo_evaluator_sdk.values.models import Model
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.params import RunConfig, RunConfigOnline, RunConfigOnlineModel
from nemo_evaluator_sdk.values.results import AggregateFieldName

from .backends.base import BackendParams, EvaluationBackend, SyncEvaluationBackend
from .backends.local.backend import LocalBackend
from .config import resolve_params

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
    if not callable(getattr(client, "evaluate_dataset", None)):
        raise TypeError("client must provide a callable evaluate_dataset method")


def _is_async_backend(client: BackendClient) -> TypeGuard[EvaluationBackend]:
    """Return whether the validated backend client exposes an async evaluator method."""
    return inspect.iscoroutinefunction(client.evaluate_dataset)


def _is_sync_backend(client: BackendClient) -> TypeGuard[SyncEvaluationBackend]:
    """Return whether the validated backend client exposes a sync evaluator method."""
    return not inspect.iscoroutinefunction(client.evaluate_dataset)


class _SyncBackendAdapter:
    """Expose a sync evaluator backend through the async backend contract."""

    def __init__(self, backend: SyncEvaluationBackend) -> None:
        """Store the sync backend to execute off the event loop."""
        self._backend = backend

    async def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        params: BackendParams,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[inference.PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[inference.PostprocessResponse, ...] | None = None,
    ) -> BenchmarkEvaluationResult:
        """Evaluate multiple metrics by running the sync backend in a worker thread."""
        return await asyncio.to_thread(
            self._backend.evaluate_dataset,
            metrics=metrics,
            dataset=dataset,
            params=params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            aggregate_fields=aggregate_fields,
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
        )


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
            metrics=[ExactMatchMetric(reference="{{item.reference}}")],
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

        # One contract method, so its flavour decides: there is no mixed sync/async case left to
        # reject. The final branch is unreachable and exists so the checker can narrow.
        if _is_async_backend(client):
            self._backend = client
        elif _is_sync_backend(client):
            self._backend = _SyncBackendAdapter(client)
        else:  # pragma: no cover
            raise TypeError("client must provide a callable evaluate_dataset method")

    @overload
    async def run(
        self,
        metrics: Sequence[Metric],
        *,
        retrieval: BeirDataset,
        target: Model,
        dataset: None = None,
        config: None = None,
        field_mapping: None = None,
        prompt_template: None = None,
        aggregate_fields: None = None,
        preprocess_hooks: None = None,
        postprocess_hooks: None = None,
    ) -> BenchmarkEvaluationResult: ...

    @overload
    async def run(
        self,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | None = None,
        target: None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> BenchmarkEvaluationResult: ...

    @overload
    async def run(
        self,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfigOnlineModel,
        target: Model,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> BenchmarkEvaluationResult: ...

    @overload
    async def run(
        self,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfigOnline,
        target: Agent,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any],
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> BenchmarkEvaluationResult: ...

    async def run(
        self,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path | None = None,
        *,
        retrieval: BeirDataset | None = None,
        config: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> BenchmarkEvaluationResult:
        """Evaluate metrics and return the finished result.

        Args:
            metrics: Metrics to execute together over each dataset row.
            dataset: Inline dataset rows, a dataset file, or a dataset directory/glob path.
            config: Optional run-level execution configuration. Offline calls default to ``RunConfig``.
            target: Optional model or agent used for online generation. Omit for offline scoring.
            field_mapping: Optional mapping from canonical evaluator fields to dataset columns.
            prompt_template: Optional prompt template to use for online target generation.
            aggregate_fields: Optional aggregate score fields to keep in the returned result.
            preprocess_hooks: Optional request preprocess hooks for online execution.
            postprocess_hooks: Optional response postprocess hooks for online execution.

        Returns:
            The completed multi-metric result.
        """
        if retrieval is not None:
            if dataset is not None:
                raise ValueError("dataset and retrieval are mutually exclusive")
            if not isinstance(target, Model):
                raise TypeError("retrieval evaluation requires a Model target")
            if any(
                value is not None
                for value in (
                    config,
                    field_mapping,
                    prompt_template,
                    aggregate_fields,
                    preprocess_hooks,
                    postprocess_hooks,
                )
            ):
                raise ValueError("retrieval evaluation does not accept dataset evaluation options")
            return await evaluate_retrieval(retrieval=retrieval, target=target, metrics=metrics)
        if dataset is None:
            raise ValueError("one of dataset or retrieval is required")

        params = resolve_params(config, target)
        normalized_preprocess_hooks = tuple(preprocess_hooks) if preprocess_hooks is not None else None
        normalized_postprocess_hooks = tuple(postprocess_hooks) if postprocess_hooks is not None else None
        return await self._backend.evaluate_dataset(
            metrics=list(metrics),
            dataset=dataset,
            params=params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            aggregate_fields=aggregate_fields,
            preprocess_hooks=normalized_preprocess_hooks,
            postprocess_hooks=normalized_postprocess_hooks,
        )

    @overload
    def run_sync(
        self,
        metrics: Sequence[Metric],
        *,
        retrieval: BeirDataset,
        target: Model,
        dataset: None = None,
        config: None = None,
        field_mapping: None = None,
        prompt_template: None = None,
        aggregate_fields: None = None,
        preprocess_hooks: None = None,
        postprocess_hooks: None = None,
    ) -> BenchmarkEvaluationResult: ...

    @overload
    def run_sync(
        self,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | None = None,
        target: None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> BenchmarkEvaluationResult: ...

    @overload
    def run_sync(
        self,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfigOnlineModel,
        target: Model,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> BenchmarkEvaluationResult: ...

    @overload
    def run_sync(
        self,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfigOnline,
        target: Agent,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any],
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> BenchmarkEvaluationResult: ...

    def run_sync(
        self,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path | None = None,
        *,
        retrieval: BeirDataset | None = None,
        config: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> BenchmarkEvaluationResult:
        """Synchronously evaluate metrics and return the finished result.

        Args:
            metrics: Metrics to execute together over each dataset row.
            dataset: Inline dataset rows, a dataset file, or a dataset directory/glob path.
            config: Optional run-level execution configuration. Offline calls default to ``RunConfig``.
            target: Optional model or agent used for online generation. Omit for offline scoring.
            field_mapping: Optional mapping from canonical evaluator fields to dataset columns.
            prompt_template: Optional prompt template to use for online target generation.
            aggregate_fields: Optional aggregate score fields to keep in the returned result.
            preprocess_hooks: Optional request preprocess hooks for online execution.
            postprocess_hooks: Optional response postprocess hooks for online execution.

        Returns:
            The completed multi-metric result.
        """

        async def _call() -> BenchmarkEvaluationResult:
            if retrieval is not None:
                if dataset is not None:
                    raise ValueError("dataset and retrieval are mutually exclusive")
                if not isinstance(target, Model):
                    raise TypeError("retrieval evaluation requires a Model target")
                if any(
                    value is not None
                    for value in (
                        config,
                        field_mapping,
                        prompt_template,
                        aggregate_fields,
                        preprocess_hooks,
                        postprocess_hooks,
                    )
                ):
                    raise ValueError("retrieval evaluation does not accept dataset evaluation options")
                return await evaluate_retrieval(retrieval=retrieval, target=target, metrics=metrics)
            if dataset is None:
                raise ValueError("one of dataset or retrieval is required")

            params = resolve_params(config, target)
            normalized_preprocess_hooks = tuple(preprocess_hooks) if preprocess_hooks is not None else None
            normalized_postprocess_hooks = tuple(postprocess_hooks) if postprocess_hooks is not None else None
            return await self._backend.evaluate_dataset(
                metrics=list(metrics),
                dataset=dataset,
                params=params,
                target=target,
                field_mapping=field_mapping,
                prompt_template=prompt_template,
                aggregate_fields=aggregate_fields,
                preprocess_hooks=normalized_preprocess_hooks,
                postprocess_hooks=normalized_postprocess_hooks,
            )

        return run_sync(_call)
