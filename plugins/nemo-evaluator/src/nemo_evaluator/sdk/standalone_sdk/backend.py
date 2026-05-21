# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapters that let the standalone evaluator SDK run through the evaluator plugin."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from nemo_evaluator.sdk.resources import AsyncEvaluator, Evaluator
from nemo_evaluator.sdk.types import ExecutionMode
from nemo_evaluator_sdk.execution.config import EvaluationRequest
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.results import EvaluationResult


def _reject_unsupported_hooks(request: EvaluationRequest) -> None:
    """Raise when standalone SDK hooks are requested for plugin execution."""
    if request.preprocess_hooks is not None or request.postprocess_hooks is not None:
        raise NotImplementedError("preprocess_hooks and postprocess_hooks are not supported.")


@dataclass(frozen=True, slots=True)
class NMPBackend:
    """Sync standalone evaluator SDK backend backed by a plugin evaluator resource.
    Implements the :class:`nemo_evaluator_sdk.execution.SyncEvaluationBackend` protocol.
    """

    resource: Evaluator
    execution_mode: ExecutionMode = "local"

    def evaluate(
        self,
        *,
        metric: Metric,
        request: EvaluationRequest,
    ) -> EvaluationResult:
        """Evaluate one metric through local or remote evaluator plugin execution."""
        _reject_unsupported_hooks(request)
        if self.execution_mode == "remote":
            return self.resource._executor.evaluate_remote(metric=metric, request=request)
        return self.resource._executor.evaluate(
            metric=metric,
            dataset=request.dataset,
            params=request.params,
            target=request.target,
            dataset_glob_pattern=request.dataset_glob_pattern,
            prompt_template=request.prompt_template,
            aggregate_fields=request.aggregate_fields,
        )

    def evaluate_benchmark(
        self,
        *,
        metrics: Sequence[Metric],
        request: EvaluationRequest,
    ) -> BenchmarkEvaluationResult:
        """Evaluate multiple metrics through local evaluator plugin execution."""
        _reject_unsupported_hooks(request)
        if self.execution_mode == "remote":
            raise NotImplementedError("Remote evaluation of benchmarks is not implemented yet.")
        return self.resource._executor.evaluate_benchmark(metrics=metrics, request=request)


@dataclass(frozen=True, slots=True)
class AsyncNMPBackend:
    """Async standalone evaluator SDK backend backed by a plugin evaluator resource.
    Implements the :class:`nemo_evaluator_sdk.execution.EvaluationBackend` protocol.
    """

    resource: AsyncEvaluator
    execution_mode: ExecutionMode = "local"

    async def evaluate(
        self,
        *,
        metric: Metric,
        request: EvaluationRequest,
    ) -> EvaluationResult:
        """Evaluate one metric through local or remote evaluator plugin execution."""
        _reject_unsupported_hooks(request)
        if self.execution_mode == "remote":
            return await self.resource._executor.evaluate_remote(metric=metric, request=request)
        return await self.resource._executor.evaluate(
            metric=metric,
            dataset=request.dataset,
            params=request.params,
            target=request.target,
            dataset_glob_pattern=request.dataset_glob_pattern,
            prompt_template=request.prompt_template,
            aggregate_fields=request.aggregate_fields,
        )

    async def evaluate_benchmark(
        self,
        *,
        metrics: Sequence[Metric],
        request: EvaluationRequest,
    ) -> BenchmarkEvaluationResult:
        """Evaluate multiple metrics through local evaluator plugin execution."""
        _reject_unsupported_hooks(request)
        if self.execution_mode == "remote":
            raise NotImplementedError("Remote evaluation of benchmarks is not implemented yet.")
        return await self.resource._executor.evaluate_benchmark(metrics=metrics, request=request)
