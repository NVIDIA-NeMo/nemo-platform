# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, patch

import nmp.evaluator.entities as entities
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_platform_plugin.jobs.api_factory import _validate_and_resolve_job_output
from nemo_platform_plugin.jobs.image import get_qualified_image
from nmp.common.entities.client import EntityClient
from nmp.evaluator.api.v2.benchmarks.endpoints import (
    get_benchmarks_manager,
    platform_job_config_compiler,
    router,
)
from nmp.evaluator.api.v2.benchmarks.manager import BenchmarksManager
from nmp.evaluator.api.v2.benchmarks.schemas.benchmarks import BenchmarkRequest
from nmp.evaluator.api.v2.benchmarks.schemas.jobs import (
    BenchmarkJob,
    BenchmarkJobAdapter,
    BenchmarkOfflineJob,
    BenchmarkOnlineAgentJob,
    BenchmarkOnlineJob,
    SystemBenchmarkOfflineJob,
    SystemBenchmarkOnlineJob,
)
from nmp.evaluator.app.evalfactory.bfcl import BFCLHandler
from nmp.evaluator.app.values import FilesetRef, MetricRef
from nmp.evaluator.config import settings


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


# Mirror the job_route_factory configuration from endpoints.py to derive
# the realistic parameters that create_job passes to the compiler.
_, transformer_func = _validate_and_resolve_job_output(
    job_output=None,  # not configured in factory
    job_input=BenchmarkJob,
    input_to_output=None,  # not configured in factory
)


def _compiler_args(
    original_spec: BenchmarkJob, workspace: str, entity_client: EntityClient
) -> tuple[BenchmarkJob, str | None]:
    """Derive transformed_spec and job_name as job_route_factory's create_job would."""
    job_name = None
    transformed_spec = (
        transformer_func(original_spec, workspace, entity_client, job_name) if transformer_func else original_spec
    )
    benchmark_job_types = (
        BenchmarkOfflineJob,
        BenchmarkOnlineJob,
        BenchmarkOnlineAgentJob,
        SystemBenchmarkOfflineJob,
        SystemBenchmarkOnlineJob,
    )
    assert isinstance(transformed_spec, benchmark_job_types), f"Expected BenchmarkJob, got {type(transformed_spec)}"
    return transformed_spec, job_name


