# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job handles for agent evaluations running on the platform.

These satisfy :class:`~nemo_evaluator_sdk.execution.jobs.EvaluationJob` structurally, so the SDK
never imports the plugin. They mirror the dataset handles in
:mod:`nemo_evaluator.sdk.job_resources`, with one addition: the handle carries the taskset it was
submitted with. Result reassembly needs the caller's live tasks because a persisted task's metrics
are serialized as descriptors that cannot be validated back into ``Metric`` objects, and holding
them here means no caller has to know that.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from nemo_evaluator.sdk._agent_eval_bundle import assemble_result, read_bundle
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask
from nemo_evaluator_sdk.execution.jobs import (
    DEFAULT_JOB_TIMEOUT_SECONDS,
    DEFAULT_PENDING_TIMEOUT_SECONDS,
    DEFAULT_POLL_INTERVAL_SECONDS,
)

#: Job-collection segment these routes hang off. Distinct from the row collection
#: (``evaluate/jobs``) because the two job types validate different specs; posting to the wrong one
#: fails at validation.
COLLECTION = "agent-evaluate/jobs"

#: Result artifact holding the whole run bundle, as ``AgentEvalJob`` names it when saving.
_BUNDLE_DOWNLOAD = "results/agent-eval-results/download"

#: The run's rollup, saved alongside the bundle. Fixed size regardless of how many tasks ran,
#: where the bundle grows with every trial, so a caller that only needs scores can skip the rest.
_SUMMARY_DOWNLOAD = "results/summary/download"

_TERMINAL_SUCCESS = "completed"
_TERMINAL_FAILURE = frozenset({"error", "cancelled", "failed"})
#: Statuses meaning the job exists but has not started doing work.
_PENDING = frozenset({"created", "pending", "queued", "scheduled"})


def _status_of(payload: Mapping[str, Any]) -> str:
    status = payload.get("status")
    return status.lower() if isinstance(status, str) else ""


def _is_terminal(status: str) -> bool:
    return status == _TERMINAL_SUCCESS or status in _TERMINAL_FAILURE


def _raise_for_status(job_name: str, status: str, payload: Mapping[str, Any]) -> None:
    """Raise unless the job finished successfully."""
    if status == _TERMINAL_SUCCESS:
        return
    raise RuntimeError(f"agent-eval job {job_name!r} finished with status {status!r}: {payload.get('error_details')}")


@dataclass(frozen=True)
class _JobAddress:
    """Everything needed to talk to one agent-eval job."""

    name: str
    base_url: str
    workspace: str
    headers: dict[str, str]
    #: Carried so every request is bounded. Without it a stalled status or download call hangs
    #: forever and the poll loop never reaches its own ``job_timeout_seconds`` check. Typed as
    #: httpx accepts it, since the platform's own timeout is a plain number or ``None``.
    timeout: httpx.Timeout | float | None

    def url(self, suffix: str) -> str:
        """Build a route under this job."""
        return f"{self.base_url}/v2/workspaces/{self.workspace}/{COLLECTION}/{quote(self.name, safe='')}/{suffix}"


