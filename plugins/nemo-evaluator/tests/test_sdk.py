# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the evaluator plugin SDK status resource."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_evaluator.filesets import FilesetRef
from nemo_evaluator.jobs.evaluate import EvaluateInputSpec, EvaluateJob, EvaluateSpec
from nemo_evaluator.sdk import http_utils
from nemo_evaluator.sdk._executor import (
    MetricBundlePackagerPolicyError,
    _AsyncEvaluatorPluginExecutor,
    _build_evaluate_spec,
    _SyncEvaluatorPluginExecutor,
    bundle_metrics_for_spec,
)
from nemo_evaluator.sdk.fs_utils import EvaluatorLocalRunResult
from nemo_evaluator.sdk.job_resources import AsyncEvaluatorJobResource, EvaluatorJobResource
from nemo_evaluator.sdk.resources import AsyncEvaluator, Evaluator
from nemo_evaluator.shared.metric_bundles.bundles import (
    MetricBundle,
    MetricBundlePackager,
    MetricBundlePayload,
    bundle_metric,
)
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.values import FieldMapping, Model, ModelRef, RunConfig, RunConfigOnline, RunConfigOnlineModel
from nemo_evaluator_sdk.values.results import AggregatedMetricResult, EvaluationResult
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.jobs.schemas import PlatformJobStatus
from pydantic import ValidationError
from pytest_mock import MockerFixture

_EXACT_MATCH_METRIC = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
_EXACT_MATCH_SPEC = {
    "metrics": [
        bundle_metric(
            _EXACT_MATCH_METRIC,
            CloudpickleMetricBundlePackager(),
        ).model_dump(mode="json")
    ],
    "dataset": [{"expected": "a", "output": "a"}],
}
_LEGACY_EXACT_MATCH_SPEC = {
    "metrics": {
        "type": "exact-match",
        "reference": "{{item.expected}}",
        "candidate": "{{item.output}}",
    },
    "dataset": [{"expected": "a", "output": "a"}],
}
_EXACT_MATCH_EVALUATE_SPEC = EvaluateSpec.model_validate(_EXACT_MATCH_SPEC)
_EXACT_MATCH_EVALUATE_SPEC_JSON = _EXACT_MATCH_EVALUATE_SPEC.model_dump(mode="json")
_EXACT_MATCH_EVALUATE_INPUT_SPEC = EvaluateInputSpec.model_validate(_EXACT_MATCH_SPEC)
_EXACT_MATCH_EVALUATE_INPUT_SPEC_JSON = _EXACT_MATCH_EVALUATE_INPUT_SPEC.model_dump(mode="json")


def _single_metric(spec: EvaluateInputSpec | EvaluateSpec) -> MetricBundle:
    """Return the single metric from an evaluator job spec."""
    if len(spec.metrics) != 1:
        raise AssertionError("Expected a single metric spec.")
    return spec.metrics[0]


def _local_run_result(tmp_path: Path, result: EvaluationResult) -> EvaluatorLocalRunResult:
    result_path = tmp_path / "evaluation-results.json"
    result_path.write_text(result.model_dump_json(), encoding="utf-8")
    return EvaluatorLocalRunResult.model_validate(
        {
            "status": "completed",
            "artifact": {"name": "evaluation-results", "artifact_url": f"file://{result_path}"},
        }
    )


class _RecordingMetricBundlePackager(MetricBundlePackager):
    """Test packager that records all runtime metrics selected for packaging."""

    def __init__(self) -> None:
        self.metrics: list[Metric] = []
        self._delegate = CloudpickleMetricBundlePackager()

    def package(self, metric: Metric) -> MetricBundlePayload:
        self.metrics.append(metric)
        return self._delegate.package(metric)

    def load(self, payload: MetricBundlePayload) -> Metric:
        del payload
        raise NotImplementedError("test packager only exercises submission-side packaging")


class _SyncPlatform:
    def __init__(self) -> None:
        self.base_url = "http://test:8000"
        self.workspace = "platform-ws"
        self.default_headers = {"Authorization": "Bearer sync-platform-token"}
        self.timeout = httpx.Timeout(42.0)
        self._client = MagicMock(spec=httpx.Client)


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

    assert http_utils.create_job_payload(_EXACT_MATCH_EVALUATE_INPUT_SPEC) == {
        "spec": _EXACT_MATCH_EVALUATE_INPUT_SPEC_JSON
    }
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


