# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK-backed evaluator job for the evaluator plugin scaffold."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, ClassVar, Self, TypeAlias

# Imported for their registration side effects: each module registers its
# payload kind in the bundle registry so MetricBundle payloads validate.
import nemo_evaluator.shared.metric_bundles.cloudpickle  # noqa: F401
import nemo_evaluator.shared.metric_bundles.inline  # noqa: F401
from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.filesets import FilesetRef, download_dataset, download_dataset_sync
from nemo_evaluator.metric_refs import MetricRef, resolve_metric_specs
from nemo_evaluator.resolvers import PlatformModelResolver
from nemo_evaluator.shared.metric_bundles.bundles import (
    MetricBundle,
    bundle_metric,
    metric_bundle_packager_for_payload,
    unbundle_metric,
)
from nemo_evaluator_sdk import Evaluator
from nemo_evaluator_sdk.execution.config import resolve_params
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
MetricSpec: TypeAlias = Annotated[list[MetricInline | MetricRef], Field(min_length=1)]
# Canonical spec carries inline metrics only (refs resolved) — still the wire DTO,
# so the runtime MetricBundle never surfaces as a public schema.
ResolvedMetricSpec: TypeAlias = Annotated[list[MetricInline], Field(min_length=1)]
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


def _unresolved_model_refs(metrics: list[Metric]) -> list[str]:
    refs = [
        model_ref.root
        for item in metrics
        if isinstance(item, MetricWithModels)
        for model_ref in item.model_refs().values()
    ]
    return sorted(refs)


def _bundle_resolved_metric(metric: Metric, source_bundle: MetricBundle) -> MetricBundle:
    packager = metric_bundle_packager_for_payload(source_bundle.payload)
    resolved_bundle = bundle_metric(metric, packager)
    return resolved_bundle.model_copy(update={"metadata": source_bundle.metadata})


def _to_inline(bundle: MetricBundle) -> MetricInline:
    """Project a runtime bundle onto the wire DTO (JSON round-trip keeps base64 consistent)."""
    return MetricInline.model_validate_json(bundle.model_dump_json())


def _to_runtime_bundle(metric: MetricInline) -> MetricBundle:
    """Reconstruct the runtime bundle from a wire DTO for execution."""
    return MetricBundle.model_validate_json(metric.model_dump_json())


def _resolve_run_dataset(
    dataset: DatasetSpec,
    *,
    ctx: JobContext,
    sdk: NeMoPlatform | None = None,
    async_sdk: AsyncNeMoPlatform | None = None,
) -> InlineDataset | Path:
    """Resolve an evaluator plugin dataset for local SDK execution."""
    if not isinstance(dataset, FilesetRef):
        return dataset

    destination = str(ctx.storage.persistent / "dataset")
    if async_sdk is not None:
        return run_sync(
            lambda: download_dataset(
                sdk=async_sdk,
                dataset=dataset,
                destination=destination,
            )
        )
    if sdk is not None:
        return download_dataset_sync(
            sdk=sdk,
            dataset=dataset,
            destination=destination,
        )
    raise ValueError("FilesetRef datasets require an SDK client for local evaluator job execution.")


class _EvaluateSpecCommon(BaseModel):
    """Fields shared by the submitter input and the canonical (resolved) spec.

    ``EvaluateInputSpec`` and ``EvaluateSpec`` are siblings rather than a
    subtype pair: they differ only in their ``metrics`` field (refs allowed vs.
    fully resolved), and a mutable field can't be narrowed across inheritance
    without violating invariance.
    """

    model_config = ConfigDict(extra="forbid")

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
    def validate_params_for_target(self) -> Self:
        self.params = resolve_params(self.params, self.target)
        return self


class EvaluateInputSpec(_EvaluateSpecCommon):
    """Submitter-facing SDK evaluation input for the evaluator plugin job."""

    metrics: MetricSpec = Field(
        description="Metrics to evaluate, given as inline metrics and/or references to stored metrics.",
    )


class EvaluateSpec(_EvaluateSpecCommon):
    """Canonical SDK evaluation spec with platform model and metric references resolved."""

    metrics: ResolvedMetricSpec = Field(description="Inline metrics with all references resolved.")

    @model_validator(mode="after")
    def reject_unresolved_metric_model_refs(self) -> Self:
        unresolved_refs = _unresolved_model_refs(
            [unbundle_metric(_to_runtime_bundle(metric)) for metric in self.metrics]
        )
        if unresolved_refs:
            raise ValueError(
                "EvaluateSpec metric models must be resolved before compile/run: " + ", ".join(unresolved_refs)
            )
        return self