class AgentEvalJobResource:
    """A sync handle on an agent evaluation running on the platform."""

    def __init__(
        self,
        *,
        address: _JobAddress,
        http_client: httpx.Client,
        taskset: Sequence[AgentEvalTask],
    ) -> None:
        """Store the job address, transport, and the taskset needed to rebuild the result."""
        self._address = address
        self._http_client = http_client
        self._taskset = list(taskset)

    @property
    def name(self) -> str:
        """The platform's name for this job."""
        return self._address.name

    def get_job_status(self) -> str:
        """Return the job's current platform status."""
        response = self._http_client.get(
            self._address.url("status"), headers=self._address.headers, timeout=self._address.timeout
        )
        response.raise_for_status()
        return _status_of(response.json())

    def wait_until_done(
        self,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        job_timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS,
        pending_timeout_seconds: float = DEFAULT_PENDING_TIMEOUT_SECONDS,
    ) -> None:
        """Poll until the job reaches a terminal status, raising if it did not succeed."""
        started = time.monotonic()
        while True:
            response = self._http_client.get(
                self._address.url("status"), headers=self._address.headers, timeout=self._address.timeout
            )
            response.raise_for_status()
            payload = response.json()
            status = _status_of(payload)
            if _is_terminal(status):
                _raise_for_status(self.name, status, payload)
                return
            elapsed = time.monotonic() - started
            _raise_for_timeout(self.name, status, elapsed, job_timeout_seconds, pending_timeout_seconds)
            time.sleep(poll_interval_seconds)

    def get_result(self) -> AgentEvalResult:
        """Download the run bundle and rebuild the result."""
        response = self._http_client.get(
            self._address.url(_BUNDLE_DOWNLOAD), headers=self._address.headers, timeout=self._address.timeout
        )
        response.raise_for_status()
        return assemble_result(read_bundle(response.content), tasks=self._taskset, job_name=self.name)

    def get_summary(self) -> AgentEvalSummary:
        """Download just the run's rollup.

        The cheap half of :meth:`get_result`: a fixed-size fetch for callers that only need the
        scores, such as a regression gate, rather than every trial the run produced.
        """
        response = self._http_client.get(
            self._address.url(_SUMMARY_DOWNLOAD), headers=self._address.headers, timeout=self._address.timeout
        )
        response.raise_for_status()
        return AgentEvalSummary.model_validate(response.json())


class AsyncAgentEvalJobResource:
    """An async handle on an agent evaluation running on the platform."""

    def __init__(
        self,
        *,
        address: _JobAddress,
        http_client: httpx.AsyncClient,
        taskset: Sequence[AgentEvalTask],
    ) -> None:
        """Store the job address, transport, and the taskset needed to rebuild the result."""
        self._address = address
        self._http_client = http_client
        self._taskset = list(taskset)

    @property
    def name(self) -> str:
        """The platform's name for this job."""
        return self._address.name

    async def _get(self, url: str) -> httpx.Response:
        response = await self._http_client.get(url, headers=self._address.headers, timeout=self._address.timeout)
        response.raise_for_status()
        return response

    async def get_job_status(self) -> str:
        """Return the job's current platform status."""
        return _status_of((await self._get(self._address.url("status"))).json())

    async def wait_until_done(
        self,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        job_timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS,
        pending_timeout_seconds: float = DEFAULT_PENDING_TIMEOUT_SECONDS,
    ) -> None:
        """Poll until the job reaches a terminal status, raising if it did not succeed."""
        loop = asyncio.get_running_loop()
        started = loop.time()
        while True:
            payload = (await self._get(self._address.url("status"))).json()
            status = _status_of(payload)
            if _is_terminal(status):
                _raise_for_status(self.name, status, payload)
                return
            elapsed = loop.time() - started
            _raise_for_timeout(self.name, status, elapsed, job_timeout_seconds, pending_timeout_seconds)
            await asyncio.sleep(poll_interval_seconds)

    async def get_result(self) -> AgentEvalResult:
        """Download the run bundle and rebuild the result."""
        response = await self._get(self._address.url(_BUNDLE_DOWNLOAD))
        contents = await asyncio.to_thread(read_bundle, response.content)
        return assemble_result(contents, tasks=self._taskset, job_name=self.name)

    async def get_summary(self) -> AgentEvalSummary:
        """Download just the run's rollup.

        See :meth:`AgentEvalJobResource.get_summary`.
        """
        return AgentEvalSummary.model_validate((await self._get(self._address.url(_SUMMARY_DOWNLOAD))).json())


def _raise_for_timeout(
    job_name: str,
    status: str,
    elapsed: float,
    job_timeout_seconds: float,
    pending_timeout_seconds: float,
) -> None:
    """Raise when the job has outrun either ceiling.

    A job stuck before it starts is a different failure from one running too long, so the pending
    ceiling is checked separately and names itself.
    """
    if status in _PENDING and elapsed >= pending_timeout_seconds:
        raise TimeoutError(f"agent-eval job {job_name!r} did not start within {pending_timeout_seconds}s")
    if elapsed >= job_timeout_seconds:
        raise TimeoutError(f"agent-eval job {job_name!r} did not finish within {job_timeout_seconds}s")
