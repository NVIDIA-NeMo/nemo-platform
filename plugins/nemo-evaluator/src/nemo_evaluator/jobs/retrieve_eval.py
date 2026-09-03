# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""BEIR corpus retrieval evaluation job."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Self

from nemo_evaluator.filesets import (
    FilesetRef,
    download_dataset,
    download_dataset_sync,
    load_beir_dataset,
)
from nemo_evaluator.jobs.evaluate import (
    AGGREGATE_SCORES_RESULT_NAME,
    ARTIFACTS_RESULT_NAME,
    DEFAULT_RESULT_NAME,
    RESULT_IGNORE_PATTERNS,
    ROW_SCORES_RESULT_NAME,
    RUN_METADATA_RESULT_NAME,
    EvaluateJob,
)
from nemo_evaluator.jobs.secret_env import build_task_environment
from nemo_evaluator.jobs.utils import run_with_isolated_async_sdk
from nemo_evaluator.resolvers import PlatformModelResolver
from nemo_evaluator_sdk import Evaluator
from nemo_evaluator_sdk.metrics.retrieval import (
    RetrievalMAPMetric,
    RetrievalNDCGMetric,
    RetrievalPrecisionMetric,
    RetrievalRecallMetric,
)
from nemo_evaluator_sdk.values.models import Model, ModelRef
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    PlatformJobSpec,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.image import get_qualified_image
from pydantic import BaseModel, ConfigDict, Field, model_validator

EVAL_RESULTS_FILE_NAME = "eval_results.json"
EVAL_RESULTS_RESULT_NAME = "eval-results"


class RetrieveEvalInputSpec(BaseModel):
    """Submitter-facing BEIR retrieval evaluation spec."""

    model_config = ConfigDict(extra="forbid")

    dataset: FilesetRef = Field(description="Fileset containing a BEIR test split.")
    target: Model | ModelRef = Field(description="Embedding NIM model or platform model reference.")
    baseline: Model | ModelRef | None = Field(
        default=None,
        description="Optional baseline embedding model used for relative nDCG@10 and Recall@10.",
    )
    k: list[int] = Field(default=[1, 5, 10, 100], min_length=1)

    @model_validator(mode="after")
    def validate_k(self) -> Self:
        """Require unique positive cutoffs."""
        if any(cutoff < 1 for cutoff in self.k):
            raise ValueError("retrieval cutoffs must be positive")
        if len(set(self.k)) != len(self.k):
            raise ValueError("retrieval cutoffs must be unique")
        self.k.sort()
        return self


class RetrieveEvalSpec(BaseModel):
    """Canonical BEIR retrieval evaluation spec."""

    model_config = ConfigDict(extra="forbid")

    dataset: FilesetRef
    target: Model
    baseline: Model | None = None
    k: list[int] = Field(default=[1, 5, 10, 100], min_length=1)

    @model_validator(mode="after")
    def validate_k(self) -> Self:
        """Require unique positive cutoffs in canonical task payloads."""
        if any(cutoff < 1 for cutoff in self.k):
            raise ValueError("retrieval cutoffs must be positive")
        if len(set(self.k)) != len(self.k):
            raise ValueError("retrieval cutoffs must be unique")
        self.k.sort()
        return self


