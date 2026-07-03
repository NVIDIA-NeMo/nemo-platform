# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP route-level tests for the /tasks CRUD endpoints.

Drives the real FastAPI router + TaskService through a TestClient with an in-memory entity store.
Covers route wiring, the get_task_service dependency, and status-code mapping (201/204/404/409/422).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_evaluator.api.dependencies import get_task_service
from nemo_evaluator.api.schemas import MetricRef, TaskInput
from nemo_evaluator.api.service.task_service import TaskService
from nemo_evaluator.api.v2 import tasks as tasks_routes
from nemo_platform_plugin.entities import (
    EntityBase,
    EntityConflictError,
    EntityNotFoundError,
    ListResponse,
    PaginationInfo,
)


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
                page=page, page_size=page_size, current_page_size=len(items), total_pages=1, total_results=len(items)
            ),
        )


class _FakeMetricService:
    """Normalizes inline metrics to derived refs; the route tests submit refs only, so it's unused."""

    async def store_derived_metric(self, metric, *, workspace: str) -> MetricRef:
        return MetricRef(f"{workspace}/derived.{metric.payload.digest}")


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(tasks_routes.router, prefix="/v2/workspaces/{workspace}")
    service = TaskService(_FakeEntityClient(), _FakeMetricService())
    app.dependency_overrides[get_task_service] = lambda: service
    return TestClient(app)


def _body() -> dict:
    return TaskInput(
        intent="Answer the question.",
        inputs={"instruction": "What is 2+2?"},
        metrics=[MetricRef("default/stored-metric")],
    ).model_dump(mode="json")


_BASE = "/v2/workspaces/default/tasks"


def test_create_then_get(client: TestClient) -> None:
    resp = client.post(f"{_BASE}/task-1", json=_body())
    assert resp.status_code == 201
    assert resp.json()["name"] == "task-1"

    got = client.get(f"{_BASE}/task-1")
    assert got.status_code == 200
    body = got.json()
    assert body["intent"] == "Answer the question."
    assert body["metrics"] == ["default/stored-metric"]  # MetricRef serializes to a bare string


def test_create_rejects_unrecognized_input_key(client: TestClient) -> None:
    # inputs is a strict TaskInputs (extra="forbid") — an unknown key is a 422, not silently stored.
    body = _body()
    body["inputs"]["expected"] = "4"
    assert client.post(f"{_BASE}/task-1", json=body).status_code == 422


def test_create_rejects_duplicate_metadata_keys(client: TestClient) -> None:
    # metadata is a key→value map as a list; duplicate keys are a 422, not a silent last-wins collapse.
    body = _body()
    body["metadata"] = [{"key": "suite", "value": "smoke"}, {"key": "suite", "value": "regression"}]
    assert client.post(f"{_BASE}/task-1", json=body).status_code == 422


def test_create_duplicate_returns_409(client: TestClient) -> None:
    assert client.post(f"{_BASE}/task-1", json=_body()).status_code == 201
    assert client.post(f"{_BASE}/task-1", json=_body()).status_code == 409


def test_create_rejects_invalid_name(client: TestClient) -> None:
    # NAME_PATTERN forbids slashes/spaces.
    assert client.post(f"{_BASE}/bad name", json=_body()).status_code == 422


def test_get_missing_returns_404(client: TestClient) -> None:
    assert client.get(f"{_BASE}/nope").status_code == 404


def test_list_returns_created_tasks(client: TestClient) -> None:
    client.post(f"{_BASE}/a", json=_body())
    client.post(f"{_BASE}/b", json=_body())

    resp = client.get(_BASE)
    assert resp.status_code == 200
    body = resp.json()
    assert {t["name"] for t in body["data"]} == {"a", "b"}
    assert body["pagination"]["total_results"] == 2


def test_delete_then_get_404(client: TestClient) -> None:
    client.post(f"{_BASE}/task-1", json=_body())
    assert client.delete(f"{_BASE}/task-1").status_code == 204
    assert client.get(f"{_BASE}/task-1").status_code == 404


def test_delete_missing_returns_404(client: TestClient) -> None:
    assert client.delete(f"{_BASE}/nope").status_code == 404
