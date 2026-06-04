# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import io
import json
import logging
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

import httpx
from data_designer.config.analysis.dataset_profiler import DatasetProfilerResults
from data_designer.config.utils.visualization import WithRecordSamplerMixin
from data_designer.logging import RandomEmoji
from nemo_data_designer_plugin.sdk import http
from nemo_data_designer_plugin.sdk.errors import DataDesignerJobError, extract_http_error_info
from nemo_data_designer_plugin.sdk.job_results import DataDesignerJobResults
from nemo_data_designer_plugin.sdk.logging import with_logging
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform.types import PlatformJobStatus
from nemo_platform_plugin.jobs.archive import safe_extract_tar
from typing_extensions import Self

logger = logging.getLogger(__name__)

CHECK_PROGRESS_LOG_MSG = (
    "To check on your job's progress, use the `get_job_status` method. "
    "If you want to wait until it's complete, use the `wait_until_done` method."
)
WAIT_INTERVAL_SECONDS = 1
MAX_CONSECUTIVE_POLL_ERRORS = 5
ARTIFACTS_RESULT_NAME = "artifacts"
ANALYSIS_RESULT_NAME = "analysis"
TERMINAL_INCOMPLETE_STATUSES = {"cancelled", "cancelling", "error"}

T = TypeVar("T")


def _pause(seconds: float) -> None:
    time.sleep(seconds)


