# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local backend implementation for completed-result evaluator execution."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from logging import getLogger
from pathlib import Path
from typing import Any, overload

from nemo_platform.beta.evaluator.agent_eval.evaluator import AgentEvaluator, validate_run_inputs
from nemo_platform.beta.evaluator.agent_eval.results import AgentEvalResult
from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_platform.beta.evaluator.agent_eval.trials import AgentEvalTarget, AgentEvalTrial
from nemo_platform.beta.evaluator.dataset_schemas.compatibility import apply_column_mapping_to_row
from nemo_platform.beta.evaluator.datasets.loader import prepare_dataset_rows
from nemo_platform.beta.evaluator.execution.backends.base import BackendParams
from nemo_platform.beta.evaluator.execution.benchmark_execution import evaluate_benchmark as sdk_evaluate_benchmark
from nemo_platform.beta.evaluator.execution.jobs import EvaluationJob, LocalJob
from nemo_platform.beta.evaluator.execution.metric_execution import _merge_online_hooks
from nemo_platform.beta.evaluator.execution.utils import prepare_metric_for_execution, unique_metric_keys
from nemo_platform.beta.evaluator.inference import PostprocessResponse, PreprocessRequest
from nemo_platform.beta.evaluator.metrics.protocol import Metric
from nemo_platform.beta.evaluator.resolvers import LocalModelResolver, LocalSecretResolver
from nemo_platform.beta.evaluator.values import Agent, DatasetInput, FieldMapping, Model, RunConfig
from nemo_platform.beta.evaluator.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_platform.beta.evaluator.values.results import AggregateFieldName

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
        """Start an in-process taskset evaluation and return its job.

        The evaluation is scheduled on the running loop before this returns, so it is already in
        flight when the caller gets the handle — the state a platform job is in once created.
        Starting several evaluations and then waiting on them therefore overlaps them, as it would
        against a remote backend. Inputs are checked now rather than at the wait, matching where
        the remote path rejects them.
        """
        validate_run_inputs(tasks=taskset, trials=trials, target=target)
        return LocalJob(asyncio.create_task(self._run_taskset(taskset, trials=trials, target=target, config=config)))

    async def _run_taskset(
        self,
        taskset: Sequence[AgentEvalTask],
        *,
        trials: Sequence[AgentEvalTrial] | None,
        target: AgentEvalTarget | None,
        config: AgentEvalRunConfig | None,
    ) -> AgentEvalResult:
        """Resolve each task's metrics against this backend's resolvers, then score.

        ``AgentEvaluator`` takes no resolvers, so a task metric carrying a ``ModelRef`` or
        ``SecretRef`` would reach scoring unresolved. The dataset path prepares its metrics the
        same way.
        """
        params = config.params if config is not None and config.params is not None else RunConfig()
        prepared = [
            task.model_copy(
                update={
                    "metrics": [
                        await prepare_metric_for_execution(
                            metric,
                            params=params,
                            model_resolver=self.model_resolver,
                            secret_resolver=self.secret_resolver,
                        )
                        for metric in task.metrics
                    ]
                }
            )
            for task in taskset
        ]
        validate_run_inputs(tasks=prepared, trials=trials, target=target)
        evaluator = AgentEvaluator()
        if trials is not None:
            return await evaluator.run(tasks=prepared, trials=trials, config=config)
        if target is not None:
            return await evaluator.run(tasks=prepared, target=target, config=config)
        raise ValueError("provide exactly one of trials or target")

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
    ) -> EvaluationJob[BenchmarkEvaluationResult]:
        """Start executing multiple metrics locally using the shared streaming pipeline.

        Scheduled on the running loop before this returns, so the evaluation is in flight when the
        caller gets the handle, matching :meth:`evaluate` and a remote backend. Delegates to
        :func:`sdk_evaluate_benchmark` so that each dataset row runs target inference exactly once,
        regardless of metric count.

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
            The job, awaited through its own methods.
        """
        return LocalJob(
            asyncio.create_task(
                self._evaluate_dataset(
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
        )

    async def _evaluate_dataset(
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
        """Run the metrics and return the finished multi-metric result."""
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
