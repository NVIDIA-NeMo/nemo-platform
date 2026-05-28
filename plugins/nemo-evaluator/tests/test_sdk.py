# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the evaluator plugin SDK status resource."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_evaluator.jobs.evaluate import EvaluateInputSpec, EvaluateJob, EvaluateSpec
from nemo_evaluator.sdk import http_utils
from nemo_evaluator.sdk._executor import (
    _AsyncEvaluatorPluginExecutor,
    _build_evaluate_spec,
    _SyncEvaluatorPluginExecutor,
    metric_config,
)
from nemo_evaluator.sdk.fs_utils import EvaluatorLocalRunResult
from nemo_evaluator.sdk.job_resources import AsyncEvaluatorJobResource, EvaluatorJobResource
from nemo_evaluator.sdk.resources import AsyncEvaluator, Evaluator
from nemo_evaluator_sdk.enums import MetricType
from nemo_evaluator_sdk.execution.config import EvaluationRequest
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.llm_judge import LLMJudgeMetric
from nemo_evaluator_sdk.metrics.types import MetricsUnion
from nemo_evaluator_sdk.values import Model, RunConfig, RunConfigOnlineModel
from nemo_evaluator_sdk.values.models import ModelRef
from nemo_evaluator_sdk.values.results import AggregatedMetricResult, EvaluationResult
from nemo_evaluator_sdk.values.scores import JSONScoreParser, RangeScore
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.jobs.schemas import PlatformJobStatus
from nmp.evaluator.app.values import FilesetRef
from pydantic import ValidationError
from pytest_mock import MockerFixture

_EXACT_MATCH_SPEC = {
    "metric": {
        "type": "exact-match",
        "reference": "{{item.expected}}",
        "candidate": "{{item.output}}",
    },
    "dataset": [{"expected": "a", "output": "a"}],
}
_EXACT_MATCH_EVALUATE_SPEC = EvaluateSpec.model_validate(_EXACT_MATCH_SPEC)
_EXACT_MATCH_EVALUATE_SPEC_JSON = _EXACT_MATCH_EVALUATE_SPEC.model_dump(mode="json")


def _llm_judge_ref_metric() -> LLMJudgeMetric:
    """Return an LLM judge metric using a platform model reference."""
    return LLMJudgeMetric(
        model=ModelRef(root="default/judge"),
        scores=[
            RangeScore(
                name="quality",
                minimum=0,
                maximum=1,
                parser=JSONScoreParser(json_path="quality"),
            )
        ],
    )


def _single_metric(spec: EvaluateSpec) -> MetricsUnion:
    """Return the single metric from an evaluator job spec."""
    if isinstance(spec.metric, list):
        raise AssertionError("Expected a single metric spec.")
    return spec.metric


class _SyncPlatform:
    def __init__(self) -> None:
        self.base_url = "http://test:8000"
        self.workspace = "platform-ws"
        self.default_headers = {"Authorization": "Bearer sync-platform-token"}
        self.timeout = httpx.Timeout(42.0)
        self._client = MagicMock(spec=httpx.Client)
        self.models = SimpleNamespace(
            retrieve=MagicMock(return_value=SimpleNamespace(model_providers=["default/provider"])),
            get_model_entity_route_openai_url=MagicMock(return_value="https://igw.example.test/v1/chat/completions"),
        )
        self.inference = SimpleNamespace(
            providers=SimpleNamespace(
                retrieve=MagicMock(return_value=SimpleNamespace(host_url="http://nim.example.test:8000"))
            )
        )


class _AsyncPlatform:
    def __init__(self) -> None:
        self.base_url = "http://test:8000"
        self.workspace = "platform-ws"
        self.default_headers = {"Authorization": "Bearer platform-token"}
        self.timeout = httpx.Timeout(43.0)
        self._client = AsyncMock(spec=httpx.AsyncClient)


class _PlatformWithoutWorkspace:
    def __init__(self) -> None:
        self.base_url = "http://test:8000/"
        self.workspace = None


def test_http_utils_builds_evaluator_urls_with_normalized_slashes() -> None:
    """Evaluator HTTP utilities should normalize base URLs and relative route paths."""
    platform = _SyncPlatform()
    platform.base_url = "http://test:8000/"

    assert http_utils.base_url("http://test:8000/") == "http://test:8000"
    assert http_utils.url(cast(NeMoPlatform, platform), "/v1/healthz") == "http://test:8000/apis/evaluator/v1/healthz"
    assert (
        http_utils.url(cast(NeMoPlatform, platform), "v2/workspaces/{workspace}/evaluate/jobs", "ws")
        == "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs"
    )