def test_bundle_metrics_for_spec_rejects_non_metric_object() -> None:
    """Metrics must satisfy the runtime Metric protocol before plugin execution."""
    bundle_metrics = object.__getattribute__(bundle_metrics_for_spec, "__call__")
    invalid_metric: Any = object()

    with pytest.raises(TypeError, match="metrics must be a Metric or a sequence of Metric objects"):
        bundle_metrics(invalid_metric, metric_bundle_packager=CloudpickleMetricBundlePackager())


def test_build_evaluate_spec_requires_metric_bundle_packager() -> None:
    with pytest.raises(MetricBundlePackagerPolicyError, match="CloudpickleMetricBundlePackager"):
        _build_evaluate_spec(
            metrics=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
            dataset=[{"expected": "a", "output": "a"}],
            params=RunConfig(),
        )


def test_build_evaluate_spec_includes_target_and_prompt_template() -> None:
    """Online evaluator specs should preserve model targets and prompt templates."""
    model = Model(url="https://model.test/v1", name="model-a")
    spec = _build_evaluate_spec(
        metrics=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
        metric_bundle_packager=CloudpickleMetricBundlePackager(),
        dataset=[{"expected": "a", "output": "a"}],
        params=RunConfigOnlineModel(),
        target=model,
        prompt_template="Answer: {{item.input}}",
    )

    assert spec.target == model
    assert spec.prompt_template == "Answer: {{item.input}}"


def test_build_evaluate_spec_uses_selected_packager_for_all_runtime_metrics() -> None:
    """Submission packages all outgoing runtime metrics with the caller-selected packager."""
    metric_a = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    metric_b = ExactMatchMetric(reference="{{item.other_expected}}", candidate="{{item.other_output}}")
    packager = _RecordingMetricBundlePackager()

    spec = _build_evaluate_spec(
        metrics=[metric_a, metric_b],
        metric_bundle_packager=packager,
        dataset=[{"expected": "a", "output": "a"}],
        params=RunConfig(),
    )

    assert packager.metrics == [metric_a, metric_b]
    assert [metric.metric_type for metric in spec.metrics] == ["exact-match", "exact-match"]


def test_build_evaluate_spec_excludes_aggregate_fields() -> None:
    """Evaluator specs should not persist result-shaping options."""
    spec = _build_evaluate_spec(
        metrics=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
        metric_bundle_packager=CloudpickleMetricBundlePackager(),
        dataset=[{"expected": "a", "output": "a"}],
        params=RunConfig(),
    )

    assert spec.params is not None
    assert "aggregate_fields" not in spec.params.model_dump(mode="json")


def test_build_evaluate_spec_preserves_field_mapping() -> None:
    """Evaluator specs should preserve dataset field mappings for local and remote jobs."""
    field_mapping = FieldMapping(output="prediction", reference="expected")

    spec = _build_evaluate_spec(
        metrics=ExactMatchMetric(reference="{{reference}}"),
        metric_bundle_packager=CloudpickleMetricBundlePackager(),
        dataset=[{"expected": "a", "prediction": "a"}],
        params=RunConfig(),
        field_mapping=field_mapping,
    )

    assert spec.field_mapping == field_mapping


def test_build_evaluate_spec_preserves_fileset_ref_dataset() -> None:
    """FilesetRef datasets should be carried to the job spec without eager row materialization."""
    dataset = FilesetRef(root="default/helpsteer2")

    spec = _build_evaluate_spec(
        metrics=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
        metric_bundle_packager=CloudpickleMetricBundlePackager(),
        dataset=dataset,
        params=RunConfig(),
    )

    assert spec.dataset == dataset


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


def test_sync_resource_does_not_expose_backend_methods() -> None:
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
    spec = _EXACT_MATCH_EVALUATE_INPUT_SPEC

    job = executor.create(spec=spec, workspace="ws")

    assert isinstance(job, EvaluatorJobResource)
    assert job.name == "job-123"
    assert job.job.status == PlatformJobStatus.CREATED
    assert job.job.spec is not None
    assert _single_metric(job.job.spec).metric_type == "exact-match"
    platform._client.post.assert_called_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_INPUT_SPEC_JSON},
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

    job = executor.create(spec=_EXACT_MATCH_EVALUATE_INPUT_SPEC, workspace="ws")

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

    job = executor.create(spec=_EXACT_MATCH_EVALUATE_INPUT_SPEC)
    assert job.name == "job-123"
    assert job.job.spec is not None
    assert _single_metric(job.job.spec).metric_type == "exact-match"
    platform._client.post.assert_called_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/platform-ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_INPUT_SPEC_JSON},
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
        executor.create(spec=_EXACT_MATCH_EVALUATE_INPUT_SPEC, workspace="ws")
    platform._client.post.assert_called_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_INPUT_SPEC_JSON},
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

    job = executor.create(spec=_EXACT_MATCH_EVALUATE_INPUT_SPEC, workspace="ws", wait_until_done=True)

    assert isinstance(job, EvaluatorJobResource)
    platform._client.post.assert_called_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_INPUT_SPEC_JSON},
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


