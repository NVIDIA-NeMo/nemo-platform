# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Any, Generator, cast
from unittest.mock import AsyncMock, patch

import nmp.evaluator.app.values as app
import nmp.evaluator.entities as entities
import pytest
import pytest_asyncio
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from nemo_evaluator_sdk.values import AggregatedMetricResult
from nemo_evaluator_sdk.values.metrics import default_judge_prompt_template_chat
from nemo_platform_plugin.jobs.api_factory import _validate_and_resolve_job_output
from nemo_platform_plugin.jobs.image import get_qualified_image
from nmp.common.entities import EntityClient
from nmp.common.jobs.constants import EPHEMERAL_TASK_STORAGE_PATH_ENVVAR, PERSISTENT_JOB_STORAGE_PATH_ENVVAR
from nmp.evaluator.api.v2.common.query_params import AggregateFieldNameList
from nmp.evaluator.api.v2.metrics.endpoints import (
    create_metric,
    delete_metric,
    evaluate_metric,
    get_metric,
    get_metrics_manager,
    platform_job_config_compiler,
    router,
)
from nmp.evaluator.api.v2.metrics.manager import MetricsManager
from nmp.evaluator.api.v2.metrics.schemas.evaluation import (
    EvaluateDatasetRows,
    MetricEvaluationRequest,
    MetricEvaluationResponse,
)
from nmp.evaluator.api.v2.metrics.schemas.jobs import (
    MetricJob,
    MetricJobAdapter,
    MetricOfflineJob,
    MetricOnlineJob,
    MetricRetrieverJob,
)
from nmp.evaluator.api.v2.metrics.schemas.metrics import (
    BLEUMetric,
    LLMJudgeMetric,
    RemoteMetric,
    ROUGEMetric,
    StringCheckMetric,
)
from nmp.evaluator.api.v2.metrics.schemas.metrics_resp import (
    MetricJobResult,
    MetricJobResultsListResponse,
    MetricResponseAdapter,
    MetricsListResponse,
)
from nmp.evaluator.app.evalfactory.agentic_eval import AgenticEvalHandler
from nmp.evaluator.app.evalfactory.retriever import RetrieverHandler
from nmp.evaluator.app.jobs.fileset import fileset_entrypoint_args
from nmp.evaluator.config import settings
from nmp.testing import create_test_client

WORKSPACE = "my-workspace"

# Mirror the job_route_factory configuration from endpoints.py to derive
# the realistic parameters that create_job passes to the compiler.
_, transformer_func = cast(
    tuple[MetricJob, None],
    _validate_and_resolve_job_output(
        job_output=None,  # not configured in factory
        job_input=MetricJob,
        input_to_output=None,  # not configured in factory
    ),
)


def _compiler_args(
    original_spec: MetricJob,
    workspace: str,
    entity_client: EntityClient,
) -> tuple[MetricJob, str | None]:
    """Derive transformed_spec and job_name as job_route_factory's create_job would."""
    job_name = None
    transformed_spec = (
        transformer_func(original_spec, workspace, entity_client, job_name) if transformer_func else original_spec
    )
    return transformed_spec, job_name


def test_metric_job_params_reject_aggregate_fields() -> None:
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        MetricJobAdapter.validate_python(
            {
                "metric": "default/exact-match",
                "dataset": "default/dataset",
                "params": {"aggregate_fields": ["mean"]},
            }
        )


def _subset_match(expected: dict[str, Any], actual: dict[str, Any], path: str = "") -> list[str]:
    """Check if expected dict is a subset of actual dict. Returns list of mismatches."""
    errors = []
    for key, expected_value in expected.items():
        current_path = f"{path}.{key}" if path else key
        if key not in actual:
            errors.append(f"Missing key: {current_path}")
            continue
        actual_value = actual[key]
        if isinstance(expected_value, dict) and isinstance(actual_value, dict):
            errors.extend(_subset_match(expected_value, actual_value, current_path))
        elif expected_value != actual_value:
            errors.append(f"Mismatch at {current_path}: expected {expected_value!r}, got {actual_value!r}")
    return errors


@pytest.fixture
def mock_entity_client() -> Generator[EntityClient, None, None]:
    """Real EntityClient backed by in-memory storage for integration-style testing."""
    # Include workspaces needed by tests (default + cross-workspace tests)
    workspaces = ["default", "system"]
    with create_test_client(client_type=EntityClient, workspaces=workspaces) as client:
        yield client


# mock_sdk fixture is now provided by conftest.py


@pytest.fixture
def metrics_manager(mock_entity_client) -> MetricsManager:
    """MetricsManager instance with mocked EntityClient."""
    return MetricsManager(mock_entity_client)


@pytest_asyncio.fixture
async def create_sample_metric_job_results(mock_entity_client):
    await mock_entity_client.create(
        entities.MetricJobResult(
            name="result1",
            workspace="default",
            metric=app.MetricRef("default/metric"),
            dataset=app.FilesetRef("default/dataset"),
            scores=AggregatedMetricResult.model_validate(
                {
                    "scores": [
                        {
                            "name": "accuracy",
                            "mean": 0.85,
                            "count": 100,
                            "nan_count": 0,
                            "std_dev": 0.2,
                            "min": 0.1,
                            "max": 1.0,
                        }
                    ]
                }
            ).scores,
        )
    )
    await mock_entity_client.create(
        entities.MetricJobResult(
            name="result2",
            workspace="default",
            metric=app.MetricRef("default/metric2"),
            dataset=app.FilesetRef("default/dataset2"),
            scores=AggregatedMetricResult.model_validate(
                {"scores": [{"name": "accuracy", "mean": 0.1, "count": 100, "nan_count": 0, "min": 0.1, "max": 0.1}]}
            ).scores,
        )
    )
    await mock_entity_client.create(
        entities.MetricJobResult(
            name="result3",
            workspace="default",
            metric=app.MetricRef("default/metric"),
            dataset=app.FilesetRef("default/dataset"),
            model=app.ModelRef("default/model"),
            labels={"label": "value"},
            scores=AggregatedMetricResult.model_validate(
                {"scores": [{"name": "accuracy", "mean": 0.1, "count": 100, "nan_count": 0, "min": 0.1}]}
            ).scores,
        )
    )