def test_http_utils_builds_evaluator_job_creation_request_parts() -> None:
    """Evaluator HTTP utilities should build job create request bodies and forwarded platform headers."""
    platform = _SyncPlatform()
    platform.default_headers = {
        "Authorization": "Bearer sync-platform-token",
        "x-trace-id": 123,
    }

    assert http_utils.create_job_payload(_EXACT_MATCH_EVALUATE_SPEC) == {"spec": _EXACT_MATCH_EVALUATE_SPEC_JSON}
    assert http_utils.platform_default_headers(cast(NeMoPlatform, platform)) == {
        "Authorization": "Bearer sync-platform-token"
    }


def test_http_utils_builds_encoded_job_route_urls() -> None:
    """Job route helpers should percent-encode route parameters and join child resources safely."""
    job_base_url = http_utils.job_route_base_url(
        raw_base_url="http://test:8000/",
        workspace="client/ws",
        job_name="job/123?",
    )

    assert job_base_url == "http://test:8000/apis/evaluator/v2/workspaces/client%2Fws/evaluate/jobs/job%2F123%3F"
    assert (
        http_utils.job_route_resource_url(job_base_url=f"{job_base_url}/", resource_path="/status")
        == "http://test:8000/apis/evaluator/v2/workspaces/client%2Fws/evaluate/jobs/job%2F123%3F/status"
    )
    assert (
        http_utils.job_route_url(
            base_url="http://test:8000/",
            workspace="client/ws",
            job_name="job/123?",
            suffix="/results/row-scores/download",
        )
        == "http://test:8000/apis/evaluator/v2/workspaces/client%2Fws/evaluate/jobs/job%2F123%3F/results/row-scores/download"
    )


def test_sync_executor_initializes_without_resource_callbacks() -> None:
    platform = _SyncPlatform()

    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))

    assert executor is not None


def test_async_executor_initializes_without_resource_callbacks() -> None:
    platform = _AsyncPlatform()

    executor = _AsyncEvaluatorPluginExecutor(platform=cast(AsyncNeMoPlatform, platform))

    assert executor is not None


def test_resolve_workspace_requires_explicit_or_default_workspace() -> None:
    """Remote/local executor helpers should fail when no workspace can be resolved."""
    with pytest.raises(ValueError, match="workspace must be provided"):
        http_utils.resolve_workspace(cast(NeMoPlatform, _PlatformWithoutWorkspace()), None, strict=True)


def test_metric_config_rejects_non_serializable_metric() -> None:
    """Metrics must expose a JSON model dump for evaluator plugin execution."""
    with pytest.raises(TypeError, match="model_dump"):
        metric_config(object())


def test_build_evaluate_spec_includes_target_and_prompt_template() -> None:
    """Online evaluator specs should preserve model targets and prompt templates."""
    model = Model(url="https://model.test/v1", name="model-a")
    spec = _build_evaluate_spec(
        metrics=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
        request=EvaluationRequest(
            dataset=[{"expected": "a", "output": "a"}],
            target=model,
            prompt_template="Answer: {{item.input}}",
        ),
    )

    assert spec.target == model
    assert spec.prompt_template == "Answer: {{item.input}}"


def test_build_evaluate_spec_allows_unresolved_metric_model_refs() -> None:
    """SDK convenience specs should preserve input-only ModelRefs for ``to_spec`` resolution."""
    spec = _build_evaluate_spec(
        metrics=_llm_judge_ref_metric(),
        request=EvaluationRequest(dataset=[{"output_text": "hello"}]),
    )

    assert isinstance(spec, EvaluateInputSpec)
    assert isinstance(spec.metric, LLMJudgeMetric)
    assert spec.metric.model == ModelRef(root="default/judge")


def test_build_evaluate_spec_excludes_aggregate_fields() -> None:
    """Evaluator specs should not persist result-shaping options."""
    spec = _build_evaluate_spec(
        metrics=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
        request=EvaluationRequest(
            dataset=[{"expected": "a", "output": "a"}],
            params=RunConfig(),
            aggregate_fields=("mean", "max"),
        ),
    )

    assert spec.params is not None
    assert "aggregate_fields" not in spec.params.model_dump(mode="json")


def test_build_evaluate_spec_preserves_fileset_ref_dataset() -> None:
    """FilesetRef datasets should be carried to the job spec without eager row materialization."""
    dataset = FilesetRef(root="default/helpsteer2")

    spec = _build_evaluate_spec(
        metrics=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
        request=EvaluationRequest(dataset=cast(Any, dataset)),
    )

    assert spec.dataset == dataset


def test_build_evaluate_spec_synthesizes_fileset_ref_fragment_from_dataset_glob_pattern() -> None:
    """FilesetRef datasets should encode dataset_glob_pattern as the existing fragment selector syntax."""
    spec = _build_evaluate_spec(
        metrics=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
        request=EvaluationRequest(
            dataset=cast(Any, FilesetRef(root="default/helpsteer2")),
            dataset_glob_pattern="validation/*.jsonl",
        ),
    )

    assert spec.dataset == FilesetRef(root="default/helpsteer2#validation/*.jsonl")


