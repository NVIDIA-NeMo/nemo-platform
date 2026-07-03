# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from nemo_evaluator.api.schemas import TaskRef, Taskset, TasksetInput
from nemo_evaluator.api.service.taskset_service import (
    DuplicateTaskRefError,
    TaskRefNotFoundError,
    TasksetExistsError,
    TasksetService,
)
from nemo_platform_plugin.entities import (
    EntityBase,
    EntityConflictError,
    EntityNotFoundError,
    ListResponse,
    PaginationInfo,
)


class _FakeTaskService:
    """Stands in for TaskService's existence check; ``get_task`` resolves only known (workspace, name)."""

    def __init__(self, existing: set[tuple[str, str]]) -> None:
        self.existing = existing

    async def get_task(self, workspace: str, name: str) -> object | None:
        return object() if (workspace, name) in self.existing else None


class _FakeEntityClient:
    def __init__(self) -> None:
        self.entities: dict[tuple[str, str, str], EntityBase] = {}

    async def create(self, entity):
        key = (entity.__entity_type__, entity.workspace, entity.name)
        if key in self.entities:
            raise EntityConflictError(f"{key} exists")
        now = datetime.now(timezone.utc)
        entity._id = f"{entity.__entity_type__}-{entity.name}"
        entity._created_at = now
        entity._updated_at = now
        self.entities[key] = entity
        return entity

    async def get(self, entity_cls, *, workspace, name):
        key = (entity_cls.__entity_type__, workspace, name)
        if key not in self.entities:
            raise EntityNotFoundError(f"{workspace}/{name} not found")
        return self.entities[key]

    async def delete(self, entity_cls, name, *, workspace):
        key = (entity_cls.__entity_type__, workspace, name)
        if key not in self.entities:
            raise EntityNotFoundError(f"{workspace}/{name} not found")
        del self.entities[key]

    async def list(self, entity_cls, *, workspace, filter_operation=None, sort=None, page=1, page_size=100):
        items = [
            e for (etype, ws, _), e in self.entities.items() if etype == entity_cls.__entity_type__ and ws == workspace
        ]
        return ListResponse(
            data=items,
            pagination=PaginationInfo(
                page=page,
                page_size=page_size,
                current_page_size=len(items),
                total_pages=1,
                total_results=len(items),
            ),
        )


def _taskset_input() -> TasksetInput:
    return TasksetInput(
        description="A smoke-test grouping.",
        tasks=[TaskRef("task-a"), TaskRef("default/task-b")],
        metadata=[{"key": "suite", "value": "smoke"}],
    )


@pytest.fixture
def existing_tasks() -> set[tuple[str, str]]:
    return {("default", "task-a"), ("default", "task-b")}


@pytest.fixture
def service(existing_tasks: set[tuple[str, str]]) -> TasksetService:
    return TasksetService(_FakeEntityClient(), _FakeTaskService(existing_tasks))


async def test_create_then_get(service: TasksetService) -> None:
    created = await service.create_taskset("ts-1", _taskset_input(), workspace="default")

    assert isinstance(created, Taskset)
    assert created.name == "ts-1"
    assert created.id == "taskset-ts-1"
    assert created.description == "A smoke-test grouping."
    assert {t.root for t in created.tasks} == {"task-a", "default/task-b"}
    assert created.created_at is not None

    got = await service.get_taskset("default", "ts-1")
    assert got is not None and got.name == "ts-1"


async def test_create_validates_missing_task_ref(service: TasksetService) -> None:
    taskset_input = TasksetInput(tasks=[TaskRef("task-a"), TaskRef("nope")])
    with pytest.raises(TaskRefNotFoundError, match="not found"):
        await service.create_taskset("ts-1", taskset_input, workspace="default")


async def test_create_resolves_bare_ref_against_taskset_workspace(existing_tasks: set[tuple[str, str]]) -> None:
    # A bare "task-a" ref must resolve against the taskset's own workspace ("other"), where it is absent.
    service = TasksetService(_FakeEntityClient(), _FakeTaskService(existing_tasks))
    with pytest.raises(ValueError, match="not found in workspace 'other'"):
        await service.create_taskset("ts-1", TasksetInput(tasks=[TaskRef("task-a")]), workspace="other")


async def test_create_rejects_refs_resolving_to_same_task(service: TasksetService) -> None:
    # "task-a" and "default/task-a" resolve to the same (default, task-a) — rejected even though the
    # ref strings differ (the field validator only catches byte-identical dupes).
    taskset_input = TasksetInput(tasks=[TaskRef("task-a"), TaskRef("default/task-a")])
    with pytest.raises(DuplicateTaskRefError, match="already in this taskset"):
        await service.create_taskset("ts-1", taskset_input, workspace="default")


async def test_create_rejects_duplicate(service: TasksetService) -> None:
    await service.create_taskset("ts-1", _taskset_input(), workspace="default")
    with pytest.raises(TasksetExistsError, match="already exists"):
        await service.create_taskset("ts-1", _taskset_input(), workspace="default")


async def test_create_allows_same_name_in_different_workspaces(service: TasksetService) -> None:
    # Taskset names are unique per workspace, not globally: the same name in another workspace is a
    # distinct taskset and must not raise TasksetExistsError (409). Empty task lists keep this focused
    # on name scoping rather than per-workspace task-ref validation.
    first = await service.create_taskset("ts-1", TasksetInput(), workspace="default")
    second = await service.create_taskset("ts-1", TasksetInput(), workspace="other")

    assert first.name == second.name == "ts-1"
    assert first.workspace == "default"
    assert second.workspace == "other"


async def test_get_returns_none_when_missing(service: TasksetService) -> None:
    assert await service.get_taskset("default", "nope") is None


async def test_list_returns_workspace_tasksets(service: TasksetService) -> None:
    await service.create_taskset("a", _taskset_input(), workspace="default")
    await service.create_taskset("b", _taskset_input(), workspace="default")

    page = await service.list_tasksets(workspace="default")

    assert {t.name for t in page.data} == {"a", "b"}
    assert page.pagination is not None and page.pagination.total_results == 2


async def test_delete(service: TasksetService) -> None:
    await service.create_taskset("ts-1", _taskset_input(), workspace="default")
    assert await service.delete_taskset("default", "ts-1") is True
    assert await service.get_taskset("default", "ts-1") is None


async def test_delete_returns_false_when_missing(service: TasksetService) -> None:
    assert await service.delete_taskset("default", "nope") is False
