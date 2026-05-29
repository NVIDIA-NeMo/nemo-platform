# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK-backed evaluator job for the evaluator plugin scaffold."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, ClassVar, Self, TypeAlias, cast

from nemo_evaluator.jobs.utils import resolve_run_dataset, resolve_submit_dataset
from nemo_evaluator.resolvers import PlatformModelResolver
from nemo_evaluator.sdk.types import FilesetRef
from nemo_evaluator_sdk import Evaluator
from nemo_evaluator_sdk.execution._protocols import JobParamsConfigurableMetric
from nemo_evaluator_sdk.execution.config import normalize_params
from nemo_evaluator_sdk.execution.metric_execution import run_sync
from nemo_evaluator_sdk.metrics.protocol import MetricWithModels, MetricWithSecrets
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
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    EnvironmentVariable,
    EnvironmentVariableFromSecret,
    PlatformJobSpec,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.constants import DEFAULT_JOB_STORAGE_PATH, PERSISTENT_JOB_STORAGE_PATH_ENVVAR
from nmp.common.jobs.image import get_qualified_image
from pydantic import BaseModel, ConfigDict, Field, model_validator

TargetSpec = Model | Agent
MetricSpec: TypeAlias = MetricsUnion | Annotated[Sequence[MetricsUnion], Field(min_length=1)]
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


class EvaluateJob(NemoJob):
    """Run one evaluator SDK metric against inline rows."""

    name: ClassVar[str] = "evaluate"
    description: ClassVar[str] = "Run an inline evaluator SDK metric against inline dataset rows."
    container: ClassVar[str] = "cpu-tasks"
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

    @staticmethod
    async def _resolve_metric_models(
        metric: MetricsUnion | Sequence[MetricsUnion],
        resolver: PlatformModelResolver,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel,
    ) -> None:
        """Resolve ModelRef fields on metric configs before local SDK execution."""
        metrics = metric if isinstance(metric, Sequence) else (metric,)
        for item in metrics:
            if isinstance(item, JobParamsConfigurableMetric):
                item.apply_evaluation_job_params(params)
            if isinstance(item, MetricWithModels):
                await item.resolve_models(resolver)

    @staticmethod
    def _unresolved_model_refs(metric: MetricsUnion | Sequence[MetricsUnion]) -> list[str]:
        metrics = metric if isinstance(metric, Sequence) else (metric,)
        refs = [
            model_ref.root
            for item in metrics
            if isinstance(item, MetricWithModels)
            for model_ref in item.model_refs().values()
        ]
        return sorted(refs)

    @staticmethod
    def _secret_envs(spec: EvaluateSpec) -> list[EnvironmentVariable]:
        """Return platform secret environment variables needed at task runtime."""
        secret_envs: list[EnvironmentVariable] = []
        target = spec.target
        if isinstance(target, (Model, Agent)) and target.api_key_secret:
            api_key_env = target.api_key_env
            if api_key_env is None:
                raise ValueError("target.api_key_env must be set when target.api_key_secret is configured")
            secret_envs.append(
                EnvironmentVariable(
                    name=api_key_env,
                    from_secret=EnvironmentVariableFromSecret(name=target.api_key_secret.root),
                )
            )

        metrics = spec.metric if isinstance(spec.metric, Sequence) else (spec.metric,)
        for metric in metrics:
            if isinstance(metric, MetricWithSecrets):
                for secret_env, secret_ref in metric.secrets().items():
                    secret_envs.append(
                        EnvironmentVariable(
                            name=secret_env,
                            from_secret=EnvironmentVariableFromSecret(name=secret_ref.root),
                        )
                    )
        return secret_envs

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
        """Compile an evaluator plugin job into a single platform task step."""
        del entity_client, job_name, options
        canonical_spec = (
            spec.model_copy(deep=True)
            if isinstance(spec, EvaluateSpec)
            else EvaluateSpec.model_validate(spec.model_dump())
        )

        await resolve_submit_dataset(cast(AsyncNeMoPlatform, async_sdk), canonical_spec.dataset)
        params = normalize_params(canonical_spec.params, canonical_spec.target)
        await cls._resolve_metric_models(canonical_spec.metric, PlatformModelResolver(async_sdk), params)
        if isinstance(canonical_spec.target, Model):
            if canonical_spec.prompt_template is None:
                raise ValueError("prompt_template is required when EvaluateSpec.target is a model")
            if not isinstance(params, RunConfigOnlineModel):
                raise TypeError("model target requires RunConfigOnlineModel")
        elif isinstance(canonical_spec.target, Agent):
            if canonical_spec.prompt_template is None:
                raise ValueError("prompt_template is required when EvaluateSpec.target is an agent")
            if not isinstance(params, RunConfigOnline):
                raise TypeError("agent target requires RunConfigOnline")
        else:
            if not isinstance(params, RunConfig):
                raise TypeError("offline evaluation requires RunConfig")
        canonical_spec.params = params
        spec_dict = canonical_spec.model_dump(mode="json", exclude_none=True)

        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="evaluation",
                    executor=CPUExecutionProviderSpec(
                        provider="cpu",
                        profile=profile or "default",
                        container=ContainerSpec(
                            image=get_qualified_image("nmp-cpu-tasks"),
                            entrypoint=["python", "-m"],
                            command=["nemo_evaluator.tasks.evaluate"],
                        ),
                    ),
                    config=spec_dict,
                    environment=[
                        EnvironmentVariable(name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR, value=DEFAULT_JOB_STORAGE_PATH),
                        EnvironmentVariable(name="LOG_FORMAT", value="json"),
                        *cls._secret_envs(canonical_spec),
                    ],
                ),
            ],
        )

    def run(self, config: dict, *, ctx: JobContext, sdk: object | None = None, async_sdk: object | None = None) -> dict:
        """Run the evaluator job locally and persist its result artifact."""
        spec = EvaluateSpec.model_validate(config)
        evaluator = Evaluator()
        platform_sdk = async_sdk or sdk
        params = normalize_params(spec.params, spec.target)
        if platform_sdk is None:
            unresolved_refs = self._unresolved_model_refs(spec.metric)
            if unresolved_refs:
                raise ValueError(
                    "ModelRef metrics require `sdk` or `async_sdk` for local execution: " + ", ".join(unresolved_refs)
                )
        else:
            run_sync(lambda: self._resolve_metric_models(spec.metric, PlatformModelResolver(platform_sdk), params))
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
        if isinstance(spec.metric, Sequence):
            result = evaluator.run_sync(metrics=spec.metric, **common_kwargs)
        else:
            result = evaluator.run_sync(metrics=cast(MetricsUnion, spec.metric), **common_kwargs)
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