def test_build_evaluate_spec_rejects_fileset_ref_fragment_and_dataset_glob_pattern() -> None:
    """FilesetRef fragment selectors and dataset_glob_pattern should not both select files."""
    with pytest.raises(ValueError, match=r"dataset_glob_pattern.*FilesetRef"):
        _build_evaluate_spec(
            metrics=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
            request=EvaluationRequest(
                dataset=cast(Any, FilesetRef(root="default/helpsteer2#validation/*.jsonl")),
                dataset_glob_pattern="train/*.jsonl",
            ),
        )


def test_sync_resource_calls_evaluator_plugin_status() -> None:
    platform = _SyncPlatform()
    platform._client.get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "http://test:8000/apis/evaluator/v1/healthz"),
        json={"plugin": "evaluator", "status": "ok"},
    )

    resource = Evaluator(cast(NeMoPlatform, platform))

    assert resource.plugin_status() == {"plugin": "evaluator", "status": "ok"}
    platform._client.get.assert_called_once_with(
        "http://test:8000/apis/evaluator/v1/healthz",
        headers={"Authorization": "Bearer sync-platform-token"},
    )


def test_sync_resource_rejects_non_object_plugin_status() -> None:
    platform = _SyncPlatform()
    platform._client.get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "http://test:8000/apis/evaluator/v1/healthz"),
        json=["ok"],
    )
    resource = Evaluator(cast(NeMoPlatform, platform))

    with pytest.raises(TypeError, match="JSON object"):
        resource.plugin_status()


def test_sync_resource_does_not_expose_standalone_sdk_backend_methods() -> None:
    resource = Evaluator(cast(NeMoPlatform, _SyncPlatform()))

    for method_name in ("create", "run_local", "evaluate", "evaluate_benchmark", "execution_mode"):
        assert not hasattr(resource, method_name)


def test_sync_executor_creates_evaluator_job() -> None:
    platform = _SyncPlatform()
    platform._client.post.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs"),
        json={"name": "job-123", "status": "created", "spec": _EXACT_MATCH_SPEC},
    )
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))
    spec = _EXACT_MATCH_EVALUATE_SPEC

    job = executor.create(spec=spec, workspace="ws")

    assert isinstance(job, EvaluatorJobResource)
    assert job.name == "job-123"
    assert job.job.status == PlatformJobStatus.CREATED
    assert job.job.spec is not None
    assert _single_metric(job.job.spec).type == MetricType.EXACT_MATCH
    platform._client.post.assert_called_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_SPEC_JSON},
        headers={"Authorization": "Bearer sync-platform-token"},
        timeout=platform.timeout,
    )


def test_sync_executor_create_does_not_use_asyncio_thread_bridge(mocker: MockerFixture) -> None:
    platform = _SyncPlatform()
    platform._client.post.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs"),
        json={"name": "job-123", "status": "created", "spec": _EXACT_MATCH_SPEC},
    )
    to_thread = mocker.patch("nemo_evaluator.sdk._executor.asyncio.to_thread", new=AsyncMock(), create=True)
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))

    job = executor.create(spec=_EXACT_MATCH_EVALUATE_SPEC, workspace="ws")

    assert isinstance(job, EvaluatorJobResource)
    to_thread.assert_not_called()
    platform._client.post.assert_called_once()


def test_sync_executor_create_uses_platform_workspace_by_default() -> None:
    platform = _SyncPlatform()
    platform._client.post.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", "http://test:8000/apis/evaluator/v2/workspaces/platform-ws/evaluate/jobs"),
        json={"name": "job-123", "spec": _EXACT_MATCH_SPEC},
    )
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))

    job = executor.create(spec=_EXACT_MATCH_EVALUATE_SPEC)
    assert job.name == "job-123"
    assert job.job.spec is not None
    assert _single_metric(job.job.spec).type == MetricType.EXACT_MATCH
    platform._client.post.assert_called_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/platform-ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_SPEC_JSON},
        headers={"Authorization": "Bearer sync-platform-token"},
        timeout=platform.timeout,
    )


def test_sync_executor_create_rejects_malformed_response() -> None:
    platform = _SyncPlatform()
    platform._client.post.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs"),
        json=["job-123"],
    )
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))

    with pytest.raises(ValidationError):
        executor.create(spec=_EXACT_MATCH_EVALUATE_SPEC, workspace="ws")
    platform._client.post.assert_called_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_SPEC_JSON},
        headers={"Authorization": "Bearer sync-platform-token"},
        timeout=platform.timeout,
    )


