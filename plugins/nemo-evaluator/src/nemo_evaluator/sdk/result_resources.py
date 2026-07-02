# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for reading persisted eval results.

Mounted as ``client.evaluator.agent_eval_results`` and ``client.evaluator.eval_results``. Results are
written by the jobs (not the SDK), so these resources are read-only: ``retrieve`` / ``list`` /
``delete`` against the evaluator service's ``/agent-eval-results`` and ``/eval-results`` routes,
returning the :class:`AgentEvalResult` / :class:`EvaluateResult` API DTOs.

``list`` mirrors the routes' trait filtering: equality filters on the persisted traits (``job_id``,
``target_kind``, ``target_name``, and ``dataset_ref`` for row results) are sent as the route's
``filter[field]=value`` query params. (Datetime-range filtering, which the routes also support, needs
a richer operator shape and isn't surfaced here yet.)
"""

from __future__ import annotations

from typing import ClassVar, Generic, TypeVar
from urllib.parse import quote

from nemo_evaluator.api.schemas import AgentEvalResult, EvaluateResult
from nemo_evaluator.sdk import http_utils
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.schema import Page, PaginationData

_ResultT = TypeVar("_ResultT", AgentEvalResult, EvaluateResult)


def _query_params(page: int, page_size: int, sort: str | None, filters: dict[str, str | None]) -> dict[str, str | int]:
    """Build the list query string: paging/sort + the route's ``filter[field]=value`` trait filters."""
    params: dict[str, str | int] = {"page": page, "page_size": page_size}
    if sort is not None:
        params["sort"] = sort
    for field, value in filters.items():
        if value is not None:
            params[f"filter[{field}]"] = value
    return params


def _to_page(payload: dict, model: type[_ResultT], sort: str | None) -> Page[_ResultT]:
    """Rebuild a typed ``Page`` from the route's JSON, deserializing each item as ``model``."""
    pagination = payload["pagination"]
    return Page(
        data=[model.model_validate(item) for item in payload["data"]],
        pagination=PaginationData(
            page=pagination["page"],
            page_size=pagination["page_size"],
            current_page_size=pagination["current_page_size"],
            total_pages=pagination["total_pages"],
            total_results=pagination["total_results"],
        ),
        sort=sort,
        filter=None,
    )


class _SyncResultsResource(Generic[_ResultT]):
    """Read-only sync resource for one result collection. Concrete subclasses declare ``list``."""

    _collection: ClassVar[str]
    _model: type[_ResultT]

    def __init__(self, platform: NeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    def _headers(self) -> dict[str, str]:
        return http_utils.platform_default_headers(self._platform)

    def _collection_url(self, workspace: str | None) -> str:
        return http_utils.url(self._platform, f"/v2/workspaces/{{workspace}}/{self._collection}", workspace)

    def _item_url(self, name: str, workspace: str | None) -> str:
        return http_utils.url(
            self._platform, f"/v2/workspaces/{{workspace}}/{self._collection}/{quote(name, safe='')}", workspace
        )

    def retrieve(self, name: str, *, workspace: str | None = None) -> _ResultT:
        """Get a result record by name (the producing job's id)."""
        response = self._http_client.get(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()
        return self._model.model_validate(response.json())

    def _list(
        self, *, workspace: str | None, page: int, page_size: int, sort: str | None, filters: dict[str, str | None]
    ) -> Page[_ResultT]:
        response = self._http_client.get(
            self._collection_url(workspace),
            params=_query_params(page, page_size, sort, filters),
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return _to_page(response.json(), self._model, sort)

    def delete(self, name: str, *, workspace: str | None = None) -> None:
        """Delete a result record by name."""
        response = self._http_client.delete(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()


class _AsyncResultsResource(Generic[_ResultT]):
    """Read-only async resource for one result collection. Concrete subclasses declare ``list``."""

    _collection: ClassVar[str]
    _model: type[_ResultT]

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    def _headers(self) -> dict[str, str]:
        return http_utils.platform_default_headers(self._platform)

    def _collection_url(self, workspace: str | None) -> str:
        return http_utils.url(self._platform, f"/v2/workspaces/{{workspace}}/{self._collection}", workspace)

    def _item_url(self, name: str, workspace: str | None) -> str:
        return http_utils.url(
            self._platform, f"/v2/workspaces/{{workspace}}/{self._collection}/{quote(name, safe='')}", workspace
        )

    async def retrieve(self, name: str, *, workspace: str | None = None) -> _ResultT:
        """Get a result record by name (the producing job's id)."""
        response = await self._http_client.get(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()
        return self._model.model_validate(response.json())

    async def _list(
        self, *, workspace: str | None, page: int, page_size: int, sort: str | None, filters: dict[str, str | None]
    ) -> Page[_ResultT]:
        response = await self._http_client.get(
            self._collection_url(workspace),
            params=_query_params(page, page_size, sort, filters),
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return _to_page(response.json(), self._model, sort)

    async def delete(self, name: str, *, workspace: str | None = None) -> None:
        """Delete a result record by name."""
        response = await self._http_client.delete(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()


class EvaluatorAgentEvalResultsResource(_SyncResultsResource[AgentEvalResult]):
    """Sync resource mounted as ``client.evaluator.agent_eval_results``."""

    _collection = "agent-eval-results"
    _model = AgentEvalResult

    def list(
        self,
        *,
        workspace: str | None = None,
        page: int = 1,
        page_size: int = 100,
        sort: str | None = None,
        job_id: str | None = None,
        target_kind: str | None = None,
        target_name: str | None = None,
    ) -> Page[AgentEvalResult]:
        """List agent-eval results, optionally filtered by job/target traits."""
        return self._list(
            workspace=workspace,
            page=page,
            page_size=page_size,
            sort=sort,
            filters={"job_id": job_id, "target_kind": target_kind, "target_name": target_name},
        )


class EvaluatorEvalResultsResource(_SyncResultsResource[EvaluateResult]):
    """Sync resource mounted as ``client.evaluator.eval_results``."""

    _collection = "eval-results"
    _model = EvaluateResult

    def list(
        self,
        *,
        workspace: str | None = None,
        page: int = 1,
        page_size: int = 100,
        sort: str | None = None,
        job_id: str | None = None,
        target_kind: str | None = None,
        target_name: str | None = None,
        dataset_ref: str | None = None,
    ) -> Page[EvaluateResult]:
        """List row-eval results, optionally filtered by job/target/dataset traits."""
        return self._list(
            workspace=workspace,
            page=page,
            page_size=page_size,
            sort=sort,
            filters={
                "job_id": job_id,
                "target_kind": target_kind,
                "target_name": target_name,
                "dataset_ref": dataset_ref,
            },
        )


class AsyncEvaluatorAgentEvalResultsResource(_AsyncResultsResource[AgentEvalResult]):
    """Async resource mounted as ``client.evaluator.agent_eval_results``."""

    _collection = "agent-eval-results"
    _model = AgentEvalResult

    async def list(
        self,
        *,
        workspace: str | None = None,
        page: int = 1,
        page_size: int = 100,
        sort: str | None = None,
        job_id: str | None = None,
        target_kind: str | None = None,
        target_name: str | None = None,
    ) -> Page[AgentEvalResult]:
        """List agent-eval results, optionally filtered by job/target traits."""
        return await self._list(
            workspace=workspace,
            page=page,
            page_size=page_size,
            sort=sort,
            filters={"job_id": job_id, "target_kind": target_kind, "target_name": target_name},
        )


class AsyncEvaluatorEvalResultsResource(_AsyncResultsResource[EvaluateResult]):
    """Async resource mounted as ``client.evaluator.eval_results``."""

    _collection = "eval-results"
    _model = EvaluateResult

    async def list(
        self,
        *,
        workspace: str | None = None,
        page: int = 1,
        page_size: int = 100,
        sort: str | None = None,
        job_id: str | None = None,
        target_kind: str | None = None,
        target_name: str | None = None,
        dataset_ref: str | None = None,
    ) -> Page[EvaluateResult]:
        """List row-eval results, optionally filtered by job/target/dataset traits."""
        return await self._list(
            workspace=workspace,
            page=page,
            page_size=page_size,
            sort=sort,
            filters={
                "job_id": job_id,
                "target_kind": target_kind,
                "target_name": target_name,
                "dataset_ref": dataset_ref,
            },
        )