@pytest.mark.asyncio
async def test_platform_job_config_compiler_system_benchmark(mock_entity_client: EntityClient, mock_sdk):
    """High level test for compiling a system benchmark to an EvalFactory job spec"""
    original_spec: SystemBenchmarkOnlineJob = BenchmarkJobAdapter.validate_python(
        {
            "model": {
                "url": "http://nim.test/v1/chat/completions",
                "name": "my/model",
            },
            "benchmark_params": {},
            "benchmark": "system/bfclv3-simple",
            "params": {
                "limit_samples": 5,
                "inference": {
                    "max_tokens": 100,
                },
            },
        }
    )

    benchmarks_manager = BenchmarksManager(mock_entity_client)
    benchmark = entities.SystemBenchmark(**BFCLHandler._system_benchmarks[0].model_dump(exclude_none=True))
    await benchmarks_manager._entity_client.create(benchmark)

    with (
        patch(
            "nmp.evaluator.app.datasets.nmp_datasets.fileset.dataset_exists", new_callable=AsyncMock
        ) as mock_fileset_exists,
        patch("nmp.evaluator.app.inference.verify_model_reachable", new_callable=AsyncMock) as mock_verify,
    ):
        mock_fileset_exists.return_value = True
        mock_verify.return_value = {"status": "success"}

        job_spec, _ = _compiler_args(original_spec, "workspace", mock_entity_client)
        platform_job_spec = await platform_job_config_compiler(
            "workspace", original_spec, job_spec, mock_entity_client, None, mock_sdk
        )

    expected_evalfactory_config_yaml = f"""config:
  params:
    limit_samples: 5
    max_new_tokens: 100
    max_retries: 3
    parallelism: 8
    task: simple
  type: bfclv3
output_dir: {settings.jobs.results_dir}
target:
  api_endpoint:
    adapter_config:
      interceptors:
      - config:
          log_failed_requests: true
          output_dir: {settings.jobs.results_dir}
        name: request_logging
      - config:
          cache_dir: {settings.jobs.results_dir}
          reuse_cached_responses: true
          save_requests: true
          save_responses: true
        name: caching
      - name: endpoint
      - config:
          output_dir: {settings.jobs.results_dir}
        name: response_logging
      - name: raise_client_errors
      - config:
          progress_tracking_interval: 1
          progress_tracking_interval_seconds: 60
          progress_tracking_url: ${{NMP_JOBS_URL}}/apis/jobs/v2/workspaces/${{NEMO_JOB_WORKSPACE}}/jobs/${{NEMO_JOB_ID}}/status-details
          request_method: PATCH
        name: progress_tracking
      post_eval_hooks:
      - config:
          report_types:
          - json
        name: post_eval_report
      - config:
          progress_tracking_interval: 1
          progress_tracking_interval_seconds: 60
          progress_tracking_url: ${{NMP_JOBS_URL}}/apis/jobs/v2/workspaces/${{NEMO_JOB_WORKSPACE}}/jobs/${{NEMO_JOB_ID}}/status-details
          request_method: PATCH
        name: progress_tracking
    model_id: my/model
    type: chat
    url: http://nim.test/v1/chat/completions
"""
    expected = {
        "steps": [
            {
                "name": "evaluation",
                "executor": {
                    "provider": "cpu",
                    "container": {
                        "image": settings.evalfactory.bfcl,
                        "command": [
                            "/bin/sh",
                            "-c",
                            f'mkdir -p {settings.jobs.configs_dir} && echo "$NEMO_EVAL_FACTORY_JOB_CONFIG" > {settings.jobs.configs_dir}/evaluation_job_file.yaml && exec nemo-evaluator run_eval --run_config {settings.jobs.configs_dir}/evaluation_job_file.yaml --output_dir {settings.jobs.results_dir} --eval_type bfclv3 --model_id my/model --model_url http://nim.test/v1/chat/completions --model_type chat',
                        ],
                    },
                },
                "config": {
                    "target": {
                        "api_endpoint": {
                            "url": "http://nim.test/v1/chat/completions",
                            "model_id": "my/model",
                            "type": "chat",
                            "adapter_config": {
                                "interceptors": [
                                    {
                                        "name": "request_logging",
                                        "config": {
                                            "output_dir": settings.jobs.results_dir,
                                            "log_failed_requests": True,
                                        },
                                    },
                                    {
                                        "name": "caching",
                                        "config": {
                                            "cache_dir": settings.jobs.results_dir,
                                            "reuse_cached_responses": True,
                                            "save_requests": True,
                                            "save_responses": True,
                                        },
                                    },
                                    {"name": "endpoint"},
                                    {
                                        "name": "response_logging",
                                        "config": {
                                            "output_dir": settings.jobs.results_dir,
                                        },
                                    },
                                    {"name": "raise_client_errors"},
                                    {
                                        "name": "progress_tracking",
                                        "config": {
                                            "progress_tracking_interval": 1,
                                            "progress_tracking_interval_seconds": 60,
                                            "progress_tracking_url": "${NMP_JOBS_URL}/apis/jobs/v2/workspaces/${NEMO_JOB_WORKSPACE}/jobs/${NEMO_JOB_ID}/status-details",
                                            "request_method": "PATCH",
                                        },
                                    },
                                ],
                                "post_eval_hooks": [
                                    {"name": "post_eval_report", "config": {"report_types": ["json"]}},
                                    {
                                        "name": "progress_tracking",
                                        "config": {
                                            "progress_tracking_interval": 1,
                                            "progress_tracking_interval_seconds": 60,
                                            "progress_tracking_url": "${NMP_JOBS_URL}/apis/jobs/v2/workspaces/${NEMO_JOB_WORKSPACE}/jobs/${NEMO_JOB_ID}/status-details",
                                            "request_method": "PATCH",
                                        },
                                    },
                                ],
                            },
                        }
                    },
                    "config": {
                        "type": "bfclv3",
                        "params": {
                            "parallelism": 8,
                            "max_retries": 3,
                            "limit_samples": 5,
                            "max_new_tokens": 100,
                            "task": "simple",
                        },
                    },
                    "output_dir": settings.jobs.results_dir,
                },
                "environment": [
                    {"name": "NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH", "value": settings.jobs.volume_path},
                    {"name": "NEMO_EVAL_FACTORY_JOB_CONFIG", "value": expected_evalfactory_config_yaml},
                ],
            },
            {
                "name": "results",
                "config": {
                    "benchmark": {
                        "description": "BFCL v3 simple single-turn function calling. Tests basic "
                        "function call generation.",
                        "labels": {
                            "eval_category": "agentic",
                            "eval_harness": "bfcl",
                        },
                        "name": "bfclv3-simple",
                        "optional_params": [],
                        "required_params": [],
                        "supported_job_types": [
                            "online",
                        ],
                    },
                    "benchmark_params": {},
                    "model": {
                        "format": "nim",
                        "name": "my/model",
                        "url": "http://nim.test/v1/chat/completions",
                    },
                    "params": {
                        "ignore_request_failure": False,
                        "inference": {
                            "max_tokens": 100,
                        },
                        "limit_samples": 5,
                        "max_retries": 3,
                        "parallelism": 8,
                    },
                },
                "executor": {
                    "provider": "cpu",
                    "container": {
                        "image": get_qualified_image("nmp-cpu-tasks"),
                        "entrypoint": ["python", "-m", "nmp.evaluator.tasks.metric_results"],
                        "command": [
                            "--progress-tracking-url",
                            "${NMP_JOBS_URL}/apis/jobs/v2/workspaces/${NEMO_JOB_WORKSPACE}/jobs/${NEMO_JOB_ID}/status-details",
                        ],
                    },
                },
                "environment": [
                    {"name": "NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH", "value": settings.jobs.volume_path},
                    {"name": "LOG_FORMAT", "value": "json"},
                    {"name": "NEMO_EVAL_HARNESS", "value": "bfcl"},
                ],
            },
        ]
    }
    assert platform_job_spec == expected