def test_sync_executor_waits_when_requested(mocker: MockerFixture) -> None:
    platform = _SyncPlatform()
    platform._client.post.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs"),
        json={"name": "job-123", "status": "created", "spec": _EXACT_MATCH_SPEC},
    )
    wait = mocker.patch("nemo_evaluator.sdk.job_resources.EvaluatorJobResource.wait_until_done")
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))

    job = executor.create(spec=_EXACT_MATCH_EVALUATE_SPEC, workspace="ws", wait_until_done=True)

    assert isinstance(job, EvaluatorJobResource)
    platform._client.post.assert_called_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_SPEC_JSON},
        headers={"Authorization": "Bearer sync-platform-token"},
        timeout=platform.timeout,
    )
    wait.assert_called_once_with(
        poll_interval_seconds=mocker.ANY,
        job_timeout_seconds=mocker.ANY,
        pending_timeout_seconds=mocker.ANY,
    )


def test_sync_resource_gets_existing_job_resource() -> None:
    platform = _SyncPlatform()
    platform._client.get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs/job-123"),
        json={"name": "job-123", "status": "created", "spec": _EXACT_MATCH_SPEC},
    )
    resource = Evaluator(cast(NeMoPlatform, platform))

    job = resource.get_job_resource("job-123", workspace="ws")

    assert isinstance(job, EvaluatorJobResource)
    assert job.name == "job-123"
    platform._client.get.assert_called_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs/job-123",
        headers={"Authorization": "Bearer sync-platform-token"},
    )


def test_sync_resource_url_encodes_reserved_chars_in_job_name() -> None:
    """Reserved URL characters in ``job_name`` must be percent-encoded so the path stays unambiguous."""
    platform = _SyncPlatform()
    platform._client.get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs/job%2F123%3F"),
        json={"name": "job/123?", "status": "created", "spec": _EXACT_MATCH_SPEC},
    )
    resource = Evaluator(cast(NeMoPlatform, platform))

    resource.get_job_resource("job/123?", workspace="ws")

    platform._client.get.assert_called_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs/job%2F123%3F",
        headers={"Authorization": "Bearer sync-platform-token"},
    )


def test_sync_executor_runs_evaluator_job_locally(mocker: MockerFixture) -> None:
    platform = _SyncPlatform()
    scheduler = mocker.Mock()
    expected = {"status": "completed", "artifact": {"name": "evaluation-results", "artifact_url": "file:///results"}}
    scheduler.run_local.return_value = expected
    scheduler_cls = mocker.patch("nemo_evaluator.sdk._executor.NemoJobScheduler", return_value=scheduler, create=True)
    to_thread = mocker.patch("nemo_evaluator.sdk._executor.asyncio.to_thread", new=AsyncMock(), create=True)
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))

    result = executor.run_local(spec=_EXACT_MATCH_EVALUATE_SPEC, workspace="ws")

    assert isinstance(result, EvaluatorLocalRunResult)
    assert result.status == "completed"
    assert result.artifact is not None
    assert result.artifact.name == "evaluation-results"
    assert result.artifact.artifact_url == "file:///results"
    scheduler_cls.assert_called_once_with()
    scheduler.run_local.assert_called_once_with(
        EvaluateJob,
        _EXACT_MATCH_EVALUATE_SPEC_JSON,
        workspace="ws",
        sdk=platform,
    )
    to_thread.assert_not_called()


def test_sync_executor_resolves_input_model_refs_before_local_scheduler(mocker: MockerFixture) -> None:
    platform = _SyncPlatform()
    scheduler = mocker.Mock()
    expected = {"status": "completed", "artifact": {"name": "evaluation-results", "artifact_url": "file:///results"}}
    scheduler.run_local.return_value = expected
    mocker.patch("nemo_evaluator.sdk._executor.NemoJobScheduler", return_value=scheduler, create=True)
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))
    spec = _build_evaluate_spec(
        metrics=_llm_judge_ref_metric(),
        request=EvaluationRequest(dataset=[{"output_text": "hello"}]),
    )

    result = executor.run_local(spec=spec, workspace="ws")

    assert result.status == "completed"
    platform.models.retrieve.assert_called_once_with("judge", workspace="default")
    platform.inference.providers.retrieve.assert_called_once_with("provider", workspace="default")
    scheduler.run_local.assert_called_once()
    args = scheduler.run_local.call_args.args
    kwargs = scheduler.run_local.call_args.kwargs
    assert args[0] is EvaluateJob
    submitted = args[1]
    assert submitted["metric"]["model"]["name"] == "judge"
    assert submitted["metric"]["model"]["url"] == "https://igw.example.test/v1/chat/completions"
    assert submitted["metric"]["model"]["host_url"] == "http://nim.example.test:8000"
    assert kwargs == {"workspace": "ws", "sdk": platform}


