# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from nemo_evaluator.api.schemas import MetricInline, MetricRef, Task, TaskInput
from nemo_evaluator.api.service.task_service import TaskService
from nemo_evaluator.shared.metric_bundles.bundles import bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_platform_plugin.entities import (
    EntityBase,
    EntityConflictError,
    EntityNotFoundError,
    ListResponse,
    PaginationInfo,
)


class _FakeMetricService:
    """Records inline-metric normalization so we can assert a task stores refs, not bundles."""

    def __init__(self) -> None:
        self.stored: list[MetricInline] = []

    async def store_derived_metric(self, metric: MetricInline, *, workspace: str) -> MetricRef:
        self.stored.append(metric)
        return MetricRef(f"{workspace}/derived.{metric.payload.digest}")


def _inline_metric() -> MetricInline:
    bundle = bundle_metric(
        ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
        CloudpickleMetricBundlePackager(),
    )
    return MetricInline.model_validate(bundle.model_dump(mode="json"))


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


def _task_input() -> TaskInput:
    return TaskInput(
        intent="Answer the question.",
        inputs={"instruction": "What is 2+2?"},
        metrics=[MetricRef("default/stored-metric")],
        metadata=[{"key": "suite", "value": "smoke"}],
    )


@pytest.fixture
def metric_service() -> _FakeMetricService:
    return _FakeMetricService()


@pytest.fixture
def service(metric_service: _FakeMetricService) -> TaskService:
    return TaskService(_FakeEntityClient(), metric_service)


async def test_create_then_get(service: TaskService) -> None:
    created = await service.create_task("task-1", _task_input(), workspace="default")

    assert isinstance(created, Task)
    assert created.name == "task-1"
    assert created.id == "task-task-1"
    assert created.intent == "Answer the question."
    assert isinstance(created.metrics[0], MetricRef)
    assert created.created_at is not None

    got = await service.get_task("default", "task-1")
    assert got is not None and got.name == "task-1"


async def test_create_normalizes_inline_metrics_to_refs(
    service: TaskService, metric_service: _FakeMetricService
) -> None:
    inline = _inline_metric()
    task_input = TaskInput(
        intent="Answer the question.",
        inputs={"instruction": "What is 2+2?"},
        metrics=[MetricRef("default/stored-metric"), inline],
    )

    created = await service.create_task("task-1", task_input, workspace="default")

    # The inline metric was offloaded to the metric service (stored as a derived metric)...
    assert metric_service.stored == [inline]
    # ...and the persisted task holds only refs — the passthrough ref plus the derived one.
    assert all(isinstance(m, MetricRef) for m in created.metrics)
    assert created.metrics[0].root == "default/stored-metric"
    assert created.metrics[1].root == f"default/derived.{inline.payload.digest}"


async def test_create_rejects_duplicate(service: TaskService) -> None:
    await service.create_task("task-1", _task_input(), workspace="default")
    with pytest.raises(ValueError, match="already exists"):
        await service.create_task("task-1", _task_input(), workspace="default")


async def test_get_returns_none_when_missing(service: TaskService) -> None:
    assert await service.get_task("default", "nope") is None


async def test_list_returns_workspace_tasks(service: TaskService) -> None:
    await service.create_task("a", _task_input(), workspace="default")
    await service.create_task("b", _task_input(), workspace="default")

    page = await service.list_tasks(workspace="default")

    assert {t.name for t in page.data} == {"a", "b"}
    assert page.pagination is not None and page.pagination.total_results == 2


async def test_delete(service: TaskService) -> None:
    await service.create_task("task-1", _task_input(), workspace="default")
    assert await service.delete_task("default", "task-1") is True
    assert await service.get_task("default", "task-1") is None


async def test_delete_returns_false_when_missing(service: TaskService) -> None:
    assert await service.delete_task("default", "nope") is False
