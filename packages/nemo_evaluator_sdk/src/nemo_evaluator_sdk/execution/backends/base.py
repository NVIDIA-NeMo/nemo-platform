# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backend protocol for completed-result evaluator execution."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, overload, runtime_checkable

from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTarget, AgentEvalTrial
from nemo_evaluator_sdk.execution.jobs import EvaluationJob, SyncEvaluationJob
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.values import (
    Agent,
    DatasetInput,
    FieldMapping,
    Model,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult

BackendParams = RunConfig | RunConfigOnline | RunConfigOnlineModel


@runtime_checkable
class EvaluationBackend(Protocol):
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
        """Start evaluating a taskset — tasks that each carry their own metrics — and return its job.

        The entrypoint ``evaluate_dataset`` is intended to fold into: a dataset with one shared
        metric list is a taskset whose metrics have been hoisted. That is not implemented yet — this
        method cannot express a dataset today — so ``evaluate_dataset`` remains the way to run one,
        and is not deprecated.

        Returns a job rather than a result so the caller chooses when to wait and can reach the
        run's identity, partial state, and artifacts meanwhile;
        :meth:`~nemo_evaluator_sdk.execution.evaluator.Evaluator.submit` waits on the caller's
        behalf. A backend that runs in-process returns a
        :class:`~nemo_evaluator_sdk.execution.jobs.LocalJob`, which likewise defers the work to the
        wait, so the call means the same thing wherever it executed. Implementations may accept extra keyword arguments with defaults (a
        workspace, a metric packager) without breaking conformance.

        Args:
            taskset: Tasks to evaluate, each carrying its own metrics.
            target: What generates trials — a model, agent, or runner. Mutually exclusive
                with ``trials``.
            trials: Precomputed trials to score instead of generating them. Mutually exclusive
                with ``target``.
            config: Run-level execution settings.

        Returns:
            The job, awaited through its own methods.
        """
        ...

    async def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        params: BackendParams,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
    ) -> EvaluationJob[BenchmarkEvaluationResult]:
        """Start evaluating multiple metrics over a dataset and return its job.

        Implementations that run in-process may accept further keyword arguments with defaults —
        inference hooks, aggregate-field projection — which cannot cross a process boundary and so
        are not part of this contract.

        Args:
            metrics: Metrics to prepare and execute together.
            dataset: Inline dataset rows, a dataset file, or a dataset directory/glob path.
            params: Validated run configuration for the selected target mode.
            target: Optional model or agent used to generate candidate responses before scoring.
            field_mapping: Optional mapping from canonical evaluator fields to dataset columns.
            prompt_template: Optional prompt template for online target generation.

        Returns:
            The job, awaited through its own methods.
        """
        ...


@runtime_checkable
class SyncEvaluationBackend(Protocol):
    @overload
    def evaluate(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget,
        config: AgentEvalRunConfig | None = None,
    ) -> SyncEvaluationJob[AgentEvalResult]: ...

    @overload
    def evaluate(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial],
        config: AgentEvalRunConfig | None = None,
    ) -> SyncEvaluationJob[AgentEvalResult]: ...

    def evaluate(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget | None = None,
        trials: Sequence[AgentEvalTrial] | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> SyncEvaluationJob[AgentEvalResult]:
        """Start evaluating a taskset — tasks that each carry their own metrics — and return its job.

        The sync counterpart of :meth:`EvaluationBackend.evaluate`.

        The entrypoint ``evaluate_dataset`` is intended to fold into: a dataset with one shared
        metric list is a taskset whose metrics have been hoisted. That is not implemented yet — this
        method cannot express a dataset today — so ``evaluate_dataset`` remains the way to run one,
        and is not deprecated.

        Returns a job rather than a result; see :meth:`EvaluationBackend.evaluate`.

        Args:
            taskset: Tasks to evaluate, each carrying its own metrics.
            target: What generates trials — a model, agent, or runner. Mutually exclusive
                with ``trials``.
            trials: Precomputed trials to score instead of generating them. Mutually exclusive
                with ``target``.
            config: Run-level execution settings.

        Returns:
            The job, awaited through its own methods.
        """
        ...

    def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: DatasetInput | str | Path,
        params: BackendParams,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
    ) -> SyncEvaluationJob[BenchmarkEvaluationResult]:
        """Start evaluating multiple metrics over a dataset and return its job.

        Implementations that run in-process may accept further keyword arguments with defaults —
        inference hooks, aggregate-field projection — which cannot cross a process boundary and so
        are not part of this contract.

        Args:
            metrics: Metrics to prepare and execute together.
            dataset: Inline dataset rows, a dataset file, or a dataset directory/glob path.
            params: Validated run configuration for the selected target mode.
            target: Optional model or agent used to generate candidate responses before scoring.
            field_mapping: Optional mapping from canonical evaluator fields to dataset columns.
            prompt_template: Optional prompt template for online target generation.

        Returns:
            The job, awaited through its own methods.
        """
        ...
