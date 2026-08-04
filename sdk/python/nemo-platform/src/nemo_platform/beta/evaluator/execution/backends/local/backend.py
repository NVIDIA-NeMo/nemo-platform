# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local backend implementation for completed-result evaluator execution."""

from __future__ import annotations

from collections.abc import Sequence
from logging import getLogger
from pathlib import Path
from typing import Any, overload

import httpx
from nemo_platform.beta.evaluator.agent_eval.results import AgentEvalResult
from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_platform.beta.evaluator.agent_eval.trials import AgentEvalTarget, AgentEvalTrial
from nemo_platform.beta.evaluator.agent_inference import AgentInferenceFn, AgentInferenceFnFactory
from nemo_platform.beta.evaluator.dataset_schemas.compatibility import apply_column_mapping_to_row
from nemo_platform.beta.evaluator.datasets.loader import prepare_dataset_rows
from nemo_platform.beta.evaluator.execution.backends.base import BackendParams
from nemo_platform.beta.evaluator.execution.benchmark_execution import evaluate_benchmark as sdk_evaluate_benchmark
from nemo_platform.beta.evaluator.execution.metric_execution import _merge_online_hooks
from nemo_platform.beta.evaluator.execution.metric_execution import evaluate_metric as evaluate_metric_over_rows
from nemo_platform.beta.evaluator.execution.utils import (
    is_metric,
    is_metric_sequence,
    prepare_metric_for_execution,
    unique_metric_keys,
)
from nemo_platform.beta.evaluator.inference import InferenceFn, PostprocessResponse, PreprocessRequest
from nemo_platform.beta.evaluator.metrics.protocol import Metric
from nemo_platform.beta.evaluator.metrics.utils import metric_type_name
from nemo_platform.beta.evaluator.resolvers import LocalModelResolver, LocalSecretResolver
from nemo_platform.beta.evaluator.values import Agent, DatasetInput, FieldMapping, Model
from nemo_platform.beta.evaluator.values.multi_metric_results import BenchmarkEvaluationResult, namespace_result
from nemo_platform.beta.evaluator.values.results import AggregateFieldName, EvaluationResult
from openai import AsyncOpenAI

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
    """Local backend that executes dataset-driven and task-driven evaluations in-process."""

    @overload
    def __init__(
        self,
        *,
        inference_fn: InferenceFn | AgentInferenceFn | None = None,
        agent_inference_fn_factory: None = None,
        client: AsyncOpenAI | httpx.AsyncClient | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        inference_fn: None = None,
        agent_inference_fn_factory: AgentInferenceFnFactory,
        client: AsyncOpenAI | httpx.AsyncClient | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None: ...

    def __init__(
        self,
        *,
        inference_fn: InferenceFn | AgentInferenceFn | None = None,
        agent_inference_fn_factory: AgentInferenceFnFactory | None = None,
        client: AsyncOpenAI | httpx.AsyncClient | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        """Create a local backend with local resolver defaults.

        The optional online-inference transport configures task-driven (agent) evaluation
        via :meth:`evaluate_taskset`; it is unused by the dataset-driven :meth:`evaluate_dataset`
        path. Leave it unset to let the engine build a default client for the resolved target type.
        ``inference_fn`` and ``agent_inference_fn_factory`` are mutually exclusive (the overloads
        enforce this statically; the body rejects both at runtime).

        Args:
            inference_fn: Optional model or agent inference override for task generation.
            agent_inference_fn_factory: Optional per-task agent-inference factory. Mutually
                exclusive with ``inference_fn``.
            client: Optional transport client matching the target type: ``AsyncOpenAI`` for
                models or ``httpx.AsyncClient`` for agents.
            default_headers: Additional HTTP headers forwarded to live inference requests.

        Raises:
            ValueError: If both ``inference_fn`` and ``agent_inference_fn_factory`` are set.
        """
        if inference_fn is not None and agent_inference_fn_factory is not None:
            raise ValueError("provide either inference_fn or agent_inference_fn_factory, not both")
        self.secret_resolver = LocalSecretResolver()
        self.model_resolver = LocalModelResolver()
        self._inference_fn = inference_fn
        self._agent_inference_fn_factory = agent_inference_fn_factory
        self._agent_client = client
        self._default_headers = default_headers

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

        result = await evaluate_metric_over_rows(
            metric=prepared_metric,
            target=target,
            rows=rows,
            prompt_template=prompt_template,
            params=params,
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
        )

        return namespace_result(metric_key, result, aggregate_fields)

    async def _evaluate_benchmark(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        params: BackendParams,
        target: Model | Agent | None,
        field_mapping: FieldMapping | None,
        prompt_template: str | dict[str, Any] | None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None,
        preprocess_hooks: tuple[PreprocessRequest, ...] | None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None,
    ) -> BenchmarkEvaluationResult:
        """Execute multiple metrics using the shared streaming pipeline (inference once per row)."""
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
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
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
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
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
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
    ) -> EvaluationResult | BenchmarkEvaluationResult:
        """Execute one metric or a sequence of metrics over a dataset in-process.

        A single metric runs the single-metric path (returns ``EvaluationResult``); a sequence runs
        the shared streaming pipeline so target inference happens once per row regardless of metric
        count (returns ``BenchmarkEvaluationResult``).
        """
        if is_metric_sequence(metrics):
            return await self._evaluate_benchmark(
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
        if not is_metric(metrics):
            raise TypeError("metrics must be a Metric or a sequence of Metric objects")
        rows = _prepare_rows(dataset, params, field_mapping)
        return await self._evaluate_one(
            metric=metrics,
            metric_key=metric_type_name(metrics),
            params=params,
            target=target,
            prompt_template=prompt_template,
            aggregate_fields=aggregate_fields,
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
            rows=rows,
        )

    async def evaluate_taskset(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        """Run a task-driven (agent) evaluation over a taskset in-process.

        Drives the internal agent-evaluation engine using this backend's configured
        online-inference transport. Provide exactly one of ``trials`` (score precomputed) or
        ``target`` (generate online); the user-facing ``Evaluator.run_taskset_eval`` overloads make
        the choice explicit.

        Args:
            taskset: Tasks to evaluate; each task carries its own metrics.
            trials: Precomputed trials to score. Mutually exclusive with ``target``.
            target: Target used to generate trials online. Mutually exclusive with ``trials``.
            config: Optional run configuration (parallelism, output, prompt template).

        Returns:
            The completed agent-evaluation result.
        """
        # Imported lazily to avoid an import cycle: agent_eval.evaluator's deprecated shim
        # imports this module (LocalBackend) in turn.
        from nemo_platform.beta.evaluator.agent_eval.evaluator import _AgentEvalEngine

        if self._agent_inference_fn_factory is not None:
            engine = _AgentEvalEngine(
                agent_inference_fn_factory=self._agent_inference_fn_factory,
                client=self._agent_client,
                default_headers=self._default_headers,
            )
        else:
            engine = _AgentEvalEngine(
                inference_fn=self._inference_fn,
                client=self._agent_client,
                default_headers=self._default_headers,
            )
        return await engine.run(tasks=taskset, trials=trials, target=target, config=config)
