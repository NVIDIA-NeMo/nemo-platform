# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP route-level tests for the /metrics CRUD endpoints.

Drives the real FastAPI router + MetricService through a TestClient, with the
entity store and Files service replaced by in-memory fakes. Covers route wiring,
the get_metric_service dependency, and status-code mapping (201/204/404/409).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_evaluator.api.dependencies import get_metric_service
from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.api.service.metric_service import MetricService
from nemo_evaluator.api.v2 import metrics as metrics_routes
from nemo_evaluator.entities import MetricBundleEntity
from nemo_evaluator.shared.metric_bundles.bundles import bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_platform_plugin.entities import (
    EntityConflictError,
    EntityNotFoundError,
    ListResponse,
    PaginationInfo,
)

# ---- in-memory fakes -------------------------------------------------------


class _FakeFile:
    def __init__(self, file_ref: str) -> None:
        self.file_ref = file_ref


class _FakeFilesets:
    def __init__(self, store: dict[tuple[str, str], dict[str, bytes]]) -> None:
        self._store = store

    async def create(self, *, name, workspace, description=None, exist_ok=False):
        self._store.setdefault((workspace, name), {})
        return object()

    async def delete(self, name, *, workspace=None):
        self._store.pop((workspace, name), None)
        return object()


class _FakeFiles:
    def __init__(self, store: dict[tuple[str, str], dict[str, bytes]]) -> None:
        self._store = store
        self.filesets = _FakeFilesets(store)

    async def _upload_file(self, *, path, body, workspace, name):
        self._store.setdefault((workspace, name), {})[path] = bytes(body)
        return _FakeFile(f"{workspace}/{name}#{path}")


class _FakeSDK:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict[str, bytes]] = {}
        self.files = _FakeFiles(self._store)


class _FakeEntityClient:
    def __init__(self) -> None:
        self.entities: dict[tuple[str, str], MetricBundleEntity] = {}

    async def get(self, entity_cls, *, workspace, name):
        key = (workspace, name)
        if key not in self.entities:
            raise EntityNotFoundError(f"{workspace}/{name} not found")
        return self.entities[key]

    async def create(self, entity):
        key = (entity.workspace, entity.name)
        if key in self.entities:
            raise EntityConflictError(f"{key} exists")
        now = datetime.now(timezone.utc)
        entity._id = f"metric_bundle-{entity.name}"
        entity._created_at = now
        entity._updated_at = now
        self.entities[key] = entity
        return entity

    async def delete(self, entity_cls, name, *, workspace):
        self.entities.pop((workspace, name), None)

    async def list(self, entity_cls, *, workspace, filter_operation=None, sort=None, page=1, page_size=100):
        items = [e for (ws, _), e in self.entities.items() if ws == workspace]
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


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    # Mirror production mounting: the router's paths are relative; the
    # workspace-scoped prefix is applied via RouterSpec in the plugin service.
    app.include_router(metrics_routes.router, prefix="/v2/workspaces/{workspace}")
    service = MetricService(_FakeEntityClient(), _FakeSDK())
    app.dependency_overrides[get_metric_service] = lambda: service
    return TestClient(app)


def _create_body() -> dict:
    """The create request body is a bare MetricInline (name comes from the path)."""
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    runtime_bundle = bundle_metric(metric, CloudpickleMetricBundlePackager())
    return MetricInline.model_validate_json(runtime_bundle.model_dump_json()).model_dump(mode="json")


_BASE = "/v2/workspaces/default/metrics"


def test_create_then_get(client: TestClient) -> None:
    resp = client.post(f"{_BASE}/exact", json=_create_body())
    assert resp.status_code == 201
    assert resp.json()["name"] == "exact"

    got = client.get(f"{_BASE}/exact")
    assert got.status_code == 200
    assert got.json()["payload_kind"] == "cloudpickle"


def test_create_duplicate_returns_409(client: TestClient) -> None:
    assert client.post(f"{_BASE}/exact", json=_create_body()).status_code == 201
    assert client.post(f"{_BASE}/exact", json=_create_body()).status_code == 409


def test_get_missing_returns_404(client: TestClient) -> None:
    assert client.get(f"{_BASE}/nope").status_code == 404


def test_list_returns_created_metrics(client: TestClient) -> None:
    client.post(f"{_BASE}/a", json=_create_body())
    client.post(f"{_BASE}/b", json=_create_body())

    resp = client.get(_BASE)
    assert resp.status_code == 200
    body = resp.json()
    assert {m["name"] for m in body["data"]} == {"a", "b"}
    assert body["pagination"]["total_results"] == 2


def test_create_then_delete(client: TestClient) -> None:
    client.post(f"{_BASE}/exact", json=_create_body())

    deleted = client.delete(f"{_BASE}/exact")
    assert deleted.status_code == 204
    assert client.get(f"{_BASE}/exact").status_code == 404


def test_delete_missing_returns_404(client: TestClient) -> None:
    assert client.delete(f"{_BASE}/nope").status_code == 404
