# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK sub-resources for ``Insight`` CRUD.

Mounted as ``client.insights.insights`` (sync) and on the async client.
Each method maps 1:1 onto the FastAPI routes in
:mod:`nemo_insights_plugin.service`.
"""

from typing import Any, Protocol

from nemo_insights_plugin.entities import Insight, InsightStatus
from nemo_insights_plugin.schema import (
    CreateInsightRequest,
    InsightPage,
    UpdateInsightRequest,
)
from nemo_insights_plugin.sdk_resources._entity import entity_from_response, hydrate_page


def _insight_from_response(data: dict[str, Any]) -> Insight:
    """Parse one insight response body, preserving its store-assigned id."""
    return entity_from_response(Insight, data)


def _page_from_response(data: dict[str, Any]) -> InsightPage:
    """Parse a list response, preserving each item's store-assigned id.

    Validated items lose their ids (computed field), so we re-attach them
    positionally from the raw payload, which preserves order.
    """
    page = InsightPage.model_validate(data)
    hydrate_page(page.data, data.get("data"))
    return page


class _ResourceParent(Protocol):
    """The slice of the insights SDK namespace these sub-resources rely on.

    Both the sync and async ``InsightsPluginResource`` satisfy this — typing
    against it (rather than importing the concrete classes from
    :mod:`nemo_insights_plugin.sdk`) avoids an import cycle, since ``sdk``
    imports the resource classes defined here.
    """

    _http_client: Any

    def _url(self, path: str) -> str: ...


def _build_create_body(
    *,
    title: str,
    agent: str,
    description: str,
    status: InsightStatus | str,
    trace_refs: list[str] | None,
) -> dict[str, Any]:
    body = CreateInsightRequest(
        title=title,
        agent=agent,
        description=description,
        status=InsightStatus(status) if isinstance(status, str) else status,
        trace_refs=list(trace_refs or []),
    )
    return body.model_dump(mode="json")


def _build_update_body(
    *,
    agent: str | None,
    description: str | None,
    status: InsightStatus | str | None,
    trace_refs: list[str] | None,
) -> dict[str, Any]:
    body = UpdateInsightRequest(
        agent=agent,
        description=description,
        status=InsightStatus(status) if isinstance(status, str) else status,
        trace_refs=trace_refs,
    )
    return body.model_dump(mode="json", exclude_none=True)


def _list_params(
    *,
    page: int,
    page_size: int,
    sort: str,
    agent: str | None,
    status: InsightStatus | str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "page_size": page_size, "sort": sort}
    if agent is not None:
        params["agent"] = agent
    if status is not None:
        params["status"] = status.value if isinstance(status, InsightStatus) else status
    return params


class _InsightResource:
    """Sync ``insights`` sub-resource — five CRUD verbs."""

    def __init__(self, parent: _ResourceParent) -> None:
        self._parent = parent

    def create(
        self,
        *,
        workspace: str,
        title: str,
        agent: str,
        description: str,
        status: InsightStatus | str = InsightStatus.OPEN,
        trace_refs: list[str] | None = None,
    ) -> Insight:
        body = _build_create_body(
            title=title,
            agent=agent,
            description=description,
            status=status,
            trace_refs=trace_refs,
        )
        response = self._parent._http_client.post(
            self._parent._url(f"/v2/workspaces/{workspace}/insights"),
            json=body,
        )
        response.raise_for_status()
        return _insight_from_response(response.json())

    def list_insights(
        self,
        *,
        workspace: str,
        page: int = 1,
        page_size: int = 20,
        sort: str = "-created_at",
        agent: str | None = None,
        status: InsightStatus | str | None = None,
    ) -> InsightPage:
        response = self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/insights"),
            params=_list_params(
                page=page,
                page_size=page_size,
                sort=sort,
                agent=agent,
                status=status,
            ),
        )
        response.raise_for_status()
        return _page_from_response(response.json())

    def get(self, *, workspace: str, insight_id: str) -> Insight:
        response = self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/insights/{insight_id}"),
        )
        response.raise_for_status()
        return _insight_from_response(response.json())

    def update(
        self,
        *,
        workspace: str,
        insight_id: str,
        agent: str | None = None,
        description: str | None = None,
        status: InsightStatus | str | None = None,
        trace_refs: list[str] | None = None,
    ) -> Insight:
        body = _build_update_body(
            agent=agent,
            description=description,
            status=status,
            trace_refs=trace_refs,
        )
        response = self._parent._http_client.patch(
            self._parent._url(f"/v2/workspaces/{workspace}/insights/{insight_id}"),
            json=body,
        )
        response.raise_for_status()
        return _insight_from_response(response.json())

    def delete(self, *, workspace: str, insight_id: str) -> None:
        response = self._parent._http_client.delete(
            self._parent._url(f"/v2/workspaces/{workspace}/insights/{insight_id}"),
        )
        response.raise_for_status()


class _AsyncInsightResource:
    """Async ``insights`` sub-resource — mirrors :class:`_InsightResource`."""

    def __init__(self, parent: _ResourceParent) -> None:
        self._parent = parent

    async def create(
        self,
        *,
        workspace: str,
        title: str,
        agent: str,
        description: str,
        status: InsightStatus | str = InsightStatus.OPEN,
        trace_refs: list[str] | None = None,
    ) -> Insight:
        body = _build_create_body(
            title=title,
            agent=agent,
            description=description,
            status=status,
            trace_refs=trace_refs,
        )
        response = await self._parent._http_client.post(
            self._parent._url(f"/v2/workspaces/{workspace}/insights"),
            json=body,
        )
        response.raise_for_status()
        return _insight_from_response(response.json())

    async def list_insights(
        self,
        *,
        workspace: str,
        page: int = 1,
        page_size: int = 20,
        sort: str = "-created_at",
        agent: str | None = None,
        status: InsightStatus | str | None = None,
    ) -> InsightPage:
        response = await self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/insights"),
            params=_list_params(
                page=page,
                page_size=page_size,
                sort=sort,
                agent=agent,
                status=status,
            ),
        )
        response.raise_for_status()
        return _page_from_response(response.json())

    async def get(self, *, workspace: str, insight_id: str) -> Insight:
        response = await self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/insights/{insight_id}"),
        )
        response.raise_for_status()
        return _insight_from_response(response.json())

    async def update(
        self,
        *,
        workspace: str,
        insight_id: str,
        agent: str | None = None,
        description: str | None = None,
        status: InsightStatus | str | None = None,
        trace_refs: list[str] | None = None,
    ) -> Insight:
        body = _build_update_body(
            agent=agent,
            description=description,
            status=status,
            trace_refs=trace_refs,
        )
        response = await self._parent._http_client.patch(
            self._parent._url(f"/v2/workspaces/{workspace}/insights/{insight_id}"),
            json=body,
        )
        response.raise_for_status()
        return _insight_from_response(response.json())

    async def delete(self, *, workspace: str, insight_id: str) -> None:
        response = await self._parent._http_client.delete(
            self._parent._url(f"/v2/workspaces/{workspace}/insights/{insight_id}"),
        )
        response.raise_for_status()


__all__ = ["_AsyncInsightResource", "_InsightResource"]
