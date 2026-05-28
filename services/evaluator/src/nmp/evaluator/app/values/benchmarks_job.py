# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, ClassVar, Literal

from nemo_evaluator_sdk.values import (
    Agent,
    AggregatedMetricResult,
    AggregateScore,
    Model,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
    SupportedJobTypes,
)
from nemo_evaluator_sdk.values.multi_metric_results import (
    BenchmarkEvaluationResult as SDKBenchmarkEvaluationResult,
)
from nmp.evaluator.app.values.benchmarks import Benchmark, BenchmarkMetric
from nmp.evaluator.app.values.common import MetricRef, ModelRef
from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, TypeAdapter

# =============================================================================
# Benchmark Job Types
# =============================================================================


class _BenchmarkJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    benchmark: Benchmark = Field(description="The benchmark for evaluation.")


OptionalFieldName = Annotated[str, Field(min_length=1)]


class BenchmarkOfflineJob(_BenchmarkJob):
    __job_type__: ClassVar[Literal[SupportedJobTypes.OFFLINE]] = SupportedJobTypes.OFFLINE
    params: RunConfig | None = Field(
        default_factory=RunConfig, description="Execution parameters for the benchmark job."
    )


class BenchmarkOnlineJob(_BenchmarkJob):
    __job_type__: ClassVar[Literal[SupportedJobTypes.ONLINE]] = SupportedJobTypes.ONLINE
    model: Model = Field(description="The model to evaluate.")
    model_ref: ModelRef | None = Field(default=None, description="Reference to the model")
    params: RunConfigOnlineModel | None = Field(
        default_factory=RunConfigOnlineModel, description="Execution parameters for the benchmark job."
    )
    prompt_template: str | dict
    optional_fields: list[OptionalFieldName] = Field(
        default_factory=list,
        description=(
            "Prompt template fields that should remain available to the prompt template but not be "
            "required by dataset schema validation."
        ),
    )


class BenchmarkOnlineAgentJob(_BenchmarkJob):
    """Online benchmark job targeting an agent."""

    __job_type__: ClassVar[Literal[SupportedJobTypes.ONLINE]] = SupportedJobTypes.ONLINE
    agent: Agent = Field(description="The agent to evaluate.")
    params: RunConfigOnline | None = Field(
        default_factory=RunConfigOnline, description="Execution parameters for the benchmark job."
    )
    prompt_template: str | dict
    optional_fields: list[OptionalFieldName] = Field(
        default_factory=list,
        description=(
            "Prompt template fields that should remain available to the prompt template but not be "
            "required by dataset schema validation."
        ),
    )


def _benchmark_job_discriminator(data: Any) -> str:
    """
    Discriminate union type specifically for internal job spec which has benchmark reference resolved.
    """
    if isinstance(data, dict):
        has_model = "model" in data
        has_agent = "agent" in data
    else:
        has_model = hasattr(data, "model")
        has_agent = hasattr(data, "agent")

    if has_agent and has_model:
        raise ValueError("Only one of 'model' or 'agent' may be specified, not both.")

    if has_agent:
        return "online-agent"

    if has_model:
        return "online"

    return "offline"


BenchmarkJob = Annotated[
    (
        Annotated[BenchmarkOfflineJob, Tag("offline")]
        | Annotated[BenchmarkOnlineJob, Tag("online")]
        | Annotated[BenchmarkOnlineAgentJob, Tag("online-agent")]
    ),
    Discriminator(_benchmark_job_discriminator),
]
BenchmarkJobAdapter = TypeAdapter(BenchmarkJob)


# =============================================================================
# Results Schema
# =============================================================================


class BenchmarkMetricResult(AggregatedMetricResult):
    """Aggregated results for a single metric within a benchmark."""

    metric: MetricRef | None = Field(
        default=None, description="The metric used for the evaluation job to generate the result."
    )


def _strip_metric_namespace(metric_ref: str, scores: Sequence[AggregateScore]) -> list[AggregateScore]:
    """Remove the ``{metric_ref}.`` prefix added by SDK-level score namespacing."""
    prefix = f"{metric_ref}."
    stripped: list[AggregateScore] = []
    for score in scores:
        if score.name.startswith(prefix):
            stripped.append(score.model_copy(update={"name": score.name[len(prefix) :]}))
        else:
            stripped.append(score)
    return stripped


class BenchmarkEvaluationResult(BaseModel):
    """Aggregated results for a benchmark evaluation."""

    results: list[BenchmarkMetricResult] = Field(description="Results for each metric in the benchmark.")

    @classmethod
    def from_sdk_results(
        cls,
        sdk_result: SDKBenchmarkEvaluationResult,
        benchmark_metrics: Sequence[BenchmarkMetric],
    ) -> BenchmarkEvaluationResult:
        """Project the SDK benchmark result onto the service REST wire shape.

        Example:
            SDK input shape:
                ``per_metric["default/exact-match"].aggregate_scores.scores[0].name == "default/exact-match.score"``

            Service output shape:
                ``results[0].metric.root == "default/exact-match"``
                ``results[0].scores[0].name == "score"``

        The transformation keeps the per-metric aggregate payload but converts
        the outer container from SDK ``per_metric`` mapping form into the
        service ``results`` list form, while stripping the ``{metric_ref}.``
        namespace prefix from each aggregate score name.
        """
        by_ref = {
            benchmark_metric.metric_ref.root: benchmark_metric.metric_ref for benchmark_metric in benchmark_metrics
        }
        results: list[BenchmarkMetricResult] = []
        for metric_ref, evaluation_result in sdk_result.per_metric.items():
            if metric_ref not in by_ref:
                raise ValueError(
                    f"SDK returned result for unknown metric_ref {metric_ref!r} "
                    "while projecting benchmark results; "
                    f"expected one of {sorted(by_ref)!r}"
                )
            metric = by_ref[metric_ref]
            results.append(
                BenchmarkMetricResult(
                    metric=metric,
                    scores=_strip_metric_namespace(metric_ref, evaluation_result.aggregate_scores.scores),
                )
            )
        return cls(results=results)
