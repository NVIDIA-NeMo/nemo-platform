# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK sub-resources for on-demand Insights analysis runs.

Mounted as ``client.insights.analysis_runs``. Each method maps 1:1 onto the
FastAPI routes in :mod:`nemo_insights_plugin.analysis_runs`, plus one
convenience verb — :meth:`_AnalysisRunResource.wait` — that polls ``get``
until the backing job reaches a terminal state. Waiting belongs here rather
than in each caller because the run/job link is derived from the shared name:
a caller polling on its own would have to know that rule.
"""

import asyncio
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

from nemo_insights_plugin.entities import AnalysisRun
from nemo_insights_plugin.schema import (
    AnalysisRunPage,
    AnalysisRunResponse,
    CreateAnalysisRunRequest,
)
from nemo_insights_plugin.sdk_resources._entity import entity_from_response, hydrate_page

DEFAULT_WAIT_TIMEOUT = 900.0
DEFAULT_POLL_INTERVAL = 5.0


class AnalysisRunNotSubmittedError(RuntimeError):
    """No job exists under the run's name, so waiting on it would never end.

    Insights names a run before submitting its job and the job takes that same
    name, so a missing job is proof the submission never landed — a resubmit
    case, not a slow one.
    """


class AnalysisRunTimeoutError(TimeoutError):
    """The backing job did not reach a terminal state within the wait budget."""


class _ResourceParent(Protocol):
    """The slice of the insights SDK namespace this sub-resource needs."""

    _http_client: Any

    def _url(self, path: str) -> str: ...


def _build_create_body(
    *,
    agent: str,
    default_model: str,
    fast_model: str,
    ethos: str | None,
    since: datetime | None,
    evaluation_id: str | None,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    body = CreateAnalysisRunRequest(
        agent=agent,
        default_model=default_model,
        fast_model=fast_model,
        ethos=ethos,
        since=since,
        evaluation_id=evaluation_id,
        timeout_seconds=timeout_seconds,
    )
    return body.model_dump(mode="json", exclude_none=True)


def _list_params(
    *,
    page: int,
    page_size: int,
    sort: str,
    agent: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "page_size": page_size, "sort": sort}
    if agent is not None:
        params["agent"] = agent
    return params


def _run_response_from_response(data: dict[str, Any]) -> AnalysisRunResponse:
    """Parse a run-plus-job body, preserving the run's store-assigned metadata."""
    response = AnalysisRunResponse.model_validate(data)
    raw_run = data.get("run")
    if isinstance(raw_run, dict):
        response.run = entity_from_response(AnalysisRun, raw_run)
    return response


def _page_from_response(data: dict[str, Any]) -> AnalysisRunPage:
    page = AnalysisRunPage.model_validate(data)
    hydrate_page(page.data, data.get("data"))
    return page


def _wait_deadline(timeout: float) -> float:
    return time.monotonic() + timeout


def _timed_out(deadline: float) -> bool:
    return time.monotonic() >= deadline


def _check_waitable(response: AnalysisRunResponse) -> None:
    if response.job is None:
        raise AnalysisRunNotSubmittedError(
            f"Analysis run '{response.run.name}' has no backing job — its submission never "
            "landed, so it will never reach a terminal state. Resubmit it."
        )


def _wait_timeout_error(response: AnalysisRunResponse, timeout: float) -> AnalysisRunTimeoutError:
    return AnalysisRunTimeoutError(
        f"Analysis run '{response.run.name}' did not finish within {timeout}s "
        f"(last job status: {response.job_status!r})."
    )


