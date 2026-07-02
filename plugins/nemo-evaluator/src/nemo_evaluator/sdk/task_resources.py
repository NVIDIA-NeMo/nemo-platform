# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for managing stored agent-eval tasks (``client.evaluator.tasks``).

Thin client over the evaluator service's ``/tasks`` create/get/list/delete API. A task is sent as a
:class:`TaskInput` (its metrics inline and/or as references to stored metrics) and returned as the
:class:`Task` DTO; the service owns persistence in the entity store.
"""

from __future__ import annotations

from urllib.parse import quote

from nemo_evaluator.api.schemas import Task, TaskInput
from nemo_evaluator.sdk import http_utils
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.schema import Page


def _list_params(page: int, page_size: int, sort: str | None) -> dict[str, str | int]:
    params: dict[str, str | int] = {"page": page, "page_size": page_size}
    if sort is not None:
        params["sort"] = sort
    return params


class EvaluatorTasksResource:
    """Sync resource mounted as ``client.evaluator.tasks``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    def _headers(self) -> dict[str, str]:
        return http_utils.platform_default_headers(self._platform)

    def _collection_url(self, workspace: str | None) -> str:
        return http_utils.url(self._platform, "/v2/workspaces/{workspace}/tasks", workspace)

    def _item_url(self, name: str, workspace: str | None) -> str:
        return http_utils.url(self._platform, f"/v2/workspaces/{{workspace}}/tasks/{quote(name, safe='')}", workspace)

    def create(self, name: str, *, task: TaskInput, project: str | None = None, workspace: str | None = None) -> Task:
        """Store a new task (addressed by workspace/name)."""
        response = self._http_client.post(
            self._item_url(name, workspace),
            json=task.model_dump(mode="json"),
            params={"project": project} if project is not None else None,
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Task.model_validate(response.json())

    def retrieve(self, name: str, *, workspace: str | None = None) -> Task:
        """Get a stored task by name."""
        response = self._http_client.get(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()
        return Task.model_validate(response.json())

    def list(
        self, *, workspace: str | None = None, page: int = 1, page_size: int = 100, sort: str | None = None
    ) -> Page[Task]:
        """List stored tasks in a workspace."""
        response = self._http_client.get(
            self._collection_url(workspace),
            params=_list_params(page, page_size, sort),
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Page[Task].model_validate(response.json())

    def delete(self, name: str, *, workspace: str | None = None) -> None:
        """Delete a stored task by name."""
        response = self._http_client.delete(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()


class AsyncEvaluatorTasksResource:
    """Async resource mounted as ``client.evaluator.tasks``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    def _headers(self) -> dict[str, str]:
        return http_utils.platform_default_headers(self._platform)

    def _collection_url(self, workspace: str | None) -> str:
        return http_utils.url(self._platform, "/v2/workspaces/{workspace}/tasks", workspace)

    def _item_url(self, name: str, workspace: str | None) -> str:
        return http_utils.url(self._platform, f"/v2/workspaces/{{workspace}}/tasks/{quote(name, safe='')}", workspace)

    async def create(
        self, name: str, *, task: TaskInput, project: str | None = None, workspace: str | None = None
    ) -> Task:
        """Store a new task (addressed by workspace/name)."""
        response = await self._http_client.post(
            self._item_url(name, workspace),
            json=task.model_dump(mode="json"),
            params={"project": project} if project is not None else None,
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Task.model_validate(response.json())

    async def retrieve(self, name: str, *, workspace: str | None = None) -> Task:
        """Get a stored task by name."""
        response = await self._http_client.get(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()
        return Task.model_validate(response.json())

    async def list(
        self, *, workspace: str | None = None, page: int = 1, page_size: int = 100, sort: str | None = None
    ) -> Page[Task]:
        """List stored tasks in a workspace."""
        response = await self._http_client.get(
            self._collection_url(workspace),
            params=_list_params(page, page_size, sort),
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Page[Task].model_validate(response.json())

    async def delete(self, name: str, *, workspace: str | None = None) -> None:
        """Delete a stored task by name."""
        response = await self._http_client.delete(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()
