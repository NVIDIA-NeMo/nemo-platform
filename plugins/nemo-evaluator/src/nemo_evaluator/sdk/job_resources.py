# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evaluator plugin job resources for status polling and result downloads."""

from __future__ import annotations

import asyncio
import json
import logging
import tarfile
import time
from collections.abc import Callable, Mapping
from io import BytesIO
from pathlib import Path
from time import monotonic
from typing import TypeAlias, cast

import httpx
from nemo_evaluator.jobs.evaluate import EvaluateSpec
from nemo_evaluator.sdk import http_utils
from nemo_evaluator.sdk.utils import filter_aggregate_scores
from nemo_evaluator_sdk.execution.job_poll import async_poll_until_terminal
from nemo_evaluator_sdk.values.results import AggregatedMetricResult, AggregateFieldName, EvaluationResult, RowScore
from nemo_platform_plugin.jobs.api_factory import BaseJob
from nemo_platform_plugin.jobs.archive import safe_extract_tar
from nemo_platform_plugin.jobs.schemas import PlatformJobStatusResponse
from pydantic import BaseModel

EvaluatorJob: TypeAlias = BaseJob[EvaluateSpec]

_TERMINAL_FAILURE_STATUSES = frozenset({"error", "cancelled", "failed"})
_TERMINAL_SUCCESS_STATUS = "completed"
_TERMINAL_STATUSES = _TERMINAL_FAILURE_STATUSES | frozenset({_TERMINAL_SUCCESS_STATUS})
_QUEUED_STATUSES = frozenset({"created", "pending"})
_RUNNING_STATUSES = frozenset({"active", "cancelling", "paused", "pausing", "resuming"})
_DEFAULT_POLL_INTERVAL_SECONDS = 10.0
_DEFAULT_JOB_TIMEOUT_SECONDS = 3600.0
_DEFAULT_PENDING_TIMEOUT_SECONDS = 600.0

_RES_STATUS = "status"
_RES_AGGREGATE_DOWNLOAD = "results/aggregate-scores/download"
_RES_ROW_SCORES_DOWNLOAD = "results/row-scores/download"
_RES_ARTIFACTS_DOWNLOAD = "results/artifacts/download"

_RowScorePayload: TypeAlias = RowScore | BaseModel | Mapping[str, object]
_AggregateScoresPayload: TypeAlias = AggregatedMetricResult | BaseModel | Mapping[str, object]
_AsyncHTTPClient: TypeAlias = httpx.AsyncClient | httpx.Client

log = logging.getLogger(__name__)


def _pause(seconds: float) -> None:
    time.sleep(seconds)


def metric_job_status_value(status: PlatformJobStatusResponse) -> str:
    """Return the normalized status value from a metric job status response."""
    raw = status.status
    return raw.lower() if isinstance(raw, str) else ""


def metric_job_status_details_value(status: PlatformJobStatusResponse) -> Mapping[str, object] | None:
    """Return status details from a metric job status response."""
    return status.status_details or None


def _coerce_row_score(row_score: _RowScorePayload) -> RowScore:
    """Convert a platform SDK row-score object to the evaluator SDK value type."""
    if isinstance(row_score, RowScore):
        return row_score
    if isinstance(row_score, BaseModel):
        return RowScore.model_validate(row_score.model_dump(mode="json"))
    return RowScore.model_validate(row_score)


def _coerce_aggregate_scores(aggregate_scores: _AggregateScoresPayload) -> AggregatedMetricResult:
    """Convert platform SDK aggregate scores to the evaluator SDK value type."""
    if isinstance(aggregate_scores, AggregatedMetricResult):
        return aggregate_scores
    if isinstance(aggregate_scores, BaseModel):
        return AggregatedMetricResult.model_validate(aggregate_scores.model_dump(mode="json"))
    return AggregatedMetricResult.model_validate(aggregate_scores)


def _parse_row_scores_jsonl(payload: str) -> list[RowScore]:
    """Parse row-score JSONL downloaded from the evaluator plugin result route."""
    row_scores: list[RowScore] = []
    for line in payload.splitlines():
        stripped = line.strip()
        if stripped:
            row_scores.append(_coerce_row_score(cast(_RowScorePayload, json.loads(stripped))))
    return row_scores


