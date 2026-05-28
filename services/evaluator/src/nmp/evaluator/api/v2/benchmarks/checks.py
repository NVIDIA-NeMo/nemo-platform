# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prechecks for benchmark job validation."""

import asyncio
import logging
from collections.abc import Iterable
from typing import get_args

import nmp.evaluator.app.values as app
import nmp.evaluator.entities as entities
from nemo_platform import AsyncNeMoPlatform
from nmp.evaluator.api.v2.benchmarks.schemas.jobs import (
    BenchmarkJob,
    benchmark_job_type,
    is_online_benchmark_job,
)
from nmp.evaluator.api.v2.common.checks import (
    ValidationResult,
    collect_schema_target_errors,
    format_model_reachability_error,
    mapping_hint,
    prompt_hint,
    schema_error_message,
    validation_result_from_exception,
)
from nmp.evaluator.app.dataset_schemas import (
    TemplateSchemaInferenceError,
    group_schema_resolution_targets,
    merge_metric_required_schemas,
    prune_schema_properties,
    resolve_dataset_schema_targets,
    runtime_available_evaluator_fields,
    validate_dataset_schema_requirement,
    validate_prompt_template_against_dataset_schema,
)

# Extract the set of built-in dataset IDs from the Literal type for runtime checking
BUILTIN_DATASET_IDS: set[str] = set(get_args(app.BuiltInDatasetID))

log = logging.getLogger(__name__)


async def job_fileset_exists_check(job: BenchmarkJob, sdk: AsyncNeMoPlatform) -> ValidationResult:
    """Check if the job's fileset dataset exists.

    Args:
        job: The benchmark job input to validate.
        sdk: SDK instance with request-scoped user context. Required and must be obtained
             from Depends(get_sdk_client) in API endpoints to ensure proper user context.

    Returns:
        ValidationResult indicating if the fileset exists.
    """
    # Lazy imports to avoid slow startup (SDK imports kubernetes, etc.)
    from nmp.evaluator.app.datasets.nmp_datasets.fileset import dataset_exists as fileset_exists

    # Check if job has a dataset attribute
    dataset: app.Dataset | None = getattr(job, "dataset", None)
    if dataset is None:
        return ValidationResult(True)

    log.info(f"job_fileset_exists_check: dataset type={type(dataset).__name__}, value={dataset}")

    # Handle FilesetRef that is actually a built-in dataset ID (e.g., "beir/fiqa")
    # This can happen when Pydantic coerces a string to FilesetRef before trying BuiltInDataset
    if isinstance(dataset, app.FilesetRef) and dataset.root in BUILTIN_DATASET_IDS:
        log.info(f"Dataset '{dataset.root}' is a built-in dataset, skipping fileset check")
        return ValidationResult(True)

    try:
        exists = await fileset_exists(sdk, dataset)
        if not exists:
            return ValidationResult(False, ["Dataset does not exist in fileset."])
    except Exception as e:
        return ValidationResult(False, [f"Error checking fileset existence: {e}"])

    return ValidationResult(True)


async def benchmark_fileset_exists_check(
    job: BenchmarkJob,
    benchmark: entities.Benchmark,
    sdk: AsyncNeMoPlatform,
) -> ValidationResult:
    """Check if the fileset dataset exists for benchmark jobs.

    Args:
        job: The benchmark job input to validate.
        benchmark: The benchmark entity to validate against.
        sdk: SDK instance with request-scoped user context. Required and must be obtained
             from Depends(get_sdk_client) in API endpoints to ensure proper user context.

    Returns:
        ValidationResult indicating if the fileset exists.
    """
    # Lazy imports to avoid slow startup (SDK imports kubernetes, etc.)
    from nmp.evaluator.app.datasets.nmp_datasets.fileset import dataset_exists as fileset_exists

    # Determine which dataset to check based on job/benchmark type
    dataset: app.Dataset | None = None

    dataset = benchmark.dataset

    if dataset is None:
        return ValidationResult(True)

    log.info(f"benchmark_fileset_exists_check: dataset type={type(dataset).__name__}, value={dataset}")

    # Handle FilesetRef that is actually a built-in dataset ID (e.g., "beir/fiqa")
    # This can happen when Pydantic coerces a string to FilesetRef before trying BuiltInDataset
    if isinstance(dataset, app.FilesetRef) and dataset.root in BUILTIN_DATASET_IDS:
        log.info(f"Dataset '{dataset.root}' is a built-in dataset, skipping fileset check")
        return ValidationResult(True)

    try:
        exists = await fileset_exists(sdk, dataset)
        if not exists:
            return ValidationResult(False, ["Benchmark dataset does not exist in fileset."])
    except Exception as e:
        return ValidationResult(False, [f"Error checking fileset existence: {e}"])

    return ValidationResult(True)