def new_test_client(manager: MetricsManager, mock_sdk=None) -> TestClient:
    """Fast API test client with metrics manager"""

    def override_get_metrics_manager() -> MetricsManager:
        return manager

    app = FastAPI()
    app.include_router(router, prefix="/apis/evaluation")
    app.dependency_overrides[get_metrics_manager] = override_get_metrics_manager

    # Override get_sdk_client if mock_sdk is provided
    if mock_sdk is not None:
        from nmp.common.service.dependencies import get_sdk_client

        app.dependency_overrides[get_sdk_client] = lambda: mock_sdk

    return TestClient(app)


class TestMetricJobSecretRefSchema:
    def test_metric_job_schema_uses_strict_service_secret_ref_pattern(self) -> None:
        schema = MetricJobAdapter.json_schema()
        secret_ref_defs = {
            name: value
            for name, value in schema["$defs"].items()
            if isinstance(value, dict) and value.get("title") == "SecretRef"
        }

        assert secret_ref_defs
        assert {value["pattern"] for value in secret_ref_defs.values()} == {r"^[a-z0-9_-]+(/[a-z0-9_-]+)?$"}

    def test_metric_response_schema_uses_strict_service_secret_ref_pattern(self) -> None:
        serialized_schema = str(MetricResponseAdapter.json_schema())

        assert "^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)?$" not in serialized_schema
        assert "^[a-z0-9_-]+(/[a-z0-9_-]+)?$" in serialized_schema

    def test_model_api_key_secret_rejects_uppercase_in_service_schema(self) -> None:
        with pytest.raises(ValueError, match="String should match pattern"):
            MetricJobAdapter.validate_python(
                {
                    "model": {
                        "url": "http://nim.test/v1/chat/completions",
                        "name": "my/model",
                        "api_key_secret": "NVIDIA_BUILD_API_KEY",
                    },
                    "dataset": {"rows": [{"prompt": "hello world"}]},
                    "metric": {
                        "type": "exact-match",
                        "reference": "{{item.expected}}",
                    },
                    "prompt_template": "{{item.prompt}}",
                }
            )

    def test_llm_judge_api_key_secret_rejects_uppercase_in_service_schema(self) -> None:
        with pytest.raises(ValueError, match="String should match pattern"):
            LLMJudgeMetric.model_validate(
                {
                    "type": "llm-judge",
                    "model": {
                        "url": "http://judge-nim.test/v1/chat/completions",
                        "name": "my/judge",
                        "api_key_secret": "NVIDIA_BUILD_API_KEY",
                    },
                    "scores": [{"name": "quality", "minimum": 1, "maximum": 5}],
                }
            )

    def test_remote_metric_api_key_secret_rejects_uppercase_in_service_schema(self) -> None:
        with pytest.raises(ValueError, match="String should match pattern"):
            RemoteMetric.model_validate(
                {
                    "type": "remote",
                    "url": "http://remote.test/score",
                    "api_key_secret": "NVIDIA_BUILD_API_KEY",
                    "body": {"input": "{{item.input}}"},
                    "scores": [{"name": "quality"}],
                }
            )


@pytest.mark.asyncio
@patch.dict(os.environ, {"my_model_secret_name": "model_secret_***", "my_judge_secret_name": "judge_secret_***"})
async def test_platform_job_config_compiler_llm_judge_metric(mock_entity_client: EntityClient, mock_sdk):
    """High level test for compiling a custom in-line metric to a job spec"""
    original_spec: MetricOnlineJob = MetricJobAdapter.validate_python(
        {
            "model": {
                "url": "http://nim.test/v1/chat/completions",
                "name": "my/model",
                "api_key_secret": "my-model-secret-name",
            },
            "dataset": {
                "rows": [{"prompt": "hello world"}],
            },
            "metric": {
                "type": "llm-judge",
                "model": {
                    "url": "http://judge-nim.test/v1/chat/completions",
                    "name": "my/judge",
                    "api_key_secret": "my-judge-secret-name",
                },
                "inference": {"max_tokens": 100},
                "scores": [
                    {
                        "name": "length",
                        "rubric": [
                            {"label": "short", "value": 0},
                            {"label": "medium", "value": 1},
                            {"label": "long", "value": 2},
                        ],
                    }
                ],
            },
            "prompt_template": {"messages": [{"role": "user", "content": "{{prompt}}"}]},
            "params": {
                "limit_samples": 5,
                "inference": {
                    "max_tokens": 300,
                },
            },
        }
    )
    # Mock the model reachability check
    with (
        patch(
            "nmp.evaluator.app.datasets.nmp_datasets.fileset.dataset_exists", new_callable=AsyncMock
        ) as mock_fileset_exists,
        patch("nmp.evaluator.app.inference.verify_model_reachable", new_callable=AsyncMock) as mock_verify,
    ):
        mock_fileset_exists.return_value = True
        mock_verify.return_value = {"status": "success"}

        transformed_spec, _ = _compiler_args(original_spec, WORKSPACE, mock_entity_client)
        platform_job_spec = await platform_job_config_compiler(
            WORKSPACE, original_spec, transformed_spec, mock_entity_client, None, mock_sdk
        )

        # Verify job can be serialized after resolving metric
        # emulates Jobs API factory handle_job_spec_mismatch
        MetricJobAdapter.validate_python(transformed_spec.model_dump(exclude_none=True))

    expected_metric_config = {
        "params": {
            "ignore_request_failure": False,
            "inference": {"max_tokens": 300},
            "parallelism": 8,
            "max_retries": 3,
            "limit_samples": 5,
        },
        "metric_params": {},
        "metric": {
            "type": "llm-judge",
            "labels": {},
            "supported_job_types": ["online", "offline"],
            "job_type": "online",
            "model": {
                "url": "http://judge-nim.test/v1/chat/completions",
                "name": "my/judge",
                "api_key_secret": "my-judge-secret-name",
                "format": "nim",
            },
            # structured_output is runtime-derived by the SDK metric from the score definitions.
            # The compiled job spec persists user/config inputs only, so it should not include
            # this generated schema payload.
            "prompt_template": default_judge_prompt_template_chat(),
            "optional_fields": [],
            "ignore_request_failure": False,
            "inference": {"max_tokens": 100},
            "scores": [
                {
                    "name": "length",
                    "rubric": [
                        {"label": "short", "value": 0},
                        {"label": "medium", "value": 1},
                        {"label": "long", "value": 2},
                    ],
                    "parser": {"type": "json", "json_path": "length"},
                }
            ],
            "structured_output": {
                "schema": {
                    "properties": {
                        "length": {
                            "enum": [
                                "short",
                                "medium",
                                "long",
                            ],
                            "type": "string",
                        },
                    },
                    "required": [
                        "length",
                    ],
                    "type": "object",
                },
            },
        },
        "model": {
            "url": "http://nim.test/v1/chat/completions",
            "name": "my/model",
            "api_key_secret": "my-model-secret-name",
            "format": "nim",
        },
        "dataset": {"rows": [{"prompt": "hello world"}]},
        "prompt_template": {"messages": [{"role": "user", "content": "{{prompt}}"}]},
        "optional_fields": [],
    }
    expected = {
        "steps": [
            {
                "name": "evaluation",
                "executor": {
                    "provider": "cpu",
                    "container": {
                        "image": get_qualified_image("nmp-cpu-tasks"),
                        "entrypoint": [
                            "python",
                            "-m",
                            "nmp.evaluator.tasks.evaluate_metric",
                        ],
                        "command": [
                            "--progress-tracking-url",
                            "${NMP_JOBS_URL}/apis/jobs/v2/workspaces/${NEMO_JOB_WORKSPACE}/jobs/${NEMO_JOB_ID}/status-details",
                        ],
                    },
                },
                "config": expected_metric_config,
                "environment": [
                    {"name": "NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH", "value": settings.jobs.volume_path},
                    {"name": "LOG_FORMAT", "value": "json"},
                    {"name": "my_model_secret_name", "from_secret": {"name": "my-model-secret-name"}},
                    {"name": "my_judge_secret_name", "from_secret": {"name": "my-judge-secret-name"}},
                ],
            },
        ]
    }

    assert platform_job_spec == expected


