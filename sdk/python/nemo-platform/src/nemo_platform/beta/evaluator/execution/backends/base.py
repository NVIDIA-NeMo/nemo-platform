# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backend protocol for completed-result evaluator execution.

A backend exposes two operations, mirrored one-to-one by the public ``Evaluator``:

- ``evaluate_dataset`` — score a dataset with one metric (returns ``EvaluationResult``) or a
  sequence of metrics (returns ``BenchmarkEvaluationResult``).
- ``evaluate_taskset`` — score a taskset (agent evaluation) from precomputed trials or a live target.

The protocol signatures are intentionally flat (union metric input / union return); the precise,
overload-driven ergonomics live on the user-facing ``Evaluator`` methods.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, overload

from nemo_platform.beta.evaluator.agent_eval.results import AgentEvalResult
from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_platform.beta.evaluator.agent_eval.trials import AgentEvalTarget, AgentEvalTrial
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

    async def evaluate_taskset(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        """Run a task-driven (agent) evaluation over a taskset and return the completed result.

        Args:
            taskset: Tasks to evaluate; each task carries its own metrics.
            trials: Precomputed trials to score. Mutually exclusive with ``target``.
            target: Target used to generate trials online. Mutually exclusive with ``trials``.
            config: Optional run configuration (parallelism, output, prompt template).

        Returns:
            The completed agent-evaluation result.
        """
        ...


class SyncEvaluationBackend(Protocol):
    @overload
    def evaluate_dataset(
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
    def evaluate_dataset(
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

    def evaluate_taskset(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        """Run a task-driven (agent) evaluation over a taskset and return the completed result.

        Args:
            taskset: Tasks to evaluate; each task carries its own metrics.
            trials: Precomputed trials to score. Mutually exclusive with ``target``.
            target: Target used to generate trials online. Mutually exclusive with ``trials``.
            config: Optional run configuration (parallelism, output, prompt template).

        Returns:
            The completed agent-evaluation result.
        """
        ...
