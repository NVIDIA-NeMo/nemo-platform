# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP route-level tests for the /tasksets CRUD endpoints.

Drives the real FastAPI router + TasksetService through a TestClient with an in-memory entity store.
Covers route wiring, the get_taskset_service dependency, and status-code mapping (201/204/404/409/422).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_evaluator.api.dependencies import get_taskset_service
from nemo_evaluator.api.schemas import TaskRef, TasksetInput
from nemo_evaluator.api.service.taskset_service import TasksetService
from nemo_evaluator.api.v2 import tasksets as tasksets_routes
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


class _FakeTaskService:
    """Resolves the member tasks the route tests reference so create-time validation passes."""

    async def get_task(self, workspace: str, name: str) -> object | None:
        return object() if name in {"task-a", "task-b"} else None


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(tasksets_routes.router, prefix="/v2/workspaces/{workspace}")
    service = TasksetService(_FakeEntityClient(), _FakeTaskService())
    app.dependency_overrides[get_taskset_service] = lambda: service
    return TestClient(app)


def _body() -> dict:
    return TasksetInput(
        description="A grouping.",
        tasks=[TaskRef("task-a"), TaskRef("default/task-b")],
    ).model_dump(mode="json")


_BASE = "/v2/workspaces/default/tasksets"


def test_create_then_get(client: TestClient) -> None:
    resp = client.post(f"{_BASE}/ts-1", json=_body())
    assert resp.status_code == 201
    assert resp.json()["name"] == "ts-1"

    got = client.get(f"{_BASE}/ts-1")
    assert got.status_code == 200
    body = got.json()
    assert body["description"] == "A grouping."
    assert body["tasks"] == ["task-a", "default/task-b"]  # TaskRef serializes to a bare string


def test_create_rejects_unknown_body_key(client: TestClient) -> None:
    # TasksetInput is extra="forbid" — an unknown key is a 422.
    body = _body()
    body["intent"] = "nope"
    assert client.post(f"{_BASE}/ts-1", json=body).status_code == 422


def test_create_rejects_duplicate_task_refs(client: TestClient) -> None:
    # Members are a set expressed as a list; a repeated ref is a 422, not a silent collapse.
    body = _body()
    body["tasks"] = ["task-a", "task-a"]
    assert client.post(f"{_BASE}/ts-1", json=body).status_code == 422


def test_create_rejects_refs_resolving_to_same_task(client: TestClient) -> None:
    # Distinct ref strings that resolve to the same task ("task-a" vs "default/task-a") are a 422.
    body = _body()
    body["tasks"] = ["task-a", "default/task-a"]
    assert client.post(f"{_BASE}/ts-1", json=body).status_code == 422


def test_create_rejects_missing_task_ref(client: TestClient) -> None:
    # A referenced task that does not exist is a 422 (client error in the submitted body).
    body = _body()
    body["tasks"] = ["task-a", "does-not-exist"]
    assert client.post(f"{_BASE}/ts-1", json=body).status_code == 422


def test_create_rejects_duplicate_metadata_keys(client: TestClient) -> None:
    body = _body()
    body["metadata"] = [{"key": "suite", "value": "smoke"}, {"key": "suite", "value": "regression"}]
    assert client.post(f"{_BASE}/ts-1", json=body).status_code == 422


def test_create_duplicate_returns_409(client: TestClient) -> None:
    assert client.post(f"{_BASE}/ts-1", json=_body()).status_code == 201
    assert client.post(f"{_BASE}/ts-1", json=_body()).status_code == 409


def test_create_rejects_invalid_name(client: TestClient) -> None:
    assert client.post(f"{_BASE}/bad name", json=_body()).status_code == 422


def test_get_missing_returns_404(client: TestClient) -> None:
    assert client.get(f"{_BASE}/nope").status_code == 404


def test_list_returns_created_tasksets(client: TestClient) -> None:
    client.post(f"{_BASE}/a", json=_body())
    client.post(f"{_BASE}/b", json=_body())

    resp = client.get(_BASE)
    assert resp.status_code == 200
    body = resp.json()
    assert {t["name"] for t in body["data"]} == {"a", "b"}
    assert body["pagination"]["total_results"] == 2


def test_delete_then_get_404(client: TestClient) -> None:
    client.post(f"{_BASE}/ts-1", json=_body())
    assert client.delete(f"{_BASE}/ts-1").status_code == 204
    assert client.get(f"{_BASE}/ts-1").status_code == 404


def test_delete_missing_returns_404(client: TestClient) -> None:
    assert client.delete(f"{_BASE}/nope").status_code == 404