class RetrieveEvalJob(NemoJob):
    """Score a BEIR fileset with a deployed embedding NIM."""

    name: ClassVar[str] = "retrieve-eval"
    description: ClassVar[str] = "Evaluate dense retrieval over a BEIR corpus with nDCG and recall."
    container: ClassVar[str] = "cpu-tasks"
    input_spec_schema: ClassVar[type[BaseModel] | None] = RetrieveEvalInputSpec
    spec_schema: ClassVar[type[BaseModel] | None] = RetrieveEvalSpec
    job_collection_path: ClassVar[str | None] = "/retrieve-eval/jobs"

    @classmethod
    async def to_spec(
        cls,
        input_spec: BaseModel,
        workspace: str,
        entity_client: object,
        async_sdk: AsyncNeMoPlatform | NeMoPlatform | None,
        is_local: bool,
    ) -> BaseModel:
        """Resolve a platform model reference before the job is compiled."""
        del workspace, entity_client, is_local
        submit_spec = RetrieveEvalInputSpec.model_validate(input_spec.model_dump())
        target = submit_spec.target
        if isinstance(target, ModelRef):
            if async_sdk is None:
                raise ValueError("a platform SDK client is required to resolve the retrieval target")
            target = await PlatformModelResolver(async_sdk).resolve_model(target)
        baseline = submit_spec.baseline
        if isinstance(baseline, ModelRef):
            if async_sdk is None:
                raise ValueError("a platform SDK client is required to resolve the retrieval baseline")
            baseline = await PlatformModelResolver(async_sdk).resolve_model(baseline)
        return RetrieveEvalSpec(
            dataset=submit_spec.dataset,
            target=target,
            baseline=baseline,
            k=submit_spec.k,
        )

    @classmethod
    async def compile(
        cls,
        workspace: str,
        spec: BaseModel,
        entity_client: object,
        job_name: str | None,
        async_sdk: AsyncNeMoPlatform | None,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        """Compile a CPU task that calls the embedding target through IGW."""
        del workspace, entity_client, job_name, async_sdk, options
        canonical = RetrieveEvalSpec.model_validate(spec.model_dump())
        environment = []
        secret_refs = [
            (model.api_key_env, model.api_key_secret.root)
            for model in (canonical.target, canonical.baseline)
            if model is not None and model.api_key_secret is not None and model.api_key_env
        ]
        if secret_refs:
            environment = build_task_environment(secret_refs)
        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="retrieve-eval",
                    executor=CPUExecutionProviderSpec(
                        profile=profile or "default",
                        provider="cpu",
                        container=ContainerSpec(
                            image=get_qualified_image("nmp-cpu-tasks"),
                            entrypoint=["python", "-m"],
                            command=["nemo_evaluator.tasks.retrieve_eval"],
                        ),
                    ),
                    config=canonical.model_dump(mode="json"),
                    environment=environment,
                )
            ]
        )

    def run(
        self,
        config: dict,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
        async_sdk: AsyncNeMoPlatform | None = None,
    ) -> dict:
        """Download, validate, score, and persist a BEIR retrieval result."""
        spec = RetrieveEvalSpec.model_validate(config)
        if sdk is not None:
            dataset_path = download_dataset_sync(
                sdk=sdk,
                dataset=spec.dataset,
                destination=str(ctx.storage.persistent / "dataset"),
            )
        elif async_sdk is not None:
            dataset_path = run_with_isolated_async_sdk(
                async_sdk,
                lambda isolated_sdk: download_dataset(
                    sdk=isolated_sdk,
                    dataset=spec.dataset,
                    destination=str(ctx.storage.persistent / "dataset"),
                ),
            )
        else:
            raise ValueError("retrieve-eval requires an SDK client to download its FilesetRef")

        dataset = load_beir_dataset(dataset_path)
        metrics = [
            RetrievalNDCGMetric(k=spec.k),
            RetrievalRecallMetric(k=spec.k),
            RetrievalPrecisionMetric(k=spec.k),
            RetrievalMAPMetric(k=spec.k),
        ]
        evaluator = Evaluator()
        result = evaluator.run_sync(retrieval=dataset, target=spec.target, metrics=metrics)
        result_files = EvaluateJob._write_result_files(
            result,
            ctx.storage.persistent,
            run_id=ctx.job_id,
            started_at=datetime.now(UTC),
        )
        artifact = ctx.results.save(DEFAULT_RESULT_NAME, result_files.full_result)
        ctx.results.save(AGGREGATE_SCORES_RESULT_NAME, result_files.aggregate_scores)
        ctx.results.save(ROW_SCORES_RESULT_NAME, result_files.row_scores)
        ctx.results.save(RUN_METADATA_RESULT_NAME, result_files.run_metadata)
        ctx.results.save(
            ARTIFACTS_RESULT_NAME,
            result_files.artifacts_dir,
            ignore_patterns=RESULT_IGNORE_PATTERNS,
        )

        eval_results = {
            score.name.rsplit(".", 1)[-1]: score.mean
            for score in result.aggregate_scores.scores
            if any(f".{metric_name}@" in score.name for metric_name in ("ndcg", "recall", "precision", "map"))
        }
        eval_results_path = Path(ctx.storage.persistent) / EVAL_RESULTS_FILE_NAME
        eval_results_path.write_text(json.dumps(eval_results, indent=2), encoding="utf-8")
        ctx.results.save(EVAL_RESULTS_RESULT_NAME, eval_results_path)
        output: dict[str, object] = {
            "status": "completed",
            "artifact": artifact.model_dump(),
            "eval_results": eval_results,
        }
        if spec.baseline is not None:
            baseline_result = evaluator.run_sync(
                retrieval=dataset,
                target=spec.baseline,
                metrics=metrics,
            )
            baseline_scores = {
                score.name.rsplit(".", 1)[-1]: score.mean
                for score in baseline_result.aggregate_scores.scores
                if ".ndcg@" in score.name or ".recall@" in score.name
            }
            relative = {
                name: _relative_change(eval_results.get(name), baseline_scores.get(name))
                for name in ("ndcg@10", "recall@10")
                if name in eval_results and name in baseline_scores
            }
            output["baseline_eval_results"] = baseline_scores
            output["relative"] = relative
        return output


def _relative_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline in (None, 0):
        return None
    return (current - baseline) / baseline