async def benchmark_model_check(
    job: BenchmarkJob,
    benchmark: entities.Benchmark,
    workspace: str,
    sdk: AsyncNeMoPlatform,
) -> ValidationResult:
    """Check if models in a benchmark job are reachable.

    Args:
        job: The benchmark job input to validate.
        benchmark: The benchmark entity (unused but kept for consistent interface).
        workspace: Workspace for resolving secrets.
        sdk: SDK instance with request-scoped user context. Required and must be obtained
             from Depends(get_sdk_client) in API endpoints to ensure proper user context.

    Returns:
        ValidationResult indicating if all models are reachable.
    """

    models_to_check: list[tuple[str, dict]] = []

    # Check job.model if present (for online benchmark jobs)
    model = getattr(job, "model", None)
    if model is not None:
        model_dict = model.model_dump() if hasattr(model, "model_dump") else model
        if isinstance(model_dict, dict) and "url" in model_dict and "name" in model_dict:
            models_to_check.append(("job.model", model_dict))

    if not models_to_check:
        return ValidationResult(True)

    # Check all models in parallel, resolving secrets before checking reachability
    from nmp.evaluator.app.inference import verify_model_reachable

    results = await asyncio.gather(
        *[verify_model_reachable(model_dict, sdk=sdk, workspace=workspace) for _, model_dict in models_to_check],
        return_exceptions=True,
    )
    errors = []
    for (name, model_dict), result in zip(models_to_check, results, strict=True):
        # Only treat Exceptions as errors; successful responses are dicts
        if isinstance(result, Exception):
            errors.append(format_model_reachability_error(name, model_dict, result))

    if errors:
        return ValidationResult(False, errors)
    return ValidationResult(True)


async def benchmark_creation_schema_check(
    dataset: app.FilesetRef,
    metrics: list[entities.Metric],
    field_mapping: app.FieldMapping | None,
    sdk: AsyncNeMoPlatform,
) -> ValidationResult:
    """Validate benchmark metric requirements and the bound dataset schema."""
    compatibility_result, requested_job_types = _resolve_benchmark_job_types(metrics, job_types=None)
    if not compatibility_result.status:
        return compatibility_result

    try:
        dataset_targets = await resolve_dataset_schema_targets(dataset, sdk)
    except Exception as e:
        return validation_result_from_exception("Invalid dataset schema metadata", e)
    if not dataset_targets:
        return ValidationResult(True)
    dataset_targets = group_schema_resolution_targets(dataset_targets)

    errors = collect_schema_target_errors(
        dataset_targets,
        lambda dataset_schema: _validate_benchmark_dataset_schema_requirements(
            metrics,
            field_mapping,
            dataset_schema,
            job_types=requested_job_types,
        ),
    )
    if errors:
        return ValidationResult(False, errors)
    return ValidationResult(True)


async def benchmark_job_schema_check(
    job: BenchmarkJob,
    benchmark: entities.Benchmark,
    sdk: AsyncNeMoPlatform,
) -> ValidationResult:
    """Validate a custom benchmark's dataset schema for the requested job type."""
    job_type = benchmark_job_type(job)
    if job_type not in {app.SupportedJobTypes.ONLINE, app.SupportedJobTypes.OFFLINE}:
        return ValidationResult(True)

    compatibility_result, requested_job_types = _resolve_benchmark_job_types(benchmark.metrics, job_types=[job_type])
    if not compatibility_result.status:
        return compatibility_result

    try:
        dataset_targets = await resolve_dataset_schema_targets(benchmark.dataset, sdk)
    except Exception as e:
        return validation_result_from_exception("Invalid dataset schema metadata", e)
    if not dataset_targets:
        return ValidationResult(True)
    dataset_targets = group_schema_resolution_targets(dataset_targets)

    schema_validation_errors = collect_schema_target_errors(
        dataset_targets,
        lambda dataset_schema: _validate_benchmark_dataset_schema_requirements(
            benchmark.metrics,
            benchmark.field_mapping,
            dataset_schema,
            job_types=requested_job_types,
        ),
    )
    if schema_validation_errors:
        return ValidationResult(False, schema_validation_errors)

    prompt_validation_errors: list[str] = []
    if is_online_benchmark_job(job):

        def validate_prompt_schema(dataset_schema: dict | None) -> ValidationResult:
            if dataset_schema is None:
                return ValidationResult(True)
            errors = validate_prompt_template_against_dataset_schema(
                dataset_schema,
                job.prompt_template,
                benchmark.field_mapping,
                ignored_roots=runtime_available_evaluator_fields(app.SupportedJobTypes.ONLINE),
                optional_fields=set(job.optional_fields),
            )
            return ValidationResult(not errors, errors)

        try:
            prompt_validation_errors = collect_schema_target_errors(dataset_targets, validate_prompt_schema)
        except TemplateSchemaInferenceError as e:
            return validation_result_from_exception("Unsupported prompt template for schema inference", e)
        except Exception as e:
            return validation_result_from_exception("Invalid dataset schema metadata", e)

    if prompt_validation_errors:
        return ValidationResult(
            False,
            [
                schema_error_message(
                    "Benchmark dataset schema is incompatible with the job prompt template",
                    prompt_validation_errors,
                    hint=prompt_hint(benchmark.field_mapping),
                )
            ],
        )

    return ValidationResult(True)