class TestEvaluatorSubmit:
    """Tests for ``Evaluator.submit`` request construction."""

    def test_builds_request_from_unpacked_fields(self, mocker: MockerFixture) -> None:
        """Submit should convert public request fields into an executor ``EvaluationRequest``."""
        platform = _SyncPlatform()
        resource = Evaluator(cast(NeMoPlatform, platform))
        expected_job = mocker.Mock(spec=EvaluatorJobResource)
        submit = mocker.patch.object(resource._executor, "submit", return_value=expected_job)
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = [{"expected": "a", "output": "a"}]
        model = Model(url="https://model.test/v1", name="model-a")
        config = RunConfigOnlineModel(parallelism=3, limit_samples=5)

        job = resource.submit(
            metric=metric,
            dataset=dataset,
            config=config,
            target=model,
            dataset_glob_pattern="*.jsonl",
            prompt_template={"template": "Answer {{item.input}}"},
        )

        assert job is expected_job
        submit.assert_called_once_with(
            metric=metric,
            dataset=dataset,
            params=config,
            target=model,
            dataset_glob_pattern="*.jsonl",
            prompt_template={"template": "Answer {{item.input}}"},
        )

    def test_accepts_fileset_ref_dataset(self, mocker: MockerFixture) -> None:
        """Submit should forward FilesetRef datasets unchanged to the executor."""
        platform = _SyncPlatform()
        resource = Evaluator(cast(NeMoPlatform, platform))
        expected_job = mocker.Mock(spec=EvaluatorJobResource)
        submit = mocker.patch.object(resource._executor, "submit", return_value=expected_job)
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = FilesetRef(root="default/helpsteer2")

        job = resource.submit(metric=metric, dataset=dataset)

        assert job is expected_job
        submit.assert_called_once_with(
            metric=metric,
            dataset=dataset,
            params=None,
            target=None,
            dataset_glob_pattern=None,
            prompt_template=None,
        )


class TestEvaluatorRun:
    """Tests for ``Evaluator.run`` executor delegation."""

    def test_builds_request_from_unpacked_fields(self, mocker: MockerFixture) -> None:
        """Run should forward the unpacked public kwargs to the executor."""
        platform = _SyncPlatform()
        resource = Evaluator(cast(NeMoPlatform, platform))
        expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
        evaluate = mocker.patch.object(resource._executor, "evaluate", return_value=expected)
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = [{"expected": "a", "output": "a"}]

        result = resource.run(
            metric=metric,
            dataset=dataset,
            config=RunConfig(parallelism=2),
            aggregate_fields=("mean", "max"),
        )

        assert result == expected
        evaluate.assert_called_once_with(
            metric=metric,
            dataset=dataset,
            params=RunConfig(parallelism=2),
            target=None,
            dataset_glob_pattern=None,
            prompt_template=None,
            aggregate_fields=("mean", "max"),
        )

    def test_accepts_fileset_ref_dataset(self, mocker: MockerFixture) -> None:
        """Run should forward FilesetRef datasets unchanged to the executor."""
        platform = _SyncPlatform()
        resource = Evaluator(cast(NeMoPlatform, platform))
        expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
        evaluate = mocker.patch.object(resource._executor, "evaluate", return_value=expected)
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = FilesetRef(root="default/helpsteer2")

        result = resource.run(metric=metric, dataset=dataset)

        assert result == expected
        evaluate.assert_called_once_with(
            metric=metric,
            dataset=dataset,
            params=None,
            target=None,
            dataset_glob_pattern=None,
            prompt_template=None,
            aggregate_fields=None,
        )

    def test_run_uses_local_executor_execution(self, mocker: MockerFixture) -> None:
        """Direct plugin SDK run should always use local executor execution."""
        platform = _SyncPlatform()
        resource = Evaluator(cast(NeMoPlatform, platform))
        expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
        local_evaluate = mocker.patch.object(resource._executor, "evaluate", return_value=expected)
        remote_evaluate = mocker.patch.object(resource._executor, "evaluate_remote")
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = [{"expected": "a", "output": "a"}]

        result = resource.run(metric=metric, dataset=dataset, aggregate_fields=("mean",))

        assert result is expected
        local_evaluate.assert_called_once_with(
            metric=metric,
            dataset=dataset,
            params=None,
            target=None,
            dataset_glob_pattern=None,
            prompt_template=None,
            aggregate_fields=("mean",),
        )
        remote_evaluate.assert_not_called()


def test_sync_executor_evaluate_remote_submits_waits_and_downloads(mocker: MockerFixture) -> None:
    platform = _SyncPlatform()
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))
    expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
    job_resource = mocker.Mock(spec=EvaluatorJobResource)
    job_resource.get_result.return_value = expected
    create = mocker.patch.object(executor, "create", return_value=job_resource)
    request = EvaluationRequest(
        dataset=[{"expected": "a", "output": "a"}],
        params=RunConfig(parallelism=2),
    )

    result = executor.evaluate_remote(
        metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
        request=request,
    )

    assert result == expected
    create.assert_called_once_with(
        spec=EvaluateInputSpec.model_validate(
            {
                "metric": {
                    "type": "exact-match",
                    "reference": "{{item.expected}}",
                    "candidate": "{{item.output}}",
                },
                "dataset": [{"expected": "a", "output": "a"}],
                "params": {"limit_samples": None, "parallelism": 2},
            }
        ),
        workspace="platform-ws",
    )
    job_resource.wait_until_done.assert_called_once_with(
        poll_interval_seconds=10.0,
        job_timeout_seconds=3600.0,
        pending_timeout_seconds=600.0,
    )
    job_resource.get_result.assert_called_once_with(aggregate_fields=None)


