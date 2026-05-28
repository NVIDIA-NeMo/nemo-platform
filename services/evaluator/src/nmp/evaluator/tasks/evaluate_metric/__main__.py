# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.
import asyncio
import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from nemo_evaluator_sdk.agent_inference import make_agent_inference_request, new_agent_inference_client
from nemo_evaluator_sdk.dataset_schemas.compatibility import apply_column_mapping_to_row
from nemo_evaluator_sdk.execution.metric_execution import (
    ComputeMetricPipeline,
    run_generated_sample_scoring_pipeline,
)
from nemo_evaluator_sdk.execution.scoring import finalize_evaluation_result
from nemo_evaluator_sdk.execution.values import EvaluationError
from nemo_evaluator_sdk.inference import InferenceFn, make_inference_request, new_inference_client
from nemo_evaluator_sdk.metrics.utils import metric_type_name
from nemo_evaluator_sdk.resilience.errors import get_evaluation_error
from nemo_evaluator_sdk.values import (
    AggregatedMetricResult,
    DatasetRows,
    RowScore,
)
from nemo_platform import AsyncNeMoPlatform
from nmp.common.jobs.constants import (
    DEFAULT_JOB_STORAGE_PATH,
    DEFAULT_NEMO_JOB_STEP_CONFIG_FILE_PATH,
    NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
)
from nmp.common.observability.otel import initialize_logging
from nmp.common.sdk_factory import get_async_platform_sdk
from nmp.evaluator.app import inference_hooks
from nmp.evaluator.app.datasets.loader import DatasetLoadError, load_dataset_from_ref_as_dicts
from nmp.evaluator.app.inference import get_platform_headers
from nmp.evaluator.app.jobs.constants import (
    EVALUATION_RESULTS_AGG_SCORES_FILE_NAME,
    EVALUATION_RESULTS_ROW_SCORES_FILE_NAME,
)
from nmp.evaluator.app.jobs.metric_results import ResultsHandlerConfig, handle_results_async
from nmp.evaluator.app.jobs.progress_tracking import ProgressTracking
from nmp.evaluator.app.metrics.metric import new_metric
from nmp.evaluator.app.tasks.termination import register_task_signal_handlers
from nmp.evaluator.app.values import (
    FilesetRef,
    MetricJob,
    MetricJobAdapter,
    MetricOnlineAgentJob,
    MetricOnlineJob,
)

log = logging.getLogger(__name__)


def _apply_optional_fields_to_row(row: dict, optional_fields: Sequence[str] | None) -> dict:
    normalized = dict(row)
    for field in optional_fields or ():
        normalized.setdefault(field, "")
    return normalized


def _json_default(obj):
    """Default serializer for json.dumps to handle non-serializable objects.

    Handles LangChain messages, Pydantic models, and other objects with common serialization methods.
    """
    # Try common serialization methods in order of preference
    if hasattr(obj, "dict"):  # LangChain messages, Pydantic v1
        return obj.dict()
    if hasattr(obj, "model_dump"):  # Pydantic v2
        return obj.model_dump()
    if hasattr(obj, "to_dict"):  # Other objects
        return obj.to_dict()
    # Fallback to string representation
    return str(obj)


def job_artifacts_dump(
    job: MetricJob, evaluation_result: AggregatedMetricResult, logs: list[RowScore], results_dir: str
):
    """
    Write job artifacts to file

    * job.json: job entity
    * results.jsonl: raw evaluation for each row
    * evaluation_results.json: aggregated evaluation for the job
    """
    os.makedirs(results_dir, exist_ok=True)

    with open(f"{results_dir}/job.json", "w") as f:
        f.write(job.model_dump_json(indent=2, exclude_none=True))
    with open(f"{results_dir}/{EVALUATION_RESULTS_ROW_SCORES_FILE_NAME}", "w") as f:
        for log_entry in logs:
            f.write(json.dumps(log_entry.model_dump(mode="json"), default=_json_default) + "\n")
    with open(os.path.join(results_dir, EVALUATION_RESULTS_AGG_SCORES_FILE_NAME), "w") as f:
        f.write(evaluation_result.model_dump_json(indent=2, exclude_none=True))