class TestEvaluatorSubmit:
    """Tests for ``Evaluator.submit`` request construction."""

    def test_builds_request_from_unpacked_fields(self, mocker: MockerFixture) -> None:
        """Submit should forward public fields to the executor explicitly."""
        platform = _SyncPlatform()
        resource = Evaluator(cast(NeMoPlatform, platform))
        expected_job = mocker.Mock(spec=EvaluatorJobResource)
        submit = mocker.patch.object(resource._executor, "submit", return_value=expected_job)
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = [{"expected": "a", "output": "a"}]
        model = Model(url="https://model.test/v1", name="model-a")
        config = RunConfigOnlineModel(parallelism=3, limit_samples=5)

        packager = CloudpickleMetricBundlePackager()

        job = resource.submit(
            metric=metric,
            dataset=dataset,
            config=config,
            target=model,
            prompt_template={"template": "Answer {{item.input}}"},
            metric_bundle_packager=packager,
        )

        assert job is expected_job
        submit.assert_called_once_with(
            metric=metric,
            dataset=dataset,
            params=config,
            target=model,
            field_mapping=None,
            prompt_template={"template": "Answer {{item.input}}"},
            metric_bundle_packager=packager,
        )

    def test_accepts_fileset_ref_dataset(self, mocker: MockerFixture) -> None:
        """Submit should forward FilesetRef datasets unchanged to the executor."""
        platform = _SyncPlatform()
        resource = Evaluator(cast(NeMoPlatform, platform))
        expected_job = mocker.Mock(spec=EvaluatorJobResource)
        submit = mocker.patch.object(resource._executor, "submit", return_value=expected_job)
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = FilesetRef(root="default/helpsteer2")

        packager = CloudpickleMetricBundlePackager()

        job = resource.submit(metric=metric, dataset=dataset, metric_bundle_packager=packager)

        assert job is expected_job
        submit.assert_called_once_with(
            metric=metric,
            dataset=dataset,
            params=None,
            target=None,
            field_mapping=None,
            prompt_template=None,
            metric_bundle_packager=packager,
        )

    def test_accepts_model_ref_target(self, mocker: MockerFixture) -> None:
        """Submit should forward platform ModelRef targets to the plugin executor."""
        platform = _SyncPlatform()
        resource = Evaluator(cast(NeMoPlatform, platform))
        expected_job = mocker.Mock(spec=EvaluatorJobResource)
        submit = mocker.patch.object(resource._executor, "submit", return_value=expected_job)
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = [{"expected": "a", "output": "a"}]
        model_ref = ModelRef(root="default/model-a")
        packager = CloudpickleMetricBundlePackager()

        job = resource.submit(
            metric=metric,
            dataset=dataset,
            config=RunConfigOnlineModel(),
            target=model_ref,
            field_mapping=None,
            prompt_template="Answer: {{item.input}}",
            metric_bundle_packager=packager,
        )

        assert job is expected_job
        submit.assert_called_once_with(
            metric=metric,
            dataset=dataset,
            params=RunConfigOnlineModel(),
            target=model_ref,
            field_mapping=None,
            prompt_template="Answer: {{item.input}}",
            metric_bundle_packager=packager,
        )

    def test_requires_metric_bundle_packager(self) -> None:
        """Submit should fail fast before delegating without a remote metric packager."""
        resource = Evaluator(cast(NeMoPlatform, _SyncPlatform()))

        with pytest.raises(ValueError, match="metric_bundle_packager is required"):
            resource.submit(
                metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
                dataset=[{"expected": "a", "output": "a"}],
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
            field_mapping=None,
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
            field_mapping=None,
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
            field_mapping=None,
            prompt_template=None,
            aggregate_fields=("mean",),
        )
        remote_evaluate.assert_not_called()