@pytest.mark.asyncio
async def test_async_resource_calls_evaluator_plugin_status() -> None:
    platform = _AsyncPlatform()
    platform._client.get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "http://test:8000/apis/evaluator/v1/healthz"),
        json={"plugin": "evaluator", "status": "ok"},
    )

    resource = AsyncEvaluator(cast(AsyncNeMoPlatform, platform))

    assert await resource.plugin_status() == {"plugin": "evaluator", "status": "ok"}
    platform._client.get.assert_awaited_once_with(
        "http://test:8000/apis/evaluator/v1/healthz",
        headers={"Authorization": "Bearer platform-token"},
    )


@pytest.mark.asyncio
async def test_async_resource_rejects_non_object_plugin_status() -> None:
    platform = _AsyncPlatform()
    platform._client.get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "http://test:8000/apis/evaluator/v1/healthz"),
        json=["ok"],
    )
    resource = AsyncEvaluator(cast(AsyncNeMoPlatform, platform))

    with pytest.raises(TypeError, match="JSON object"):
        await resource.plugin_status()


def test_async_resource_does_not_expose_standalone_sdk_backend_methods() -> None:
    resource = AsyncEvaluator(cast(AsyncNeMoPlatform, _AsyncPlatform()))

    for method_name in ("create", "run_local", "evaluate", "evaluate_benchmark", "execution_mode"):
        assert not hasattr(resource, method_name)


@pytest.mark.asyncio
async def test_async_executor_creates_evaluator_job(mocker: MockerFixture) -> None:
    platform = _AsyncPlatform()
    platform._client.post.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs"),
        json={"name": "job-123", "status": "created", "spec": _EXACT_MATCH_SPEC},
    )
    to_thread = mocker.patch("nemo_evaluator.sdk._executor.asyncio.to_thread", new=AsyncMock(), create=True)
    http_client_cls = mocker.patch("nemo_evaluator.sdk._executor.httpx.Client")
    executor = _AsyncEvaluatorPluginExecutor(platform=cast(AsyncNeMoPlatform, platform))
    spec = _EXACT_MATCH_EVALUATE_SPEC

    job = await executor.create(spec=spec, workspace="ws")

    assert isinstance(job, AsyncEvaluatorJobResource)
    assert job.name == "job-123"
    assert job.job.status == PlatformJobStatus.CREATED
    assert job.job.spec is not None
    assert _single_metric(job.job.spec).type == MetricType.EXACT_MATCH
    platform._client.post.assert_awaited_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_SPEC_JSON},
        headers={"Authorization": "Bearer platform-token"},
        timeout=platform.timeout,
    )
    to_thread.assert_not_awaited()
    http_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_async_executor_waits_when_requested(mocker: MockerFixture) -> None:
    platform = _AsyncPlatform()
    platform._client.post.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs"),
        json={"name": "job-123", "status": "created", "spec": _EXACT_MATCH_SPEC},
    )
    wait = mocker.patch(
        "nemo_evaluator.sdk.job_resources.AsyncEvaluatorJobResource.wait_until_done",
        new=AsyncMock(),
    )
    executor = _AsyncEvaluatorPluginExecutor(platform=cast(AsyncNeMoPlatform, platform))

    job = await executor.create(spec=_EXACT_MATCH_EVALUATE_SPEC, workspace="ws", wait_until_done=True)

    assert isinstance(job, AsyncEvaluatorJobResource)
    platform._client.post.assert_awaited_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_SPEC_JSON},
        headers={"Authorization": "Bearer platform-token"},
        timeout=platform.timeout,
    )
    wait.assert_awaited_once_with(
        poll_interval_seconds=mocker.ANY,
        job_timeout_seconds=mocker.ANY,
        pending_timeout_seconds=mocker.ANY,
    )


@pytest.mark.asyncio
async def test_async_resource_gets_existing_job_resource() -> None:
    platform = _AsyncPlatform()
    platform._client.get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs/job-123"),
        json={"name": "job-123", "status": "created", "spec": _EXACT_MATCH_SPEC},
    )
    resource = AsyncEvaluator(cast(AsyncNeMoPlatform, platform))

    job = await resource.get_job_resource("job-123", workspace="ws")

    assert isinstance(job, AsyncEvaluatorJobResource)
    assert job.name == "job-123"
    platform._client.get.assert_awaited_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs/job-123",
        headers={"Authorization": "Bearer platform-token"},
    )


