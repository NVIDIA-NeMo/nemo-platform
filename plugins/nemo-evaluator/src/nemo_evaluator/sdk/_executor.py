# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Private evaluator plugin executor implementation shared by SDK resources."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, Literal, Protocol, runtime_checkable

import httpx
from nemo_evaluator.jobs.evaluate import EvaluateJob, EvaluateSpec
from nemo_evaluator.sdk import http_utils
from nemo_evaluator.sdk.fs_utils import EvaluatorLocalRunResult, local_result_path
from nemo_evaluator.sdk.job_resources import (
    AsyncEvaluatorJobResource,
    EvaluatorJob,
    EvaluatorJobResource,
)
from nemo_evaluator.sdk.types import PluginDatasetInput
from nemo_evaluator.sdk.utils import filter_benchmark_result, filter_evaluation_result
from nemo_evaluator_sdk.datasets.loader import prepare_dataset_rows
from nemo_evaluator_sdk.execution.config import EvaluationRequest, normalize_params
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.values import (
    Agent,
    Model,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.results import AggregateFieldName, EvaluationResult
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.scheduler import NemoJobScheduler
from nmp.evaluator.app.values import FilesetRef

_DEFAULT_POLL_INTERVAL_SECONDS = 10.0
_DEFAULT_JOB_TIMEOUT_SECONDS = 3600.0
_DEFAULT_PENDING_TIMEOUT_SECONDS = 600.0


@runtime_checkable
class _SerializableMetric(Protocol):
    """Metric shape required for evaluator plugin job serialization."""

    def model_dump(self, *, mode: Literal["json"]) -> dict[str, Any]:
        """Return the metric as a JSON-serializable payload."""
        ...


def _dataset_config(request: EvaluationRequest) -> list[dict[str, Any]] | FilesetRef:
    """Return the dataset payload to store in an evaluator plugin job spec."""
    if isinstance(request.dataset, FilesetRef):
        if request.dataset_glob_pattern is None:
            return request.dataset
        if "#" in request.dataset.root:
            raise ValueError("dataset_glob_pattern cannot be used when FilesetRef already includes a fragment.")
        return request.dataset.with_fragment(request.dataset_glob_pattern)
    return prepare_dataset_rows(
        request.dataset,
        request.dataset_glob_pattern,
        request.params.limit_samples if request.params else None,
    )


def _build_evaluate_spec(*, metrics: Metric | Sequence[Metric], request: EvaluationRequest) -> EvaluateSpec:
    """Build the evaluator plugin spec shared by local and remote execution."""
    spec = {
        "metric": metrics_config(metrics),
        "dataset": _dataset_config(request),
        "params": request.params.model_dump(mode="json") if request.params else None,
    }
    if request.target is not None:
        spec["target"] = request.target.model_dump(mode="json")
    if request.prompt_template is not None:
        spec["prompt_template"] = request.prompt_template
    return EvaluateSpec.model_validate(spec)


class _SyncEvaluatorPluginExecutor:
    """Sync evaluator plugin executor used by the sync SDK resource."""

    def __init__(
        self,
        *,
        platform: NeMoPlatform,
        workspace: str | None = None,
        poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
        job_timeout_seconds: float = _DEFAULT_JOB_TIMEOUT_SECONDS,
        pending_timeout_seconds: float = _DEFAULT_PENDING_TIMEOUT_SECONDS,
    ) -> None:
        """Store the sync platform client used for evaluator execution."""
        self._platform = platform
        self._http_client: httpx.Client = platform._client
        self._workspace = workspace
        self._poll_interval_seconds = poll_interval_seconds
        self._job_timeout_seconds = job_timeout_seconds
        self._pending_timeout_seconds = pending_timeout_seconds

    def create(
        self,
        *,
        spec: EvaluateSpec,
        workspace: str | None = None,
        wait_until_done: bool = False,
    ) -> EvaluatorJobResource:
        """Create an evaluator plugin job with a sync platform client."""
        resolved_workspace = http_utils.resolve_workspace(self._platform, workspace)
        response = self._http_client.post(
            http_utils.url(self._platform, "/v2/workspaces/{workspace}/evaluate/jobs", resolved_workspace),
            json=http_utils.create_job_payload(spec),
            headers=http_utils.platform_default_headers(self._platform),
            timeout=self._platform.timeout,
        )

        response.raise_for_status()
        payload = response.json()

        job_resource = EvaluatorJobResource(
            job=EvaluatorJob.model_validate(payload),
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=resolved_workspace,
            headers=http_utils.platform_default_headers(self._platform),
        )

        if wait_until_done:
            job_resource.wait_until_done(
                poll_interval_seconds=self._poll_interval_seconds,
                job_timeout_seconds=self._job_timeout_seconds,
                pending_timeout_seconds=self._pending_timeout_seconds,
            )
        return job_resource

    def run_local(self, *, spec: EvaluateSpec, workspace: str | None = None) -> EvaluatorLocalRunResult:
        """Run an evaluator plugin job locally with a sync platform client."""
        payload = NemoJobScheduler().run_local(
            EvaluateJob,
            spec.model_dump(mode="json"),
            workspace=http_utils.resolve_workspace(self._platform, workspace),
            sdk=self._platform,
        )

        return EvaluatorLocalRunResult.model_validate(payload)

    def evaluate_remote(
        self,
        *,
        metric: Metric,
        request: EvaluationRequest,
    ) -> EvaluationResult:
        """Submit, poll, and download a remote evaluator plugin metric job."""
        spec = _build_evaluate_spec(metrics=metric, request=request)

        job = self.create(
            spec=spec, workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True)
        )
        job.wait_until_done(
            poll_interval_seconds=self._poll_interval_seconds,
            job_timeout_seconds=self._job_timeout_seconds,
            pending_timeout_seconds=self._pending_timeout_seconds,
        )

        return job.get_result(aggregate_fields=request.aggregate_fields)

    def evaluate(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        dataset_glob_pattern: str | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult:
        """Evaluate one metric through local in-process plugin execution."""
        request = EvaluationRequest(
            dataset=dataset,
            params=normalize_params(params, target),
            target=target,
            dataset_glob_pattern=dataset_glob_pattern,
            prompt_template=prompt_template,
            aggregate_fields=aggregate_fields,
        )
        spec = _build_evaluate_spec(metrics=metric, request=request)

        payload = self.run_local(
            spec=spec,
            workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True),
        )

        result_path = local_result_path(payload)
        result = EvaluationResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        return filter_evaluation_result(result, aggregate_fields)

    def submit(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        dataset_glob_pattern: str | None = None,
        prompt_template: str | dict[str, Any] | None = None,
    ) -> EvaluatorJobResource:
        """Submit a remote evaluator plugin metric job and return the job resource."""
        request = EvaluationRequest(
            dataset=dataset,
            params=normalize_params(params, target),
            target=target,
            dataset_glob_pattern=dataset_glob_pattern,
            prompt_template=prompt_template,
        )
        spec = _build_evaluate_spec(metrics=metric, request=request)

        job = self.create(
            spec=spec, workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True)
        )

        return job

    def evaluate_benchmark(
        self,
        *,
        metrics: Sequence[Metric],
        request: EvaluationRequest,
    ) -> BenchmarkEvaluationResult:
        """Evaluate multiple metrics through local in-process plugin execution."""
        spec = _build_evaluate_spec(metrics=metrics, request=request)

        payload = self.run_local(
            spec=spec,
            workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True),
        )

        result_path = local_result_path(payload)
        result = BenchmarkEvaluationResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        return filter_benchmark_result(result, request.aggregate_fields)


