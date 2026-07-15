# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK sub-resources for periodic analysis opt-in configs and run status."""

from datetime import datetime
from typing import Any, Protocol

from nemo_insights_plugin.entities import (
    AnalysisConfig,
    AnalysisConfigStatus,
    AnalysisRunStatus,
)
from nemo_insights_plugin.schema import (
    AnalysisConfigPage,
    AnalysisRunStatusPage,
    UpdateAnalysisConfigRequest,
    UpdateAnalysisRunStatusRequest,
)
from nemo_insights_plugin.sdk_resources._entity import entity_from_response, hydrate_page


class _ResourceParent(Protocol):
    """The slice of the insights SDK namespace this sub-resource needs."""

    _http_client: Any

    def _url(self, path: str) -> str: ...


def _list_params(
    *,
    page: int,
    page_size: int,
    sort: str,
    enabled: bool | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "page_size": page_size, "sort": sort}
    if enabled is not None:
        params["enabled"] = enabled
    return params


def _build_update_body(
    *,
    enabled: bool | None,
) -> dict[str, Any]:
    body = UpdateAnalysisConfigRequest(enabled=enabled)
    return body.model_dump(mode="json", exclude_none=True, exclude_unset=True)


def _build_status_update_body(
    *,
    status: AnalysisConfigStatus | str | None,
    last_successful_run_at: datetime | None,
    last_attempted_at: datetime | None,
    last_completed_at: datetime | None,
    last_submitted_job: str | None,
    last_error: str | None,
) -> dict[str, Any]:
    body = UpdateAnalysisRunStatusRequest(
        status=AnalysisConfigStatus(status) if isinstance(status, str) else status,
        last_successful_run_at=last_successful_run_at,
        last_attempted_at=last_attempted_at,
        last_completed_at=last_completed_at,
        last_submitted_job=last_submitted_job,
        last_error=last_error,
    )
    return body.model_dump(mode="json", exclude_none=True, exclude_unset=True)


def _analysis_config_page_from_response(data: dict[str, Any]) -> AnalysisConfigPage:
    page = AnalysisConfigPage.model_validate(data)
    hydrate_page(page.data, data.get("data"))
    return page


def _analysis_run_status_page_from_response(data: dict[str, Any]) -> AnalysisRunStatusPage:
    page = AnalysisRunStatusPage.model_validate(data)
    hydrate_page(page.data, data.get("data"))
    return page


class _AnalysisConfigResource:
    """Sync ``analysis_configs`` sub-resource."""

    def __init__(self, parent: _ResourceParent) -> None:
        self._parent = parent

    def enable(self, *, workspace: str, agent: str) -> AnalysisConfig:
        response = self._parent._http_client.post(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-configs/{agent}/enable")
        )
        response.raise_for_status()
        return entity_from_response(AnalysisConfig, response.json())

    def disable(self, *, workspace: str, agent: str) -> AnalysisConfig:
        response = self._parent._http_client.post(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-configs/{agent}/disable")
        )
        response.raise_for_status()
        return entity_from_response(AnalysisConfig, response.json())

    def list_configs(
        self,
        *,
        workspace: str,
        page: int = 1,
        page_size: int = 20,
        sort: str = "-created_at",
        enabled: bool | None = None,
    ) -> AnalysisConfigPage:
        response = self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-configs"),
            params=_list_params(page=page, page_size=page_size, sort=sort, enabled=enabled),
        )
        response.raise_for_status()
        return _analysis_config_page_from_response(response.json())

    def get(self, *, workspace: str, agent: str) -> AnalysisConfig:
        response = self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-configs/{agent}")
        )
        response.raise_for_status()
        return entity_from_response(AnalysisConfig, response.json())

    def update(
        self,
        *,
        workspace: str,
        agent: str,
        enabled: bool | None = None,
    ) -> AnalysisConfig:
        response = self._parent._http_client.patch(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-configs/{agent}"),
            json=_build_update_body(enabled=enabled),
        )
        response.raise_for_status()
        return entity_from_response(AnalysisConfig, response.json())


