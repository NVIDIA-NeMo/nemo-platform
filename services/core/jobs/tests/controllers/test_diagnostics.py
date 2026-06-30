# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import Mock, patch

from nmp.core.jobs.controllers.diagnostics import _MAX_ERROR_STACK_CHARS, collect_job_diagnostics


def _make_sdk_with_logs() -> Mock:
    sdk = Mock()
    sdk.jobs.retrieve.return_value = SimpleNamespace(
        name="job-1",
        status="error",
        status_details={},
        error_details={},
    )
    sdk.jobs.get_status.return_value = SimpleNamespace(
        status="error",
        status_details={},
        error_details={},
        steps=[],
    )
    sdk.jobs.steps.retrieve.return_value = SimpleNamespace(
        name="step-1",
        status="error",
        status_details={},
        error_details={},
    )
    sdk.jobs.tasks.list.return_value = SimpleNamespace(data=[])
    sdk.jobs.get_logs.return_value = SimpleNamespace(
        data=[SimpleNamespace(message="secret-token=abc123"), SimpleNamespace(message="another line")]
    )
    return sdk


def test_collect_job_diagnostics_omits_raw_job_logs_by_default() -> None:
    sdk = _make_sdk_with_logs()

    with patch("nmp.core.jobs.controllers.diagnostics.config.include_job_logs_in_diagnostics", False):
        diagnostics = collect_job_diagnostics(
            sdk,
            workspace="default",
            job_name="job-1",
            step_name="step-1",
            context="test",
        )

    assert "job_logs" not in diagnostics
    sdk.jobs.get_logs.assert_not_called()


def test_collect_job_diagnostics_includes_raw_job_logs_when_enabled() -> None:
    sdk = _make_sdk_with_logs()

    with patch("nmp.core.jobs.controllers.diagnostics.config.include_job_logs_in_diagnostics", True):
        diagnostics = collect_job_diagnostics(
            sdk,
            workspace="default",
            job_name="job-1",
            step_name="step-1",
            context="test",
        )

    assert diagnostics["job_logs"] == ["secret-token=abc123", "another line"]
    sdk.jobs.get_logs.assert_called_once_with(workspace="default", name="job-1")


def test_collect_job_diagnostics_trims_long_error_details_tracebacks() -> None:
    sdk = Mock()
    long_error = "traceback-" + ("x" * (_MAX_ERROR_STACK_CHARS + 50))
    expected_trimmed = long_error[-_MAX_ERROR_STACK_CHARS:]
    error_details = {"message": "boom", "error": long_error, "other": "keep"}
    sdk.jobs.retrieve.return_value = SimpleNamespace(
        name="job-1",
        status="error",
        status_details={},
        error_details=error_details,
    )
    sdk.jobs.get_status.return_value = SimpleNamespace(
        status="error",
        status_details={},
        error_details=error_details,
        steps=[
            SimpleNamespace(
                name="step-1",
                status="error",
                status_details={},
                error_details=error_details,
                tasks=[
                    SimpleNamespace(
                        name="task-1",
                        status="error",
                        status_details={},
                        error_details=error_details,
                        error_stack=long_error,
                    )
                ],
            )
        ],
    )
    sdk.jobs.steps.retrieve.return_value = SimpleNamespace(
        name="step-1",
        status="error",
        status_details={},
        error_details=error_details,
    )
    sdk.jobs.tasks.list.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(
                name="task-1",
                status="error",
                status_details={},
                error_details=error_details,
                error_stack=long_error,
            )
        ]
    )

    diagnostics = collect_job_diagnostics(
        sdk,
        workspace="default",
        job_name="job-1",
        step_name="step-1",
        context="test",
    )

    assert diagnostics["job"]["error_details"]["error"] == expected_trimmed
    assert diagnostics["status_api"]["error_details"]["error"] == expected_trimmed
    assert diagnostics["status_api"]["steps"][0]["error_details"]["error"] == expected_trimmed
    assert diagnostics["status_api"]["steps"][0]["tasks"][0]["error_details"]["error"] == expected_trimmed
    assert diagnostics["step"]["error_details"]["error"] == expected_trimmed
    assert diagnostics["tasks_api"][0]["error_details"]["error"] == expected_trimmed
