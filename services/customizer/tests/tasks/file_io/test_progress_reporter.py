# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the progress_reporter module."""

from pathlib import Path

import pytest
from nemo_platform import omit
from nemo_platform._exceptions import APIError
from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.customizer.app.jobs.context import NMPJobContext
from nmp.customizer.shared.tasks.file_io.progress_reporter import (
    JobsServiceProgressReporter,
    NoOpProgressReporter,
)
from pytest_mock import MockerFixture


class TestNoOpProgressReporter:
    """Tests for NoOpProgressReporter."""

    def test_update_progress_does_nothing(self):
        """Should silently ignore progress updates."""
        reporter = NoOpProgressReporter()

        # Should not raise any exceptions
        reporter.update_progress(status=PlatformJobStatus.ACTIVE)
        reporter.update_progress(
            status=PlatformJobStatus.COMPLETED,
            status_details={"phase": "test"},
            error_details={"message": "error"},
            error_stack="stack trace",
        )


class TestJobsServiceProgressReporter:
    """Tests for JobsServiceProgressReporter."""

    @pytest.fixture
    def mock_sdk(self, mocker: MockerFixture):
        """Create a mock SDK."""
        return mocker.MagicMock()

    @pytest.fixture
    def reporter(self, mock_sdk):
        """Create a JobsServiceProgressReporter instance."""
        return JobsServiceProgressReporter(
            sdk=mock_sdk,
            workspace="test-workspace",
            job_id="job-123",
            step_name="download",
            task_id="task-456",
        )

    def test_init_stores_all_parameters(self, mock_sdk):
        """Should store all initialization parameters."""
        reporter = JobsServiceProgressReporter(
            sdk=mock_sdk,
            workspace="my-workspace",
            job_id="my-job",
            step_name="my-step",
            task_id="my-task",
        )

        assert reporter.sdk is mock_sdk
        assert reporter.workspace == "my-workspace"
        assert reporter.job_id == "my-job"
        assert reporter.step_name == "my-step"
        assert reporter.task_id == "my-task"

    def test_update_progress_calls_sdk_with_status_only(self, reporter, mock_sdk):
        """Should call SDK with correct parameters when only status is provided."""
        reporter.update_progress(status=PlatformJobStatus.ACTIVE)

        mock_sdk.jobs.tasks.create_or_update.assert_called_once_with(
            "task-456",
            workspace="test-workspace",
            job="job-123",
            step="download",
            status="active",
            status_details=omit,
            error_details=omit,
            error_stack=omit,
        )

    def test_update_progress_with_status_details(self, reporter, mock_sdk):
        """Should pass status_details to SDK when provided."""
        status_details = {"phase": "downloading", "progress": 50}

        reporter.update_progress(
            status=PlatformJobStatus.ACTIVE,
            status_details=status_details,
        )

        mock_sdk.jobs.tasks.create_or_update.assert_called_once_with(
            "task-456",
            workspace="test-workspace",
            job="job-123",
            step="download",
            status="active",
            status_details=status_details,
            error_details=omit,
            error_stack=omit,
        )

    def test_update_progress_with_error_details(self, reporter, mock_sdk):
        """Should pass error_details to SDK when provided."""
        error_details = {"message": "Something went wrong", "type": "ValueError"}

        reporter.update_progress(
            status=PlatformJobStatus.ERROR,
            error_details=error_details,
        )

        mock_sdk.jobs.tasks.create_or_update.assert_called_once_with(
            "task-456",
            workspace="test-workspace",
            job="job-123",
            step="download",
            status="error",
            status_details=omit,
            error_details=error_details,
            error_stack=omit,
        )

    def test_update_progress_with_error_stack(self, reporter, mock_sdk):
        """Should pass error_stack to SDK when provided."""
        error_stack = "Traceback (most recent call last):\n  File ..."

        reporter.update_progress(
            status=PlatformJobStatus.ERROR,
            error_stack=error_stack,
        )

        mock_sdk.jobs.tasks.create_or_update.assert_called_once_with(
            "task-456",
            workspace="test-workspace",
            job="job-123",
            step="download",
            status="error",
            status_details=omit,
            error_details=omit,
            error_stack=error_stack,
        )

    def test_update_progress_with_all_parameters(self, reporter, mock_sdk):
        """Should pass all parameters to SDK when provided."""
        status_details = {"phase": "error"}
        error_details = {"message": "Failed"}
        error_stack = "stack trace"

        reporter.update_progress(
            status=PlatformJobStatus.ERROR,
            status_details=status_details,
            error_details=error_details,
            error_stack=error_stack,
        )

        mock_sdk.jobs.tasks.create_or_update.assert_called_once_with(
            "task-456",
            workspace="test-workspace",
            job="job-123",
            step="download",
            status="error",
            status_details=status_details,
            error_details=error_details,
            error_stack=error_stack,
        )

    def test_update_progress_empty_status_details_uses_omit(self, reporter, mock_sdk):
        """Should use omit for empty status_details dict."""
        reporter.update_progress(
            status=PlatformJobStatus.ACTIVE,
            status_details={},
        )

        mock_sdk.jobs.tasks.create_or_update.assert_called_once_with(
            "task-456",
            workspace="test-workspace",
            job="job-123",
            step="download",
            status="active",
            status_details=omit,
            error_details=omit,
            error_stack=omit,
        )

    def test_update_progress_empty_error_details_uses_omit(self, reporter, mock_sdk):
        """Should use omit for empty error_details dict."""
        reporter.update_progress(
            status=PlatformJobStatus.ERROR,
            error_details={},
        )

        mock_sdk.jobs.tasks.create_or_update.assert_called_once_with(
            "task-456",
            workspace="test-workspace",
            job="job-123",
            step="download",
            status="error",
            status_details=omit,
            error_details=omit,
            error_stack=omit,
        )

    def test_update_progress_empty_error_stack_uses_omit(self, reporter, mock_sdk):
        """Should use omit for empty error_stack string."""
        reporter.update_progress(
            status=PlatformJobStatus.ERROR,
            error_stack="",
        )

        mock_sdk.jobs.tasks.create_or_update.assert_called_once_with(
            "task-456",
            workspace="test-workspace",
            job="job-123",
            step="download",
            status="error",
            status_details=omit,
            error_details=omit,
            error_stack=omit,
        )

    def test_update_progress_catches_exception_and_logs_warning(self, reporter, mock_sdk, mocker: MockerFixture):
        """Should catch exceptions and log warning instead of crashing."""
        mock_sdk.jobs.tasks.create_or_update.side_effect = Exception("Network error")
        mock_logger = mocker.patch("nmp.customizer.shared.tasks.file_io.progress_reporter.logger")

        # Should not raise
        reporter.update_progress(status=PlatformJobStatus.ACTIVE)

        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "Failed to report progress" in warning_msg
        assert "task-456" in warning_msg
        assert "job-123" in warning_msg
        assert "download" in warning_msg
        assert "Network error" in warning_msg

    def test_update_progress_catches_api_error_and_logs_warning(self, reporter, mock_sdk, mocker: MockerFixture):
        """Should catch APIError and log warning instead of crashing."""
        mock_request = mocker.MagicMock()
        mock_response = mocker.MagicMock()
        mock_response.status_code = 500
        api_error = APIError(message="Server error", request=mock_request, body=None)
        mock_sdk.jobs.tasks.create_or_update.side_effect = api_error
        mock_logger = mocker.patch("nmp.customizer.shared.tasks.file_io.progress_reporter.logger")

        # Should not raise
        reporter.update_progress(status=PlatformJobStatus.ACTIVE)

        mock_logger.warning.assert_called_once()

    @pytest.mark.parametrize(
        ("status", "expected_value"),
        [
            (PlatformJobStatus.CREATED, "created"),
            (PlatformJobStatus.PENDING, "pending"),
            (PlatformJobStatus.ACTIVE, "active"),
            (PlatformJobStatus.COMPLETED, "completed"),
            (PlatformJobStatus.ERROR, "error"),
            (PlatformJobStatus.CANCELLED, "cancelled"),
        ],
    )
    def test_update_progress_uses_status_value(self, reporter, mock_sdk, status, expected_value):
        """Should use the enum value when calling SDK."""
        reporter.update_progress(status=status)

        call_kwargs = mock_sdk.jobs.tasks.create_or_update.call_args[1]
        assert call_kwargs["status"] == expected_value


