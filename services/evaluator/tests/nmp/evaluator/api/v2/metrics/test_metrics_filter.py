# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for metrics filter functionality."""

import json
from typing import Generator

import nmp.evaluator.entities as entities
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nmp.common.entities import EntityClient
from nmp.evaluator.api.v2.metrics.endpoints import get_metrics_manager, router
from nmp.evaluator.api.v2.metrics.manager import MetricsManager
from nmp.evaluator.api.v2.metrics.schemas.metrics_resp import MetricsListResponse
from nmp.testing import create_test_client


@pytest.fixture
def mock_entity_client() -> Generator[EntityClient, None, None]:
    workspaces = ["default", "system"]
    projects = ["default/project-a", "default/project-b"]
    with create_test_client(client_type=EntityClient, workspaces=workspaces, projects=projects) as client:
        yield client


@pytest.fixture
def metrics_manager(mock_entity_client) -> MetricsManager:
    return MetricsManager(mock_entity_client)


def new_test_client(manager: MetricsManager, mock_sdk=None) -> TestClient:
    def override_get_metrics_manager() -> MetricsManager:
        return manager

    app = FastAPI()
    app.include_router(router, prefix="/apis/evaluation")
    app.dependency_overrides[get_metrics_manager] = override_get_metrics_manager

    if mock_sdk is not None:
        from nmp.common.service.dependencies import get_sdk_client

        app.dependency_overrides[get_sdk_client] = lambda: mock_sdk

    return TestClient(app)


