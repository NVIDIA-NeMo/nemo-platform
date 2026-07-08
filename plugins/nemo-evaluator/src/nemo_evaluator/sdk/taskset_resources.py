# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for managing stored tasksets (``client.evaluator.tasksets``).

Thin client over the evaluator service's ``/tasksets`` create/get/list/delete API. A taskset is sent
as a :class:`TasksetInput` (its members as references to stored tasks) and returned as the
:class:`Taskset` DTO; the service owns persistence in the entity store.
"""

from __future__ import annotations

from urllib.parse import quote

from nemo_evaluator.api.schemas import Taskset, TasksetInput
from nemo_evaluator.sdk import http_utils
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.schema import Page


def _list_params(page: int, page_size: int, sort: str | None) -> dict[str, str | int]:
    params: dict[str, str | int] = {"page": page, "page_size": page_size}
    if sort is not None:
        params["sort"] = sort
    return params


class EvaluatorTasksetsResource:
    """Sync resource mounted as ``client.evaluator.tasksets``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    def _headers(self) -> dict[str, str]:
        return http_utils.platform_default_headers(self._platform)

    def _collection_url(self, workspace: str | None) -> str:
        return http_utils.url(self._platform, "/v2/workspaces/{workspace}/tasksets", workspace)

    def _item_url(self, name: str, workspace: str | None) -> str:
        return http_utils.url(
            self._platform, f"/v2/workspaces/{{workspace}}/tasksets/{quote(name, safe='')}", workspace
        )

    def create(
        self, name: str, *, taskset: TasksetInput, project: str | None = None, workspace: str | None = None
    ) -> Taskset:
        """Store a new taskset (addressed by workspace/name)."""
        response = self._http_client.post(
            self._item_url(name, workspace),
            json=taskset.model_dump(mode="json"),
            params={"project": project} if project is not None else None,
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Taskset.model_validate(response.json())

    def retrieve(self, name: str, *, workspace: str | None = None) -> Taskset:
        """Get a stored taskset by name."""
        response = self._http_client.get(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()
        return Taskset.model_validate(response.json())

    def list(
        self, *, workspace: str | None = None, page: int = 1, page_size: int = 100, sort: str | None = None
    ) -> Page[Taskset]:
        """List stored tasksets in a workspace."""
        response = self._http_client.get(
            self._collection_url(workspace),
            params=_list_params(page, page_size, sort),
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Page[Taskset].model_validate(response.json())

    def delete(self, name: str, *, workspace: str | None = None) -> None:
        """Delete a stored taskset by name."""
        response = self._http_client.delete(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()


class AsyncEvaluatorTasksetsResource:
    """Async resource mounted as ``client.evaluator.tasksets``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    def _headers(self) -> dict[str, str]:
        return http_utils.platform_default_headers(self._platform)

    def _collection_url(self, workspace: str | None) -> str:
        return http_utils.url(self._platform, "/v2/workspaces/{workspace}/tasksets", workspace)

    def _item_url(self, name: str, workspace: str | None) -> str:
        return http_utils.url(
            self._platform, f"/v2/workspaces/{{workspace}}/tasksets/{quote(name, safe='')}", workspace
        )

    async def create(
        self, name: str, *, taskset: TasksetInput, project: str | None = None, workspace: str | None = None
    ) -> Taskset:
        """Store a new taskset (addressed by workspace/name)."""
        response = await self._http_client.post(
            self._item_url(name, workspace),
            json=taskset.model_dump(mode="json"),
            params={"project": project} if project is not None else None,
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Taskset.model_validate(response.json())

    async def retrieve(self, name: str, *, workspace: str | None = None) -> Taskset:
        """Get a stored taskset by name."""
        response = await self._http_client.get(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()
        return Taskset.model_validate(response.json())

    async def list(
        self, *, workspace: str | None = None, page: int = 1, page_size: int = 100, sort: str | None = None
    ) -> Page[Taskset]:
        """List stored tasksets in a workspace."""
        response = await self._http_client.get(
            self._collection_url(workspace),
            params=_list_params(page, page_size, sort),
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Page[Taskset].model_validate(response.json())

    async def delete(self, name: str, *, workspace: str | None = None) -> None:
        """Delete a stored taskset by name."""
        response = await self._http_client.delete(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()
