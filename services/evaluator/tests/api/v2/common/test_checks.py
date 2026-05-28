# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for common validation-check helpers."""

from nemo_evaluator_sdk.inference import ClientInferenceError
from nmp.evaluator.api.v2.common.checks import (
    MODEL_NO_DEPLOYMENT_MESSAGE,
    MODEL_UNREACHABLE_MESSAGE,
    ValidationResult,
    compress_schema_errors,
    format_model_reachability_error,
)


def test_compress_schema_errors_deduplicates_and_preserves_order() -> None:
    errors = [
        "alpha",
        "beta",
        "alpha",
        "gamma",
        "beta",
    ]

    assert compress_schema_errors(errors) == ["alpha", "beta", "gamma"]


def test_compress_schema_errors_drops_missing_definition_when_required_exists() -> None:
    errors = [
        "dataset schema missing field definition 'reference'",
        "dataset schema missing required field 'reference'",
        "dataset schema missing field definition 'context'",
        "dataset schema missing required field 'output'",
    ]

    assert compress_schema_errors(errors) == [
        "dataset schema missing required field 'reference'",
        "dataset schema missing field definition 'context'",
        "dataset schema missing required field 'output'",
    ]


def test_compress_schema_errors_keeps_non_matching_messages() -> None:
    errors = [
        "dataset schema incompatible type at 'input'",
        "dataset schema missing field definition 'input'",
        "custom parser error",
    ]

    assert compress_schema_errors(errors) == [
        "dataset schema incompatible type at 'input'",
        "dataset schema missing field definition 'input'",
        "custom parser error",
    ]


class _FakeClientInferenceError(ClientInferenceError):
    """Stand-in ClientInferenceError that skips its openai-coupled __init__."""

    def __init__(self, status_code: int, message: str = "boom"):
        Exception.__init__(self, message)
        self.status_code = status_code


class _FakeStatusError(Exception):
    """Non-ClientInferenceError exception that still exposes a status_code attribute.

    Models exceptions like nemo_platform.NotFoundError raised by sdk.secrets.access()
    when an api_key_secret is missing during model reachability checks.
    """

    def __init__(self, status_code: int, message: str = "boom"):
        super().__init__(message)
        self.status_code = status_code


def test_format_model_reachability_error_404_evaluation_model() -> None:
    error = _FakeClientInferenceError(status_code=404)
    message = format_model_reachability_error(
        "job.model", {"name": "qwen2-5-1-5b-instruct", "url": "http://gateway/v1"}, error
    )
    assert message == MODEL_NO_DEPLOYMENT_MESSAGE.format(label="Evaluation Model", model_name="qwen2-5-1-5b-instruct")


def test_format_model_reachability_error_404_judge_model_via_metric_params() -> None:
    error = _FakeClientInferenceError(status_code=404)
    message = format_model_reachability_error(
        "metric_params.judge.model", {"name": "judge-7b", "url": "http://gateway/v1"}, error
    )
    assert message == MODEL_NO_DEPLOYMENT_MESSAGE.format(label="Judge Model", model_name="judge-7b")


def test_format_model_reachability_error_404_judge_model_via_inline_metric() -> None:
    error = _FakeClientInferenceError(status_code=404)
    message = format_model_reachability_error(
        "job.metric.model", {"name": "judge-7b", "url": "http://gateway/v1"}, error
    )
    assert message == MODEL_NO_DEPLOYMENT_MESSAGE.format(label="Judge Model", model_name="judge-7b")


def test_format_model_reachability_error_non_inference_404_falls_back_to_generic_message() -> None:
    """Regression: 404s outside the inference call (e.g. nemo_platform.NotFoundError from
    sdk.secrets.access when api_key_secret is missing) must NOT be reported as a missing
    inference deployment — that would mask the real cause.
    """
    error = _FakeStatusError(status_code=404, message="Secret not found: my-api-key")
    message = format_model_reachability_error(
        "job.model", {"name": "qwen2-5-1-5b-instruct", "url": "http://gateway/v1"}, error
    )
    assert message == MODEL_UNREACHABLE_MESSAGE.format(
        label="Evaluation Model", model_name="qwen2-5-1-5b-instruct", error=error
    )


def test_format_model_reachability_error_non_404_falls_back_to_generic_message() -> None:
    error = _FakeClientInferenceError(status_code=500, message="server exploded")
    message = format_model_reachability_error(
        "job.model", {"name": "qwen2-5-1-5b-instruct", "url": "http://gateway/v1"}, error
    )
    assert message == MODEL_UNREACHABLE_MESSAGE.format(
        label="Evaluation Model", model_name="qwen2-5-1-5b-instruct", error=error
    )


def test_format_model_reachability_error_no_status_code_attr_falls_back() -> None:
    error = RuntimeError("Error connecting to inference server")
    message = format_model_reachability_error(
        "job.model", {"name": "qwen2-5-1-5b-instruct", "url": "http://gateway/v1"}, error
    )
    assert message == MODEL_UNREACHABLE_MESSAGE.format(
        label="Evaluation Model", model_name="qwen2-5-1-5b-instruct", error=error
    )


def test_format_model_reachability_error_unknown_field_path_uses_path_as_label() -> None:
    error = _FakeClientInferenceError(status_code=404)
    message = format_model_reachability_error("custom.path", {"name": "foo"}, error)
    assert message == MODEL_NO_DEPLOYMENT_MESSAGE.format(label="custom.path", model_name="foo")


def test_format_model_reachability_error_missing_model_name_uses_placeholder() -> None:
    error = _FakeClientInferenceError(status_code=404)
    message = format_model_reachability_error("job.model", {"url": "http://gateway/v1"}, error)
    assert message == MODEL_NO_DEPLOYMENT_MESSAGE.format(label="Evaluation Model", model_name="<unnamed>")


def test_format_model_reachability_error_wrapped_in_validation_result_has_single_terminal_period() -> None:
    """End-to-end: the ValidationResult string the user sees ends with exactly one period.

    Locks the structural pipeline (label mapping + ValidationResult wrap + trailing period)
    against the literal copy template — fails loudly if either drifts.
    """
    error = _FakeClientInferenceError(status_code=404)
    inner = format_model_reachability_error(
        "job.model", {"name": "qwen2-5-1-5b-instruct", "url": "http://gateway/v1"}, error
    )
    wrapped = str(ValidationResult(False, [inner]))
    expected_inner = MODEL_NO_DEPLOYMENT_MESSAGE.format(label="Evaluation Model", model_name="qwen2-5-1-5b-instruct")
    assert wrapped == f"Invalid payload. Errors: {expected_inner}."
    assert not wrapped.endswith(".."), "Expected single trailing period, not double"