def test_sync_executor_evaluate_runs_local_job_with_packaged_input(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    platform = _SyncPlatform()
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))
    expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
    run_local = mocker.patch.object(executor, "run_local", return_value=_local_run_result(tmp_path, expected))
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    dataset = [{"expected": "a", "output": "a"}]

    result = executor.evaluate(
        metric=metric,
        dataset=dataset,
        params=RunConfig(parallelism=2),
    )

    assert result == expected
    run_local.assert_called_once()
    assert run_local.call_args.kwargs["workspace"] == "platform-ws"
    spec = run_local.call_args.kwargs["spec"]
    assert isinstance(spec, EvaluateInputSpec)
    assert _single_metric(spec).metric_type == "exact-match"
    assert spec.dataset == dataset
    assert spec.params == RunConfig(parallelism=2)


def test_sync_executor_evaluate_encodes_fileset_ref_before_local_job(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    platform = _SyncPlatform()
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))
    expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
    run_local = mocker.patch.object(executor, "run_local", return_value=_local_run_result(tmp_path, expected))
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    dataset = FilesetRef(root="default/helpsteer2#validation/*.jsonl")

    result = executor.evaluate(
        metric=metric,
        dataset=dataset,
    )

    assert result == expected
    run_local.assert_called_once()
    spec = run_local.call_args.kwargs["spec"]
    assert isinstance(spec, EvaluateInputSpec)
    assert spec.dataset == FilesetRef(root="default/helpsteer2#validation/*.jsonl")


def test_sync_executor_evaluate_remote_submits_waits_and_downloads(mocker: MockerFixture) -> None:
    platform = _SyncPlatform()
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))
    expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
    job_resource = mocker.Mock(spec=EvaluatorJobResource)
    job_resource.get_result.return_value = expected
    create = mocker.patch.object(executor, "create", return_value=job_resource)
    result = executor.evaluate_remote(
        metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
        dataset=[{"expected": "a", "output": "a"}],
        params=RunConfig(parallelism=2),
        metric_bundle_packager=CloudpickleMetricBundlePackager(),
    )

    assert result == expected
    create.assert_called_once()
    assert create.call_args.kwargs["workspace"] == "platform-ws"
    created_spec = create.call_args.kwargs["spec"]
    assert _single_metric(created_spec).metric_type == "exact-match"
    assert created_spec.dataset == [{"expected": "a", "output": "a"}]
    assert created_spec.params == RunConfig(parallelism=2)
    job_resource.wait_until_done.assert_called_once_with(
        poll_interval_seconds=10.0,
        job_timeout_seconds=3600.0,
        pending_timeout_seconds=600.0,
    )
    job_resource.get_result.assert_called_once_with(aggregate_fields=None)


def test_sync_executor_submit_resolves_model_ref_before_creating_job(mocker: MockerFixture) -> None:
    platform = _SyncPlatform()
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))
    expected_job = mocker.Mock(spec=EvaluatorJobResource)
    create = mocker.patch.object(executor, "create", return_value=expected_job)
    resolved_model = Model(url="https://igw.example.test/v1/chat/completions", name="model-a")
    resolver = mocker.patch("nemo_evaluator.sdk._executor.PlatformModelResolver").return_value
    resolver.resolve_model = AsyncMock(return_value=resolved_model)
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    dataset = [{"expected": "a", "output": "a"}]

    job = executor.submit(
        metric=metric,
        dataset=dataset,
        params=RunConfigOnlineModel(),
        target=ModelRef(root="default/model-a"),
        metric_bundle_packager=CloudpickleMetricBundlePackager(),
    )

    assert job is expected_job
    resolver.resolve_model.assert_awaited_once_with(ModelRef(root="default/model-a"))
    created_spec = create.call_args.kwargs["spec"]
    assert created_spec.target == resolved_model


def test_sync_executor_submit_requires_online_model_params_for_model_ref() -> None:
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, _SyncPlatform()))

    with pytest.raises(TypeError, match="ModelRef target requires RunConfigOnlineModel"):
        executor.submit(
            metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
            dataset=[{"expected": "a", "output": "a"}],
            params=RunConfig(),
            target=ModelRef(root="default/model-a"),
            metric_bundle_packager=CloudpickleMetricBundlePackager(),
        )


def test_sync_executor_submit_rejects_online_params_without_target() -> None:
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, _SyncPlatform()))

    with pytest.raises(TypeError, match="offline evaluation requires RunConfig"):
        executor.submit(
            metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
            dataset=[{"expected": "a", "output": "a"}],
            params=RunConfigOnline(),
            metric_bundle_packager=CloudpickleMetricBundlePackager(),
        )


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


