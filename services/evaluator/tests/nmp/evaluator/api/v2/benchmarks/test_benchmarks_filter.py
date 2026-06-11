# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for benchmarks filter functionality."""

import json
from datetime import datetime
from typing import Generator

import nmp.evaluator.entities as entities
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_evaluator_sdk.enums import MetricType, ModelFormat
from nemo_evaluator_sdk.values import Model, Rubric, RubricScore
from nmp.common.entities.client import EntityClient
from nmp.evaluator.api.v2.benchmarks.endpoints import get_benchmarks_manager, router
from nmp.evaluator.api.v2.benchmarks.manager import BenchmarksManager
from nmp.evaluator.api.v2.benchmarks.schemas.benchmarks import BenchmarkRequest
from nmp.evaluator.app.values import FilesetRef, MetricRef
from nmp.testing import create_test_client


@pytest.fixture
def mock_entity_client() -> Generator[EntityClient, None, None]:
    workspaces = ["default", "system"]
    with create_test_client(client_type=EntityClient, workspaces=workspaces) as client:
        yield client


@pytest.fixture
def benchmarks_manager(mock_entity_client) -> BenchmarksManager:
    return BenchmarksManager(mock_entity_client)


@pytest.fixture
def sample_metric_entity() -> entities.Metric:
    entity = entities.LLMJudgeMetric(
        name="test-metric",
        workspace="default",
        type=MetricType.LLM_JUDGE,
        description="Test metric",
        model=Model(
            url="https://api.openai.com/v1",
            name="gpt-4o",
            format=ModelFormat.OPEN_AI,
        ),
        prompt_template="Rate the response: {output}",
        scores=[
            RubricScore(
                name="quality",
                description="Quality of response",
                rubric=[
                    Rubric(label="good", description="Good response", value=1),
                    Rubric(label="bad", description="Bad response", value=0),
                ],
            )
        ],
    )
    entity._id = "metric-123"
    entity._created_at = datetime(2024, 1, 1, 0, 0, 0)
    entity._updated_at = datetime(2024, 1, 1, 0, 0, 0)
    return entity


def new_test_client(manager: BenchmarksManager) -> TestClient:
    def override_get_benchmarks_manager() -> BenchmarksManager:
        return manager

    app = FastAPI()
    app.include_router(router, prefix="/apis/evaluation")
    app.dependency_overrides[get_benchmarks_manager] = override_get_benchmarks_manager
    return TestClient(app)


@pytest_asyncio.fixture
async def create_sample_benchmarks(benchmarks_manager, mock_entity_client, mock_sdk, sample_metric_entity):
    """Create metrics and benchmarks for filter tests."""
    await mock_entity_client.create(sample_metric_entity)

    metric1 = entities.StringCheckMetric(
        name="metric-1",
        workspace="default",
        operation="equals",
        left_template="{{expected}}",
        right_template="{{output}}",
    )
    await mock_entity_client.create(metric1)

    await benchmarks_manager.create(
        "default",
        BenchmarkRequest(
            name="benchmark-alpha",
            description="First benchmark",
            metrics=[MetricRef(root="default/test-metric")],
            dataset=FilesetRef(root="default/dataset-a"),
            labels={"label1": "value1"},
        ),
        mock_sdk,
    )
    await benchmarks_manager.create(
        "default",
        BenchmarkRequest(
            name="benchmark-beta",
            description="Second benchmark",
            metrics=[MetricRef(root="default/metric-1")],
            dataset=FilesetRef(root="default/dataset-b"),
            labels={"label2": "value2"},
        ),
        mock_sdk,
    )


