# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Precheck Protocol and utilities for validation checks.

This module defines the Protocol that all prechecks must implement
and the ValidationResult class for check responses.
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Iterable
from typing import Protocol, runtime_checkable

from nemo_evaluator_sdk.inference import ClientInferenceError
from nemo_evaluator_sdk.values.dataset_schemas import FieldMapping

log = logging.getLogger(__name__)
_MISSING_REQUIRED_FIELD_RE = re.compile(r"dataset schema missing required field '([^']+)'")
_MISSING_FIELD_DEFINITION_RE = re.compile(r"dataset schema missing field definition '([^']+)'")


class ValidationResult:
    """Result of a validation check.

    Provides structure to responses from validation checks.
    """

    def __init__(self, status: bool = True, errors: list[str] | None = None):
        self.status = status
        self.errors = errors or []

    def update(self, other_response: "ValidationResult"):
        """Update the current status and error based on passed instance of ValidationResult."""
        self.status = self.status and other_response.status
        self.errors.extend(other_response.errors)

    def __str__(self):
        if self.status:
            return "Valid payload."
        else:
            if isinstance(self.errors, str):
                return self.errors
            joined_errors = " ".join(self.errors)
            return f"Invalid payload. Errors: {joined_errors}."


@runtime_checkable
class Check(Protocol):
    """Protocol for validation checks.

    Prechecks validate job or entity configuration before execution.
    They can be implemented as functions or callable classes.

    Example:
        async def check_fileset_exists(job: MetricJob) -> ValidationResult:
            # ... validation logic
            return ValidationResult(True)
    """

    async def __call__(self, *args, **kwargs) -> Awaitable[ValidationResult]:
        """Execute the precheck validation.

        Returns:
            ValidationResult indicating success or failure with error details.
        """
        ...


# Type alias for check functions
CheckFn = Callable[..., Awaitable[ValidationResult]]


class SchemaValidationTarget(Protocol):
    schema: dict | None

    def path_context(self) -> str | None: ...


class CompositeCheck:
    """Run multiple validation checks in parallel and aggregate results.

    Example:
        result = await CompositeCheck(
            job_fileset_exists_check(job),
            job_model_check(job, workspace),
        )()
    """

    def __init__(self, *checks: Awaitable[ValidationResult]):
        """Initialize with check coroutines to run.

        Args:
            *checks: Coroutines that return ValidationResult.
        """
        self.checks = checks

    async def __call__(self) -> ValidationResult:
        """Run all checks in parallel and aggregate results.

        Returns:
            ValidationResult with combined status and errors from all checks.
        """
        if not self.checks:
            return ValidationResult(True)

        results = await asyncio.gather(*self.checks, return_exceptions=True)
        errors = []

        for result in results:
            if isinstance(result, Exception):
                errors.append(f"Check failed with exception: {result}")
            elif isinstance(result, ValidationResult) and not result.status:
                errors.extend(result.errors)

        if errors:
            return ValidationResult(False, errors)
        return ValidationResult(True)


def unique_preserve_order(items: list[str]) -> list[str]:
    """Return unique strings while preserving first-seen order."""
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique_items.append(item)
    return unique_items


def collect_schema_target_errors(
    dataset_targets: Iterable[SchemaValidationTarget],
    validate_schema: Callable[[dict | None], ValidationResult],
) -> list[str]:
    """Run schema validation across resolved targets and attach path context."""
    errors: list[str] = []
    for dataset_target in dataset_targets:
        result = validate_schema(dataset_target.schema)
        if result.status:
            continue
        path_context = dataset_target.path_context()
        if path_context:
            errors.extend(f"[{path_context}] {error}" for error in result.errors)
        else:
            errors.extend(result.errors)
    return errors