class TestCreateProgressReporter:
    """Tests for JobsServiceProgressReporter.create_progress_reporter static method."""

    @pytest.fixture
    def mock_sdk(self, mocker: MockerFixture):
        """Create a mock SDK."""
        return mocker.MagicMock()

    @pytest.fixture
    def job_ctx_with_jobs_url(self, tmp_path: Path) -> NMPJobContext:
        """Create a job context with jobs_url configured."""
        return NMPJobContext(
            workspace="my-workspace",
            job_id="job-123",
            attempt_id="attempt-0",
            step="download",
            task="task-456",
            jobs_url="http://jobs-service:8080",
            files_url="http://files:8000",
            storage_path=tmp_path,
            config_path=tmp_path / "config.json",
        )

    @pytest.fixture
    def job_ctx_without_jobs_url(self, tmp_path: Path) -> NMPJobContext:
        """Create a job context without jobs_url configured."""
        return NMPJobContext(
            workspace="my-workspace",
            job_id="job-123",
            attempt_id="attempt-0",
            step="download",
            task="task-456",
            jobs_url=None,
            files_url="http://files:8000",
            storage_path=tmp_path,
            config_path=tmp_path / "config.json",
        )

    def test_returns_jobs_service_reporter_when_url_configured(self, mock_sdk, job_ctx_with_jobs_url: NMPJobContext):
        """Should return JobsServiceProgressReporter when jobs_url is set."""
        reporter = JobsServiceProgressReporter.create_progress_reporter(
            sdk=mock_sdk,
            job_ctx=job_ctx_with_jobs_url,
        )

        assert isinstance(reporter, JobsServiceProgressReporter)
        assert reporter.sdk is mock_sdk
        assert reporter.workspace == "my-workspace"
        assert reporter.job_id == "job-123"
        assert reporter.step_name == "download"
        assert reporter.task_id == "task-456"

    def test_returns_noop_reporter_when_url_not_configured(self, mock_sdk, job_ctx_without_jobs_url: NMPJobContext):
        """Should return NoOpProgressReporter when jobs_url is not set."""
        reporter = JobsServiceProgressReporter.create_progress_reporter(
            sdk=mock_sdk,
            job_ctx=job_ctx_without_jobs_url,
        )

        assert isinstance(reporter, NoOpProgressReporter)

    def test_create_progress_reporter_normalizes_raw_uuid_task_id(self, mock_sdk, tmp_path: Path):
        """Should normalize raw UUID task names when creating a reporter from context."""
        raw_task = "22ae6989-fcbe-4be2-8c89-37ef9da06aec"
        job_ctx = NMPJobContext(
            workspace="my-workspace",
            job_id="job-123",
            attempt_id="attempt-0",
            step="download",
            task=raw_task,
            jobs_url="http://jobs-service:8080",
            files_url="http://files:8000",
            storage_path=tmp_path,
            config_path=tmp_path / "config.json",
        )

        reporter = JobsServiceProgressReporter.create_progress_reporter(
            sdk=mock_sdk,
            job_ctx=job_ctx,
        )

        assert isinstance(reporter, JobsServiceProgressReporter)
        assert reporter.task_id == f"task-{raw_task}"

    def test_returns_noop_reporter_when_url_empty_string(self, mock_sdk, tmp_path: Path):
        """Should return NoOpProgressReporter when jobs_url is empty string."""
        job_ctx = NMPJobContext(
            workspace="my-workspace",
            job_id="job-123",
            attempt_id="attempt-0",
            step="download",
            task="task-456",
            jobs_url="",
            files_url="http://files:8000",
            storage_path=tmp_path,
            config_path=tmp_path / "config.json",
        )

        reporter = JobsServiceProgressReporter.create_progress_reporter(
            sdk=mock_sdk,
            job_ctx=job_ctx,
        )

        assert isinstance(reporter, NoOpProgressReporter)

    def test_logs_info_when_progress_enabled(
        self, mock_sdk, job_ctx_with_jobs_url: NMPJobContext, mocker: MockerFixture
    ):
        """Should log info message when progress reporting is enabled."""
        mock_logger = mocker.patch("nmp.customizer.shared.tasks.file_io.progress_reporter.logger")

        JobsServiceProgressReporter.create_progress_reporter(
            sdk=mock_sdk,
            job_ctx=job_ctx_with_jobs_url,
        )

        mock_logger.info.assert_called_once()
        log_msg = mock_logger.info.call_args[0][0]
        assert "Progress reporting enabled" in log_msg
        assert "http://jobs-service:8080" in log_msg

    def test_logs_info_when_progress_disabled(
        self, mock_sdk, job_ctx_without_jobs_url: NMPJobContext, mocker: MockerFixture
    ):
        """Should log info message when progress reporting is disabled."""
        mock_logger = mocker.patch("nmp.customizer.shared.tasks.file_io.progress_reporter.logger")

        JobsServiceProgressReporter.create_progress_reporter(
            sdk=mock_sdk,
            job_ctx=job_ctx_without_jobs_url,
        )

        mock_logger.info.assert_called_once()
        log_msg = mock_logger.info.call_args[0][0]
        assert "Progress reporting disabled" in log_msg