@pytest.mark.asyncio
async def test_async_resource_url_encodes_reserved_chars_in_job_name() -> None:
    """Reserved URL characters in ``job_name`` must be percent-encoded on the async path too."""
    platform = _AsyncPlatform()
    platform._client.get.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs/job%2F123%3F"),
        json={"name": "job/123?", "status": "created", "spec": _EXACT_MATCH_SPEC},
    )
    resource = AsyncEvaluator(cast(AsyncNeMoPlatform, platform))

    await resource.get_job_resource("job/123?", workspace="ws")

    platform._client.get.assert_awaited_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs/job%2F123%3F",
        headers={"Authorization": "Bearer platform-token"},
    )


@pytest.mark.asyncio
async def test_async_executor_runs_evaluator_job_locally_in_worker_thread(mocker: MockerFixture) -> None:
    platform = _AsyncPlatform()
    scheduler = mocker.Mock()
    expected = {"status": "completed", "artifact": {"name": "evaluation-results", "artifact_url": "file:///results"}}
    scheduler_cls = mocker.patch("nemo_evaluator.sdk._executor.NemoJobScheduler", return_value=scheduler, create=True)
    mock_to_thread = mocker.patch(
        "nemo_evaluator.sdk._executor.asyncio.to_thread",
        new=AsyncMock(return_value=expected),
        create=True,
    )
    executor = _AsyncEvaluatorPluginExecutor(platform=cast(AsyncNeMoPlatform, platform))

    result = await executor.run_local(spec=_EXACT_MATCH_EVALUATE_SPEC, workspace="ws")

    assert isinstance(result, EvaluatorLocalRunResult)
    assert result.status == "completed"
    assert result.artifact is not None
    assert result.artifact.name == "evaluation-results"
    assert result.artifact.artifact_url == "file:///results"
    scheduler_cls.assert_called_once_with()
    mock_to_thread.assert_awaited_once_with(
        scheduler.run_local,
        EvaluateJob,
        _EXACT_MATCH_EVALUATE_SPEC_JSON,
        workspace="ws",
        async_sdk=platform,
    )


class TestAsyncEvaluatorSubmit:
    """Tests for ``AsyncEvaluator.submit`` request construction."""

    @pytest.mark.asyncio
    async def test_builds_request_from_unpacked_fields(self, mocker: MockerFixture) -> None:
        """Submit should convert public request fields into an executor ``EvaluationRequest``."""
        platform = _AsyncPlatform()
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, platform))
        expected_job = mocker.Mock(spec=AsyncEvaluatorJobResource)
        submit = mocker.patch.object(resource._executor, "submit", new=AsyncMock(return_value=expected_job))
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = [{"expected": "a", "output": "a"}]
        model = Model(url="https://model.test/v1", name="model-a")
        config = RunConfigOnlineModel(parallelism=3, limit_samples=5)

        job = await resource.submit(
            metric=metric,
            dataset=dataset,
            config=config,
            target=model,
            dataset_glob_pattern="*.jsonl",
            prompt_template={"template": "Answer {{item.input}}"},
        )

        assert job is expected_job
        submit.assert_awaited_once_with(
            metric=metric,
            dataset=dataset,
            params=config,
            target=model,
            dataset_glob_pattern="*.jsonl",
            prompt_template={"template": "Answer {{item.input}}"},
        )

    @pytest.mark.asyncio
    async def test_accepts_fileset_ref_dataset(self, mocker: MockerFixture) -> None:
        """Submit should forward FilesetRef datasets unchanged to the executor."""
        platform = _AsyncPlatform()
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, platform))
        expected_job = mocker.Mock(spec=AsyncEvaluatorJobResource)
        submit = mocker.patch.object(resource._executor, "submit", new=AsyncMock(return_value=expected_job))
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = FilesetRef(root="default/helpsteer2")

        job = await resource.submit(metric=metric, dataset=dataset)

        assert job is expected_job
        submit.assert_awaited_once_with(
            metric=metric,
            dataset=dataset,
            params=None,
            target=None,
            dataset_glob_pattern=None,
            prompt_template=None,
        )