def compress_schema_errors(errors: list[str]) -> list[str]:
    """Deduplicate noisy schema errors while preserving first-seen order."""
    # TODO: Replace this regex-based dedupe once schema compatibility checks return
    # structured issue objects instead of flattened strings. Today the SDK/precheck
    # layers erase error codes/paths before we reach the API formatter.
    missing_required_fields = {
        match.group(1) for error in errors if (match := _MISSING_REQUIRED_FIELD_RE.fullmatch(error)) is not None
    }
    compressed: list[str] = []
    for error in unique_preserve_order(errors):
        missing_definition_match = _MISSING_FIELD_DEFINITION_RE.fullmatch(error)
        if missing_definition_match and missing_definition_match.group(1) in missing_required_fields:
            continue
        compressed.append(error)
    return compressed


def mapping_hint(field_mapping: FieldMapping | None) -> str:
    """Return an actionable hint for field_mapping-related schema validation failures."""
    mapping = field_mapping.mapping() if field_mapping is not None else {}
    if mapping:
        return "Hint: Check field_mapping values against your dataset schema"
    return "Hint: If your dataset uses different field names, provide field_mapping to map canonical evaluator fields to dataset fields"


def prompt_hint(field_mapping: FieldMapping | None) -> str:
    """Return an actionable hint for prompt-template schema validation failures."""
    mapping = field_mapping.mapping() if field_mapping is not None else {}
    if mapping:
        return "Hint: Update the prompt template variables or correct field_mapping to reference fields present in the dataset schema"
    return "Hint: Update the prompt template variables to match your dataset schema, or provide field_mapping if the dataset uses different field names"


def schema_error_message(prefix: str, errors: list[str], *, hint: str | None = None) -> str:
    """Format compressed schema-validation errors with an optional hint."""
    compressed = compress_schema_errors(errors)
    message = f"{prefix}: " + "; ".join(compressed)
    if hint:
        message = f"{message}. {hint}"
    return message


def validation_result_from_exception(prefix: str, error: Exception) -> ValidationResult:
    """Convert an exception into a failed ValidationResult with a contextual prefix."""
    return ValidationResult(False, [f"{prefix}: {error}"])


# User-facing copy for model reachability failures. Edit these to update wording.
# Templates expect `label` and `model_name` (and `error` for the unreachable variant).
# Strings do NOT end with a period: ValidationResult.__str__ appends one when joining.
MODEL_NO_DEPLOYMENT_MESSAGE = (
    "{label} '{model_name}' has no active inference deployment; deploy the model before running evaluation"
)
MODEL_UNREACHABLE_MESSAGE = "{label} '{model_name}' is not reachable: {error}"

# Map internal job-spec field paths to user-facing labels for error messages.
_MODEL_FIELD_LABELS: dict[str, str] = {
    "job.model": "Evaluation Model",
    "job.metric.model": "Judge Model",
    "metric_params.judge.model": "Judge Model",
}


def format_model_reachability_error(field_path: str, model_dict: dict, error: BaseException) -> str:
    """Build a user-facing error message for a failed model reachability check.

    Distinguishes the common "no active inference deployment" case (HTTP 404 from the
    inference gateway) from other transport / inference failures, and substitutes a
    user-facing label for the internal job-spec field path.

    Args:
        field_path: Internal job-spec path (e.g. "job.model", "metric_params.judge.model").
        model_dict: Dict-form model spec with at least a "name" key.
        error: Exception raised by the reachability check.
    """
    label = _MODEL_FIELD_LABELS.get(field_path, field_path)
    model_name = model_dict.get("name") or "<unnamed>"
    # Only treat 404s coming from the inference call itself as "no active deployment".
    # Other 404s in the reachability path (e.g. nemo_platform.NotFoundError raised by
    # sdk.secrets.access() when an api_key_secret is missing) must fall through to the
    # generic unreachable message so the real cause isn't masked.
    if isinstance(error, ClientInferenceError) and error.status_code == 404:
        return MODEL_NO_DEPLOYMENT_MESSAGE.format(label=label, model_name=model_name)
    return MODEL_UNREACHABLE_MESSAGE.format(label=label, model_name=model_name, error=error)
