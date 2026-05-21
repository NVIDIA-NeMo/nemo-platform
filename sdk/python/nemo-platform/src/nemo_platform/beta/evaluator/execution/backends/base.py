# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backend protocol for completed-result evaluator execution."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from nemo_platform.beta.evaluator.execution.config import EvaluationRequest
from nemo_platform.beta.evaluator.metrics.protocol import Metric
from nemo_platform.beta.evaluator.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_platform.beta.evaluator.values.results import EvaluationResult


class EvaluationBackend(Protocol):
    async def evaluate(
        self,
        *,
        metric: Metric,
        request: EvaluationRequest,
    ) -> EvaluationResult:
        """Evaluate one metric directly and return the completed result.

        Args:
            metric: Metric to execute.
            request: Normalized evaluator request shared across backends.

        Returns:
            The completed single-metric evaluation result.
        """
        ...

    async def evaluate_benchmark(
        self,
        *,
        metrics: Sequence[Metric],
        request: EvaluationRequest,
    ) -> BenchmarkEvaluationResult:
        """Evaluate multiple metrics directly and return the completed result.

        Args:
            metrics: Metrics to execute together.
            request: Normalized evaluator request shared across backends.

        Returns:
            The completed multi-metric evaluation result.
        """
        ...


class SyncEvaluationBackend(Protocol):
    def evaluate(
        self,
        *,
        metric: Metric,
        request: EvaluationRequest,
    ) -> EvaluationResult:
        """Evaluate one metric directly and return the completed result.

        Args:
            metric: Metric to execute.
            request: Normalized evaluator request shared across backends.

        Returns:
            The completed single-metric evaluation result.
        """
        ...

    def evaluate_benchmark(
        self,
        *,
        metrics: Sequence[Metric],
        request: EvaluationRequest,
    ) -> BenchmarkEvaluationResult:
        """Evaluate multiple metrics directly and return the completed result.

        Args:
            metrics: Metrics to execute together.
            request: Normalized evaluator request shared across backends.

        Returns:
            The completed multi-metric result.
        """
        ...