def _resolve_benchmark_job_types(
    metrics: list[entities.Metric],
    job_types: Iterable[app.SupportedJobTypes] | None,
) -> tuple[ValidationResult, tuple[app.SupportedJobTypes, ...]]:
    supported_job_types = _supported_benchmark_job_types(metrics)
    if not supported_job_types:
        return (
            ValidationResult(
                False,
                ["Benchmark metrics have no compatible job types. The supported_job_types intersection is empty."],
            ),
            (),
        )

    requested_job_types = tuple(job_types) if job_types is not None else _ordered_job_types(supported_job_types)
    unsupported_job_types = [job_type for job_type in requested_job_types if job_type not in supported_job_types]
    if unsupported_job_types:
        labels = ", ".join(job_type.value for job_type in unsupported_job_types)
        return ValidationResult(False, [f"Benchmark does not support {labels} jobs."]), ()
    return ValidationResult(True), requested_job_types


def _validate_benchmark_dataset_schema_requirements(
    metrics: list[entities.Metric],
    field_mapping: app.FieldMapping | None,
    dataset_schema: dict | None,
    job_types: Iterable[app.SupportedJobTypes],
) -> ValidationResult:
    if dataset_schema is None:
        return ValidationResult(True)

    errors: list[str] = []
    for job_type in job_types:
        try:
            merged_required_schema = merge_metric_required_schemas(
                _metric_required_schemas_for_job_type(metrics, job_type)
            )
            required_schema = prune_schema_properties(
                merged_required_schema,
                runtime_available_evaluator_fields(job_type),
            )
            errors.extend(validate_dataset_schema_requirement(dataset_schema, required_schema, field_mapping))
        except Exception as e:
            return validation_result_from_exception("Invalid dataset schema metadata", e)

    if errors:
        return ValidationResult(
            False,
            [
                schema_error_message(
                    "Benchmark dataset schema is incompatible with benchmark metrics",
                    errors,
                    hint=mapping_hint(field_mapping),
                )
            ],
        )
    return ValidationResult(True)


def _metric_required_schemas_for_job_type(
    metrics: Iterable[entities.Metric],
    job_type: app.SupportedJobTypes,
) -> Iterable[tuple[str, dict]]:
    for metric in metrics:
        input_schema = metric.input_schema()
        supported_job_types = getattr(metric, "supported_job_types", [])
        if supported_job_types and job_type not in supported_job_types:
            continue
        metric_name = f"{metric.workspace}/{metric.name}"
        yield metric_name, input_schema.schema_


def _supported_benchmark_job_types(metrics: Iterable[entities.Metric]) -> set[app.SupportedJobTypes]:
    intersections: set[app.SupportedJobTypes] | None = None
    for metric in metrics:
        supported = set(getattr(metric, "supported_job_types", None) or [])
        if intersections is None:
            intersections = supported
        else:
            intersections &= supported
    return intersections or set()


def _ordered_job_types(job_types: set[app.SupportedJobTypes]) -> tuple[app.SupportedJobTypes, ...]:
    ordering = (app.SupportedJobTypes.OFFLINE, app.SupportedJobTypes.ONLINE)
    return tuple(job_type for job_type in ordering if job_type in job_types)