class TestCreateBenchmarkJobEndpoint:
    @pytest.mark.asyncio
    async def test_create_system_benchmark_unsupported_offline_job(self, benchmarks_manager, mock_sdk):
        """Test job spec and serialization of API schemas for system benchmark job."""
        # Populate system benchmark to reference for job.
        system_benchmark = entities.SystemBenchmark(**BFCLHandler._system_benchmarks[0].model_dump(exclude_none=True))
        await benchmarks_manager._entity_client.create(system_benchmark)

        job_spec = {
            "benchmark": "system/bfclv3-simple",
            "dataset": "default/test-dataset",
            "params": {
                "limit_samples": 5,
            },
        }
        job = BenchmarkJobAdapter.validate_python(job_spec)
        assert isinstance(job, SystemBenchmarkOfflineJob), (
            "unexpected serialization to job type with BenchmarkJobAdapter"
        )

        with patch(
            "nmp.evaluator.app.datasets.nmp_datasets.fileset.dataset_exists", new_callable=AsyncMock
        ) as mock_fileset_exists:
            mock_fileset_exists.return_value = True

            client = new_test_client(benchmarks_manager, mock_sdk=mock_sdk)
            resp = client.post("/apis/evaluation/v2/workspaces/default/benchmark-jobs", json={"spec": job_spec})
            assert resp.status_code == 422, resp.text
            assert "benchmark does not support offline evaluations" in resp.text

    @pytest.mark.asyncio
    async def test_create_system_benchmark_online_job(self, benchmarks_manager, mock_sdk):
        """Test job spec and serialization of API schemas for system benchmark job."""
        # Populate system benchmark to reference for job.
        system_benchmark = entities.SystemBenchmark(**BFCLHandler._system_benchmarks[0].model_dump(exclude_none=True))
        await benchmarks_manager._entity_client.create(system_benchmark)

        job_spec = {
            "benchmark": "system/bfclv3-simple",
            "model": {
                "url": "http://nim.test/v1/chat/completions",
                "name": "my/model",
            },
            "params": {
                "limit_samples": 5,
                "inference": {
                    "max_tokens": 100,
                },
            },
        }
        job = BenchmarkJobAdapter.validate_python(job_spec)
        assert isinstance(job, SystemBenchmarkOnlineJob), (
            "unexpected serialization to job type with BenchmarkJobAdapter"
        )

        with patch("nmp.evaluator.app.inference.verify_model_reachable", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"status": "success"}

            client = new_test_client(benchmarks_manager, mock_sdk=mock_sdk)
            resp = client.post("/apis/evaluation/v2/workspaces/default/benchmark-jobs", json={"spec": job_spec})
            assert resp.status_code == 201, resp.text

            job_resp_spec = BenchmarkJobAdapter.validate_python(resp.json().get("spec"))
            assert isinstance(job_resp_spec, SystemBenchmarkOnlineJob), (
                "unexpected serialization to job type with BenchmarkJobAdapter"
            )

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
