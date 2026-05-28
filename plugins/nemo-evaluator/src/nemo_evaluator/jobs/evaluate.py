# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK-backed evaluator job for the evaluator plugin scaffold."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, ClassVar, Self, TypeAlias, cast

from nemo_evaluator.jobs.utils import remote_compile_metric, resolve_run_dataset, resolve_submit_dataset
from nemo_evaluator.resolvers import PlatformModelResolver
from nemo_evaluator_sdk import Evaluator
from nemo_evaluator_sdk.execution._protocols import JobParamsConfigurableMetric
from nemo_evaluator_sdk.execution.config import normalize_params
from nemo_evaluator_sdk.metrics.protocol import MetricWithModels
from nemo_evaluator_sdk.metrics.types import MetricsUnion
from nemo_evaluator_sdk.values import (
    Agent,
    Model,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.results import EvaluationResult
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from nmp.evaluator.app.values import FilesetRef
from pydantic import BaseModel, ConfigDict, Field, model_validator

TargetSpec = Model | Agent
MetricSpec: TypeAlias = MetricsUnion | Annotated[list[MetricsUnion], Field(min_length=1)]
EvaluationArtifactResult: TypeAlias = EvaluationResult | BenchmarkEvaluationResult
InlineDataset: TypeAlias = Annotated[list[dict[str, object]], Field(min_length=1)]
DatasetSpec: TypeAlias = InlineDataset | FilesetRef

DEFAULT_RESULT_NAME = "evaluation-results"
DEFAULT_FILE_NAME = "evaluation-results.json"
ARTIFACTS_RESULT_NAME = "artifacts"
AGGREGATE_SCORES_RESULT_NAME = "aggregate-scores"
ROW_SCORES_RESULT_NAME = "row-scores"
AGGREGATE_SCORES_FILE_NAME = "aggregate-scores.json"
ROW_SCORES_FILE_NAME = "row-scores.jsonl"
RESULT_IGNORE_PATTERNS = ["cache.db", "cache/"]


@dataclass(frozen=True)
class EvaluationResultFiles:
    """Filesystem layout for an evaluator SDK result."""

    full_result: Path
    aggregate_scores: Path
    row_scores: Path
    artifacts_dir: Path


def _unresolved_model_refs(metric: MetricsUnion | list[MetricsUnion]) -> list[str]:
    metrics = metric if isinstance(metric, list) else [metric]
    refs = [
        model_ref.root
        for item in metrics
        if isinstance(item, MetricWithModels)
        for model_ref in item.model_refs().values()
    ]
    return sorted(refs)


async def _resolve_metric_models(
    metric: MetricsUnion | list[MetricsUnion],
    resolver: PlatformModelResolver,
    params: RunConfig | RunConfigOnline | RunConfigOnlineModel,
) -> None:
    """Resolve ModelRef fields on metric configs before SDK execution."""
    metrics = metric if isinstance(metric, list) else [metric]
    for item in metrics:
        if isinstance(item, JobParamsConfigurableMetric):
            item.apply_evaluation_job_params(params)
        if isinstance(item, MetricWithModels):
            await item.resolve_models(resolver)


class EvaluateInputSpec(BaseModel):
    """Submitter-facing SDK evaluation input for the evaluator plugin job."""

    model_config = ConfigDict(extra="forbid")

    metric: MetricSpec = Field(description="Inline evaluator SDK metric configuration or benchmark metrics.")
    dataset: DatasetSpec = Field(
        description="Inline dataset rows or a persisted FilesetRef dataset source to evaluate.",
    )
    params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = Field(
        default=None, description="Optional evaluator SDK execution parameters."
    )
    target: TargetSpec | None = Field(default=None, description="Optional model or agent target for online evaluation.")
    prompt_template: str | dict[str, Any] | None = Field(
        default=None, description="Optional prompt template for online target generation."
    )

    @model_validator(mode="after")
    def normalize_params_for_target(self) -> Self:
        self.params = normalize_params(self.params, self.target)
        return self


class EvaluateSpec(EvaluateInputSpec):
    """Canonical SDK evaluation spec with platform model references resolved."""

    @model_validator(mode="after")
    def reject_unresolved_metric_model_refs(self) -> Self:
        unresolved_refs = _unresolved_model_refs(self.metric)
        if unresolved_refs:
            raise ValueError(
                "EvaluateSpec metric models must be resolved before compile/run: " + ", ".join(unresolved_refs)
            )
        return self


class EvaluateJob(NemoJob):
    """Run one evaluator SDK metric against inline rows."""

    name: ClassVar[str] = "evaluate"
    description: ClassVar[str] = "Run an inline evaluator SDK metric against inline dataset rows."
    container: ClassVar[str] = "cpu-tasks"
    input_spec_schema: ClassVar[type[BaseModel] | None] = EvaluateInputSpec
    spec_schema: ClassVar[type[BaseModel] | None] = EvaluateSpec
    job_collection_path: ClassVar[str | None] = "/evaluate/jobs"

    @staticmethod
    def _write_result_files(result: EvaluationArtifactResult, persistent_dir: Path) -> EvaluationResultFiles:
        """Write full, aggregate, and row-level evaluator artifacts."""
        result_payload = result.model_dump(mode="json")
        full_result_path = persistent_dir / DEFAULT_FILE_NAME
        full_result_path.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")

        artifacts_dir = persistent_dir / ARTIFACTS_RESULT_NAME
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        aggregate_path = artifacts_dir / AGGREGATE_SCORES_FILE_NAME
        aggregate_path.write_text(result.aggregate_scores.model_dump_json(indent=2), encoding="utf-8")
        row_scores_path = artifacts_dir / ROW_SCORES_FILE_NAME
        with row_scores_path.open("w", encoding="utf-8") as f:
            for row_score in result.row_scores:
                f.write(row_score.model_dump_json() + "\n")

        return EvaluationResultFiles(
            full_result=full_result_path,
            aggregate_scores=aggregate_path,
            row_scores=row_scores_path,
            artifacts_dir=artifacts_dir,
        )

    @classmethod
    async def to_spec(
        cls,
        input_spec: BaseModel,
        *,
        workspace: str,
        entity_client: object,
        async_sdk: AsyncNeMoPlatform,
        is_local: bool,
    ) -> BaseModel:
        """Resolve submitter-facing model references into the canonical evaluation spec."""
        del workspace, entity_client, is_local
        submit_spec = (
            input_spec.model_copy(deep=True)
            if isinstance(input_spec, EvaluateInputSpec)
            else EvaluateInputSpec.model_validate(input_spec.model_dump())
        )
        unresolved_refs = _unresolved_model_refs(submit_spec.metric)
        if unresolved_refs:
            if async_sdk is None:
                raise ValueError(
                    "ModelRef metrics require `async_sdk` for spec resolution: " + ", ".join(unresolved_refs)
                )
            await _resolve_metric_models(
                submit_spec.metric,
                PlatformModelResolver(async_sdk),
                normalize_params(submit_spec.params, submit_spec.target),
            )
        return EvaluateSpec.model_validate(submit_spec.model_dump(mode="python"))

    @classmethod
    async def compile(
        cls,
        *,
        workspace: str,
        spec: BaseModel,
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        """Compile canonical spec using the evaluator service metric job compiler."""
        del workspace, entity_client, job_name, profile, options
        canonical_spec = (
            spec.model_copy(deep=True)
            if isinstance(spec, EvaluateSpec)
            else EvaluateSpec.model_validate(spec.model_dump())
        )

        from nmp.evaluator.app.jobs.metrics import compile_metric_job
        from nmp.evaluator.app.values import Dataset, MetricOfflineJob, MetricOnlineAgentJob, MetricOnlineJob

        dataset, dataset_ref = await resolve_submit_dataset(cast(AsyncNeMoPlatform, async_sdk), canonical_spec.dataset)
        compiled_dataset = cast(Dataset, dataset)
        params = normalize_params(canonical_spec.params, canonical_spec.target)
        metric = remote_compile_metric(canonical_spec.metric)
        if isinstance(canonical_spec.target, Model):
            model = canonical_spec.target
            prompt_template = canonical_spec.prompt_template
            if prompt_template is None:
                raise ValueError("prompt_template is required when EvaluateSpec.target is a model")
            if not isinstance(params, RunConfigOnlineModel):
                raise TypeError("model target requires RunConfigOnlineModel")
            metric_job = MetricOnlineJob(
                metric=metric,
                model=model,
                dataset=compiled_dataset,
                dataset_ref=dataset_ref,
                params=params,
                prompt_template=prompt_template,
            )
        elif isinstance(canonical_spec.target, Agent):
            agent = canonical_spec.target
            prompt_template = canonical_spec.prompt_template
            if prompt_template is None:
                raise ValueError("prompt_template is required when EvaluateSpec.target is an agent")
            if not isinstance(params, RunConfigOnline):
                raise TypeError("agent target requires RunConfigOnline")
            metric_job = MetricOnlineAgentJob(
                metric=metric,
                agent=agent,
                dataset=compiled_dataset,
                dataset_ref=dataset_ref,
                params=params,
                prompt_template=prompt_template,
            )
        else:
            if not isinstance(params, RunConfig):
                raise TypeError("offline evaluation requires RunConfig")
            metric_job = MetricOfflineJob(
                metric=metric,
                dataset=compiled_dataset,
                dataset_ref=dataset_ref,
                params=params,
            )
        return await compile_metric_job(metric_job)

    def run(self, config: dict, *, ctx: JobContext, sdk: object | None = None, async_sdk: object | None = None) -> dict:
        """Run the evaluator job locally and persist its result artifact."""
        spec = EvaluateSpec.model_validate(config)
        evaluator = Evaluator()
        params = normalize_params(spec.params, spec.target)
        dataset = resolve_run_dataset(
            spec.dataset,
            ctx=ctx,
            sdk=cast(NeMoPlatform | None, sdk),
            async_sdk=cast(AsyncNeMoPlatform | None, async_sdk),
        )
        common_kwargs: dict[str, Any] = {
            "dataset": dataset,
            "config": params,
            "target": spec.target,
            "prompt_template": spec.prompt_template,
        }
        result = evaluator.run_sync(metrics=spec.metric, **common_kwargs)
        result_files = self._write_result_files(result, ctx.storage.persistent)
        artifact = ctx.results.save(DEFAULT_RESULT_NAME, result_files.full_result)
        ctx.results.save(AGGREGATE_SCORES_RESULT_NAME, result_files.aggregate_scores)
        ctx.results.save(ROW_SCORES_RESULT_NAME, result_files.row_scores)
        ctx.results.save(ARTIFACTS_RESULT_NAME, result_files.artifacts_dir, ignore_patterns=RESULT_IGNORE_PATTERNS)

        # TODO: Implement progress reporting hook in SDK - AALGO-149
        # self.report_progress(
        #     ctx,
        #     work_done=1,
        #     work_total=1,
        #     status="completed",
        # )

        return {
            "status": "completed",
            "artifact": artifact.model_dump(),
        }