class _AsyncEvaluatorPluginExecutor:
    """Async evaluator plugin executor used by the async SDK resource."""

    def __init__(
        self,
        *,
        platform: AsyncNeMoPlatform,
        workspace: str | None = None,
        poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
        job_timeout_seconds: float = _DEFAULT_JOB_TIMEOUT_SECONDS,
        pending_timeout_seconds: float = _DEFAULT_PENDING_TIMEOUT_SECONDS,
    ) -> None:
        """Store the async platform client used for evaluator execution."""
        self._platform = platform
        self._http_client: httpx.AsyncClient = platform._client
        self._workspace = workspace
        self._poll_interval_seconds = poll_interval_seconds
        self._job_timeout_seconds = job_timeout_seconds
        self._pending_timeout_seconds = pending_timeout_seconds

    async def create(
        self,
        *,
        spec: EvaluateSpec,
        workspace: str | None = None,
        wait_until_done: bool = False,
    ) -> AsyncEvaluatorJobResource:
        """Create an evaluator plugin job and return a high-level async job resource."""
        resolved_workspace = http_utils.resolve_workspace(self._platform, workspace)
        response = await self._http_client.post(
            http_utils.url(self._platform, "/v2/workspaces/{workspace}/evaluate/jobs", resolved_workspace),
            json=http_utils.create_job_payload(spec),
            headers=http_utils.platform_default_headers(self._platform),
            timeout=self._platform.timeout,
        )

        response.raise_for_status()
        payload = response.json()

        job_resource = AsyncEvaluatorJobResource(
            job=EvaluatorJob.model_validate(payload),
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=resolved_workspace,
            headers=http_utils.platform_default_headers(self._platform),
        )

        if wait_until_done:
            await job_resource.wait_until_done(
                poll_interval_seconds=self._poll_interval_seconds,
                job_timeout_seconds=self._job_timeout_seconds,
                pending_timeout_seconds=self._pending_timeout_seconds,
            )
        return job_resource

    async def run_local(self, *, spec: EvaluateSpec, workspace: str | None = None) -> EvaluatorLocalRunResult:
        """Run an evaluator plugin job locally without blocking the event loop."""
        scheduler = NemoJobScheduler()
        # Leverages programmatic dispatch as described in
        # packages/nemo_platform_plugin/src/nemo_platform_plugin/docs/ARCHITECTURE.md#job-entry-point-keys
        payload = await asyncio.to_thread(
            scheduler.run_local,
            EvaluateJob,
            spec.model_dump(mode="json"),
            workspace=http_utils.resolve_workspace(self._platform, workspace),
            async_sdk=self._platform,
        )
        return EvaluatorLocalRunResult.model_validate(payload)

    async def submit(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        dataset_glob_pattern: str | None = None,
        prompt_template: str | dict[str, Any] | None = None,
    ) -> AsyncEvaluatorJobResource:
        """Submit a remote evaluator plugin metric job and return the job resource."""
        request = EvaluationRequest(
            dataset=dataset,
            params=normalize_params(params, target),
            target=target,
            dataset_glob_pattern=dataset_glob_pattern,
            prompt_template=prompt_template,
        )
        spec = _build_evaluate_spec(metrics=metric, request=request)

        job = await self.create(
            spec=spec, workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True)
        )

        return job

    async def evaluate_remote(
        self,
        *,
        metric: Metric,
        request: EvaluationRequest,
    ) -> EvaluationResult:
        """Submit, poll, and download a remote evaluator plugin metric job."""
        spec = _build_evaluate_spec(metrics=metric, request=request)

        job = await self.create(
            spec=spec, workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True)
        )
        await job.wait_until_done(
            poll_interval_seconds=self._poll_interval_seconds,
            job_timeout_seconds=self._job_timeout_seconds,
            pending_timeout_seconds=self._pending_timeout_seconds,
        )

        return await job.get_result(aggregate_fields=request.aggregate_fields)

    async def evaluate(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        dataset_glob_pattern: str | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult:
        """Evaluate one metric through local in-process plugin execution."""
        request = EvaluationRequest(
            dataset=dataset,
            params=normalize_params(params, target),
            target=target,
            dataset_glob_pattern=dataset_glob_pattern,
            prompt_template=prompt_template,
            aggregate_fields=aggregate_fields,
        )
        spec = _build_evaluate_spec(metrics=metric, request=request)

        payload = await self.run_local(
            spec=spec,
            workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True),
        )

        result_path = local_result_path(payload)
        result_text = await asyncio.to_thread(result_path.read_text, encoding="utf-8")
        result = EvaluationResult.model_validate_json(result_text)
        return filter_evaluation_result(result, aggregate_fields)

    async def evaluate_benchmark(
        self,
        *,
        metrics: Sequence[Metric],
        request: EvaluationRequest,
    ) -> BenchmarkEvaluationResult:
        """Evaluate multiple metrics through local in-process plugin execution."""
        spec = _build_evaluate_spec(metrics=metrics, request=request)

        payload = await self.run_local(
            spec=spec,
            workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True),
        )

        result_path = local_result_path(payload)
        result_text = await asyncio.to_thread(result_path.read_text, encoding="utf-8")
        result = BenchmarkEvaluationResult.model_validate_json(result_text)
        return filter_benchmark_result(result, request.aggregate_fields)


def metric_config(metric: object) -> dict[str, Any]:
    """Serialize one metric config for evaluator plugin job submission."""
    if not isinstance(metric, _SerializableMetric):
        raise TypeError("metrics must provide model_dump(mode='json') for evaluator plugin execution")
    return metric.model_dump(mode="json")


def metrics_config(metrics: object | Sequence[object]) -> dict[str, Any] | list[dict[str, Any]]:
    """Serialize one metric or a benchmark metric sequence for an evaluator plugin spec."""
    if isinstance(metrics, Sequence) and not isinstance(metrics, (str, bytes)):
        return [metric_config(metric) for metric in metrics]
    return metric_config(metrics)