def no_aggregated_metric_scores(evaluation_result: AggregatedMetricResult) -> bool:
    """Check if aggregated result has no valid metric scores.

    Returns True if all scores have count=0 (all values were NaN).
    """
    if not evaluation_result.scores:
        return True

    for score in evaluation_result.scores:
        if score.count > 0:
            return False

    return True


def metric_evaluation_entrypoint() -> list[str]:
    """
    Entrypoint for custom eval job.
    """
    return ["python", "-m", "nmp.evaluator.tasks.evaluate_metric"]


def metric_evaluation_entrypoint_args(
    progress_tracking_url: str | None = None,
    progress_tracking_interval: int | None = None,
) -> list[str]:
    """
    Command args to run custom job.
    """
    command: list[str] = []
    if progress_tracking_url:
        command.extend(["--progress-tracking-url", progress_tracking_url])
    if progress_tracking_interval:
        command.extend(["--progress-tracking-interval", str(progress_tracking_interval)])
    return command


def _default_results_dir() -> str:
    return str(Path(os.environ.get(PERSISTENT_JOB_STORAGE_PATH_ENVVAR, DEFAULT_JOB_STORAGE_PATH)) / "results")


def _default_dataset_dir() -> str:
    return str(Path(os.environ.get(PERSISTENT_JOB_STORAGE_PATH_ENVVAR, DEFAULT_JOB_STORAGE_PATH)) / "datasets")


def _default_config_file() -> str:
    return os.environ.get(NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, DEFAULT_NEMO_JOB_STEP_CONFIG_FILE_PATH)


def _load_dataset_items(job: MetricJob, dataset_dir: str | None = None) -> list[dict[str, Any]]:
    """Load dataset items from inline rows or downloaded fileset.

    For FilesetRef datasets, the data should have been downloaded to the
    dataset_dir by a prior dataset-download step. The FilesetRef can include
    a fragment to specify which files to load:
        - workspace/fileset: Load all parsable files
        - workspace/fileset#file.json: Load a specific file
        - workspace/fileset#*.jsonl: Load files matching a glob pattern

    Args:
        job: The metric job containing the dataset specification.
        dataset_dir: Directory containing downloaded dataset files. Defaults to
            the job runtime storage dataset directory if not provided.

    Returns:
        List of data rows for evaluation.

    Raises:
        ValueError: If no data rows are found or dataset cannot be loaded.
    """
    dataset = getattr(job, "dataset", None)
    metric = getattr(job, "metric", None)
    optional_fields = getattr(metric, "optional_fields", [])
    field_mapping = getattr(job, "field_mapping", None)

    # Inline dataset - use rows directly
    if isinstance(dataset, DatasetRows):
        if not dataset.rows:
            raise ValueError("DatasetRows has no rows")
        return [
            _apply_optional_fields_to_row(apply_column_mapping_to_row(row, field_mapping), optional_fields)
            for row in dataset.rows
        ]

    # FilesetRef - load from downloaded files using the new loader
    # The dataset-download step places files at {dataset_dir}/{workspace}/{fileset-name}/
    if isinstance(dataset, FilesetRef):
        effective_dir = dataset_dir or _default_dataset_dir()
        dataset_ref = dataset.root

        try:
            items = load_dataset_from_ref_as_dicts(dataset_ref, base_dir=effective_dir)
        except DatasetLoadError as e:
            raise ValueError(
                f"Failed to load dataset '{dataset_ref}': {e}. "
                f"The dataset should have been downloaded by the dataset-download step."
            ) from e

        if not items:
            raise ValueError(f"Dataset '{dataset_ref}' is empty")

        log.info(f"Loaded {len(items)} items from dataset '{dataset_ref}'")
        return [
            _apply_optional_fields_to_row(apply_column_mapping_to_row(item, field_mapping), optional_fields)
            for item in items
        ]

    raise ValueError(f"Unsupported dataset type: {type(dataset).__name__}")


