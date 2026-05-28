# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import logging

import nmp.evaluator.app.values as app
import nmp.evaluator.entities as entities
from nemo_evaluator_sdk.values import AggregatedMetricResult
from nemo_platform import AsyncNeMoPlatform
from nmp.common.entities import EntityClient
from nmp.common.jobs.result_manager import result_manager_factory
from nmp.evaluator.app.jobs.constants import (
    JOB_RESULTS_AGGREGATE_SCORES,
    JOB_RESULTS_ROW_SCORES,
    JOBS_RESULTS_ARTIFACTS,
)
from nmp.evaluator.app.jobs.result_parsers.base import ResultsParser
from nmp.evaluator.app.jobs.result_parsers.custom import CustomResultsParser
from pydantic import Field
from pydantic_settings import BaseSettings

log = logging.getLogger(__name__)

ignore_patterns: list[str] = []


class ResultsHandlerConfig(BaseSettings):
    # Jobs MS environment variable
    NEMO_JOB_ID: str = Field(description="Jobs MS job ID")
    NEMO_JOB_WORKSPACE: str = Field(description="Jobs MS job workspace")


def handle_results(
    job: app.MetricJob | app.BenchmarkJob,
    config: ResultsHandlerConfig,
    local_results_dir_path: str,
    sdk: AsyncNeMoPlatform,
):
    """
    Handle results for an evaluation. Runs async operations via asyncio.run().

    Args:
        config: Configuration containing job ID and workspace.
        local_results_dir_path: Path to directory containing evaluation results.
        sdk: Async SDK instance for API operations. Useful for testing.

    Steps:
    1. Select the custom evaluator results parser.
    2. Normalize aggregate/row outputs into evaluator schema when needed.
    3. Upload artifacts, aggregate-scores, and optional row-scores to Jobs API.
    """
    asyncio.run(handle_results_async(job, config, local_results_dir_path, sdk))


async def handle_results_async(
    job: app.MetricJob | app.BenchmarkJob,
    config: ResultsHandlerConfig,
    local_results_dir_path: str,
    sdk: AsyncNeMoPlatform,
):
    """Async implementation of handle_results with parallel uploads.

    Args:
        config: Configuration containing job ID and workspace.
        local_results_dir_path: Path to directory containing evaluation results.
        sdk: Async SDK instance for API operations. If provided, used for both
            files and jobs operations. Useful for testing with in-memory services.
    """
    manager = result_manager_factory(
        job_name=config.NEMO_JOB_ID,
        workspace=config.NEMO_JOB_WORKSPACE,
        is_async=True,
        files_sdk=sdk,
        jobs_sdk=sdk,
    )

    parser = _get_results_parser()
    prepared_results = parser.prepare_results(local_results_dir_path)

    # Build list of tasks to run in parallel
    tasks = [
        manager.create_result(
            JOBS_RESULTS_ARTIFACTS,
            artifact_local_path=local_results_dir_path,
            ignore_patterns=ignore_patterns,
        ),
        manager.create_result(JOB_RESULTS_AGGREGATE_SCORES, artifact_local_path=prepared_results.aggregate_scores_path),
        register_result_entity(prepared_results.aggregate_scores_path, job, config, sdk),
    ]

    if prepared_results.row_scores_path is not None:
        tasks.append(
            manager.create_result(JOB_RESULTS_ROW_SCORES, artifact_local_path=prepared_results.row_scores_path)
        )

    await asyncio.gather(*tasks)


def _get_results_parser() -> ResultsParser:
    return CustomResultsParser()


async def register_result_entity(
    aggregate_scores_path: str,
    job: app.MetricJob | app.BenchmarkJob,
    config: ResultsHandlerConfig,
    sdk: AsyncNeMoPlatform,
) -> entities.BenchmarkJobResult | entities.MetricJobResult:
    log.info("Registering result entity", extra={"aggregate_scores_path": aggregate_scores_path})

    if isinstance(job, app.MetricOfflineJob | app.MetricOnlineJob | app.MetricOnlineAgentJob):
        result_entity = load_metric_result_entity(aggregate_scores_path, job, config)
    elif isinstance(job, app.BenchmarkOfflineJob | app.BenchmarkOnlineJob | app.BenchmarkOnlineAgentJob):
        result_entity = load_benchmark_result_entity(aggregate_scores_path, job, config)
    else:
        raise ValueError(f"unsupported job {type(job)}")

    entity_client = EntityClient(sdk.entities)
    return await entity_client.create(result_entity)


def load_metric_result_entity(
    aggregate_scores_path: str, job: app.MetricJob, config: ResultsHandlerConfig
) -> entities.MetricJobResult:
    with open(aggregate_scores_path, "r") as f:
        scores = json.load(f)

    return entities.MetricJobResult(
        name=config.NEMO_JOB_ID,
        workspace=config.NEMO_JOB_WORKSPACE,
        metric=job.metric_ref,
        dataset=job.dataset_ref,
        model=getattr(job, "model_ref", None),
        labels=job.metric.labels,
        scores=AggregatedMetricResult.model_validate(scores).scores,
    )


def load_benchmark_result_entity(
    aggregate_scores_path: str, job: app.BenchmarkJob, config: ResultsHandlerConfig
) -> entities.BenchmarkJobResult:
    with open(aggregate_scores_path, "r") as f:
        scores = json.load(f)

    metric_refs = [metric.metric_ref for metric in job.benchmark.metrics]
    dataset_ref = job.benchmark.dataset
    benchmark_ref = app.BenchmarkRef(root=job.benchmark.name)

    return entities.BenchmarkJobResult(
        name=config.NEMO_JOB_ID,
        workspace=config.NEMO_JOB_WORKSPACE,
        benchmark=benchmark_ref,
        metrics=metric_refs,
        dataset=dataset_ref,
        model=getattr(job, "model_ref", None),
        labels=job.benchmark.labels,
        results=app.BenchmarkEvaluationResult.model_validate(scores).results,
    )
