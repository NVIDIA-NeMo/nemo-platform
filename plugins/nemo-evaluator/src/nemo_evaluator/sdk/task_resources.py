# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for managing stored agent-eval tasks (``client.evaluator.tasks``).

Thin client over the evaluator service's ``/tasks`` create/get/list/delete API. A task is sent as a
:class:`TaskInput` (its metrics inline and/or as references to stored metrics) and returned as the
:class:`Task` DTO; the service owns persistence in the entity store.
"""

from __future__ import annotations

from urllib.parse import quote

from nemo_evaluator.api.schemas import Revision, Task, TaskInput
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

    def replace(self, name: str, *, task: TaskInput, project: str | None = None, workspace: str | None = None) -> Task:
        """Publish a revision of a task, creating it if absent.

        Upsert, so a publisher needs no existence check. Submitting content identical to the current
        revision publishes nothing and returns the task unchanged.

        The response body is the same either way, so this does not report whether a revision was
        cut — the server signals that with 201 vs 200, which is discarded here. Compare the returned
        ``revision`` against a prior read if you need to know."""
        response = self._http_client.put(
            self._item_url(name, workspace),
            json=task.model_dump(mode="json"),
            params={"project": project} if project is not None else None,
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Task.model_validate(response.json())

    def list_revisions(
        self, name: str, *, page: int = 1, page_size: int = 100, workspace: str | None = None
    ) -> Page[Revision]:
        """List a task's published revisions, newest first."""
        response = self._http_client.get(
            f"{self._item_url(name, workspace)}/revisions",
            params={"page": page, "page_size": page_size},
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Page[Revision].model_validate(response.json())

    def tag(self, name: str, *, tag: str, revision: str, workspace: str | None = None) -> Task:
        """Point ``tag`` at an existing revision, named by digest or by another tag.

        Both selectors are keyword-only: ``tag`` names the pointer being written and ``revision``
        names what it points at, and two bare strings in a row gave no hint which was which.
        """
        response = self._http_client.put(
            f"{self._item_url(name, workspace)}/tags/{quote(tag, safe='')}",
            params={"revision": revision},
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Task.model_validate(response.json())

    def retrieve(
        self, name: str, *, revision: str | None = None, tag: str | None = None, workspace: str | None = None
    ) -> Task:
        """Get a stored task by name, or as of a published revision.

        Pass ``revision`` for a content digest or ``tag`` for a named pointer — not both. With
        neither, this returns the task's current content.
        """
        url = self._item_url(name, workspace)
        selector = http_utils.revision_selector(revision, tag)
        if selector is not None:
            url = f"{url}/revisions/{selector}"
        response = self._http_client.get(url, headers=self._headers(), timeout=self._platform.timeout)
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

    async def replace(
        self, name: str, *, task: TaskInput, project: str | None = None, workspace: str | None = None
    ) -> Task:
        """Publish a revision of a task, creating it if absent.

        Upsert, so a publisher needs no existence check. Submitting content identical to the current
        revision publishes nothing and returns the task unchanged.

        The response body is the same either way, so this does not report whether a revision was
        cut — the server signals that with 201 vs 200, which is discarded here. Compare the returned
        ``revision`` against a prior read if you need to know."""
        response = await self._http_client.put(
            self._item_url(name, workspace),
            json=task.model_dump(mode="json"),
            params={"project": project} if project is not None else None,
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Task.model_validate(response.json())

    async def list_revisions(
        self, name: str, *, page: int = 1, page_size: int = 100, workspace: str | None = None
    ) -> Page[Revision]:
        """List a task's published revisions, newest first."""
        response = await self._http_client.get(
            f"{self._item_url(name, workspace)}/revisions",
            params={"page": page, "page_size": page_size},
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Page[Revision].model_validate(response.json())

    async def tag(self, name: str, *, tag: str, revision: str, workspace: str | None = None) -> Task:
        """Point ``tag`` at an existing revision, named by digest or by another tag.

        Both selectors are keyword-only: ``tag`` names the pointer being written and ``revision``
        names what it points at, and two bare strings in a row gave no hint which was which.
        """
        response = await self._http_client.put(
            f"{self._item_url(name, workspace)}/tags/{quote(tag, safe='')}",
            params={"revision": revision},
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Task.model_validate(response.json())

    async def retrieve(
        self, name: str, *, revision: str | None = None, tag: str | None = None, workspace: str | None = None
    ) -> Task:
        """Get a stored task by name, or as of a published revision.

        Pass ``revision`` for a content digest or ``tag`` for a named pointer — not both. With
        neither, this returns the task's current content.
        """
        url = self._item_url(name, workspace)
        selector = http_utils.revision_selector(revision, tag)
        if selector is not None:
            url = f"{url}/revisions/{selector}"
        response = await self._http_client.get(url, headers=self._headers(), timeout=self._platform.timeout)
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