async def evaluate_metric(
    job: MetricJob,
    results_dir: str,
    progress_tracking: ProgressTracking | None = None,
    *,
    dataset_dir: str | None = None,
    inference_fn: InferenceFn | None = None,
) -> AggregatedMetricResult:
    """
    Entrypoint to run offline metric evaluation with Jobs MS.

    Args:
        job: The metric job configuration.
        results_dir: Directory to write evaluation results.
        progress_tracking: Optional progress tracking for job updates.
        dataset_dir: Directory containing downloaded dataset files (for FilesetRef datasets).
            Defaults to the job runtime storage dataset directory if not provided.
        inference_fn: Function to make inference requests. Defaults to
            make_inference_request if not provided.
    """
    judge_inference_fn: InferenceFn = inference_fn or make_inference_request
    log.info(
        "Starting metric evaluation",
        extra={"metric_type": str(job.metric.type)},
    )

    # Load dataset items - either from inline rows or from downloaded file
    items = _load_dataset_items(job, dataset_dir=dataset_dir)

    log.debug("Job configuration", extra={"results_dir": results_dir, "total_rows": len(items)})

    if job.params.limit_samples:
        log.debug("Limiting samples", extra={"limit": job.params.limit_samples})
        items = items[: job.params.limit_samples]

    log.debug("Creating metric instance", extra={"metric_type": str(job.metric.type)})
    metric = await new_metric(job.metric, job.__job_type__, inference_fn=judge_inference_fn, run_preflight=True)

    # Log evaluation mode; per-branch pipeline construction happens below.
    model_format = None
    default_headers = None
    if isinstance(job, MetricOnlineAgentJob):
        log.debug(
            "Online evaluation mode (agent)",
            extra={
                "agent_name": job.agent.name,
                "agent_endpoint": job.agent.url,
                "agent_format": job.agent.format,
            },
        )
        default_headers = get_platform_headers(job.agent.url)
    elif isinstance(job, MetricOnlineJob):
        model_format = job.model.format
        default_headers = get_platform_headers(job.model.url)
        log.debug(
            "Online evaluation mode",
            extra={
                "model_name": job.model.name,
                "model_endpoint": job.model.url,
                "model_format": job.model.format,
            },
        )
    else:
        log.debug("Offline evaluation mode")

    log.info("Evaluating samples", extra={"sample_count": len(items), "parallelism": job.params.parallelism})

    preprocess_hooks, postprocess_hooks = inference_hooks.new_hooks(
        job.params,
        model_format=model_format,
    )

    if progress_tracking:
        progress_tracking.total_samples = len(items)
        postprocess_hooks.append(inference_hooks.ProgressTrackingHook(progress_tracking))
        log.debug(
            "Progress tracking configured",
            extra={"interval": progress_tracking.interval, "total_samples": progress_tracking.total_samples},
        )

    metric_key = metric_type_name(metric)

    # Overloaded __init__ enforces Agent↔AgentInferenceFn / Model↔InferenceFn at
    # type-check time, so branch on target before constructing the pipeline.
    if isinstance(job, MetricOnlineAgentJob):
        pipeline = ComputeMetricPipeline(
            rows=items,
            parallelism=job.params.parallelism,
            metric=metric,
            target=job.agent,
            params=job.params,
            prompt_template=job.prompt_template,
            metric_key=metric_key,
            inference_fn=make_agent_inference_request,
            client=new_agent_inference_client(),
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
            default_headers=default_headers,
        )
    elif isinstance(job, MetricOnlineJob):
        pipeline = ComputeMetricPipeline(
            rows=items,
            parallelism=job.params.parallelism,
            metric=metric,
            target=job.model,
            params=job.params,
            prompt_template=job.prompt_template,
            metric_key=metric_key,
            inference_fn=judge_inference_fn,
            client=new_inference_client(job.model),
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
            default_headers=default_headers,
        )
    else:
        pipeline = ComputeMetricPipeline(
            rows=items,
            parallelism=job.params.parallelism,
            metric=metric,
            target=None,
            metric_key=metric_key,
            params=job.params,
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
        )

    try:
        eval_result = await run_generated_sample_scoring_pipeline(pipeline)
    except Exception as e:
        evaluation_error = get_evaluation_error(e)
        if isinstance(evaluation_error, EvaluationError):
            log.exception(
                "Metric evaluation failed",
                extra={
                    "phase": evaluation_error.phase.value,
                    "metric_key": evaluation_error.metric_key,
                    "row_index": evaluation_error.index,
                    "error": evaluation_error.message,
                },
            )
            if evaluation_error.__cause__ is not None:
                raise evaluation_error from evaluation_error.__cause__
        raise evaluation_error from e

    log.debug("Aggregating metric results")
    evaluation_result = await finalize_evaluation_result(metric, eval_result)
    aggregated_result = evaluation_result.aggregate_scores
    log.debug(
        "Aggregation complete",
        extra={
            "input_count": sum(1 for _, result, _ in eval_result if result is not None),
            "score_count": len(aggregated_result.scores),
        },
    )

    log.debug("Writing job artifacts to disk")
    job_artifacts_dump(job, aggregated_result, evaluation_result.row_scores, results_dir)

    log.info(
        "Evaluation completed",
        extra={
            "scores": {s.name: (round(s.mean, 4) if s.mean is not None else None) for s in aggregated_result.scores}
        },
    )

    return aggregated_result