def _extract_artifacts_tarball(payload: bytes, output_path: Path) -> Path:
    """Extract a job artifacts tarball into ``output_path`` and return it.

    The evaluator artifact route returns a tarball produced by the Jobs result
    serializer. Validate every member before extraction so a malformed archive
    cannot write outside the selected destination or create links/special files.
    """
    with tarfile.open(fileobj=BytesIO(payload), mode="r:*") as tar:
        safe_extract_tar(tar, output_path, error_cls=ValueError)
    return output_path


def _artifact_output_path(path: Path | str | None, job_name: str) -> Path:
    """Return the job-specific local directory for downloaded artifacts.

    Validates ``job_name`` so it cannot escape the chosen base directory. Job
    names flow in from API responses and could otherwise contain path
    separators or ``..`` segments that would land the extracted artifacts
    outside the intended location.
    """
    job_path = Path(job_name)
    if job_path.is_absolute() or len(job_path.parts) != 1 or job_name in {".", ".."}:
        raise ValueError(f"Invalid job name for artifact path: {job_name!r}")
    base = Path(".") if path is None else Path(path)
    return base / job_name


def _raise_for_terminal_status(status: PlatformJobStatusResponse) -> None:
    """Raise when a terminal evaluator job status is not successful."""
    status_value = metric_job_status_value(status)
    if status_value == _TERMINAL_SUCCESS_STATUS:
        return
    if status_value in _TERMINAL_FAILURE_STATUSES:
        error_details = status.error_details or "Unknown error"
        raise RuntimeError(
            f"NeMo Platform metric job {status.name!r} finished with status {status_value!r}: {error_details}"
        )
    raise RuntimeError(f"NeMo Platform metric job {status.name!r} reached unexpected terminal status {status_value!r}")


def _status_is_complete(status: PlatformJobStatusResponse, raise_if_not_complete: bool) -> bool:
    """Return whether the job completed and optionally raise for other statuses."""
    status_value = metric_job_status_value(status)
    if status_value == _TERMINAL_SUCCESS_STATUS:
        return True
    if status_value in _TERMINAL_FAILURE_STATUSES:
        msg = f"NeMo Platform metric job {status.name!r} stopped with status {status_value!r}"
        if raise_if_not_complete:
            error_details = status.error_details or "Unknown error"
            raise RuntimeError(f"{msg}: {error_details}")
        return False
    if status_value in _QUEUED_STATUSES | _RUNNING_STATUSES:
        if raise_if_not_complete:
            raise RuntimeError(f"NeMo Platform metric job {status.name!r} is not complete; status is {status_value!r}")
        return False
    msg = f"NeMo Platform metric job {status.name!r} is in an unknown state: {status_value!r}"
    if raise_if_not_complete:
        raise RuntimeError(msg)
    log.error(msg)
    return False


def _poll_until_terminal(
    get_status: Callable[[], PlatformJobStatusResponse],
    *,
    job_name: str,
    timeout: float,
    pending_timeout: float,
    poll_interval: float,
) -> PlatformJobStatusResponse:
    """Synchronously poll an evaluator job until it reaches a terminal status."""
    elapsed = 0.0
    pending_elapsed = 0.0

    while True:
        poll_start = monotonic()
        status_response = get_status()
        status = metric_job_status_value(status_response)
        log_payload: dict[str, object] = {
            "job_name": job_name,
            "status": status or "<empty>",
            "elapsed_s": round(elapsed, 1),
            "poll_interval_s": poll_interval,
        }
        if status == "pending":
            log_payload["pending_elapsed_s"] = round(pending_elapsed, 1)
        details = metric_job_status_details_value(status_response)
        if details:
            log_payload["status_details"] = dict(details)
        log.info(json.dumps(log_payload, separators=(",", ":")))

        if status in _TERMINAL_STATUSES:
            return status_response

        poll_duration = monotonic() - poll_start
        if status == "pending":
            pending_elapsed += poll_duration
            if pending_elapsed >= pending_timeout:
                raise TimeoutError(f"'{job_name}' stuck in pending after {pending_timeout}s.")
        else:
            elapsed += poll_duration
            if elapsed >= timeout:
                raise TimeoutError(f"'{job_name}' timed out after {timeout}s. Status: {status}")

        sleep_start = monotonic()
        _pause(poll_interval)
        sleep_duration = monotonic() - sleep_start
        if status == "pending":
            pending_elapsed += sleep_duration
        else:
            elapsed += sleep_duration


