# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CRUD service for persisted taskset entities.

A taskset is a flexible grouping of stored tasks: it holds references to its members
(``workspace/name``) plus free-form annotations, stored whole in the entity store. Stored
``TasksetEntity`` rows are mapped to the :class:`Taskset` API DTO — the same DTO/entity split
``TaskService`` uses — so the wire contract round-trips cleanly (an ``EntityBase``'s ``id``/
``created_at`` are computed and don't deserialize from the entity's own serialized form).

Unlike ``TaskService`` there are no inline members to normalize; instead, each referenced task is
validated to exist at create time (a taskset that points at missing tasks is rejected).
"""

from __future__ import annotations

import logging

from nemo_evaluator.api.schemas import TaskRef, Taskset, TasksetInput, parse_entity_ref
from nemo_evaluator.api.service.task_service import TaskService
from nemo_evaluator.entities import TasksetEntity
from nemo_platform_plugin.entities import EntityClient, EntityConflictError, EntityNotFoundError, PaginationInfo
from nemo_platform_plugin.filter_ops import FilterOperation
from nemo_platform_plugin.log_utils import sanitize_for_log
from nemo_platform_plugin.schema import Page, PaginationData

logger = logging.getLogger(__name__)


class TaskRefNotFoundError(ValueError):
    """A taskset references a task that does not exist.

    Subclasses ``ValueError`` so existing callers still catch it, while letting the route distinguish
    a missing-member reference (a 422 on the submitted body) from other validation errors.
    """


class DuplicateTaskRefError(ValueError):
    """A taskset lists two references that resolve to the same task.

    The field validator already rejects byte-identical refs; this catches refs that differ in form
    but resolve to the same ``(workspace, name)`` (e.g. ``task-a`` and ``default/task-a`` when the
    taskset lives in ``default``). Subclasses ``ValueError`` so the route can map it to a 422.
    """


class TasksetExistsError(ValueError):
    """A taskset with the given workspace/name already exists.

    Subclasses ``ValueError`` so existing callers still catch it, while letting the route map a
    name collision to a 409 without inspecting the message text.
    """


def _entity_to_taskset(entity: TasksetEntity) -> Taskset:
    """Map a stored taskset entity to its API DTO, guarding the persistence timestamps."""
    created_at = entity.created_at
    updated_at = entity.updated_at
    if created_at is None or updated_at is None:
        raise ValueError(f"Stored taskset '{entity.workspace}/{entity.name}' is missing persistence timestamps")
    return Taskset(
        id=entity.id,
        name=entity.name,
        workspace=entity.workspace,
        project=entity.project,
        description=entity.description,
        tasks=entity.tasks,
        metadata=entity.metadata,
        created_at=created_at,
        updated_at=updated_at,
    )


def _pagination(src: PaginationInfo, current_page_size: int) -> PaginationData:
    """Carry the entity-store pagination counts into the API ``Page`` envelope."""
    return PaginationData(
        page=src.page,
        page_size=src.page_size,
        current_page_size=current_page_size,
        total_pages=src.total_pages,
        total_results=src.total_results,
    )


class TasksetService:
    """Create/get/list/delete for persisted taskset entities, exposed as the ``Taskset`` DTO."""

    def __init__(self, entity_client: EntityClient, task_service: TaskService):
        self.entity_client = entity_client
        self.task_service = task_service

    async def _validate_tasks_exist(self, tasks: list[TaskRef], *, workspace: str) -> None:
        """Validate the member refs: each must resolve to a stored task, and no two may resolve to the
        same one.

        A bare ``name`` ref resolves against the taskset's own workspace; a ``workspace/name`` ref
        resolves against the named workspace. Raises :class:`DuplicateTaskRefError` if two refs point
        at the same ``(workspace, name)`` and :class:`TaskRefNotFoundError` if a referenced task is
        missing.
        """
        seen: set[tuple[str, str]] = set()
        for ref in tasks:
            resolved = parse_entity_ref(ref.root, workspace)
            if resolved in seen:
                raise DuplicateTaskRefError(
                    f"Task reference '{ref.root}' resolves to '{resolved[0]}/{resolved[1]}', already in this taskset"
                )
            seen.add(resolved)
            if await self.task_service.get_task(*resolved) is None:
                raise TaskRefNotFoundError(f"Task reference '{ref.root}' not found in workspace '{resolved[0]}'")

    async def create_taskset(
        self, name: str, taskset_input: TasksetInput, *, workspace: str, project: str | None = None
    ) -> Taskset:
        """Store a new taskset (addressed by workspace/name).

        Raises ``ValueError`` if it already exists or if any referenced task does not exist.
        """
        await self._validate_tasks_exist(taskset_input.tasks, workspace=workspace)
        entity = TasksetEntity(
            name=name,
            workspace=workspace,
            project=project,
            description=taskset_input.description,
            tasks=taskset_input.tasks,
            metadata=taskset_input.metadata,
        )
        try:
            created = await self.entity_client.create(entity)
        except EntityConflictError as exc:
            raise TasksetExistsError(f"Taskset '{workspace}/{name}' already exists") from exc
        logger.info(
            "Taskset created",
            extra={"workspace": sanitize_for_log(workspace), "taskset_name": sanitize_for_log(name)},
        )
        return _entity_to_taskset(created)

    async def get_taskset(self, workspace: str, name: str) -> Taskset | None:
        try:
            entity = await self.entity_client.get(TasksetEntity, workspace=workspace, name=name)
        except EntityNotFoundError:
            return None
        return _entity_to_taskset(entity)

    async def list_tasksets(
        self,
        *,
        workspace: str,
        page: int = 1,
        page_size: int = 100,
        sort: str | None = None,
        filter_operation: FilterOperation | None = None,
    ) -> Page[Taskset]:
        result = await self.entity_client.list(
            TasksetEntity,
            workspace=workspace,
            filter_operation=filter_operation,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        data = [_entity_to_taskset(entity) for entity in result.data]
        return Page(data=data, pagination=_pagination(result.pagination, len(data)), sort=sort, filter=None)

    async def delete_taskset(self, workspace: str, name: str) -> bool:
        """Delete a stored taskset; ``False`` if absent."""
        try:
            await self.entity_client.delete(TasksetEntity, name, workspace=workspace)
        except EntityNotFoundError:
            return False
        logger.info(
            "Taskset deleted",
            extra={"workspace": sanitize_for_log(workspace), "taskset_name": sanitize_for_log(name)},
        )
        return True