async def main(
    args: Sequence[str] | None = None,
    *,
    sdk: AsyncNeMoPlatform | None = None,
) -> int:
    """Main entry point for the evaluate_metric task.

    Args:
        args: Optional list of CLI arguments (for testing). If None, uses sys.argv.
        sdk: Optional SDK instance for dependency injection (for testing).
            If None, uses get_async_platform_sdk().

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    import argparse

    # Configure logging using platform's standard setup for consistent formatting
    initialize_logging()

    parser = argparse.ArgumentParser(description="Watch benchmark container")
    parser.add_argument(
        "--progress-tracking-url",
        type=str,
        default=os.getenv("EVALUATIONS_CALLBACK_URL"),
        help="Optional callback URL to update progress tracking details.",
    )
    parser.add_argument(
        "--progress-tracking-interval",
        type=str,
        default=50,
        help="Interval to update progress tracking details.",
    )
    parser.add_argument(
        "--progress-tracking-interval-seconds",
        type=str,
        default=60,
        help="Time interval (seconds) to update progress tracking details.",
    )
    parser.add_argument(
        "--skip-upload-results",
        type=bool,
        default=False,
        help="Skip uploading results to Jobs MS",
    )
    parsed_args = parser.parse_args(args)
    results_dir = _default_results_dir()
    config_file = _default_config_file()

    if not parsed_args.skip_upload_results:
        results_handler_config = cast(Any, ResultsHandlerConfig)()
    else:
        results_handler_config = ResultsHandlerConfig(NEMO_JOB_ID="", NEMO_JOB_WORKSPACE="")

    with open(config_file, "r") as f:
        job_config = json.load(f)

    job = MetricJobAdapter.validate_python(job_config)

    progress_tracking = None
    try:
        if parsed_args.progress_tracking_url:
            progress_tracking = ProgressTracking(
                parsed_args.progress_tracking_url,
                parsed_args.progress_tracking_interval,
                parsed_args.progress_tracking_interval_seconds,
            )
        else:
            log.warning("Progress tracking is not configured.")

        evaluation_result = await evaluate_metric(job, results_dir, progress_tracking)

        if not parsed_args.skip_upload_results:
            effective_sdk = sdk or get_async_platform_sdk(as_service="evaluator", internal=True)
            await handle_results_async(job, results_handler_config, results_dir, sdk=effective_sdk)

        if no_aggregated_metric_scores(evaluation_result):
            # This edge case happens when inference fails and no outputs can be
            # evaluated to generate metrics.
            raise ValueError(
                f"Job {results_handler_config.NEMO_JOB_ID} completed but no evaluation results detected. Job marked as failed: {evaluation_result}"
            )

        if progress_tracking:
            # Update job progress to 100% when contains results
            progress_tracking.update_progress(100)

        return 0
    finally:
        if progress_tracking:
            progress_tracking.stop()


def run(
    args: Sequence[str] | None = None,
    *,
    sdk: AsyncNeMoPlatform | None = None,
) -> int:
    """Synchronous wrapper for main() - for task_harness compatibility.

    Args:
        args: Optional list of CLI arguments (for testing). If None, uses sys.argv.
        sdk: Optional SDK instance for dependency injection (for testing).
            If None, uses get_async_platform_sdk().

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    register_task_signal_handlers()
    try:
        return asyncio.run(main(args, sdk=sdk))
    except KeyboardInterrupt:
        log.info("Received termination signal. Exiting task gracefully.")
        return 0
    except Exception:
        log.exception("Error in evaluate_metric task")
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