@pytest.mark.asyncio
async def test_platform_job_config_compiler_unsupported_inline_system_metric(
    mock_entity_client: EntityClient, mock_sdk
):
    """Test system metric cannot be inline and only supports metric ref"""

    original_spec = MetricOfflineJob(
        metric=app.SystemMetric(
            name="my-custom-system-metric",
        ),
        dataset=app.FilesetRef(root="default/my-dataset"),
    )
    with pytest.raises(HTTPException) as exc_info:
        transformed_spec, _ = _compiler_args(original_spec, WORKSPACE, mock_entity_client)
        await platform_job_config_compiler(
            WORKSPACE, original_spec, transformed_spec, mock_entity_client, None, mock_sdk
        )

    assert isinstance(exc_info.value, HTTPException)
    assert exc_info.value.status_code == 422
    assert (
        "Unsupported job with custom system metric. Use metric reference instead 'system/<metric-name>'"
        in exc_info.value.detail
    )


@pytest.mark.asyncio
async def test_platform_job_config_compiler_system_metric(mock_entity_client: EntityClient, mock_sdk):
    """High level test for compiling a system metric to an EvalFactory job spec"""
    job: MetricOfflineJob = MetricJobAdapter.validate_python(
        {
            "metric": "system/trajectory-evaluation",
            "dataset": "my-workspace/dataset",
            "params": {
                "limit_samples": 5,
            },
            "metric_params": {
                "judge": {"model": {"url": "http://nim.test/v1/chat/completions", "name": "my/judge"}},
                "trajectory_used_tools": "tool1,tool2",
            },
        }
    )

    metrics_manager = MetricsManager(mock_entity_client)
    agentic_metric = AgenticEvalHandler._system_metrics[0]
    agentic_metric_config = agentic_metric.model_dump(mode="json", exclude_none=True)
    agentic_metric_entity = entities.SystemMetric(**agentic_metric_config)
    await metrics_manager.create(agentic_metric_entity, sdk=mock_sdk)

    with (
        patch(
            "nmp.evaluator.app.datasets.nmp_datasets.fileset.dataset_exists", new_callable=AsyncMock
        ) as mock_fileset_exists,
        patch("nmp.evaluator.app.inference.verify_model_reachable", new_callable=AsyncMock) as mock_verify,
    ):
        mock_fileset_exists.return_value = True
        mock_verify.return_value = {"status": "success"}

        transformed_spec, _ = _compiler_args(job, WORKSPACE, mock_entity_client)
        platform_job_spec = await platform_job_config_compiler(
            WORKSPACE, job, transformed_spec, mock_entity_client, None, mock_sdk
        )

    # Verify job can be serialized after resolving metric
    # emulates Jobs API factory handle_job_spec_mismatch
    MetricJobAdapter.validate_python(job.model_dump(exclude_none=True))

    expected_evalfactory_config_yaml = f"""config:
  params:
    extra:
      dataset_path: {settings.jobs.dataset_dir}/my-workspace/dataset
      judge:
        model:
          name: my/judge
          url: http://nim.test/v1/chat/completions
      judge_model_args: {{}}
      judge_model_type: nvidia-nim
      trajectory_used_tools: tool1,tool2
    limit_samples: 5
    parallelism: 8
  type: agentic_eval_trajectory_evaluation
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
    model_id: my/judge
    type: chat
    url: http://nim.test/v1/chat/completions
"""
    scratch_path = f"${{{EPHEMERAL_TASK_STORAGE_PATH_ENVVAR}}}"
    target_download_dir = f"${{{PERSISTENT_JOB_STORAGE_PATH_ENVVAR}}}/datasets"
    dataset_download_command = fileset_entrypoint_args(
        app.FilesetRef(root="my-workspace/dataset"),
        target_download_dir,
        scratch_path,
    )

    expected = {
        "steps": [
            {
                "environment": [
                    {
                        "name": "NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH",
                        "value": settings.jobs.volume_path,
                    },
                ],
                "executor": {
                    "container": {
                        "command": dataset_download_command,
                        "entrypoint": [
                            "python",
                            "-m",
                            "nmp.evaluator.tasks.download_fileset",
                        ],
                        "image": get_qualified_image("nmp-cpu-tasks"),
                    },
                    "provider": "cpu",
                },
                "name": "dataset-download",
            },
            {
                "name": "evaluation",
                "executor": {
                    "provider": "cpu",
                    "container": {
                        "image": settings.evalfactory.agentic_eval,
                        "command": [
                            "/bin/sh",
                            "-c",
                            f'mkdir -p {settings.jobs.configs_dir} && echo "$NEMO_EVAL_FACTORY_JOB_CONFIG" > {settings.jobs.configs_dir}/evaluation_job_file.yaml && exec nemo-evaluator run_eval --run_config {settings.jobs.configs_dir}/evaluation_job_file.yaml --output_dir {settings.jobs.results_dir} --eval_type agentic_eval_trajectory_evaluation --model_id my/judge --model_url http://nim.test/v1/chat/completions --model_type chat',
                        ],
                    },
                },
                "config": {
                    "target": {
                        "api_endpoint": {
                            "url": "http://nim.test/v1/chat/completions",
                            "model_id": "my/judge",
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
                        "type": "agentic_eval_trajectory_evaluation",
                        "params": {
                            "extra": {
                                "dataset_path": f"{settings.jobs.dataset_dir}/my-workspace/dataset",
                                "judge": {"model": {"url": "http://nim.test/v1/chat/completions", "name": "my/judge"}},
                                "judge_model_args": {},
                                "judge_model_type": "nvidia-nim",
                                "trajectory_used_tools": "tool1,tool2",
                            },
                            "parallelism": 8,
                            "limit_samples": 5,
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
                    "dataset": "my-workspace/dataset",
                    "dataset_ref": "my-workspace/dataset",
                    "metric": agentic_metric_config,
                    "metric_params": {
                        "judge": {
                            "model": {
                                "name": "my/judge",
                                "url": "http://nim.test/v1/chat/completions",
                            },
                        },
                        "judge_model_args": {},
                        "judge_model_type": "nvidia-nim",
                        "trajectory_used_tools": "tool1,tool2",
                    },
                    "metric_ref": "system/trajectory-evaluation",
                    "params": {
                        "limit_samples": 5,
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
                    {"name": "NEMO_EVAL_HARNESS", "value": "agentic_eval"},
                ],
            },
        ]
    }
    assert platform_job_spec == expected


class TestCreateMetricEndpoint:
    """Tests for the create_metric endpoint function.

    Regression tests for NVBug 5827225: isinstance() was incorrectly used with
    a subscripted generic type (Metric = Annotated[Union[...]]), causing a
    TypeError when creating BLEU, ROUGE, or StringCheck metrics.

    """

    @pytest.mark.asyncio
    async def test_create_metric_bleu(self, metrics_manager):
        """Test create_metric endpoint successfully creates a BLEU metric.

        Regression test for NVBug 5827225.
        """
        # Arrange
        bleu_request = BLEUMetric(
            references=["{{item.reference}}"],
        )

        # Act - call the endpoint function directly
        result = await create_metric(
            workspace="default",
            name="test-bleu",
            metric_request=bleu_request,
            metrics_manager=metrics_manager,
        )

        # Assert
        assert result is not None
        assert result.name == "test-bleu"
        assert result.type == "bleu"

    @pytest.mark.asyncio
    async def test_create_metric_rouge(self, metrics_manager):
        """Test create_metric endpoint successfully creates a ROUGE metric.

        Regression test for NVBug 5827225.
        """
        # Arrange
        rouge_request = ROUGEMetric(
            reference="{{item.reference}}",
        )

        # Act - call the endpoint function directly
        result = await create_metric(
            workspace="default",
            name="test-rouge",
            metric_request=rouge_request,
            metrics_manager=metrics_manager,
        )

        # Assert
        assert result is not None
        assert result.name == "test-rouge"
        assert result.type == "rouge"

    @pytest.mark.asyncio
    async def test_create_metric_string_check(self, metrics_manager):
        """Test create_metric endpoint successfully creates a StringCheck metric.

        Regression test for NVBug 5827225.
        """
        # Arrange
        string_check_request = StringCheckMetric(
            operation="contains",
            left_template="{{item.response}}",
            right_template="{{item.expected}}",
        )

        # Act - call the endpoint function directly
        result = await create_metric(
            workspace="default",
            name="test-string-check",
            metric_request=string_check_request,
            metrics_manager=metrics_manager,
        )

        # Assert
        assert result is not None
        assert result.name == "test-string-check"
        assert result.type == "string-check"


@pytest.mark.asyncio
async def test_platform_job_config_compiler_retriever_metric(
    mock_entity_client: EntityClient, mock_sdk, metrics_manager: MetricsManager
):
    """End-to-end test for compiling a retriever system metric to an EvalFactory job spec.

    This test verifies the complete flow from retriever job input to platform job spec,
    using a BuiltInDataset (BEIR) for evaluation.
    """
    original_spec: MetricRetrieverJob = MetricJobAdapter.validate_python(
        {
            "retriever_pipeline": {
                "embeddings_model": {
                    "url": "https://integrate.api.nvidia.com/v1",
                    "name": "nvidia/nv-embedqa-e5-v5",
                    "format": "nim",
                    "api_key_secret": "embedding-secret",
                },
            },
            "dataset": "beir/fiqa",  # BuiltInDataset (plain string)
            "metric": "system/retriever-ndcg-cut-10",
            "metric_params": {
                "dataset_format": "beir",
                "top_k": 10,
            },
        }
    )

    # Register the retriever metric in the entity store
    retriever_metric = next(m for m in RetrieverHandler._system_metrics if m.name == "retriever-ndcg-cut-10")
    retriever_metric_entity = entities.SystemMetric(**retriever_metric.model_dump(exclude_none=True))
    await metrics_manager.create(retriever_metric_entity, sdk=mock_sdk)

    # Mock the fileset check
    with (
        patch(
            "nmp.evaluator.app.datasets.nmp_datasets.fileset.dataset_exists", new_callable=AsyncMock
        ) as mock_fileset_exists,
        patch("nmp.evaluator.app.inference.verify_model_reachable", new_callable=AsyncMock) as mock_verify,
    ):
        mock_fileset_exists.return_value = True
        mock_verify.return_value = {"status": "success"}

        transformed_spec, _ = _compiler_args(original_spec, WORKSPACE, mock_entity_client)
        platform_job_spec = await platform_job_config_compiler(
            WORKSPACE, original_spec, transformed_spec, mock_entity_client, None, mock_sdk
        )

    # Verify job can be serialized after resolving metric
    # emulates Jobs API factory handle_job_spec_mismatch
    MetricJobAdapter.validate_python(transformed_spec.model_dump(exclude_none=True))

    # Expected evaluation step configuration
    expected_eval_step = yaml.safe_load(
        """
        name: evaluation
        executor:
            container:
                image: {image}
        config:
            target:
                api_endpoint:
                    type: embedding
            config:
                type: retriever
                params:
                    extra:
                        tasks:
                            retriever:
                                dataset:
                                    format: beir
                                    path: fiqa
                                metrics:
                                    ndcg_cut_10:
                                        type: pytrec_eval
                        pipeline:
                            query_embedding_model:
                                api_endpoint:
                                    url: https://integrate.api.nvidia.com/v1
                                    model_id: nvidia/nv-embedqa-e5-v5
                                    format: nim
                                    api_key: $QUERY_API_KEY
                            index_embedding_model:
                                api_endpoint:
                                    url: https://integrate.api.nvidia.com/v1
                                    model_id: nvidia/nv-embedqa-e5-v5
                                    format: nim
                                    api_key: $INDEX_API_KEY
                            top_k: 10
    """.format(image=settings.evalfactory.rag_retriever)
    )

    # Expected results step configuration
    expected_results_step = yaml.safe_load(
        """
        name: results
        executor:
            container:
                image: {image}
                entrypoint:
                    - python
                    - -m
                    - nmp.evaluator.tasks.metric_results
    """.format(image=get_qualified_image("nmp-cpu-tasks"))
    )

    # Verify job structure has both evaluation and results steps
    assert "steps" in platform_job_spec
    steps = list(platform_job_spec["steps"])
    assert len(steps) >= 2, "Expected at least evaluation and results steps"

    eval_step = cast(dict[str, Any], steps[0])
    results_step = cast(dict[str, Any], steps[1])

    # Extract expected path before comparison (BuiltInDataset uses the name directly)
    expected_dataset_path = expected_eval_step["config"]["config"]["params"]["extra"]["tasks"]["retriever"][
        "dataset"
    ].pop("path")

    # Compare evaluation step using subset matching (excluding dynamic path)
    errors = _subset_match(expected_eval_step, eval_step)
    assert not errors, "Evaluation step config mismatch:\n" + "\n".join(errors)

    # Compare results step using subset matching
    errors = _subset_match(expected_results_step, results_step)
    assert not errors, "Results step config mismatch:\n" + "\n".join(errors)

    # Verify dataset path ends with expected value (path includes output_dir prefix)
    dataset = eval_step["config"]["config"]["params"]["extra"]["tasks"]["retriever"]["dataset"]
    assert dataset["path"].endswith(expected_dataset_path), (
        f"Expected dataset path to end with '{expected_dataset_path}', got: {dataset['path']}"
    )

    # Verify dense_only yaml files are used (no reranker configured)
    retriever_params = eval_step["config"]["config"]["params"]["extra"]["pipeline"]["params"]
    assert "dense_only" in retriever_params["index_pipeline_yaml_file"]
    assert "dense_only" in retriever_params["query_pipeline_yaml_file"]

    # Verify secrets in environment (only embedding, no reranker)
    env_names = [e["name"] for e in eval_step["environment"] if "from_secret" in e]
    assert "QUERY_API_KEY" in env_names
    assert "INDEX_API_KEY" in env_names


class TestAggregateFieldNameList:
    """Tests for AggregateFieldNameList query parameter parsing."""

    def test_parse_none(self):
        """Test parsing None value returns empty list."""
        result = AggregateFieldNameList.model_validate(None)
        assert result.root == []

    def test_parse_empty_list(self):
        """Test parsing empty list returns empty list."""
        result = AggregateFieldNameList.model_validate([])
        assert result.root == []

    def test_parse_single_value(self):
        """Test parsing a single string value."""
        result = AggregateFieldNameList.model_validate(["mean"])
        assert result.root == ["mean"]

    def test_parse_multiple_values(self):
        """Test parsing multiple string values."""
        result = AggregateFieldNameList.model_validate(["mean", "std_dev", "min"])
        assert result.root == ["mean", "std_dev", "min"]

    def test_parse_comma_separated_string(self):
        """Test parsing comma-separated values in a single string."""
        result = AggregateFieldNameList.model_validate(["mean,std_dev,min"])
        assert result.root == ["mean", "std_dev", "min"]

    def test_parse_mixed_formats(self):
        """Test parsing mixed formats (comma-separated and separate items)."""
        result = AggregateFieldNameList.model_validate(["mean,std_dev", "min", "max"])
        assert result.root == ["mean", "std_dev", "min", "max"]

    def test_parse_with_whitespace(self):
        """Test parsing values with whitespace are trimmed."""
        result = AggregateFieldNameList.model_validate(["mean , std_dev , min"])
        assert result.root == ["mean", "std_dev", "min"]

    def test_parse_dict_with_aggregate_fields_key(self):
        """Test parsing dict format (FastAPI query param representation)."""
        result = AggregateFieldNameList.model_validate({"aggregate_fields": ["mean", "std_dev"]})
        assert result.root == ["mean", "std_dev"]

    def test_parse_dict_with_root_key(self):
        """Test parsing dict format with 'root' key."""
        result = AggregateFieldNameList.model_validate({"root": ["mean", "std_dev"]})
        assert result.root == ["mean", "std_dev"]


class TestListMetricsEndpoint:
    """Tests for the list_metrics endpoint function."""

    async def _create_metrics(self, metrics_manager: MetricsManager, mock_sdk):
        metric1 = entities.StringCheckMetric(
            name="metric-1",
            workspace="default",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
            labels={"label1": "value1"},
        )
        metric2 = entities.BLEUMetric(
            name="metric-2",
            workspace="default",
            references=["{{reference}}"],
        )
        await metrics_manager.create(metric1, sdk=mock_sdk)
        await metrics_manager.create(metric2, sdk=mock_sdk)

    @pytest.mark.asyncio
    async def test_list_metrics_empty(self, metrics_manager):
        """Test list_metrics returns empty page when no metrics exist."""
        client = new_test_client(metrics_manager)
        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics")
        assert resp.status_code == 200, resp.json()

        result = MetricsListResponse.model_validate(resp.json())

        assert result.data == []
        assert result.pagination is not None
        assert result.pagination.total_results == 0
        assert result.pagination.page == 1

    @pytest.mark.asyncio
    async def test_list_metrics_returns_metrics(self, metrics_manager, mock_sdk):
        """Test list_metrics returns all metrics for the workspace."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics")
        assert resp.status_code == 200, resp.json()

        result = MetricsListResponse.model_validate(resp.json())

        assert len(result.data) == 2
        assert result.pagination is not None
        assert result.pagination.total_results == 2
        names = {m.name for m in result.data}
        assert names == {"metric-1", "metric-2"}

    @pytest.mark.asyncio
    async def test_list_metrics_sort_pagination(self, metrics_manager, mock_sdk):
        """Test list_metrics returns sorted response."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?page_size=5&sort=name")
        assert resp.status_code == 200, resp.json()

        result = MetricsListResponse.model_validate(resp.json())

        assert len(result.data) == 2
        assert result.pagination is not None
        assert result.pagination.total_results == 2
        assert result.pagination.page_size == 5
        assert result.sort == "name"
        names = [m.name for m in result.data]
        assert names == ["metric-1", "metric-2"]

    @pytest.mark.asyncio
    async def test_list_metrics_filter_type(self, metrics_manager, mock_sdk):
        """Test list_metrics returns filtered by metric type."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?filter[type]=bleu")
        assert resp.status_code == 200, resp.json()

        result = MetricsListResponse.model_validate(resp.json())

        assert len(result.data) == 1
        assert result.pagination is not None
        assert result.pagination.total_results == 1
        assert result.filter == {"type": {"$eq": "bleu"}}
        names = {m.name for m in result.data}
        assert names == {"metric-2"}

    @pytest.mark.asyncio
    async def test_list_metrics_filter_label(self, metrics_manager, mock_sdk):
        """Test list_metrics returns filtered by label."""
        await self._create_metrics(metrics_manager, mock_sdk)
        client = new_test_client(metrics_manager)

        # Filter with brackets
        resp = client.get("/apis/evaluation/v2/workspaces/default/metrics?filter[data.labels.label1]=value1")
        assert resp.status_code == 200, resp.json()

        result_bracket = MetricsListResponse.model_validate(resp.json())

        assert len(result_bracket.data) == 1
        assert result_bracket.pagination is not None
        assert result_bracket.pagination.total_results == 1
        names = {m.name for m in result_bracket.data}
        assert names == {"metric-1"}

        # Filter with json
        resp = client.get(
            '/apis/evaluation/v2/workspaces/default/metrics?filter={"data.labels.label1": {"$eq": "value1"}}'
        )
        assert resp.status_code == 200, resp.json()

        result_json = MetricsListResponse.model_validate(resp.json())
        assert result_bracket.data == result_json.data
        assert result_bracket.pagination == result_json.pagination


class TestGetMetricEndpoint:
    """Tests for the get_metric endpoint function."""

    @pytest.mark.asyncio
    async def test_get_metric_success(self, metrics_manager, mock_sdk):
        """Test get_metric returns the metric when found."""
        metric = entities.StringCheckMetric(
            name="test-metric",
            workspace="default",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        await metrics_manager.create(metric, sdk=mock_sdk)

        result = await get_metric(workspace="default", name="test-metric", metrics_manager=metrics_manager)

        assert result.name == "test-metric"
        assert result.type == "string-check"

    @pytest.mark.asyncio
    async def test_get_metric_not_found_raises_404(self, metrics_manager):
        """Test get_metric raises HTTPException 404 when metric not found."""
        with pytest.raises(HTTPException) as exc_info:
            await get_metric(workspace="default", name="nonexistent", metrics_manager=metrics_manager)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()


class TestDeleteMetricEndpoint:
    """Tests for the delete_metric endpoint function."""

    @pytest.mark.asyncio
    async def test_delete_metric_success(self, metrics_manager, mock_sdk):
        """Test delete_metric successfully deletes a metric."""
        metric = entities.StringCheckMetric(
            name="to-delete",
            workspace="default",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        await metrics_manager.create(metric, sdk=mock_sdk)

        result = await delete_metric(workspace="default", name="to-delete", metrics_manager=metrics_manager)

        assert result.message is not None
        # Verify it's actually deleted
        with pytest.raises(HTTPException) as exc_info:
            await get_metric(workspace="default", name="to-delete", metrics_manager=metrics_manager)
        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_metric_not_found_raises_404(self, metrics_manager):
        """Test delete_metric raises HTTPException 404 when metric not found."""
        with pytest.raises(HTTPException) as exc_info:
            await delete_metric(workspace="default", name="nonexistent", metrics_manager=metrics_manager)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_metric_system_workspace_raises_403(self, metrics_manager):
        """Test delete_metric raises HTTPException 403 for system workspace."""
        with pytest.raises(HTTPException) as exc_info:
            await delete_metric(workspace="system", name="any-metric", metrics_manager=metrics_manager)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 403
        assert "system" in exc_info.value.detail.lower()


class TestEvaluateMetricEndpoint:
    """Tests for the evaluate_metric endpoint function.

    This endpoint was missing tests, which allowed a bug (metric vs metric_ref
    parameter name mismatch) to go undetected.
    """

    @pytest.mark.asyncio
    async def test_evaluate_metric_with_inline_metric(self, metrics_manager, mock_sdk):
        """Test evaluate_metric with an inline metric definition."""
        # Arrange
        metric = StringCheckMetric(
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        request = MetricEvaluationRequest(
            metric=metric,
            dataset=EvaluateDatasetRows(
                rows=[
                    {"expected": "hello", "output": "hello"},
                    {"expected": "world", "output": "world"},
                    {"expected": "foo", "output": "bar"},
                ],
            ),
        )

        client = new_test_client(metrics_manager, mock_sdk=mock_sdk)
        resp = client.post(
            "/apis/evaluation/v2/workspaces/default/metric-evaluate",
            json=request.model_dump(mode="json", exclude_unset=True),
        )
        assert resp.status_code == 200, resp.text

        result = MetricEvaluationResponse.model_validate(resp.json())

        # Assert
        assert result.metric.model_dump(exclude_none=True) == metric.model_dump(exclude_none=True)
        assert result.row_scores is not None
        assert len(result.row_scores) == 3
        assert result.row_scores[0].scores is not None
        assert result.row_scores[1].scores is not None
        assert result.row_scores[2].scores is not None
        assert result.row_scores[0].scores["string-check"] == 1.0
        assert result.row_scores[1].scores["string-check"] == 1.0
        assert result.row_scores[2].scores["string-check"] == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_metric_with_stored_metric_urn(self, metrics_manager, mock_sdk):
        """Test evaluate_metric with a stored metric referenced by URN."""
        # Arrange - Create and store a metric
        metric = entities.StringCheckMetric(
            name="stored-metric",
            workspace="default",
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        await metrics_manager.create(metric, sdk=mock_sdk)

        request = MetricEvaluationRequest(
            metric=app.MetricRef(root="default/stored-metric"),  # URN reference
            dataset=EvaluateDatasetRows(
                rows=[{"expected": "match", "output": "match"}],
            ),
        )

        client = new_test_client(metrics_manager, mock_sdk=mock_sdk)
        resp = client.post(
            "/apis/evaluation/v2/workspaces/default/metric-evaluate",
            json=request.model_dump(mode="json", exclude_unset=True),
        )
        assert resp.status_code == 200, resp.text

        result = MetricEvaluationResponse.model_validate(resp.json())

        # Assert
        assert result.row_scores is not None
        assert len(result.row_scores) == 1
        assert result.row_scores[0].scores is not None
        assert result.row_scores[0].scores["string-check"] == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_metric_not_found_raises_404(self, metrics_manager, mock_sdk):
        """Test evaluate_metric raises HTTPException 404 when metric URN not found."""
        request = MetricEvaluationRequest(
            metric=app.MetricRef(root="nonexistent/metric"),
            dataset=EvaluateDatasetRows(rows=[{"input": "test"}]),
        )

        client = new_test_client(metrics_manager, mock_sdk=mock_sdk)
        resp = client.post(
            "/apis/evaluation/v2/workspaces/default/metric-evaluate",
            json=request.model_dump(mode="json", exclude_unset=True),
        )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_evaluate_metric_with_aggregate_fields(self, metrics_manager, mock_sdk):
        """Test evaluate_metric respects aggregate_fields query parameter."""
        metric = StringCheckMetric(
            operation="equals",
            left_template="{{expected}}",
            right_template="{{output}}",
        )
        request = MetricEvaluationRequest(
            metric=metric,
            dataset=EvaluateDatasetRows(
                rows=[{"expected": "hello", "output": "hello"}],
            ),
        )

        # Request only specific aggregate fields - pass plain list as expected by endpoint
        client = new_test_client(metrics_manager, mock_sdk=mock_sdk)
        resp = client.post(
            "/apis/evaluation/v2/workspaces/default/metric-evaluate?aggregate_fields=mean,std_dev",
            json=request.model_dump(mode="json", exclude_unset=True),
        )
        assert resp.status_code == 200, resp.text

        # Check that only requested fields are present
        assert "mean" in resp.text
        assert "std_dev" in resp.text
        # Default fields that weren't requested should be absent
        assert "sum" not in resp.text
        assert "min" not in resp.text
        assert "max" not in resp.text

    @pytest.mark.asyncio
    async def test_evaluate_metric_evaluation_error_raises_500(self, metrics_manager):
        """Test evaluate_metric raises HTTPException 500 on evaluation failure."""
        # Use a metric with invalid template that will cause evaluation to fail
        metric = StringCheckMetric(
            operation="equals",
            left_template="{{nonexistent_field}}",
            right_template="{{output}}",
        )
        request = MetricEvaluationRequest(
            metric=metric,
            dataset=EvaluateDatasetRows(
                rows=[{"input": "test", "output": "test"}],
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await evaluate_metric(
                workspace="default",
                request=request,
                metrics_manager=metrics_manager,
                aggregate_fields=[],
            )

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 500
        assert "nonexistent_field" in exc_info.value.detail


class TestGetMetricJobResultsEndpoint:
    @pytest.mark.asyncio
    async def test_get_404(self, metrics_manager, create_sample_metric_job_results):
        client = new_test_client(metrics_manager)
        resp = client.get("/apis/evaluation/v2/workspaces/default/metric-job-results/dne")
        assert resp.status_code == 404, resp.json()

    @pytest.mark.asyncio
    async def test_get(self, metrics_manager, create_sample_metric_job_results):
        client = new_test_client(metrics_manager)
        resp = client.get("/apis/evaluation/v2/workspaces/default/metric-job-results/result1")
        assert resp.status_code == 200, resp.text

        # Verify entity attrs
        raw_result = resp.json()
        assert "created_at" in raw_result, "missing entity private attributes"

        # doesn't serialize entity attrs, SDK types to though
        result = MetricJobResult.model_validate(raw_result)
        assert result.name == "result1"
        assert result.workspace == "default"
        assert result.metric is not None
        assert result.dataset is not None
        assert len(result.scores) == 1
        assert result.scores[0].name == "accuracy"
        assert result.scores[0].mean == 0.85

    @pytest.mark.asyncio
    async def test_get_aggregate_fields_invalid(self, metrics_manager, create_sample_metric_job_results):
        client = new_test_client(metrics_manager)
        resp = client.get("/apis/evaluation/v2/workspaces/default/metric-job-results/result1?aggregate_fields=dne")
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_get_aggregate_fields(self, metrics_manager, create_sample_metric_job_results):
        client = new_test_client(metrics_manager)
        resp = client.get("/apis/evaluation/v2/workspaces/default/metric-job-results/result1")
        assert resp.status_code == 200, resp.text
        assert "count" in resp.text, "always expect count"
        assert "std_dev" in resp.text, "expected for default"
        assert "min" in resp.text, "expected for default"
        assert "max" in resp.text, "expected for default"

        resp = client.get("/apis/evaluation/v2/workspaces/default/metric-job-results/result1?aggregate_fields=std_dev")
        assert resp.status_code == 200, resp.text
        assert "count" in resp.text, "always expect count"
        assert "std_dev" in resp.text, "included in filter"
        assert "min" not in resp.text, "excluded from filter"
        assert "max" not in resp.text, "excluded from filter"

        resp = client.get(
            "/apis/evaluation/v2/workspaces/default/metric-job-results/result1?aggregate_fields=std_dev,min"
        )
        assert resp.status_code == 200, resp.text
        assert "count" in resp.text, "always expect count"
        assert "std_dev" in resp.text, "included in filter"
        assert "min" in resp.text, "included in filter"
        assert "max" not in resp.text, "excluded from filter"


class TestDeleteMetricJobResultsEndpoint:
    @pytest.mark.asyncio
    async def test_delete_404(self, metrics_manager, create_sample_metric_job_results):
        client = new_test_client(metrics_manager)
        resp = client.delete("/apis/evaluation/v2/workspaces/default/metric-job-results/dne")
        assert resp.status_code == 404, resp.json()

    @pytest.mark.asyncio
    async def test_delete(self, metrics_manager, create_sample_metric_job_results):
        client = new_test_client(metrics_manager)

        resp = client.get("/apis/evaluation/v2/workspaces/default/metric-job-results/result1")
        assert resp.status_code == 200

        resp = client.delete("/apis/evaluation/v2/workspaces/default/metric-job-results/result1")
        assert resp.status_code == 200, resp.json()

        resp = client.get("/apis/evaluation/v2/workspaces/default/metric-job-results/result1")
        assert resp.status_code == 404, "expected entity to be deleted"


class TestListMetricJobResultsEndpoint:
    @pytest.mark.asyncio
    async def test_list(self, metrics_manager, create_sample_metric_job_results):
        client = new_test_client(metrics_manager)
        resp = client.get("/apis/evaluation/v2/workspaces/default/metric-job-results")
        assert resp.status_code == 200, resp.json()

        results = MetricJobResultsListResponse.model_validate(resp.json())
        assert len(results.data) == 3
        assert results.pagination is not None
        assert results.pagination.total_results == 3

    @pytest.mark.asyncio
    async def test_list_filter_empty(self, metrics_manager, create_sample_metric_job_results):
        client = new_test_client(metrics_manager)
        resp = client.get("/apis/evaluation/v2/workspaces/default/metric-job-results?filter[model]=ws/dne")
        assert resp.status_code == 200, resp.json()

        results = MetricJobResultsListResponse.model_validate(resp.json())
        assert len(results.data) == 0
        assert results.pagination is not None
        assert results.pagination.total_results == 0

    @pytest.mark.asyncio
    async def test_list_filter_metric(self, metrics_manager, create_sample_metric_job_results):
        filter = "filter[metric]=default/metric"
        client = new_test_client(metrics_manager)
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metric-job-results?{filter}")
        assert resp.status_code == 200, resp.json()

        results = MetricJobResultsListResponse.model_validate(resp.json())
        assert results.pagination is not None
        assert len(results.data) == 2
        assert results.pagination.total_results == 2
        for result in results.data:
            assert result.name in ["result1", "result3"]
            assert result.metric is not None
            assert result.metric.root == "default/metric"

        # Filter and Sort
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metric-job-results?{filter}&sort=name")
        assert resp.status_code == 200, resp.json()
        results = MetricJobResultsListResponse.model_validate(resp.json())
        assert results.data[0].name == "result1"
        assert results.data[1].name == "result3"

    @pytest.mark.asyncio
    async def test_list_filter_dataset(self, metrics_manager, create_sample_metric_job_results):
        filter = "filter[dataset]=default/dataset2"
        client = new_test_client(metrics_manager)
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metric-job-results?{filter}")
        assert resp.status_code == 200, resp.json()

        results = MetricJobResultsListResponse.model_validate(resp.json())
        assert results.pagination is not None
        assert len(results.data) == 1
        assert results.pagination.total_results == 1
        assert results.data[0].name == "result2"
        assert results.data[0].metric is not None
        assert results.data[0].dataset is not None
        assert results.data[0].metric.root == "default/metric2"
        assert results.data[0].dataset.root == "default/dataset2"

    @pytest.mark.asyncio
    async def test_list_filter_model(self, metrics_manager, create_sample_metric_job_results):
        filter = "filter[model]=default/model"
        client = new_test_client(metrics_manager)
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metric-job-results?{filter}")
        assert resp.status_code == 200, resp.json()

        results = MetricJobResultsListResponse.model_validate(resp.json())
        assert results.pagination is not None
        assert len(results.data) == 1
        assert results.pagination.total_results == 1
        assert results.data[0].name == "result3"
        assert results.data[0].model is not None
        assert results.data[0].model.root == "default/model"

    @pytest.mark.asyncio
    async def test_list_filter_multiple(self, metrics_manager, create_sample_metric_job_results):
        filter = "filter[metric]=default/metric&filter[model]=default/model"
        client = new_test_client(metrics_manager)
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metric-job-results?{filter}")
        assert resp.status_code == 200, resp.json()

        results = MetricJobResultsListResponse.model_validate(resp.json())
        assert results.pagination is not None
        assert len(results.data) == 1
        assert results.pagination.total_results == 1
        assert results.data[0].name == "result3"
        assert results.data[0].metric is not None
        assert results.data[0].model is not None
        assert results.data[0].metric.root == "default/metric"
        assert results.data[0].model.root == "default/model"

    @pytest.mark.asyncio
    async def test_list_filter_label(self, metrics_manager, create_sample_metric_job_results):
        client = new_test_client(metrics_manager)

        # Filter with brackets
        filter_param = "filter[data.labels.label]=value"
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metric-job-results?{filter_param}")
        assert resp.status_code == 200, resp.json()

        results_bracket = MetricJobResultsListResponse.model_validate(resp.json())
        assert results_bracket.pagination is not None
        assert len(results_bracket.data) == 1
        assert results_bracket.pagination.total_results == 1
        assert results_bracket.data[0].name == "result3"
        assert "label" in results_bracket.data[0].labels
        assert results_bracket.data[0].labels["label"] == "value"

        # Filter with json
        filter_param = 'filter={"data.labels.label": {"$eq": "value"}}'
        resp = client.get(f"/apis/evaluation/v2/workspaces/default/metric-job-results?{filter_param}")
        assert resp.status_code == 200, resp.json()

        result_json = MetricJobResultsListResponse.model_validate(resp.json())
        assert results_bracket.data == result_json.data
        assert results_bracket.pagination == result_json.pagination
