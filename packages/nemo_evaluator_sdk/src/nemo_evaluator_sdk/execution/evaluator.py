# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public evaluator entrypoint for completed-result execution."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Generic, TypeGuard, TypeVar, overload

import nemo_evaluator_sdk.inference as inference
from nemo_evaluator_sdk.agent_eval.evaluator import validate_run_inputs
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTarget, AgentEvalTrial
from nemo_evaluator_sdk.execution.jobs import (
    DEFAULT_JOB_TIMEOUT_SECONDS,
    DEFAULT_PENDING_TIMEOUT_SECONDS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    EvaluationJob,
    SyncEvaluationJob,
)
from nemo_evaluator_sdk.execution.metric_execution import run_sync
from nemo_evaluator_sdk.metrics.protocol import Metric
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

#: See :mod:`nemo_evaluator_sdk.execution.jobs` — PEP 695 syntax would break Python 3.11.
_ResultT = TypeVar("_ResultT")


def _local_only(
    aggregate_fields: tuple[AggregateFieldName, ...] | None,
    preprocess_hooks: tuple[inference.PreprocessRequest, ...] | None,
    postprocess_hooks: tuple[inference.PostprocessResponse, ...] | None,
) -> dict[str, Any]:
    """Collect the arguments the backend contract does not carry, omitting the unset ones.

    Inference hooks are Python callables and aggregate-field projection shapes a result the
    backend has already produced, so neither can cross a process boundary. A backend that runs
    in-process accepts them as extras; passing them to one that does not raises rather than
    dropping them silently.
    """
    extra: dict[str, Any] = {}
    if aggregate_fields is not None:
        extra["aggregate_fields"] = aggregate_fields
    if preprocess_hooks is not None:
        extra["preprocess_hooks"] = preprocess_hooks
    if postprocess_hooks is not None:
        extra["postprocess_hooks"] = postprocess_hooks
    return extra


def _validate_backend_client(client: BackendClient) -> None:
    """Validate that a backend client implements the evaluator backend contract.

    Only for the error message: without it the flavour check below reaches for a missing attribute
    and reports one name with no statement of what the contract is. Static typing already rejects a
    non-conforming backend; this is for clients assembled dynamically.

    Args:
        client: Backend client to validate.

    Raises:
        TypeError: If the backend client does not implement the contract.
    """
    # Typecheckers catch a non-conforming backend statically; this is the runtime equivalent.
    if isinstance(client, EvaluationBackend):
        return
    raise TypeError("client must provide callable evaluate and evaluate_dataset methods")


def _is_async_backend(client: BackendClient) -> TypeGuard[EvaluationBackend]:
    """Return whether the validated backend client exposes async evaluator methods.

    ``isinstance`` against a runtime-checkable protocol cannot answer this: the async and sync
    contracts declare identical member names, so only :func:`inspect.iscoroutinefunction` separates
    them.
    """
    return inspect.iscoroutinefunction(client.evaluate) and inspect.iscoroutinefunction(client.evaluate_dataset)


def _is_sync_backend(client: BackendClient) -> TypeGuard[SyncEvaluationBackend]:
    """Return whether the validated backend client exposes sync evaluator methods."""
    return not inspect.iscoroutinefunction(client.evaluate) and not inspect.iscoroutinefunction(client.evaluate_dataset)


class _SyncJobAdapter(Generic[_ResultT]):
    """Expose a sync evaluation job through the async job contract."""

    def __init__(self, job: SyncEvaluationJob[_ResultT]) -> None:
        """Store the sync job to drive off the event loop."""
        self._job = job

    async def wait_until_done(
        self,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        job_timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS,
        pending_timeout_seconds: float = DEFAULT_PENDING_TIMEOUT_SECONDS,
    ) -> None:
        """Wait by polling the sync job in a worker thread."""
        await asyncio.to_thread(
            self._job.wait_until_done,
            poll_interval_seconds=poll_interval_seconds,
            job_timeout_seconds=job_timeout_seconds,
            pending_timeout_seconds=pending_timeout_seconds,
        )

    async def get_result(self) -> _ResultT:
        """Fetch the finished result in a worker thread."""
        return await asyncio.to_thread(self._job.get_result)


class _SyncBackendAdapter:
    """Expose a sync evaluator backend through the async backend contract."""

    def __init__(self, backend: SyncEvaluationBackend) -> None:
        """Store the sync backend to execute off the event loop."""
        self._backend = backend

    @overload
    async def evaluate(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget,
        config: AgentEvalRunConfig | None = None,
    ) -> EvaluationJob[AgentEvalResult]: ...

    @overload
    async def evaluate(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial],
        config: AgentEvalRunConfig | None = None,
    ) -> EvaluationJob[AgentEvalResult]: ...

    async def evaluate(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget | None = None,
        trials: Sequence[AgentEvalTrial] | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> EvaluationJob[AgentEvalResult]:
        """Start a taskset evaluation by running the sync backend in a worker thread.

        Branches on the seam because ``to_thread`` forwards through a ``ParamSpec``, which binds
        to a single overload and cannot express "one of these two arguments".
        """
        validate_run_inputs(tasks=taskset, trials=trials, target=target)
        if trials is not None:
            job = await asyncio.to_thread(self._backend.evaluate, taskset=taskset, trials=trials, config=config)
        elif target is not None:
            job = await asyncio.to_thread(self._backend.evaluate, taskset=taskset, target=target, config=config)
        else:  # pragma: no cover - validate_run_inputs above already rejected this
            raise ValueError("provide exactly one of trials or target")
        return _SyncJobAdapter(job)

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
    ) -> EvaluationJob[BenchmarkEvaluationResult]:
        """Start a dataset evaluation by running the sync backend in a worker thread."""
        job = await asyncio.to_thread(
            self._backend.evaluate_dataset,
            metrics=metrics,
            dataset=dataset,
            params=params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            **_local_only(aggregate_fields, preprocess_hooks, postprocess_hooks),
        )
        return _SyncJobAdapter(job)


