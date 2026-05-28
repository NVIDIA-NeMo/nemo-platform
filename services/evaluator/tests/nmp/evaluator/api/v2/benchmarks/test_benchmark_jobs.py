# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, patch

import nmp.evaluator.entities as entities
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nmp.evaluator.api.v2.benchmarks.endpoints import (
    get_benchmarks_manager,
    router,
)
from nmp.evaluator.api.v2.benchmarks.manager import BenchmarksManager
from nmp.evaluator.api.v2.benchmarks.schemas.benchmarks import BenchmarkRequest
from nmp.evaluator.api.v2.benchmarks.schemas.jobs import (
    BenchmarkJobAdapter,
    BenchmarkOfflineJob,
    BenchmarkOnlineJob,
)
from nmp.evaluator.app.values import FilesetRef, MetricRef


def new_test_client(manager: BenchmarksManager, mock_sdk=None) -> TestClient:
    """Fast API test client with benchmarks manager"""

    def override_get_benchmarks_manager() -> BenchmarksManager:
        return manager

    app = FastAPI()
    app.include_router(router, prefix="/apis/evaluation")
    app.dependency_overrides[get_benchmarks_manager] = override_get_benchmarks_manager

    from nmp.common.service.dependencies import get_entity_client

    app.dependency_overrides[get_entity_client] = lambda: manager._entity_client

    # Override get_sdk_client if mock_sdk is provided
    if mock_sdk is not None:
        from nmp.common.service.dependencies import get_sdk_client

        app.dependency_overrides[get_sdk_client] = lambda: mock_sdk

    return TestClient(app)


class TestCreateBenchmarkJobEndpoint:
    @pytest.mark.asyncio
    async def test_create_custom_benchmark_offline_job(self, benchmarks_manager, mock_sdk):
        """Test job spec and serialization of API schemas for custom benchmark job."""
        metric = entities.BLEUMetric(
            name="custom-metric",
            workspace="default",
            references=["{{reference}}"],
        )
        await benchmarks_manager._entity_client.create(metric)
        await benchmarks_manager.create(
            "default",
            BenchmarkRequest(
                name="custom-benchmark",
                description=None,
                metrics=[MetricRef(root="default/custom-metric")],
                dataset=FilesetRef(root="default/test-dataset"),
            ),
            mock_sdk,
        )

        job_spec = {
            "benchmark": "default/custom-benchmark",
            "params": {
                "limit_samples": 5,
            },
        }
        job = BenchmarkJobAdapter.validate_python(job_spec)
        assert isinstance(job, BenchmarkOfflineJob), "unexpected serialization to job type with BenchmarkJobAdapter"

        with patch(
            "nmp.evaluator.app.datasets.nmp_datasets.fileset.dataset_exists", new_callable=AsyncMock
        ) as mock_fileset_exists:
            mock_fileset_exists.return_value = True

            client = new_test_client(benchmarks_manager, mock_sdk=mock_sdk)
            resp = client.post("/apis/evaluation/v2/workspaces/default/benchmark-jobs", json={"spec": job_spec})
            assert resp.status_code == 201, resp.text

            job_resp_spec = BenchmarkJobAdapter.validate_python(resp.json().get("spec"))
            assert isinstance(job_resp_spec, BenchmarkOfflineJob), (
                "unexpected serialization to job type with BenchmarkJobAdapter"
            )

    @pytest.mark.asyncio
    async def test_create_custom_benchmark_online_job(self, benchmarks_manager, mock_sdk):
        """Test job spec and serialization of API schemas for custom benchmark job."""
        metric = entities.BLEUMetric(
            name="custom-metric",
            workspace="default",
            references=["{{reference}}"],
        )
        await benchmarks_manager._entity_client.create(metric)
        await benchmarks_manager.create(
            "default",
            BenchmarkRequest(
                name="custom-benchmark",
                description=None,
                metrics=[MetricRef(root="default/custom-metric")],
                dataset=FilesetRef(root="default/test-dataset"),
            ),
            mock_sdk,
        )

        job_spec = {
            "benchmark": "default/custom-benchmark",
            "model": {
                "url": "http://nim.test/v1/chat/completions",
                "name": "my/model",
            },
            "prompt_template": "prompt_template",
            "params": {
                "limit_samples": 5,
                "inference": {
                    "max_tokens": 100,
                },
            },
        }
        job = BenchmarkJobAdapter.validate_python(job_spec)
        assert isinstance(job, BenchmarkOnlineJob), "unexpected serialization to job type with BenchmarkJobAdapter"

        with (
            patch(
                "nmp.evaluator.app.datasets.nmp_datasets.fileset.dataset_exists", new_callable=AsyncMock
            ) as mock_fileset_exists,
            patch("nmp.evaluator.app.inference.verify_model_reachable", new_callable=AsyncMock) as mock_verify,
        ):
            mock_fileset_exists.return_value = True
            mock_verify.return_value = {"status": "success"}

            client = new_test_client(benchmarks_manager, mock_sdk=mock_sdk)
            resp = client.post("/apis/evaluation/v2/workspaces/default/benchmark-jobs", json={"spec": job_spec})
            assert resp.status_code == 201, resp.text

            job_resp_spec = BenchmarkJobAdapter.validate_python(resp.json().get("spec"))
            assert isinstance(job_resp_spec, BenchmarkOnlineJob), (
                "unexpected serialization to job type with BenchmarkJobAdapter"
            )