class _AsyncAnalysisConfigResource:
    """Async ``analysis_configs`` sub-resource."""

    def __init__(self, parent: _ResourceParent) -> None:
        self._parent = parent

    async def enable(self, *, workspace: str, agent: str) -> AnalysisConfig:
        response = await self._parent._http_client.post(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-configs/{agent}/enable")
        )
        response.raise_for_status()
        return entity_from_response(AnalysisConfig, response.json())

    async def disable(self, *, workspace: str, agent: str) -> AnalysisConfig:
        response = await self._parent._http_client.post(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-configs/{agent}/disable")
        )
        response.raise_for_status()
        return entity_from_response(AnalysisConfig, response.json())

    async def list_configs(
        self,
        *,
        workspace: str,
        page: int = 1,
        page_size: int = 20,
        sort: str = "-created_at",
        enabled: bool | None = None,
    ) -> AnalysisConfigPage:
        response = await self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-configs"),
            params=_list_params(page=page, page_size=page_size, sort=sort, enabled=enabled),
        )
        response.raise_for_status()
        return _analysis_config_page_from_response(response.json())

    async def get(self, *, workspace: str, agent: str) -> AnalysisConfig:
        response = await self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-configs/{agent}")
        )
        response.raise_for_status()
        return entity_from_response(AnalysisConfig, response.json())

    async def update(
        self,
        *,
        workspace: str,
        agent: str,
        enabled: bool | None = None,
    ) -> AnalysisConfig:
        response = await self._parent._http_client.patch(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-configs/{agent}"),
            json=_build_update_body(enabled=enabled),
        )
        response.raise_for_status()
        return entity_from_response(AnalysisConfig, response.json())


class _AnalysisRunStatusResource:
    """Sync ``analysis_run_statuses`` sub-resource."""

    def __init__(self, parent: _ResourceParent) -> None:
        self._parent = parent

    def list_statuses(
        self,
        *,
        workspace: str,
        page: int = 1,
        page_size: int = 20,
        sort: str = "-updated_at",
    ) -> AnalysisRunStatusPage:
        response = self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-run-statuses"),
            params={"page": page, "page_size": page_size, "sort": sort},
        )
        response.raise_for_status()
        return _analysis_run_status_page_from_response(response.json())

    def get(self, *, workspace: str, agent: str) -> AnalysisRunStatus:
        response = self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-run-statuses/{agent}")
        )
        response.raise_for_status()
        return entity_from_response(AnalysisRunStatus, response.json())

    def update(
        self,
        *,
        workspace: str,
        agent: str,
        status: AnalysisConfigStatus | str | None = None,
        last_successful_run_at: datetime | None = None,
        last_attempted_at: datetime | None = None,
        last_completed_at: datetime | None = None,
        last_submitted_job: str | None = None,
        last_error: str | None = None,
    ) -> AnalysisRunStatus:
        response = self._parent._http_client.patch(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-run-statuses/{agent}"),
            json=_build_status_update_body(
                status=status,
                last_successful_run_at=last_successful_run_at,
                last_attempted_at=last_attempted_at,
                last_completed_at=last_completed_at,
                last_submitted_job=last_submitted_job,
                last_error=last_error,
            ),
        )
        response.raise_for_status()
        return entity_from_response(AnalysisRunStatus, response.json())


class _AsyncAnalysisRunStatusResource:
    """Async ``analysis_run_statuses`` sub-resource."""

    def __init__(self, parent: _ResourceParent) -> None:
        self._parent = parent

    async def list_statuses(
        self,
        *,
        workspace: str,
        page: int = 1,
        page_size: int = 20,
        sort: str = "-updated_at",
    ) -> AnalysisRunStatusPage:
        response = await self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-run-statuses"),
            params={"page": page, "page_size": page_size, "sort": sort},
        )
        response.raise_for_status()
        return _analysis_run_status_page_from_response(response.json())

    async def get(self, *, workspace: str, agent: str) -> AnalysisRunStatus:
        response = await self._parent._http_client.get(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-run-statuses/{agent}")
        )
        response.raise_for_status()
        return entity_from_response(AnalysisRunStatus, response.json())

    async def update(
        self,
        *,
        workspace: str,
        agent: str,
        status: AnalysisConfigStatus | str | None = None,
        last_successful_run_at: datetime | None = None,
        last_attempted_at: datetime | None = None,
        last_completed_at: datetime | None = None,
        last_submitted_job: str | None = None,
        last_error: str | None = None,
    ) -> AnalysisRunStatus:
        response = await self._parent._http_client.patch(
            self._parent._url(f"/v2/workspaces/{workspace}/analysis-run-statuses/{agent}"),
            json=_build_status_update_body(
                status=status,
                last_successful_run_at=last_successful_run_at,
                last_attempted_at=last_attempted_at,
                last_completed_at=last_completed_at,
                last_submitted_job=last_submitted_job,
                last_error=last_error,
            ),
        )
        response.raise_for_status()
        return entity_from_response(AnalysisRunStatus, response.json())


__all__ = [
    "_AnalysisConfigResource",
    "_AnalysisRunStatusResource",
    "_AsyncAnalysisConfigResource",
    "_AsyncAnalysisRunStatusResource",
]