def test_async_resource_does_not_expose_backend_methods() -> None:
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
    spec = _EXACT_MATCH_EVALUATE_INPUT_SPEC

    job = await executor.create(spec=spec, workspace="ws")

    assert isinstance(job, AsyncEvaluatorJobResource)
    assert job.name == "job-123"
    assert job.job.status == PlatformJobStatus.CREATED
    assert job.job.spec is not None
    assert _single_metric(job.job.spec).metric_type == "exact-match"
    platform._client.post.assert_awaited_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_INPUT_SPEC_JSON},
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

    job = await executor.create(spec=_EXACT_MATCH_EVALUATE_INPUT_SPEC, workspace="ws", wait_until_done=True)

    assert isinstance(job, AsyncEvaluatorJobResource)
    platform._client.post.assert_awaited_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_INPUT_SPEC_JSON},
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
        """Submit should forward public fields to the executor explicitly."""
        platform = _AsyncPlatform()
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, platform))
        expected_job = mocker.Mock(spec=AsyncEvaluatorJobResource)
        submit = mocker.patch.object(resource._executor, "submit", new=AsyncMock(return_value=expected_job))
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = [{"expected": "a", "output": "a"}]
        model = Model(url="https://model.test/v1", name="model-a")
        config = RunConfigOnlineModel(parallelism=3, limit_samples=5)

        packager = CloudpickleMetricBundlePackager()

        job = await resource.submit(
            metric=metric,
            dataset=dataset,
            config=config,
            target=model,
            prompt_template={"template": "Answer {{item.input}}"},
            metric_bundle_packager=packager,
        )

        assert job is expected_job
        submit.assert_awaited_once_with(
            metric=metric,
            dataset=dataset,
            params=config,
            target=model,
            field_mapping=None,
            prompt_template={"template": "Answer {{item.input}}"},
            metric_bundle_packager=packager,
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

        packager = CloudpickleMetricBundlePackager()

        job = await resource.submit(metric=metric, dataset=dataset, metric_bundle_packager=packager)

        assert job is expected_job
        submit.assert_awaited_once_with(
            metric=metric,
            dataset=dataset,
            params=None,
            target=None,
            field_mapping=None,
            prompt_template=None,
            metric_bundle_packager=packager,
        )

    @pytest.mark.asyncio
    async def test_accepts_model_ref_target(self, mocker: MockerFixture) -> None:
        """Submit should forward platform ModelRef targets to the plugin executor."""
        platform = _AsyncPlatform()
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, platform))
        expected_job = mocker.Mock(spec=AsyncEvaluatorJobResource)
        submit = mocker.patch.object(resource._executor, "submit", new=AsyncMock(return_value=expected_job))
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
        dataset = [{"expected": "a", "output": "a"}]
        model_ref = ModelRef(root="default/model-a")
        packager = CloudpickleMetricBundlePackager()

        job = await resource.submit(
            metric=metric,
            dataset=dataset,
            config=RunConfigOnlineModel(),
            target=model_ref,
            field_mapping=None,
            prompt_template="Answer: {{item.input}}",
            metric_bundle_packager=packager,
        )

        assert job is expected_job
        submit.assert_awaited_once_with(
            metric=metric,
            dataset=dataset,
            params=RunConfigOnlineModel(),
            target=model_ref,
            field_mapping=None,
            prompt_template="Answer: {{item.input}}",
            metric_bundle_packager=packager,
        )

    @pytest.mark.asyncio
    async def test_requires_metric_bundle_packager(self) -> None:
        """Submit should fail fast before delegating without a remote metric packager."""
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, _AsyncPlatform()))

        with pytest.raises(ValueError, match="metric_bundle_packager is required"):
            await resource.submit(
                metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
                dataset=[{"expected": "a", "output": "a"}],
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
            field_mapping=None,
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
            field_mapping=None,
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
            field_mapping=None,
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

    job = await executor.create(spec=_EXACT_MATCH_EVALUATE_INPUT_SPEC, workspace="ws")

    assert job.name == "job-123"
    platform._client.post.assert_awaited_once_with(
        "http://test:8000/apis/evaluator/v2/workspaces/ws/evaluate/jobs",
        json={"spec": _EXACT_MATCH_EVALUATE_INPUT_SPEC_JSON},
        headers={"Authorization": "Bearer platform-token"},
        timeout=platform.timeout,
    )
    http_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_async_executor_evaluate_runs_local_job_with_packaged_input(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    platform = _AsyncPlatform()
    executor = _AsyncEvaluatorPluginExecutor(platform=cast(AsyncNeMoPlatform, platform))
    expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
    run_local = mocker.patch.object(
        executor,
        "run_local",
        new=AsyncMock(return_value=_local_run_result(tmp_path, expected)),
    )
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    dataset = [{"expected": "a", "output": "a"}]

    result = await executor.evaluate(
        metric=metric,
        dataset=dataset,
        params=RunConfig(parallelism=2),
    )

    assert result == expected
    run_local.assert_awaited_once()
    assert run_local.call_args.kwargs["workspace"] == "platform-ws"
    spec = run_local.call_args.kwargs["spec"]
    assert isinstance(spec, EvaluateInputSpec)
    assert _single_metric(spec).metric_type == "exact-match"
    assert spec.dataset == dataset
    assert spec.params == RunConfig(parallelism=2)


@pytest.mark.asyncio
async def test_async_executor_evaluate_remote_submits_waits_and_downloads(mocker: MockerFixture) -> None:
    platform = _AsyncPlatform()
    executor = _AsyncEvaluatorPluginExecutor(platform=cast(AsyncNeMoPlatform, platform))
    expected = EvaluationResult(row_scores=[], aggregate_scores=AggregatedMetricResult(scores=[]))
    job_resource = mocker.Mock(spec=AsyncEvaluatorJobResource)
    job_resource.wait_until_done = AsyncMock()
    job_resource.get_result = AsyncMock(return_value=expected)
    create = mocker.patch.object(executor, "create", new=AsyncMock(return_value=job_resource))
    result = await executor.evaluate_remote(
        metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
        dataset=[{"expected": "a", "output": "a"}],
        params=RunConfig(parallelism=2),
        metric_bundle_packager=CloudpickleMetricBundlePackager(),
    )

    assert result == expected
    create.assert_awaited_once()
    assert create.call_args.kwargs["workspace"] == "platform-ws"
    created_spec = create.call_args.kwargs["spec"]
    assert _single_metric(created_spec).metric_type == "exact-match"
    assert created_spec.dataset == [{"expected": "a", "output": "a"}]
    assert created_spec.params == RunConfig(parallelism=2)
    job_resource.wait_until_done.assert_awaited_once_with(
        poll_interval_seconds=10.0,
        job_timeout_seconds=3600.0,
        pending_timeout_seconds=600.0,
    )
    job_resource.get_result.assert_awaited_once_with(aggregate_fields=None)


@pytest.mark.asyncio
async def test_async_executor_submit_resolves_model_ref_before_creating_job(mocker: MockerFixture) -> None:
    platform = _AsyncPlatform()
    executor = _AsyncEvaluatorPluginExecutor(platform=cast(AsyncNeMoPlatform, platform))
    expected_job = mocker.Mock(spec=AsyncEvaluatorJobResource)
    create = mocker.patch.object(executor, "create", new=AsyncMock(return_value=expected_job))
    resolved_model = Model(url="https://igw.example.test/v1/chat/completions", name="model-a")
    resolver = mocker.patch("nemo_evaluator.sdk._executor.PlatformModelResolver").return_value
    resolver.resolve_model = AsyncMock(return_value=resolved_model)
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    dataset = [{"expected": "a", "output": "a"}]

    job = await executor.submit(
        metric=metric,
        dataset=dataset,
        params=RunConfigOnlineModel(),
        target=ModelRef(root="default/model-a"),
        metric_bundle_packager=CloudpickleMetricBundlePackager(),
    )

    assert job is expected_job
    resolver.resolve_model.assert_awaited_once_with(ModelRef(root="default/model-a"))
    created_spec = create.call_args.kwargs["spec"]
    assert created_spec.target == resolved_model


@pytest.mark.asyncio
async def test_async_executor_submit_rejects_online_params_without_target() -> None:
    executor = _AsyncEvaluatorPluginExecutor(platform=cast(AsyncNeMoPlatform, _AsyncPlatform()))

    with pytest.raises(TypeError, match="offline evaluation requires RunConfig"):
        await executor.submit(
            metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
            dataset=[{"expected": "a", "output": "a"}],
            params=RunConfigOnline(),
            metric_bundle_packager=CloudpickleMetricBundlePackager(),
        )


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