class Evaluator:
    """Evaluator convenience API for backends that return completed results.

    ``Evaluator`` evaluates metrics locally by default. When constructed with an
    evaluator backend object, it delegates completed-result execution to that
    backend. Sync backends are adapted to the async backend contract.

    Examples:
        Local evaluation uses `run_dataset` directly:

        ```python
        evaluator = Evaluator()
        result = await evaluator.run_dataset(
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

        if _is_async_backend(client):
            self._backend = client
        elif _is_sync_backend(client):
            self._backend = _SyncBackendAdapter(client)
        else:
            raise TypeError(
                "client must implement either async evaluate/evaluate_dataset "
                "or sync evaluate/evaluate_dataset; "
                "mixed sync/async clients are not supported"
            )

    @overload
    async def run(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult: ...

    @overload
    async def run(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial],
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult: ...

    async def run(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget | None = None,
        trials: Sequence[AgentEvalTrial] | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        """Evaluate a taskset and return the completed result.

        Local versus remote is an argument, not a different API — omit ``client`` and the work runs
        in-process; inject a backend and the identical call runs there instead:

        ```python
        async def run_eval(backend: EvaluationBackend | None = None) -> AgentEvalResult:
            return await Evaluator(client=backend).run(taskset=tasks, target=model)
        ```

        Args:
            taskset: Tasks to evaluate, each carrying its own metrics.
            target: What generates trials — a model, agent, or runner. Mutually exclusive
                with ``trials``.
            trials: Precomputed trials to score instead of generating them. Mutually exclusive
                with ``target``.
            config: Run-level execution settings.

        Returns:
            The completed evaluation result.
        """
        # The overloads promise this constraint, so honour it here rather than leaving it to
        # whichever backend happens to be injected.
        validate_run_inputs(tasks=taskset, trials=trials, target=target)
        if trials is not None:
            job = await self._backend.evaluate(taskset=taskset, trials=trials, config=config)
        elif target is not None:
            job = await self._backend.evaluate(taskset=taskset, target=target, config=config)
        else:  # pragma: no cover - validate_run_inputs above already rejected this
            raise ValueError("provide exactly one of trials or target")
        await job.wait_until_done()
        return await job.get_result()

    @overload
    def run_sync(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult: ...

    @overload
    def run_sync(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial],
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult: ...

    def run_sync(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget | None = None,
        trials: Sequence[AgentEvalTrial] | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        """Synchronous bridge for :meth:`run`.

        Branches on which seam was supplied because the overloads keep the two apart.
        """
        validate_run_inputs(tasks=taskset, trials=trials, target=target)
        if trials is not None:
            return run_sync(lambda: self.run(taskset=taskset, trials=trials, config=config))
        if target is not None:
            return run_sync(lambda: self.run(taskset=taskset, target=target, config=config))
        raise ValueError("provide exactly one of trials or target")

    @overload
    async def run_dataset(
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
    async def run_dataset(
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
    async def run_dataset(
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

    async def run_dataset(
        self,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
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
        params = resolve_params(config, target)
        normalized_preprocess_hooks = tuple(preprocess_hooks) if preprocess_hooks is not None else None
        normalized_postprocess_hooks = tuple(postprocess_hooks) if postprocess_hooks is not None else None
        job = await self._backend.evaluate_dataset(
            metrics=list(metrics),
            dataset=dataset,
            params=params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            **_local_only(aggregate_fields, normalized_preprocess_hooks, normalized_postprocess_hooks),
        )
        await job.wait_until_done()
        return await job.get_result()

    @overload
    def run_dataset_sync(
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
    def run_dataset_sync(
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
    def run_dataset_sync(
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

    def run_dataset_sync(
        self,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        *,
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
            params = resolve_params(config, target)
            normalized_preprocess_hooks = tuple(preprocess_hooks) if preprocess_hooks is not None else None
            normalized_postprocess_hooks = tuple(postprocess_hooks) if postprocess_hooks is not None else None
            job = await self._backend.evaluate_dataset(
                metrics=list(metrics),
                dataset=dataset,
                params=params,
                target=target,
                field_mapping=field_mapping,
                prompt_template=prompt_template,
                **_local_only(aggregate_fields, normalized_preprocess_hooks, normalized_postprocess_hooks),
            )
            await job.wait_until_done()
            return await job.get_result()

        return run_sync(_call)