class EvaluatorJobResource:
    """High-level SDK handle for a submitted evaluator plugin job."""

    def __init__(
        self,
        *,
        job: EvaluatorJob,
        http_client: httpx.Client,
        base_url: str,
        workspace: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Store the job identity and HTTP client used for status and result calls."""
        self._job = job
        self._http_client = http_client
        self._base_url = http_utils.base_url(base_url)
        self._workspace = workspace
        self._headers = dict(headers or {})
        self._job_base_url = http_utils.job_route_base_url(
            raw_base_url=self._base_url,
            workspace=self._workspace,
            job_name=self.name,
        )

    @property
    def name(self) -> str:
        """Return the evaluator job name."""
        return self._job.name

    @property
    def job(self) -> EvaluatorJob:
        """Return the raw evaluator job payload captured at resource creation."""
        return self._job

    def get_job_status(self) -> PlatformJobStatusResponse:
        """Fetch the current evaluator job status from the evaluator plugin API."""
        response = self._http_client.get(
            http_utils.job_route_resource_url(job_base_url=self._job_base_url, resource_path=_RES_STATUS),
            headers=self._headers,
        )
        response.raise_for_status()
        return PlatformJobStatusResponse.model_validate(response.json())

    def check_if_complete(self, *, raise_if_not_complete: bool = False) -> bool:
        """Return whether the evaluator job has completed.

        Args:
            raise_if_not_complete: When true, raise ``RuntimeError`` for any
                status other than ``completed``.

        Returns:
            ``True`` only when the current status is ``completed``.
        """
        return _status_is_complete(self.get_job_status(), raise_if_not_complete)

    def wait_until_done(
        self,
        *,
        poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
        job_timeout_seconds: float = _DEFAULT_JOB_TIMEOUT_SECONDS,
        pending_timeout_seconds: float = _DEFAULT_PENDING_TIMEOUT_SECONDS,
    ) -> None:
        """Block until the evaluator job reaches a terminal platform status.

        Raises:
            RuntimeError: If the job reaches a terminal failure status.
            TimeoutError: If polling exceeds configured timeouts.
        """
        status = _poll_until_terminal(
            self.get_job_status,
            job_name=self.name,
            timeout=job_timeout_seconds,
            pending_timeout=pending_timeout_seconds,
            poll_interval=poll_interval_seconds,
        )
        _raise_for_terminal_status(status)

    def get_result(self, aggregate_fields: tuple[AggregateFieldName, ...] | None = None) -> EvaluationResult:
        """Get aggregate and row-score artifacts as an ``EvaluationResult``."""
        aggregate_response = self._http_client.get(
            http_utils.job_route_resource_url(
                job_base_url=self._job_base_url,
                resource_path=_RES_AGGREGATE_DOWNLOAD,
            ),
            headers=self._headers,
        )
        aggregate_response.raise_for_status()
        row_scores_response = self._http_client.get(
            http_utils.job_route_resource_url(
                job_base_url=self._job_base_url,
                resource_path=_RES_ROW_SCORES_DOWNLOAD,
            ),
            headers=self._headers,
        )
        row_scores_response.raise_for_status()
        aggregate_scores = filter_aggregate_scores(
            _coerce_aggregate_scores(cast(_AggregateScoresPayload, aggregate_response.json())),
            aggregate_fields,
        )
        return EvaluationResult(
            row_scores=_parse_row_scores_jsonl(row_scores_response.text),
            aggregate_scores=aggregate_scores,
        )

    def download_artifacts(self, path: Path | str | None = None) -> Path:
        """Download and extract the full evaluator job artifacts tarball.

        Args:
            path: Base output directory. Defaults to the current directory.

        Returns:
            The job-specific directory that contains the extracted artifacts.
        """
        response = self._http_client.get(
            http_utils.job_route_resource_url(
                job_base_url=self._job_base_url,
                resource_path=_RES_ARTIFACTS_DOWNLOAD,
            ),
            headers=self._headers,
        )
        response.raise_for_status()
        return _extract_artifacts_tarball(
            response.content,
            _artifact_output_path(path, self.name),
        )

    def as_async(self) -> AsyncEvaluatorJobResource:
        """Return an async resource view that shares this resource's job and HTTP client."""
        return AsyncEvaluatorJobResource(
            job=self._job,
            http_client=self._http_client,
            base_url=self._base_url,
            workspace=self._workspace,
            headers=self._headers,
        )


class AsyncEvaluatorJobResource:
    """Async high-level SDK handle for a submitted evaluator plugin job."""

    def __init__(
        self,
        *,
        job: EvaluatorJob,
        http_client: _AsyncHTTPClient,
        base_url: str,
        workspace: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Store the job identity and HTTP client used for async status and result calls."""
        self._job = job
        self._http_client = http_client
        self._base_url = http_utils.base_url(base_url)
        self._workspace = workspace
        self._headers = dict(headers or {})
        self._job_base_url = http_utils.job_route_base_url(
            raw_base_url=self._base_url,
            workspace=self._workspace,
            job_name=self.name,
        )

    @property
    def name(self) -> str:
        """Return the evaluator job name."""
        return self._job.name

    @property
    def job(self) -> EvaluatorJob:
        """Return the raw evaluator job payload captured at resource creation."""
        return self._job

    async def get_job_status(self) -> PlatformJobStatusResponse:
        """Fetch the current evaluator job status from the evaluator plugin API."""
        response = await self._get(
            http_utils.job_route_resource_url(job_base_url=self._job_base_url, resource_path=_RES_STATUS)
        )
        response.raise_for_status()
        return PlatformJobStatusResponse.model_validate(response.json())

    async def check_if_complete(self, *, raise_if_not_complete: bool = False) -> bool:
        """Return whether the evaluator job has completed.

        Args:
            raise_if_not_complete: When true, raise ``RuntimeError`` for any
                status other than ``completed``.

        Returns:
            ``True`` only when the current status is ``completed``.
        """
        return _status_is_complete(await self.get_job_status(), raise_if_not_complete)

    async def wait_until_done(
        self,
        *,
        poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
        job_timeout_seconds: float = _DEFAULT_JOB_TIMEOUT_SECONDS,
        pending_timeout_seconds: float = _DEFAULT_PENDING_TIMEOUT_SECONDS,
    ) -> None:
        """Wait until the evaluator job reaches a terminal platform status.

        Raises:
            RuntimeError: If the job reaches a terminal failure status.
            TimeoutError: If polling exceeds configured timeouts.
        """
        status = await async_poll_until_terminal(
            self.get_job_status,
            status_value=metric_job_status_value,
            details_value=metric_job_status_details_value,
            job_name=self.name,
            terminal=_TERMINAL_STATUSES,
            timeout=job_timeout_seconds,
            pending_timeout=pending_timeout_seconds,
            poll_interval=poll_interval_seconds,
        )
        _raise_for_terminal_status(status)

    async def get_result(
        self,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult:
        """Get aggregate and row-score artifacts as an ``EvaluationResult``.

        Aggregate and row-score downloads are dispatched concurrently so a slow
        artifact never serializes the other.
        """
        aggregate_response, row_scores_response = await asyncio.gather(
            self._get(
                http_utils.job_route_resource_url(
                    job_base_url=self._job_base_url,
                    resource_path=_RES_AGGREGATE_DOWNLOAD,
                )
            ),
            self._get(
                http_utils.job_route_resource_url(
                    job_base_url=self._job_base_url,
                    resource_path=_RES_ROW_SCORES_DOWNLOAD,
                )
            ),
        )
        aggregate_response.raise_for_status()
        row_scores_response.raise_for_status()
        aggregate_scores = filter_aggregate_scores(
            _coerce_aggregate_scores(cast(_AggregateScoresPayload, aggregate_response.json())),
            aggregate_fields,
        )
        return EvaluationResult(
            row_scores=_parse_row_scores_jsonl(row_scores_response.text),
            aggregate_scores=aggregate_scores,
        )

    async def download_artifacts(self, path: Path | str | None = None) -> Path:
        """Download and extract the full evaluator job artifacts tarball.

        Args:
            path: Base output directory. Defaults to the current directory.

        Returns:
            The job-specific directory that contains the extracted artifacts.
        """
        response = await self._get(
            http_utils.job_route_resource_url(
                job_base_url=self._job_base_url,
                resource_path=_RES_ARTIFACTS_DOWNLOAD,
            )
        )
        response.raise_for_status()
        return await asyncio.to_thread(
            _extract_artifacts_tarball,
            response.content,
            _artifact_output_path(path, self.name),
        )

    async def _get(self, url: str) -> httpx.Response:
        """Run one HTTP GET without blocking the event loop for sync clients."""
        if isinstance(self._http_client, httpx.Client):
            return await asyncio.to_thread(self._http_client.get, url, headers=self._headers)
        return await self._http_client.get(url, headers=self._headers)