class _AnalysisRunResource:
    """Sync ``analysis_runs`` sub-resource."""

    def __init__(self, parent: _ResourceParent) -> None:
        self._parent = parent

    def create(
        self,
        *,
        workspace: str,
        agent: str,
        default_model: str,
        fast_model: str,
        ethos: str | None = None,
        since: datetime | None = None,
        evaluation_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> AnalysisRunResponse:
        """Submit an analysis run. The model pair is required — see the route."""
        response = self._parent._http_client.post(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-runs"),
            json=_build_create_body(
                agent=agent,
                default_model=default_model,
                fast_model=fast_model,
                ethos=ethos,
                since=since,
                evaluation_id=evaluation_id,
                timeout_seconds=timeout_seconds,
            ),
        )
        response.raise_for_status()
        return _run_response_from_response(response.json())

    def list_runs(
        self,
        *,
        workspace: str,
        page: int = 1,
        page_size: int = 20,
        sort: str = "-created_at",
        agent: str | None = None,
    ) -> AnalysisRunPage:
        """List analysis runs. Job state is not joined — read one run to get it."""
        response = self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-runs"),
            params=_list_params(page=page, page_size=page_size, sort=sort, agent=agent),
        )
        response.raise_for_status()
        return _page_from_response(response.json())

    def get(self, *, workspace: str, name: str) -> AnalysisRunResponse:
        """Get one analysis run joined with the live state of its backing job."""
        response = self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-runs/{name}"),
        )
        response.raise_for_status()
        return _run_response_from_response(response.json())

    def wait(
        self,
        *,
        workspace: str,
        name: str,
        timeout: float = DEFAULT_WAIT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        on_status: Callable[[str | None], None] | None = None,
    ) -> AnalysisRunResponse:
        """Poll a run until its job finishes, then return the final state.

        Raises :class:`AnalysisRunNotSubmittedError` if the run has no job and
        :class:`AnalysisRunTimeoutError` if *timeout* elapses first.
        """
        deadline = _wait_deadline(timeout)
        last_status: str | None = ""
        while True:
            response = self.get(workspace=workspace, name=name)
            _check_waitable(response)
            if on_status is not None and response.job_status != last_status:
                on_status(response.job_status)
            last_status = response.job_status
            if response.job_is_terminal:
                return response
            if _timed_out(deadline):
                raise _wait_timeout_error(response, timeout)
            time.sleep(poll_interval)


class _AsyncAnalysisRunResource:
    """Async ``analysis_runs`` sub-resource — mirrors :class:`_AnalysisRunResource`."""

    def __init__(self, parent: _ResourceParent) -> None:
        self._parent = parent

    async def create(
        self,
        *,
        workspace: str,
        agent: str,
        default_model: str,
        fast_model: str,
        ethos: str | None = None,
        since: datetime | None = None,
        evaluation_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> AnalysisRunResponse:
        """Submit an analysis run. The model pair is required — see the route."""
        response = await self._parent._http_client.post(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-runs"),
            json=_build_create_body(
                agent=agent,
                default_model=default_model,
                fast_model=fast_model,
                ethos=ethos,
                since=since,
                evaluation_id=evaluation_id,
                timeout_seconds=timeout_seconds,
            ),
        )
        response.raise_for_status()
        return _run_response_from_response(response.json())

    async def list_runs(
        self,
        *,
        workspace: str,
        page: int = 1,
        page_size: int = 20,
        sort: str = "-created_at",
        agent: str | None = None,
    ) -> AnalysisRunPage:
        """List analysis runs. Job state is not joined — read one run to get it."""
        response = await self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-runs"),
            params=_list_params(page=page, page_size=page_size, sort=sort, agent=agent),
        )
        response.raise_for_status()
        return _page_from_response(response.json())

    async def get(self, *, workspace: str, name: str) -> AnalysisRunResponse:
        """Get one analysis run joined with the live state of its backing job."""
        response = await self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-runs/{name}"),
        )
        response.raise_for_status()
        return _run_response_from_response(response.json())

    async def wait(
        self,
        *,
        workspace: str,
        name: str,
        timeout: float = DEFAULT_WAIT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        on_status: Callable[[str | None], None] | None = None,
    ) -> AnalysisRunResponse:
        """Poll a run until its job finishes, then return the final state.

        Raises :class:`AnalysisRunNotSubmittedError` if the run has no job and
        :class:`AnalysisRunTimeoutError` if *timeout* elapses first.
        """
        deadline = _wait_deadline(timeout)
        last_status: str | None = ""
        while True:
            response = await self.get(workspace=workspace, name=name)
            _check_waitable(response)
            if on_status is not None and response.job_status != last_status:
                on_status(response.job_status)
            last_status = response.job_status
            if response.job_is_terminal:
                return response
            if _timed_out(deadline):
                raise _wait_timeout_error(response, timeout)
            await asyncio.sleep(poll_interval)


__all__ = [
    "AnalysisRunNotSubmittedError",
    "AnalysisRunTimeoutError",
    "_AnalysisRunResource",
    "_AsyncAnalysisRunResource",
]