async def _async_pause(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _job_url(platform: http.PlatformClient, workspace: str | None, path: str) -> str:
    return http.url(platform, workspace, f"/jobs/create{path}")


def _raise_for_status(resp: httpx.Response) -> None:
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status_code, detail = extract_http_error_info(exc)
        raise DataDesignerJobError(detail, status_code=status_code) from exc


def _safe_extract_tar(tar: tarfile.TarFile, output_path: Path) -> None:
    safe_extract_tar(tar, output_path, error_cls=DataDesignerJobError)


@dataclass
class _WaitLogCollector:
    """Collects and processes log entries emitted during job polling."""

    seen_logs: list[dict[str, str]]
    error_occurred: bool
    warning_occurred: bool

    @classmethod
    def create(cls) -> Self:
        return cls(seen_logs=[], error_occurred=False, warning_occurred=False)

    def accept_logs(self, current_logs: list[dict[str, str]]) -> None:
        for log in current_logs[len(self.seen_logs) :]:
            self.seen_logs.append(log)
            if not log["name"].startswith("data_designer"):
                continue
            level = log["levelname"].lower()
            if level == "info":
                logger.info(log["message"])
            elif level in {"warning", "warn"}:
                logger.warning(log["message"])
                self.warning_occurred = True
            elif level == "error":
                logger.error(log["message"])
                self.error_occurred = True

    def log_final_status(self) -> None:
        if self.error_occurred:
            logger.error("🛑 Dataset generation completed with errors.")
        elif self.warning_occurred:
            logger.warning("⚠️ Dataset generation completed with warnings.")
        else:
            logger.info(f"{RandomEmoji.success()} Dataset generation completed successfully.")


@with_logging
class DataDesignerJobResource(WithRecordSamplerMixin):
    def __init__(self, *, job_name: str, platform: NeMoPlatform, workspace: str | None):
        self._job_name = job_name
        self._platform = platform
        self._workspace = workspace
        self._consecutive_poll_errors = 0

    def get_job(self) -> dict[str, object]:
        """Get the current job.

        Returns:
            The job dict with up-to-date details.
        """
        resp = self._platform._client.get(
            _job_url(self._platform, self._workspace, f"/{self._job_name}"),
            headers=http.headers(self._platform),
        )
        _raise_for_status(resp)
        return resp.json()

    def get_job_status(self) -> PlatformJobStatus | None:
        """Get the current status of the job.

        Returns:
            The current job status.
        """
        resp = self._platform._client.get(
            _job_url(self._platform, self._workspace, f"/{self._job_name}/status"),
            headers=http.headers(self._platform),
        )
        _raise_for_status(resp)
        return resp.json().get("status")

    def check_if_complete(self, *, raise_if_not_complete: bool = False) -> bool:
        """Check if the job is in a completed state.

        Args:
            raise_if_not_complete: If True, raises DataDesignerJobError when job is not complete.
                                   If False, only logs warnings/errors without raising exceptions.

        Returns:
            True if job is completed, False otherwise.

        Raises:
            DataDesignerJobError: If raise_if_not_complete is True and job is not in completed state.
        """
        status = self.get_job_status()
        return _status_is_complete(status, raise_if_not_complete)

    def wait_until_done(self) -> None:
        """Wait for the job to complete and monitor its progress.

        This method blocks execution until the job reaches a terminal state.
        During the wait, it continuously monitors job logs and displays relevant messages to the user.

        The method will:
        - Poll the job status at regular intervals
        - Display log messages from the data designer service
        - Handle warnings and errors appropriately
        - Provide final status summary when complete
        """
        log_collector = _WaitLogCollector.create()
        job_status = self.get_job_status()
        while job_status != "completed":
            _pause(WAIT_INTERVAL_SECONDS)
            current_logs = self._poll_safe(self.get_logs, log_collector.seen_logs)
            log_collector.accept_logs(current_logs)
            if job_status in TERMINAL_INCOMPLETE_STATUSES:
                log_collector.error_occurred = True
                logger.error(f"🛑 Terminating generation job with status `{job_status}`.")
                break
            job_status = self._poll_safe(self.get_job_status, job_status)
        log_collector.log_final_status()

    def get_logs(self) -> list[dict[str, str]]:
        """Page through and fetch all job logs.

        Returns:
            A list of log entries, where each entry is a dictionary containing log information.
        """
        logs = []
        page_cursor = None
        while True:
            params = {"page_cursor": page_cursor} if page_cursor else None
            resp = self._platform._client.get(
                _job_url(self._platform, self._workspace, f"/{self._job_name}/logs"),
                headers=http.headers(self._platform),
                params=params,
            )
            _raise_for_status(resp)
            response = resp.json()
            for log in response.get("data", []):
                deserialized = _try_parse_log_message(log.get("message", ""))
                if deserialized is not None:
                    logs.append(deserialized)
            page_cursor = response.get("next_page")
            if page_cursor is None:
                break
        return logs

    def download_artifacts(self, path: Path | str | None = None) -> DataDesignerJobResults:
        """Download the Job's artifacts to the specified path.

        Args:
            path: Save artifacts to this path. If not specified, creates a local directory using the job name.

        Returns:
            An object with methods for inspecting the saved job results.
        """
        self._check_if_result_available(ARTIFACTS_RESULT_NAME)
        output_path = Path(path or self._job_name)
        logger.info(f"🏺 Downloading artifacts from Job {self._job_name!r}")

        resp = self._platform._client.get(
            _job_url(self._platform, self._workspace, f"/{self._job_name}/results/artifacts/download"),
            headers=http.headers(self._platform),
        )
        _raise_for_status(resp)
        with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:*") as tar:
            _safe_extract_tar(tar, output_path)

        try:
            analysis_resp = self._platform._client.get(
                _job_url(self._platform, self._workspace, f"/{self._job_name}/results/analysis/download"),
                headers=http.headers(self._platform),
            )
            _raise_for_status(analysis_resp)
            analysis = DatasetProfilerResults.model_validate(analysis_resp.json())
        except Exception as e:
            msg = f"Unable to fetch analysis: {e}"
            logger.warning(msg)
            analysis = msg

        artifacts_dir = output_path / "artifacts"
        logger.info(f"✅ Artifacts downloaded to {artifacts_dir}")
        return DataDesignerJobResults(artifacts_dir, analysis)

    def load_analysis(self) -> DatasetProfilerResults:
        """Load the dataset analysis as a DatasetProfilerResults object.

        Returns:
            The analysis results containing dataset statistics and profiling information.

        Raises:
            DataDesignerJobError: If the job is not completed or if there's an error loading the analysis.
        """
        self._check_if_result_available(ANALYSIS_RESULT_NAME)
        try:
            resp = self._platform._client.get(
                _job_url(self._platform, self._workspace, f"/{self._job_name}/results/analysis/download"),
                headers=http.headers(self._platform),
            )
            _raise_for_status(resp)
            return DatasetProfilerResults.model_validate(resp.json())
        except Exception as e:
            raise DataDesignerJobError(f"🛑 Error loading analysis: {e}") from e

    def _check_if_result_available(self, result_name: str) -> None:
        status = self.get_job_status()
        if status == "completed":
            return
        if status == "active" or status in TERMINAL_INCOMPLETE_STATUSES:
            try:
                resp = self._platform._client.get(
                    _job_url(self._platform, self._workspace, f"/{self._job_name}/results/{result_name}"),
                    headers=http.headers(self._platform),
                )
                _raise_for_status(resp)
                if status == "active":
                    logger.info(
                        f"{RandomEmoji.cooking()} Your dataset is still cooking. "
                        "Fetching completed results for your enjoyment."
                    )
                else:
                    logger.warning(f"Job ended with status {status!r}. Fetching completed {result_name} result.")
            except DataDesignerJobError as e:
                if e.status_code == 404:
                    raise DataDesignerJobError(f"{result_name!r} result is not available.") from e
                raise DataDesignerJobError(f"🛑 Error loading dataset: {e}") from e
        else:
            raise DataDesignerJobError(f"Current job status is {status!r}, results are not available.")

    def _poll_safe(self, fn: Callable[[], T], fallback: T) -> T:
        """Wrapper function to add resilience to network calls made while polling.

        This method will call the provided function and, in the happy path,
        reset the consecutive errors counter and return the result.

        If an error occurs, the consecutive errors counter is incremented.
        - If the threshold is not yet met, the fallback value is returned. Typically
          the fallback value is the last cached response from the network call.
        - If the counter has met the threshold, the counter is reset for future use
          and the caught error is raised.
        """
        try:
            response = fn()
            self._consecutive_poll_errors = 0
            return response
        except Exception:
            self._consecutive_poll_errors += 1
            if self._consecutive_poll_errors >= MAX_CONSECUTIVE_POLL_ERRORS:
                self._consecutive_poll_errors = 0
                raise
            return fallback


@with_logging
class AsyncDataDesignerJobResource(WithRecordSamplerMixin):
    def __init__(self, *, job_name: str, platform: AsyncNeMoPlatform, workspace: str | None):
        self._job_name = job_name
        self._platform = platform
        self._workspace = workspace
        self._consecutive_poll_errors = 0

    async def get_job(self) -> dict[str, object]:
        """Get the current job.

        Returns:
            The job dict with up-to-date details.
        """
        resp = await self._platform._client.get(
            _job_url(self._platform, self._workspace, f"/{self._job_name}"),
            headers=http.headers(self._platform),
        )
        _raise_for_status(resp)
        return resp.json()

    async def get_job_status(self) -> PlatformJobStatus | None:
        """Get the current status of the job.

        Returns:
            The current job status.
        """
        resp = await self._platform._client.get(
            _job_url(self._platform, self._workspace, f"/{self._job_name}/status"),
            headers=http.headers(self._platform),
        )
        _raise_for_status(resp)
        return resp.json().get("status")

    async def check_if_complete(self, *, raise_if_not_complete: bool = False) -> bool:
        """Check if the job is in a completed state.

        Args:
            raise_if_not_complete: If True, raises DataDesignerJobError when job is not complete.
                                   If False, only logs warnings/errors without raising exceptions.

        Returns:
            True if job is completed, False otherwise.

        Raises:
            DataDesignerJobError: If raise_if_not_complete is True and job is not in completed state.
        """
        status = await self.get_job_status()
        return _status_is_complete(status, raise_if_not_complete)

    async def wait_until_done(self) -> None:
        """Wait for the job to complete and monitor its progress.

        This method blocks execution until the job reaches a terminal state.
        During the wait, it continuously monitors job logs and displays relevant messages to the user.

        The method will:
        - Poll the job status at regular intervals
        - Display log messages from the data designer service
        - Handle warnings and errors appropriately
        - Provide final status summary when complete
        """
        log_collector = _WaitLogCollector.create()
        job_status = await self.get_job_status()
        while job_status != "completed":
            await _async_pause(WAIT_INTERVAL_SECONDS)
            current_logs = await self._poll_safe(self.get_logs, log_collector.seen_logs)
            log_collector.accept_logs(current_logs)
            if job_status in TERMINAL_INCOMPLETE_STATUSES:
                log_collector.error_occurred = True
                logger.error(f"🛑 Terminating generation job with status `{job_status}`.")
                break
            job_status = await self._poll_safe(self.get_job_status, job_status)
        log_collector.log_final_status()

    async def get_logs(self) -> list[dict[str, str]]:
        """Page through and fetch all job logs.

        Returns:
            A list of log entries, where each entry is a dictionary containing log information.
        """
        logs = []
        page_cursor = None
        while True:
            params = {"page_cursor": page_cursor} if page_cursor else None
            resp = await self._platform._client.get(
                _job_url(self._platform, self._workspace, f"/{self._job_name}/logs"),
                headers=http.headers(self._platform),
                params=params,
            )
            _raise_for_status(resp)
            response = resp.json()
            for log in response.get("data", []):
                deserialized = _try_parse_log_message(log.get("message", ""))
                if deserialized is not None:
                    logs.append(deserialized)
            page_cursor = response.get("next_page")
            if page_cursor is None:
                break
        return logs

    async def download_artifacts(self, path: Path | str | None = None) -> DataDesignerJobResults:
        """Download the Job's artifacts to the specified path.

        Args:
            path: Save artifacts to this path. If not specified, creates a local directory using the job name.

        Returns:
            An object with methods for inspecting the saved job results.
        """
        await self._check_if_result_available(ARTIFACTS_RESULT_NAME)
        output_path = Path(path or self._job_name)
        logger.info(f"🏺 Downloading artifacts from Job {self._job_name!r}")

        resp = await self._platform._client.get(
            _job_url(self._platform, self._workspace, f"/{self._job_name}/results/artifacts/download"),
            headers=http.headers(self._platform),
        )
        _raise_for_status(resp)
        with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:*") as tar:
            _safe_extract_tar(tar, output_path)

        try:
            analysis_resp = await self._platform._client.get(
                _job_url(self._platform, self._workspace, f"/{self._job_name}/results/analysis/download"),
                headers=http.headers(self._platform),
            )
            _raise_for_status(analysis_resp)
            analysis = DatasetProfilerResults.model_validate(analysis_resp.json())
        except Exception as e:
            msg = f"Unable to fetch analysis: {e}"
            logger.warning(msg)
            analysis = msg

        artifacts_dir = output_path / "artifacts"
        logger.info(f"✅ Artifacts downloaded to {artifacts_dir}")
        return DataDesignerJobResults(artifacts_dir, analysis)

    async def load_analysis(self) -> DatasetProfilerResults:
        """Load the dataset analysis as a DatasetProfilerResults object.

        Returns:
            The analysis results containing dataset statistics and profiling information.

        Raises:
            DataDesignerJobError: If the job is not completed or if there's an error loading the analysis.
        """
        await self._check_if_result_available(ANALYSIS_RESULT_NAME)
        try:
            resp = await self._platform._client.get(
                _job_url(self._platform, self._workspace, f"/{self._job_name}/results/analysis/download"),
                headers=http.headers(self._platform),
            )
            _raise_for_status(resp)
            return DatasetProfilerResults.model_validate(resp.json())
        except Exception as e:
            raise DataDesignerJobError(f"🛑 Error loading analysis: {e}") from e

    async def _check_if_result_available(self, result_name: str) -> None:
        status = await self.get_job_status()
        if status == "completed":
            return
        if status == "active" or status in TERMINAL_INCOMPLETE_STATUSES:
            try:
                resp = await self._platform._client.get(
                    _job_url(self._platform, self._workspace, f"/{self._job_name}/results/{result_name}"),
                    headers=http.headers(self._platform),
                )
                _raise_for_status(resp)
                if status == "active":
                    logger.info(
                        f"{RandomEmoji.cooking()} Your dataset is still cooking. "
                        "Fetching completed results for your enjoyment."
                    )
                else:
                    logger.warning(f"Job ended with status {status!r}. Fetching completed {result_name} result.")
            except DataDesignerJobError as e:
                if e.status_code == 404:
                    raise DataDesignerJobError(f"{result_name!r} result is not available.") from e
                raise DataDesignerJobError(f"🛑 Error loading dataset: {e}") from e
        else:
            raise DataDesignerJobError(f"Current job status is {status!r}, results are not available.")

    async def _poll_safe(self, fn: Callable[[], Awaitable[T]], fallback: T) -> T:
        """Wrapper function to add resilience to network calls made while polling.

        This method will call the provided function and, in the happy path,
        reset the consecutive errors counter and return the result.

        If an error occurs, the consecutive errors counter is incremented.
        - If the threshold is not yet met, the fallback value is returned. Typically
          the fallback value is the last cached response from the network call.
        - If the counter has met the threshold, the counter is reset for future use
          and the caught error is raised.
        """
        try:
            response = await fn()
            self._consecutive_poll_errors = 0
            return response
        except Exception:
            self._consecutive_poll_errors += 1
            if self._consecutive_poll_errors >= MAX_CONSECUTIVE_POLL_ERRORS:
                self._consecutive_poll_errors = 0
                raise
            return fallback


def _try_parse_log_message(raw_message: str) -> dict[str, str] | None:
    """Best-effort extraction of the JSON payload from a platform log entry.

    Job logs come back as ``log["message"]`` strings. The platform's log
    capture sometimes prepends a stream marker like ``"[stderr] "`` before the
    JSON dict our task emits via ``_make_json_formatter``. Slice from the
    first ``{`` so the prefix doesn't break parsing; non-JSON messages
    (heartbeats, raw stderr lines from third-party libraries, etc.) silently
    return ``None`` and the caller drops them.
    """
    json_start = raw_message.find("{")
    if json_start < 0:
        return None
    try:
        deserialized = json.loads(raw_message[json_start:])
    except Exception:
        return None
    if not isinstance(deserialized, dict) or "message" not in deserialized:
        return None
    return deserialized


def _status_is_complete(status: PlatformJobStatus | None, raise_if_not_complete: bool) -> bool:
    if status == "completed":
        return True
    if status == "active":
        msg = f"Your dataset generation job is still running. {CHECK_PROGRESS_LOG_MSG}"
        if raise_if_not_complete:
            raise DataDesignerJobError(f"🛑 {msg}")
        logger.warning(f"⏳ {msg}")
        return False
    if status in TERMINAL_INCOMPLETE_STATUSES:
        msg = f"🛑 Your dataset generation job stopped with status `{status}`."
        if raise_if_not_complete:
            raise DataDesignerJobError(msg)
        logger.error(msg)
        return False
    if status in {"created", "pending"}:
        msg = f"⏹️ Your dataset generation job is still in the queue with status `{status}`. {CHECK_PROGRESS_LOG_MSG}"
        if raise_if_not_complete:
            raise DataDesignerJobError(msg)
        logger.warning(msg)
        return False
    msg = f"Your job is in an unknown state: `{status}`."
    if raise_if_not_complete:
        raise DataDesignerJobError(msg)
    logger.error(msg)
    return False