class TestMetricsFilterEndpoints:
    """Integration tests for metrics filter via HTTP endpoints."""

    async def _create_metrics(self, metrics_manager: MetricsManager, mock_sdk):
        metric1 = entities.StringCheckMetric(
            name="metric-alpha",
            workspace="default",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
            project="project-a",
            labels={"label1": "value1"},
        )
        metric2 = entities.BLEUMetric(
            name="metric-beta",
            workspace="default",
            references=["{{reference}}"],
            project="project-b",
        )
        metric3 = entities.ExactMatchMetric(
            name="metric-gamma",
            workspace="default",
            reference="{{reference}}",
            project="project-a",
        )
        await metrics_manager.create(metric1, sdk=mock_sdk)
        await metrics_manager.create(metric2, sdk=mock_sdk)
        await metrics_manager.create(metric3, sdk=mock_sdk)

    @pytest.mark.asyncio
    async def test_list_metrics_filter_type(self, metrics_manager, mock_sdk):
        """Test filter by metric type."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?filter[type]=bleu")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 1
        assert result.data[0].name == "metric-beta"

    @pytest.mark.asyncio
    async def test_list_metrics_filter_project(self, metrics_manager, mock_sdk):
        """Test filter by project."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?filter[project]=project-a")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 2
        names = {m.name for m in result.data}
        assert names == {"metric-alpha", "metric-gamma"}

    @pytest.mark.asyncio
    async def test_list_metrics_filter_json(self, metrics_manager, mock_sdk):
        """Test advanced JSON filter."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        filter_json = json.dumps({"name": {"$like": "beta"}})
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metrics?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 1
        assert result.data[0].name == "metric-beta"

    @pytest.mark.asyncio
    async def test_list_metrics_filter_json_combined(self, metrics_manager, mock_sdk):
        """Test JSON filter combined with project filter."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        filter_json = json.dumps({"$and": [{"project": {"$eq": "project-a"}}, {"name": {"$like": "metric"}}]})
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metrics?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 2
        names = {m.name for m in result.data}
        assert names == {"metric-alpha", "metric-gamma"}

    @pytest.mark.asyncio
    async def test_list_metrics_filter_invalid_json(self, metrics_manager, mock_sdk):
        """Test invalid JSON filter returns 400."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?filter={invalid-json}")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_metrics_filter_bracket_like(self, metrics_manager, mock_sdk):
        """Test bracket filter with $like operator."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?filter[name][$like]=beta")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 1
        assert result.data[0].name == "metric-beta"

    @pytest.mark.asyncio
    async def test_list_metrics_filter_bracket_eq(self, metrics_manager, mock_sdk):
        """Test bracket filter with $eq operator."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?filter[name][$eq]=metric-alpha")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 1
        assert result.data[0].name == "metric-alpha"

    @pytest.mark.asyncio
    async def test_list_metrics_filter_bracket_no_operator(self, metrics_manager, mock_sdk):
        """Test bracket filter without operator defaults to $eq."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?filter[name]=metric-alpha")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 1
        assert result.data[0].name == "metric-alpha"

    @pytest.mark.asyncio
    async def test_list_metrics_filter_bracket_combined(self, metrics_manager, mock_sdk):
        """Test bracket filter combining project and name."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get(
            "/apis/evaluation/v2/workspaces/default/metrics?filter[project]=project-a&filter[name][$like]=metric"
        )
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 2
        names = {m.name for m in result.data}
        assert names == {"metric-alpha", "metric-gamma"}

    @pytest.mark.asyncio
    async def test_list_metrics_filter_invalid_field(self, metrics_manager, mock_sdk):
        """Test invalid filter field returns 400."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?filter[nonexistent]=value")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_metrics_filter_bracket_label_field(self, metrics_manager, mock_sdk):
        """Test bracket filter can filter labels via filter[data.labels.KEY]."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?filter[data.labels.label1]=value1")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 1
        assert result.data[0].name == "metric-alpha"

    @pytest.mark.asyncio
    async def test_list_metrics_filter_json_label_eq(self, metrics_manager, mock_sdk):
        """Test JSON filter on data.labels with $eq operator."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        filter_json = json.dumps({"data.labels.label1": {"$eq": "value1"}})
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metrics?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 1
        assert result.data[0].name == "metric-alpha"

    @pytest.mark.asyncio
    async def test_list_metrics_filter_json_label_no_match(self, metrics_manager, mock_sdk):
        """Test JSON filter on data.labels returns empty when no match."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        filter_json = json.dumps({"data.labels.label1": {"$eq": "nonexistent"}})
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metrics?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 0

    @pytest.mark.asyncio
    async def test_list_metrics_filter_json_label_or(self, metrics_manager, mock_sdk):
        """Test JSON filter with $or to match metrics by different criteria."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        filter_json = json.dumps(
            {
                "$or": [
                    {"data.labels.label1": {"$eq": "value1"}},
                    {"name": {"$eq": "metric-beta"}},
                ]
            }
        )
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metrics?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 2
        names = {m.name for m in result.data}
        assert names == {"metric-alpha", "metric-beta"}

    @pytest.mark.asyncio
    async def test_list_metrics_filter_json_label_with_type(self, metrics_manager, mock_sdk):
        """Test JSON filter on labels combined with type filter."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        filter_json = json.dumps(
            {"$and": [{"type": {"$eq": "string-check"}}, {"data.labels.label1": {"$eq": "value1"}}]}
        )
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metrics?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 1
        assert result.data[0].name == "metric-alpha"

    @pytest.mark.asyncio
    async def test_list_metrics_filter_json_name_eq(self, metrics_manager, mock_sdk):
        """Test JSON filter on name with $eq operator."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        filter_json = json.dumps({"name": {"$eq": "metric-gamma"}})
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metrics?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 1
        assert result.data[0].name == "metric-gamma"

    @pytest.mark.asyncio
    async def test_list_metrics_filter_json_type_eq(self, metrics_manager, mock_sdk):
        """Test JSON filter on type with $eq operator."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        filter_json = json.dumps({"type": {"$eq": "bleu"}})
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metrics?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        result = MetricsListResponse.model_validate(resp.json())
        assert len(result.data) == 1
        assert result.data[0].name == "metric-beta"

    @pytest.mark.asyncio
    async def test_list_metrics_rejects_unknown_top_level_query_param(self, metrics_manager, mock_sdk):
        """Test unknown top-level query params are rejected with 400."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?labels=custom.bfcl")
        assert resp.status_code == 400, resp.json()
        detail = resp.json().get("detail", "")
        assert "unsupported query parameter" in detail.lower()
        assert "labels" in detail.lower()

    @pytest.mark.asyncio
    async def test_list_metrics_search_param_rejected(self, metrics_manager, mock_sdk):
        """Test that search query param is no longer accepted."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?search[name]=test")
        assert resp.status_code == 400
