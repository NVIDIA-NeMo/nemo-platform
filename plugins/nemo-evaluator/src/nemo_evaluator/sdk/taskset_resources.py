# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for managing stored tasksets (``client.evaluator.tasksets``).

Thin client over the evaluator service's ``/tasksets`` create/get/list/delete API. A taskset is sent
as a :class:`TasksetInput` (its members as references to stored tasks) and returned as the
:class:`Taskset` DTO; the service owns persistence in the entity store.
"""

from __future__ import annotations

from urllib.parse import quote

from nemo_evaluator.api.schemas import Revision, Taskset, TasksetInput
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

    def replace(
        self, name: str, *, taskset: TasksetInput, project: str | None = None, workspace: str | None = None
    ) -> Taskset:
        """Publish a revision of a taskset, creating it if absent.

        Members are re-resolved to exact revision digests on every call, so identical member names
        can still publish a new revision if a member task published in the meantime.

        The response body is the same either way, so this does not report whether a revision was
        cut — the server signals that with 201 vs 200, which is discarded here. Compare the returned
        ``revision`` against a prior read if you need to know."""
        response = self._http_client.put(
            self._item_url(name, workspace),
            json=taskset.model_dump(mode="json"),
            params={"project": project} if project is not None else None,
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Taskset.model_validate(response.json())

    def list_revisions(
        self, name: str, *, page: int = 1, page_size: int = 100, workspace: str | None = None
    ) -> Page[Revision]:
        """List a taskset's published revisions, newest first."""
        response = self._http_client.get(
            f"{self._item_url(name, workspace)}/revisions",
            params={"page": page, "page_size": page_size},
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Page[Revision].model_validate(response.json())

    def tag(self, name: str, *, tag: str, revision: str, workspace: str | None = None) -> Taskset:
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
        return Taskset.model_validate(response.json())

    def retrieve(
        self, name: str, *, revision: str | None = None, tag: str | None = None, workspace: str | None = None
    ) -> Taskset:
        """Get a stored taskset by name, or as of a published revision.

        Pass ``revision`` for a content digest or ``tag`` for a named pointer — not both. With
        neither, this returns the taskset's current membership.
        """
        url = self._item_url(name, workspace)
        selector = http_utils.revision_selector(revision, tag)
        if selector is not None:
            url = f"{url}/revisions/{selector}"
        response = self._http_client.get(url, headers=self._headers(), timeout=self._platform.timeout)
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

    async def replace(
        self, name: str, *, taskset: TasksetInput, project: str | None = None, workspace: str | None = None
    ) -> Taskset:
        """Publish a revision of a taskset, creating it if absent.

        Members are re-resolved to exact revision digests on every call, so identical member names
        can still publish a new revision if a member task published in the meantime.

        The response body is the same either way, so this does not report whether a revision was
        cut — the server signals that with 201 vs 200, which is discarded here. Compare the returned
        ``revision`` against a prior read if you need to know."""
        response = await self._http_client.put(
            self._item_url(name, workspace),
            json=taskset.model_dump(mode="json"),
            params={"project": project} if project is not None else None,
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Taskset.model_validate(response.json())

    async def list_revisions(
        self, name: str, *, page: int = 1, page_size: int = 100, workspace: str | None = None
    ) -> Page[Revision]:
        """List a taskset's published revisions, newest first."""
        response = await self._http_client.get(
            f"{self._item_url(name, workspace)}/revisions",
            params={"page": page, "page_size": page_size},
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Page[Revision].model_validate(response.json())

    async def tag(self, name: str, *, tag: str, revision: str, workspace: str | None = None) -> Taskset:
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
        return Taskset.model_validate(response.json())

    async def retrieve(
        self, name: str, *, revision: str | None = None, tag: str | None = None, workspace: str | None = None
    ) -> Taskset:
        """Get a stored taskset by name, or as of a published revision.

        Pass ``revision`` for a content digest or ``tag`` for a named pointer — not both. With
        neither, this returns the taskset's current membership.
        """
        url = self._item_url(name, workspace)
        selector = http_utils.revision_selector(revision, tag)
        if selector is not None:
            url = f"{url}/revisions/{selector}"
        response = await self._http_client.get(url, headers=self._headers(), timeout=self._platform.timeout)
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
