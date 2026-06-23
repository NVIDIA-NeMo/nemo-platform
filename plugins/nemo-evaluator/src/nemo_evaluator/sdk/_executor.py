# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Private evaluator plugin executor implementation shared by SDK resources."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, TypeAlias, cast

import httpx
from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.filesets import FilesetRef
from nemo_evaluator.jobs.evaluate import EvaluateInputSpec, EvaluateJob, EvaluateSpec, TargetSpec
from nemo_evaluator.resolvers import PlatformModelResolver
from nemo_evaluator.sdk import http_utils
from nemo_evaluator.sdk.fs_utils import EvaluatorLocalRunResult, local_result_path
from nemo_evaluator.sdk.job_resources import (
    AsyncEvaluatorJobResource,
    EvaluatorJob,
    EvaluatorJobResource,
)
from nemo_evaluator.sdk.types import PluginDatasetInput
from nemo_evaluator.sdk.utils import filter_benchmark_result, filter_evaluation_result
from nemo_evaluator.shared.metric_bundles.bundles import MetricBundle, MetricBundlePackager, bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.datasets.loader import prepare_dataset_rows
from nemo_evaluator_sdk.execution.config import resolve_params
from nemo_evaluator_sdk.execution.metric_execution import run_sync
from nemo_evaluator_sdk.execution.utils import is_metric, is_metric_sequence
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.values import (
    Agent,
    FieldMapping,
    Model,
    ModelRef,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.results import AggregateFieldName, EvaluationResult
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.scheduler import NemoJobScheduler

_DEFAULT_POLL_INTERVAL_SECONDS = 10.0
_DEFAULT_JOB_TIMEOUT_SECONDS = 3600.0
_DEFAULT_PENDING_TIMEOUT_SECONDS = 600.0

EvaluateRequestSpec: TypeAlias = EvaluateInputSpec | EvaluateSpec
SubmitTargetSpec = TargetSpec | ModelRef


class MetricBundlePackagerPolicyError(RuntimeError):
    """Raised when plugin backend metric packaging is not configured."""


def _require_metric_bundle_packager(metric_bundle_packager: MetricBundlePackager | None) -> MetricBundlePackager:
    if metric_bundle_packager is None:
        raise MetricBundlePackagerPolicyError(
            "Packaging runtime metrics for evaluator plugin submission requires an explicit metric_bundle_packager. "
            "Pass CloudpickleMetricBundlePackager() to opt in to cloudpickle metric bundles."
        )
    return metric_bundle_packager


def _submit_params(
    params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None,
    target: SubmitTargetSpec | None,
) -> RunConfig | RunConfigOnline | RunConfigOnlineModel:
    if isinstance(target, ModelRef):
        if not isinstance(params, RunConfigOnlineModel):
            raise TypeError("ModelRef target requires RunConfigOnlineModel")
        return params
    return resolve_params(params, target)


def _resolve_submit_target(
    platform: NeMoPlatform,
    target: SubmitTargetSpec | None,
) -> Model | Agent | None:
    if isinstance(target, ModelRef):
        return run_sync(lambda: PlatformModelResolver(platform).resolve_model(target))
    return target


async def _resolve_submit_target_async(
    platform: AsyncNeMoPlatform,
    target: SubmitTargetSpec | None,
) -> Model | Agent | None:
    if isinstance(target, ModelRef):
        return await PlatformModelResolver(platform).resolve_model(target)
    return target


def _dataset_config(
    dataset: PluginDatasetInput,
    params: RunConfig | RunConfigOnline | RunConfigOnlineModel,
) -> list[dict[str, Any]] | FilesetRef:
    """Return the dataset payload to store in an evaluator plugin job spec."""
    if isinstance(dataset, FilesetRef):
        return dataset
    return prepare_dataset_rows(
        dataset,
        None,
        params.limit_samples,
    )


def _build_evaluate_spec(
    *,
    metrics: Metric | Sequence[Metric],
    dataset: PluginDatasetInput,
    params: RunConfig | RunConfigOnline | RunConfigOnlineModel,
    target: TargetSpec | None = None,
    field_mapping: FieldMapping | None = None,
    prompt_template: str | dict[str, Any] | None = None,
    metric_bundle_packager: MetricBundlePackager | None = None,
) -> EvaluateInputSpec:
    """Build the evaluator plugin input spec shared by local and remote execution."""
    effective_packager = _require_metric_bundle_packager(metric_bundle_packager)
    runtime_bundles = bundle_metrics_for_spec(metrics, metric_bundle_packager=effective_packager)
    spec = {
        # Carry inline metrics as the wire DTO (matches EvaluateInputSpec.metrics).
        "metrics": [MetricInline.model_validate_json(bundle.model_dump_json()) for bundle in runtime_bundles],
        "dataset": _dataset_config(dataset, params),
        "params": params.model_dump(mode="json"),
    }
    if target is not None:
        spec["target"] = target.model_dump(mode="json")
    if field_mapping is not None:
        spec["field_mapping"] = field_mapping.model_dump(mode="json")
    if prompt_template is not None:
        spec["prompt_template"] = prompt_template
    return EvaluateInputSpec.model_validate(spec)


def _resolve_sync_local_spec(
    spec: EvaluateRequestSpec,
    *,
    platform: NeMoPlatform,
    workspace: str,
) -> EvaluateSpec:
    """Return a canonical local spec, resolving input-only model references with the sync SDK."""
    if isinstance(spec, EvaluateSpec):
        return spec
    return cast(
        EvaluateSpec,
        run_sync(
            lambda: EvaluateJob.to_spec(
                spec,
                workspace=workspace,
                entity_client=None,
                async_sdk=platform,
                is_local=True,
            )
        ),
    )


async def _resolve_async_local_spec(
    spec: EvaluateRequestSpec,
    *,
    platform: AsyncNeMoPlatform,
    workspace: str,
) -> EvaluateSpec:
    """Return a canonical local spec, resolving input-only model references with the async SDK."""
    if isinstance(spec, EvaluateSpec):
        return spec
    return cast(
        EvaluateSpec,
        await EvaluateJob.to_spec(
            spec,
            workspace=workspace,
            entity_client=None,
            async_sdk=platform,
            is_local=True,
        ),
    )


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
        spec: EvaluateInputSpec,
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

    def run_local(self, *, spec: EvaluateRequestSpec, workspace: str | None = None) -> EvaluatorLocalRunResult:
        """Run an evaluator plugin job locally with a sync platform client."""
        resolved_workspace = http_utils.resolve_workspace(self._platform, workspace)
        canonical_spec = _resolve_sync_local_spec(
            spec,
            platform=self._platform,
            workspace=resolved_workspace,
        )
        payload = NemoJobScheduler().run_local(
            EvaluateJob,
            canonical_spec.model_dump(mode="json"),
            workspace=resolved_workspace,
            sdk=self._platform,
        )

        return EvaluatorLocalRunResult.model_validate(payload)

    def evaluate_remote(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> EvaluationResult:
        """Submit, poll, and download a remote evaluator plugin metric job."""
        normalized_params = resolve_params(params, target)
        spec = _build_evaluate_spec(
            metrics=metric,
            dataset=dataset,
            params=normalized_params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=metric_bundle_packager,
        )

        job = self.create(
            spec=spec, workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True)
        )
        job.wait_until_done(
            poll_interval_seconds=self._poll_interval_seconds,
            job_timeout_seconds=self._job_timeout_seconds,
            pending_timeout_seconds=self._pending_timeout_seconds,
        )

        return job.get_result(aggregate_fields=aggregate_fields)

    def evaluate(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult:
        """Evaluate one metric through local plugin job execution."""
        normalized_params = resolve_params(params, target)
        spec = _build_evaluate_spec(
            metrics=metric,
            dataset=dataset,
            params=normalized_params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=CloudpickleMetricBundlePackager(),
        )
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
        target: SubmitTargetSpec | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> EvaluatorJobResource:
        """Submit a remote evaluator plugin metric job and return the job resource."""
        submit_params = _submit_params(params, target)
        resolved_target = _resolve_submit_target(self._platform, target)
        spec = _build_evaluate_spec(
            metrics=metric,
            dataset=dataset,
            params=submit_params,
            target=resolved_target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=metric_bundle_packager,
        )

        job = self.create(
            spec=spec, workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True)
        )

        return job

    def evaluate_benchmark(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> BenchmarkEvaluationResult:
        """Evaluate multiple metrics through local plugin job execution."""
        normalized_params = resolve_params(params, target)
        spec = _build_evaluate_spec(
            metrics=metrics,
            dataset=dataset,
            params=normalized_params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=CloudpickleMetricBundlePackager(),
        )
        payload = self.run_local(
            spec=spec,
            workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True),
        )
        result_path = local_result_path(payload)
        result = BenchmarkEvaluationResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        return filter_benchmark_result(result, aggregate_fields)


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
        spec: EvaluateInputSpec,
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

    async def run_local(self, *, spec: EvaluateRequestSpec, workspace: str | None = None) -> EvaluatorLocalRunResult:
        """Run an evaluator plugin job locally without blocking the event loop."""
        resolved_workspace = http_utils.resolve_workspace(self._platform, workspace)
        canonical_spec = await _resolve_async_local_spec(
            spec,
            platform=self._platform,
            workspace=resolved_workspace,
        )
        scheduler = NemoJobScheduler()
        # Leverages programmatic dispatch as described in
        # packages/nemo_platform_plugin/src/nemo_platform_plugin/docs/ARCHITECTURE.md#job-entry-point-keys
        payload = await asyncio.to_thread(
            scheduler.run_local,
            EvaluateJob,
            canonical_spec.model_dump(mode="json"),
            workspace=resolved_workspace,
            async_sdk=self._platform,
        )
        return EvaluatorLocalRunResult.model_validate(payload)

    async def submit(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: SubmitTargetSpec | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> AsyncEvaluatorJobResource:
        """Submit a remote evaluator plugin metric job and return the job resource."""
        submit_params = _submit_params(params, target)
        resolved_target = await _resolve_submit_target_async(self._platform, target)
        spec = _build_evaluate_spec(
            metrics=metric,
            dataset=dataset,
            params=submit_params,
            target=resolved_target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=metric_bundle_packager,
        )

        job = await self.create(
            spec=spec, workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True)
        )

        return job

    async def evaluate_remote(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> EvaluationResult:
        """Submit, poll, and download a remote evaluator plugin metric job."""
        normalized_params = resolve_params(params, target)
        spec = _build_evaluate_spec(
            metrics=metric,
            dataset=dataset,
            params=normalized_params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=metric_bundle_packager,
        )

        job = await self.create(
            spec=spec, workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True)
        )
        await job.wait_until_done(
            poll_interval_seconds=self._poll_interval_seconds,
            job_timeout_seconds=self._job_timeout_seconds,
            pending_timeout_seconds=self._pending_timeout_seconds,
        )

        return await job.get_result(aggregate_fields=aggregate_fields)

    async def evaluate(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult:
        """Evaluate one metric through local plugin job execution."""
        normalized_params = resolve_params(params, target)
        spec = _build_evaluate_spec(
            metrics=metric,
            dataset=dataset,
            params=normalized_params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=CloudpickleMetricBundlePackager(),
        )
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
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> BenchmarkEvaluationResult:
        """Evaluate multiple metrics through local plugin job execution."""
        normalized_params = resolve_params(params, target)
        spec = _build_evaluate_spec(
            metrics=metrics,
            dataset=dataset,
            params=normalized_params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=CloudpickleMetricBundlePackager(),
        )
        payload = await self.run_local(
            spec=spec,
            workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True),
        )
        result_path = local_result_path(payload)
        result_text = await asyncio.to_thread(result_path.read_text, encoding="utf-8")
        result = BenchmarkEvaluationResult.model_validate_json(result_text)
        return filter_benchmark_result(result, aggregate_fields)


def bundle_metrics_for_spec(
    metrics: Metric | Sequence[Metric], *, metric_bundle_packager: MetricBundlePackager
) -> list[MetricBundle]:
    """Package one metric or a benchmark metric sequence for an evaluator plugin spec."""
    if is_metric(metrics):
        return [bundle_metric(metrics, metric_bundle_packager)]
    if is_metric_sequence(metrics):
        return [bundle_metric(metric, metric_bundle_packager) for metric in metrics]
    raise TypeError("metrics must be a Metric or a sequence of Metric objects")