class EvaluateJob(NemoJob):
    """Run evaluator SDK metrics against inline rows or FilesetRef datasets."""

    name: ClassVar[str] = "evaluate"
    description: ClassVar[str] = "Run evaluator SDK metrics against inline rows or FilesetRef datasets."
    container: ClassVar[str] = "cpu-tasks"
    input_spec_schema: ClassVar[type[BaseModel] | None] = EvaluateInputSpec
    spec_schema: ClassVar[type[BaseModel] | None] = EvaluateSpec
    job_collection_path: ClassVar[str | None] = "/evaluate/jobs"

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
        canonical_spec.params = resolve_params(canonical_spec.params, canonical_spec.target)
        return compile_evaluate_job(canonical_spec, profile=profile)

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
        async_sdk: AsyncNeMoPlatform | NeMoPlatform | None,
        is_local: bool,
    ) -> BaseModel:
        """Resolve submitter-facing model and metric references into the canonical evaluation spec."""
        del is_local
        submit_spec = (
            input_spec.model_copy(deep=True)
            if isinstance(input_spec, EvaluateInputSpec)
            else EvaluateInputSpec.model_validate_json(input_spec.model_dump_json())
        )
        resolved_async_sdk = async_sdk if isinstance(async_sdk, AsyncNeMoPlatform) else None
        resolved_metrics = await resolve_metric_specs(
            submit_spec.metrics,
            workspace=workspace,
            entity_client=entity_client,
            async_sdk=resolved_async_sdk,
        )
        metrics = [unbundle_metric(bundle) for bundle in resolved_metrics]
        params = resolve_params(submit_spec.params, submit_spec.target)
        final_bundles = resolved_metrics
        unresolved_refs = _unresolved_model_refs(metrics)
        if unresolved_refs:
            if async_sdk is None:
                raise ValueError(
                    "ModelRef metrics require `async_sdk` for spec resolution: " + ", ".join(unresolved_refs)
                )
            resolver = PlatformModelResolver(async_sdk)
            await asyncio.gather(
                *(metric.resolve_models(resolver) for metric in metrics if isinstance(metric, MetricWithModels))
            )
            final_bundles = [
                _bundle_resolved_metric(metric, bundle)
                for metric, bundle in zip(metrics, resolved_metrics, strict=True)
            ]
        return EvaluateSpec(
            metrics=[_to_inline(bundle) for bundle in final_bundles],
            dataset=submit_spec.dataset,
            params=params,
            target=submit_spec.target,
            prompt_template=submit_spec.prompt_template,
            field_mapping=submit_spec.field_mapping,
        )

    def run(
        self,
        config: dict,
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
        async_sdk: AsyncNeMoPlatform | None = None,
    ) -> dict:
        """Run the evaluator job locally and persist its result artifact."""
        spec = EvaluateSpec.model_validate(config)
        evaluator = Evaluator()
        params = resolve_params(spec.params, spec.target)
        metrics = [unbundle_metric(_to_runtime_bundle(metric)) for metric in spec.metrics]
        dataset = _resolve_run_dataset(
            spec.dataset,
            ctx=ctx,
            sdk=sdk,
            async_sdk=async_sdk,
        )
        runtime_metrics = metrics if len(metrics) > 1 else metrics[0]
        if isinstance(spec.target, Model):
            if not isinstance(params, RunConfigOnlineModel):
                raise TypeError("model target requires RunConfigOnlineModel")
            result = evaluator.run_sync(
                metrics=runtime_metrics,
                dataset=dataset,
                config=params,
                target=spec.target,
                field_mapping=spec.field_mapping,
                prompt_template=spec.prompt_template,
            )
        elif isinstance(spec.target, Agent):
            if type(params) is not RunConfigOnline:
                raise TypeError("agent target requires RunConfigOnline")
            if spec.prompt_template is None:
                raise ValueError("agent target requires prompt_template")
            result = evaluator.run_sync(
                metrics=runtime_metrics,
                dataset=dataset,
                config=params,
                target=spec.target,
                field_mapping=spec.field_mapping,
                prompt_template=spec.prompt_template,
            )
        else:
            if type(params) is not RunConfig:
                raise TypeError("offline evaluation requires RunConfig")
            result = evaluator.run_sync(
                metrics=runtime_metrics,
                dataset=dataset,
                config=params,
                target=None,
                field_mapping=spec.field_mapping,
                prompt_template=None,
            )
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
