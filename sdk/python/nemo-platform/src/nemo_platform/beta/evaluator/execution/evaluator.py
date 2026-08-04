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
from nemo_platform.beta.evaluator.agent_eval.results import AgentEvalResult
from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_platform.beta.evaluator.agent_eval.trials import AgentEvalTarget, AgentEvalTrial
from nemo_platform.beta.evaluator.execution.metric_execution import run_sync
from nemo_platform.beta.evaluator.execution.utils import is_metric, is_metric_sequence
from nemo_platform.beta.evaluator.metrics.protocol import Metric
from nemo_platform.beta.evaluator.values.agents import Agent
from nemo_platform.beta.evaluator.values.dataset_schemas import FieldMapping
from nemo_platform.beta.evaluator.values.datasets import DatasetInput
from nemo_platform.beta.evaluator.values.models import Model
from nemo_platform.beta.evaluator.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_platform.beta.evaluator.values.params import RunConfig, RunConfigOnline, RunConfigOnlineModel
from nemo_platform.beta.evaluator.values.results import AggregateFieldName, EvaluationResult

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
    missing = [
        method_name
        for method_name in ("evaluate_dataset", "evaluate_taskset")
        if not callable(getattr(client, method_name, None))
    ]
    if missing:
        raise TypeError(
            f"client must provide callable evaluate_dataset and evaluate_taskset methods; missing: {', '.join(missing)}"
        )


def _is_async_backend(client: BackendClient) -> TypeGuard[EvaluationBackend]:
    """Return whether the validated backend client exposes async evaluator methods."""
    return inspect.iscoroutinefunction(client.evaluate_dataset) and inspect.iscoroutinefunction(client.evaluate_taskset)


def _is_sync_backend(client: BackendClient) -> TypeGuard[SyncEvaluationBackend]:
    """Return whether the validated backend client exposes sync evaluator methods."""
    return not inspect.iscoroutinefunction(client.evaluate_dataset) and not inspect.iscoroutinefunction(
        client.evaluate_taskset
    )