class TestBenchmarksFilterEndpoints:
    """Integration tests for benchmarks filter via HTTP endpoints."""

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_dataset(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test filter by dataset."""
        client = new_test_client(benchmarks_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/benchmarks?filter[dataset]=default/dataset-a")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-alpha"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_json(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test advanced JSON filter."""
        client = new_test_client(benchmarks_manager)

        filter_json = json.dumps({"name": {"$like": "beta"}})
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/benchmarks?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-beta"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_json_combined(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test JSON filter combining dataset and name."""
        client = new_test_client(benchmarks_manager)

        filter_json = json.dumps(
            {"$and": [{"dataset": {"$eq": "default/dataset-a"}}, {"name": {"$like": "benchmark"}}]}
        )
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/benchmarks?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-alpha"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_invalid_json(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test invalid JSON filter returns 400."""
        client = new_test_client(benchmarks_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/benchmarks?filter={invalid-json}")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_bracket_like(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test bracket filter with $like operator."""
        client = new_test_client(benchmarks_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/benchmarks?filter[name][$like]=beta")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-beta"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_bracket_eq(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test bracket filter with $eq operator."""
        client = new_test_client(benchmarks_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/benchmarks?filter[name][$eq]=benchmark-alpha")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-alpha"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_bracket_no_operator(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test bracket filter without operator defaults to $eq."""
        client = new_test_client(benchmarks_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/benchmarks?filter[name]=benchmark-alpha")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-alpha"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_bracket_combined(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test bracket filter combining dataset and name."""
        client = new_test_client(benchmarks_manager)

        resp = client.get(
            "/apis/evaluation/v2/workspaces/default/benchmarks?filter[dataset]=default/dataset-a&filter[name][$like]=benchmark"
        )
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-alpha"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_invalid_field(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test invalid filter field returns 400."""
        client = new_test_client(benchmarks_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/benchmarks?filter[nonexistent]=value")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_bracket_label_field(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test bracket filter can filter labels via filter[data.labels.KEY]."""
        client = new_test_client(benchmarks_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/benchmarks?filter[data.labels.label1]=value1")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-alpha"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_bracket_label_field_no_prefix(
        self, benchmarks_manager, create_sample_benchmarks
    ):  # noqa: ARG002
        """AIRCORE-389: the clean filter[labels.KEY] path returns the same rows as filter[data.labels.KEY]."""
        client = new_test_client(benchmarks_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/benchmarks?filter[labels.label1]=value1")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-alpha"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_json_label_eq(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test JSON filter on data.labels with $eq operator."""
        client = new_test_client(benchmarks_manager)

        filter_json = json.dumps({"data.labels.label1": {"$eq": "value1"}})
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/benchmarks?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-alpha"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_json_label_no_match(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test JSON filter on data.labels returns empty when no match."""
        client = new_test_client(benchmarks_manager)

        filter_json = json.dumps({"data.labels.label1": {"$eq": "nonexistent"}})
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/benchmarks?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 0

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_json_label_or(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test JSON filter with $or across different labels."""
        client = new_test_client(benchmarks_manager)

        filter_json = json.dumps(
            {
                "$or": [
                    {"data.labels.label1": {"$eq": "value1"}},
                    {"data.labels.label2": {"$eq": "value2"}},
                ]
            }
        )
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/benchmarks?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 2
        names = {b["name"] for b in data["data"]}
        assert names == {"benchmark-alpha", "benchmark-beta"}

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_json_label_with_name(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test JSON filter combining label and name conditions."""
        client = new_test_client(benchmarks_manager)

        filter_json = json.dumps(
            {
                "$and": [
                    {"data.labels.label1": {"$eq": "value1"}},
                    {"name": {"$like": "alpha"}},
                ]
            }
        )
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/benchmarks?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-alpha"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_json_description_eq(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test JSON filter on description with $eq operator."""
        client = new_test_client(benchmarks_manager)

        filter_json = json.dumps({"description": {"$eq": "First benchmark"}})
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/benchmarks?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-alpha"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_json_description_like(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test JSON filter on description with $like operator."""
        client = new_test_client(benchmarks_manager)

        filter_json = json.dumps({"description": {"$like": "Second"}})
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/benchmarks?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-beta"

    @pytest.mark.asyncio
    async def test_list_benchmarks_filter_json_name_eq(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test JSON filter on name with $eq operator."""
        client = new_test_client(benchmarks_manager)

        filter_json = json.dumps({"name": {"$eq": "benchmark-beta"}})
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/benchmarks?filter={filter_json}")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "benchmark-beta"

    @pytest.mark.asyncio
    async def test_list_benchmarks_rejects_unknown_top_level_query_param(
        self, benchmarks_manager, create_sample_benchmarks
    ):  # noqa: ARG002
        """Test unknown top-level query params are rejected with 400."""
        client = new_test_client(benchmarks_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/benchmarks?labels=eval_harness.bfcl")
        assert resp.status_code == 400, resp.json()
        detail = resp.json().get("detail", "")
        assert "unsupported query parameter" in detail.lower()
        assert "labels" in detail.lower()

    @pytest.mark.asyncio
    async def test_list_benchmarks_search_param_rejected(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test that search query param is no longer accepted."""
        client = new_test_client(benchmarks_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/benchmarks?search[name]=test")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_benchmarks_no_search_in_response(self, benchmarks_manager, create_sample_benchmarks):  # noqa: ARG002
        """Test that response does not include search field."""
        client = new_test_client(benchmarks_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/benchmarks")
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert "search" not in data