class TestAsyncEvaluatorRun:
    """Tests for ``AsyncEvaluator.run`` executor delegation."""

    @pytest.mark.asyncio
    async def test_builds_request_from_unpacked_fields(self, mocker: MockerFixture) -> None:
        """Run should forward the unpacked public kwargs to the executor."""
        platform = _AsyncPlatform()
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, platform))
        expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
        evaluate = mocker.patch.object(resource._executor, "evaluate", new=AsyncMock(return_value=expected))
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = [{"expected": "a", "output": "a"}]

        result = await resource.run(
            metric=metric,
            dataset=dataset,
            config=RunConfig(parallelism=2),
            aggregate_fields=("mean", "max"),
        )

        assert result == expected
        evaluate.assert_awaited_once_with(
            metric=metric,
            dataset=dataset,
            params=RunConfig(parallelism=2),
            target=None,
            dataset_glob_pattern=None,
            prompt_template=None,
            aggregate_fields=("mean", "max"),
        )

    @pytest.mark.asyncio
    async def test_accepts_fileset_ref_dataset(self, mocker: MockerFixture) -> None:
        """Run should forward FilesetRef datasets unchanged to the executor."""
        platform = _AsyncPlatform()
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, platform))
        expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
        evaluate = mocker.patch.object(resource._executor, "evaluate", new=AsyncMock(return_value=expected))
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = FilesetRef(root="default/helpsteer2")

        result = await resource.run(metric=metric, dataset=dataset)

        assert result == expected
        evaluate.assert_awaited_once_with(
            metric=metric,
            dataset=dataset,
            params=None,
            target=None,
            dataset_glob_pattern=None,
            prompt_template=None,
            aggregate_fields=None,
        )

    @pytest.mark.asyncio
    async def test_run_uses_local_executor_execution(self, mocker: MockerFixture) -> None:
        """Direct async plugin SDK run should always use local executor execution."""
        platform = _AsyncPlatform()
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, platform))
        expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
        local_evaluate = mocker.patch.object(resource._executor, "evaluate", new=AsyncMock(return_value=expected))
        remote_evaluate = mocker.patch.object(resource._executor, "evaluate_remote", new=AsyncMock())
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = [{"expected": "a", "output": "a"}]

        result = await resource.run(metric=metric, dataset=dataset, aggregate_fields=("mean",))

        assert result is expected
        local_evaluate.assert_awaited_once_with(
            metric=metric,
            dataset=dataset,
            params=None,
            target=None,
            dataset_glob_pattern=None,
            prompt_template=None,
            aggregate_fields=("mean",),
        )
        remote_evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_executor_remote_submit_uses_platform_async_client_headers_and_timeout(
    mocker: MockerFixture,
) -> None:
    platform = _AsyncPlatform()
    platform._client.post.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs"),
        json={"name": "job-123", "status": "created", "spec": _EXACT_MATCH_SPEC},
    )
    http_client_cls = mocker.patch("nemo_evaluator.sdk._executor.httpx.Client")
    executor = _AsyncEvaluatorPluginExecutor(platform=cast(AsyncNeMoPlatform, platform))

    job = await executor.create(spec=_EXACT_MATCH_EVALUATE_SPEC, workspace="ws")

    assert job.name == "job-123"
    platform._client.post.assert_awaited_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_SPEC_JSON},
        headers={"Authorization": "Bearer platform-token"},
        timeout=platform.timeout,
    )
    http_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_async_executor_evaluate_remote_submits_waits_and_downloads(mocker: MockerFixture) -> None:
    platform = _AsyncPlatform()
    executor = _AsyncEvaluatorPluginExecutor(platform=cast(AsyncNeMoPlatform, platform))
    expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
    job_resource = mocker.Mock(spec=AsyncEvaluatorJobResource)
    job_resource.wait_until_done = AsyncMock()
    job_resource.get_result = AsyncMock(return_value=expected)
    create = mocker.patch.object(executor, "create", new=AsyncMock(return_value=job_resource))
    request = EvaluationRequest(
        dataset=[{"expected": "a", "output": "a"}],
        params=RunConfig(parallelism=2),
    )

    result = await executor.evaluate_remote(
        metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
        request=request,
    )

    assert result == expected
    create.assert_awaited_once_with(
        spec=EvaluateInputSpec.model_validate(
            {
                "metric": {
                    "type": "exact-match",
                    "reference": "{{item.expected}}",
                    "candidate": "{{item.output}}",
                },
                "dataset": [{"expected": "a", "output": "a"}],
                "params": {"limit_samples": None, "parallelism": 2},
            }
        ),
        workspace="platform-ws",
    )
    job_resource.wait_until_done.assert_awaited_once_with(
        poll_interval_seconds=10.0,
        job_timeout_seconds=3600.0,
        pending_timeout_seconds=600.0,
    )
    job_resource.get_result.assert_awaited_once_with(aggregate_fields=None)


def test_local_run_result_requires_completed_artifact() -> None:
    with pytest.raises(ValidationError):
        EvaluatorLocalRunResult.model_validate({"status": "completed"})


def test_local_run_result_allows_error_without_artifact_and_preserves_details() -> None:
    result = EvaluatorLocalRunResult.model_validate({"status": "error", "message": "task failed"})

    assert result.status == "error"
    assert result.artifact is None
    assert result.model_extra == {"message": "task failed"}


def test_local_run_result_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        EvaluatorLocalRunResult.model_validate({"status": "cancelled"})