class _SyncBackendAdapter:
    """Expose a sync evaluator backend through the async backend contract."""

    def __init__(self, backend: SyncEvaluationBackend) -> None:
        """Store the sync backend to execute off the event loop."""
        self._backend = backend

    @overload
    async def evaluate_dataset(
        self,
        *,
        metrics: Metric,
        dataset: DatasetInput | str | Path,
        params: BackendParams,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[inference.PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[inference.PostprocessResponse, ...] | None = None,
    ) -> EvaluationResult: ...

    @overload
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
    ) -> BenchmarkEvaluationResult: ...

    async def evaluate_dataset(
        self,
        *,
        metrics: Metric | Sequence[Metric],
        dataset: DatasetInput | str | Path,
        params: BackendParams,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[inference.PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[inference.PostprocessResponse, ...] | None = None,
    ) -> EvaluationResult | BenchmarkEvaluationResult:
        """Evaluate a dataset by running the sync backend in a worker thread.

        Narrow to the metric-shape before calling so the sync backend's ``evaluate_dataset``
        overload picks the precise return type.
        """
        if is_metric_sequence(metrics):
            return await asyncio.to_thread(
                lambda: self._backend.evaluate_dataset(
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
            )
        if is_metric(metrics):
            return await asyncio.to_thread(
                lambda: self._backend.evaluate_dataset(
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
            )
        raise TypeError("metrics must be a Metric or a sequence of Metric objects")

    async def evaluate_taskset(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        """Run a task-driven evaluation by running the sync backend in a worker thread."""
        return await asyncio.to_thread(
            self._backend.evaluate_taskset,
            taskset=taskset,
            trials=trials,
            target=target,
            config=config,
        )


class Evaluator:
    """Unified evaluator for dataset-driven and task-driven (agent) evaluation.

    ``Evaluator`` runs evaluations in-process by default. When constructed with an
    evaluator backend object, it delegates completed-result execution to that backend
    (sync backends are adapted to the async backend contract) — the same ``Evaluator``
    code runs locally or against a platform backend depending on the injected client.

    Its methods mirror the backend protocol one-to-one:

    - :meth:`run_dataset_eval` (backend ``evaluate_dataset``) — score a dataset with one metric
      (returns ``EvaluationResult``) or a sequence of metrics (returns ``BenchmarkEvaluationResult``).
    - :meth:`run_taskset_eval` (backend ``evaluate_taskset``) — score a taskset (each task carrying
      its own metrics) from precomputed trials or a live target.

    Each has a ``_sync`` variant. ``run`` / ``run_sync`` are backward-compatible aliases of
    ``run_dataset_eval`` / ``run_dataset_eval_sync``.

    Examples:
        Dataset-driven evaluation:

        ```python
        result = await Evaluator().run_dataset_eval(
            ExactMatchMetric(reference="{{item.reference}}"),
            dataset=[{"reference": "Paris", "output_text": "Paris"}],
        )
        ```

        Task-driven (agent) evaluation:

        ```python
        result = await Evaluator().run_taskset_eval(taskset=tasks, target=agent_target)
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
                "client must implement either async evaluate_dataset/evaluate_taskset "
                "or sync evaluate_dataset/evaluate_taskset; "
                "mixed sync/async clients are not supported"
            )

    async def _dataset_eval(
        self,
        metrics: Metric | Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult | BenchmarkEvaluationResult:
        """Flat dataset-eval implementation shared by the overloaded public methods.

        Kept non-overloaded so the sync bridge and other internal callers can forward
        ``metrics``/``config``/``target`` unions; narrows to the metric shape here so the
        backend's ``evaluate_dataset`` overload picks the precise return type.
        """
        params = resolve_params(config, target)
        normalized_preprocess_hooks = tuple(preprocess_hooks) if preprocess_hooks is not None else None
        normalized_postprocess_hooks = tuple(postprocess_hooks) if postprocess_hooks is not None else None
        if is_metric_sequence(metrics):
            return await self._backend.evaluate_dataset(
                metrics=metrics,
                dataset=dataset,
                params=params,
                target=target,
                field_mapping=field_mapping,
                prompt_template=prompt_template,
                aggregate_fields=aggregate_fields,
                preprocess_hooks=normalized_preprocess_hooks,
                postprocess_hooks=normalized_postprocess_hooks,
            )
        if is_metric(metrics):
            return await self._backend.evaluate_dataset(
                metrics=metrics,
                dataset=dataset,
                params=params,
                target=target,
                field_mapping=field_mapping,
                prompt_template=prompt_template,
                aggregate_fields=aggregate_fields,
                preprocess_hooks=normalized_preprocess_hooks,
                postprocess_hooks=normalized_postprocess_hooks,
            )
        raise TypeError("metrics must be a Metric or a sequence of Metric objects")

    @overload
    async def run_dataset_eval(
        self,
        metrics: Metric,
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | None = None,
        target: None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult: ...

    @overload
    async def run_dataset_eval(
        self,
        metrics: Metric,
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfigOnlineModel,
        target: Model,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult: ...

    @overload
    async def run_dataset_eval(
        self,
        metrics: Metric,
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfigOnline,
        target: Agent,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any],
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult: ...

    @overload
    async def run_dataset_eval(
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
    async def run_dataset_eval(
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
    async def run_dataset_eval(
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

    async def run_dataset_eval(
        self,
        metrics: Metric | Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult | BenchmarkEvaluationResult:
        """Evaluate a dataset with one metric or a sequence of metrics.

        Mirrors the backend ``evaluate_dataset`` operation: a single metric returns an
        ``EvaluationResult``; a sequence returns a ``BenchmarkEvaluationResult``.

        Args:
            metrics: One metric or a sequence of metrics to execute.
            dataset: Inline dataset rows, a dataset file, or a dataset directory/glob path.
            config: Optional run-level execution configuration. Offline calls default to ``RunConfig``.
            target: Optional model or agent used for online generation. Omit for offline scoring.
            field_mapping: Optional mapping from canonical evaluator fields to dataset columns.
            prompt_template: Optional prompt template to use for online target generation.
            aggregate_fields: Optional aggregate score fields to keep in the returned result.
            preprocess_hooks: Optional request preprocess hooks for online execution.
            postprocess_hooks: Optional response postprocess hooks for online execution.

        Returns:
            A single-metric or multi-metric result, matching the input metric shape.
        """
        return await self._dataset_eval(
            metrics,
            dataset,
            config=config,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            aggregate_fields=aggregate_fields,
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
        )

    @overload
    def run_dataset_eval_sync(
        self,
        metrics: Metric,
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | None = None,
        target: None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult: ...

    @overload
    def run_dataset_eval_sync(
        self,
        metrics: Metric,
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfigOnlineModel,
        target: Model,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult: ...

    @overload
    def run_dataset_eval_sync(
        self,
        metrics: Metric,
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfigOnline,
        target: Agent,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any],
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult: ...

    @overload
    def run_dataset_eval_sync(
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
    def run_dataset_eval_sync(
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
    def run_dataset_eval_sync(
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

    def run_dataset_eval_sync(
        self,
        metrics: Metric | Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
        config: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: Sequence[inference.PreprocessRequest] | None = None,
        postprocess_hooks: Sequence[inference.PostprocessResponse] | None = None,
    ) -> EvaluationResult | BenchmarkEvaluationResult:
        """Synchronous bridge for :meth:`run_dataset_eval`."""
        return run_sync(
            lambda: self._dataset_eval(
                metrics,
                dataset,
                config=config,
                target=target,
                field_mapping=field_mapping,
                prompt_template=prompt_template,
                aggregate_fields=aggregate_fields,
                preprocess_hooks=preprocess_hooks,
                postprocess_hooks=postprocess_hooks,
            )
        )

    @overload
    async def run_taskset_eval(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult: ...

    @overload
    async def run_taskset_eval(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial],
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult: ...

    async def run_taskset_eval(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        """Evaluate a taskset (agent evaluation) and return the finished result.

        Mirrors the backend ``evaluate_taskset`` operation. Each task carries its own metrics.
        Provide exactly one of ``trials`` (score precomputed trials) or ``target`` (generate trials
        online before scoring) — the overloads make the choice explicit.

        Args:
            taskset: Tasks to evaluate.
            trials: Precomputed trials to score. Mutually exclusive with ``target``.
            target: Target used to generate trials online. Mutually exclusive with ``trials``.
            config: Optional run configuration (parallelism, output, prompt template).

        Returns:
            The completed agent-evaluation result.
        """
        return await self._backend.evaluate_taskset(taskset=taskset, trials=trials, target=target, config=config)

    @overload
    def run_taskset_eval_sync(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult: ...

    @overload
    def run_taskset_eval_sync(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial],
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult: ...

    def run_taskset_eval_sync(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        """Synchronous bridge for :meth:`run_taskset_eval`."""
        return run_sync(
            lambda: self._backend.evaluate_taskset(taskset=taskset, trials=trials, target=target, config=config)
        )

    # Backward-compatible aliases for the dataset path: ``run`` / ``run_sync`` are the dataset-eval
    # methods under their historical names (they predate the dataset/taskset split).
    run = run_dataset_eval
    run_sync = run_dataset_eval_sync
