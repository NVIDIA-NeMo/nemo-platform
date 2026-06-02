# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK-backed evaluator job for the evaluator plugin scaffold."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, ClassVar, Self, TypeAlias, cast

from nemo_evaluator.jobs.utils import resolve_run_dataset
from nemo_evaluator.resolvers import PlatformModelResolver
from nemo_evaluator.sdk.values.filesets import FilesetRef
from nemo_evaluator.shared.metric_bundles.bundles import MetricBundle, unbundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricPayload  # noqa: F401
from nemo_evaluator_sdk import Evaluator
from nemo_evaluator_sdk.execution._protocols import JobParamsConfigurableMetric
from nemo_evaluator_sdk.execution.config import normalize_params
from nemo_evaluator_sdk.execution.metric_execution import run_sync
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricWithModels
from nemo_evaluator_sdk.values import (
    Agent,
    FieldMapping,
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
from pydantic import BaseModel, ConfigDict, Field, model_validator

TargetSpec = Model | Agent
MetricSpec: TypeAlias = Annotated[list[MetricBundle], Field(min_length=1)]
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


class EvaluateSpec(BaseModel):
    """Inline SDK evaluation input for the first evaluator plugin job."""

    model_config = ConfigDict(extra="forbid")

    metrics: MetricSpec = Field(description="Bundled metric entities to evaluate.")
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
    field_mapping: FieldMapping | None = Field(
        default=None, description="Optional mapping from canonical evaluator fields to dataset columns."
    )

    @model_validator(mode="after")
    def normalize_params_for_target(self) -> Self:
        self.params = normalize_params(self.params, self.target)
        return self


class EvaluateJob(NemoJob):
    """Run one evaluator SDK metric against inline rows."""

    name: ClassVar[str] = "evaluate"
    description: ClassVar[str] = "Run an inline evaluator SDK metric against inline dataset rows."
    container: ClassVar[str] = "cpu-tasks"
    spec_schema: ClassVar[type[BaseModel] | None] = EvaluateSpec
    job_collection_path: ClassVar[str | None] = "/evaluate/jobs"

    @staticmethod
    async def _resolve_metric_models(
        metrics: list[Metric],
        resolver: PlatformModelResolver,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel,
    ) -> None:
        """Resolve ModelRef fields on metric configs before local SDK execution."""
        for item in metrics:
            if isinstance(item, JobParamsConfigurableMetric):
                item.apply_evaluation_job_params(params)
            if isinstance(item, MetricWithModels):
                await item.resolve_models(resolver)

    @staticmethod
    def _unresolved_model_refs(metrics: list[Metric]) -> list[str]:
        refs = [
            model_ref.root
            for item in metrics
            if isinstance(item, MetricWithModels)
            for model_ref in item.model_refs().values()
        ]
        return sorted(refs)

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
        """Compile canonical spec to a plugin-native evaluator job."""
        del workspace, entity_client, job_name, async_sdk, options
        from nemo_evaluator.jobs.compiler import compile_evaluate_job

        canonical_spec = spec if isinstance(spec, EvaluateSpec) else EvaluateSpec.model_validate(spec.model_dump())
        return compile_evaluate_job(canonical_spec, profile=profile)

    @staticmethod
    def _hydrate_metrics(metrics: MetricSpec) -> list[Metric]:
        return [unbundle_metric(bundle) for bundle in metrics]

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

    def run(self, config: dict, *, ctx: JobContext, sdk: object | None = None, async_sdk: object | None = None) -> dict:
        """Run the evaluator job locally and persist its result artifact."""
        spec = EvaluateSpec.model_validate(config)
        evaluator = Evaluator()
        platform_sdk = async_sdk or sdk
        params = normalize_params(spec.params, spec.target)
        metrics = self._hydrate_metrics(spec.metrics)
        if platform_sdk is None:
            unresolved_refs = self._unresolved_model_refs(metrics)
            if unresolved_refs:
                raise ValueError(
                    "ModelRef metrics require `sdk` or `async_sdk` for local execution: " + ", ".join(unresolved_refs)
                )
        else:
            run_sync(lambda: self._resolve_metric_models(metrics, PlatformModelResolver(platform_sdk), params))
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
        if spec.field_mapping is not None:
            common_kwargs["field_mapping"] = spec.field_mapping
        runtime_metrics = metrics if len(metrics) > 1 else metrics[0]
        result = evaluator.run_sync(metrics=runtime_metrics, **common_kwargs)
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
