# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for the evaluator plugin scaffold."""

from __future__ import annotations

from typing import Any, overload
from urllib.parse import quote

from nemo_evaluator.sdk import http_utils
from nemo_evaluator.sdk._executor import (
    SubmitTargetSpec,
    _AsyncEvaluatorPluginExecutor,
    _SyncEvaluatorPluginExecutor,
)
from nemo_evaluator.sdk.job_resources import (
    AsyncEvaluatorJobResource,
    EvaluatorJob,
    EvaluatorJobResource,
)
from nemo_evaluator.sdk.metric_resources import (
    AsyncEvaluatorMetricsResource,
    EvaluatorMetricsResource,
)
from nemo_evaluator.sdk.types import (
    PluginDatasetInput,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from nemo_evaluator.shared.metric_bundles.bundles import MetricBundlePackager
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.values import (
    Agent,
    AggregateFieldName,
    FieldMapping,
    Model,
    ModelRef,
)
from nemo_evaluator_sdk.values.results import EvaluationResult
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.sdk import NemoPluginSDKResources


class Evaluator:
    """Sync SDK namespace mounted as ``client.evaluator``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        """Store the platform client used for evaluator plugin HTTP calls."""
        self._platform = platform
        self._http_client = platform._client
        self._executor = _SyncEvaluatorPluginExecutor(platform=platform)
        self.metrics = EvaluatorMetricsResource(platform)

    def plugin_status(self) -> dict[str, object]:
        """Return evaluator plugin health information from the service."""
        response = self._http_client.get(
            http_utils.url(self._platform, "/v1/healthz"),
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Evaluator plugin status response must be a JSON object.")
        return {str(key): value for key, value in payload.items()}

    def get_job_resource(self, job_name: str, workspace: str | None = None) -> EvaluatorJobResource:
        """Get a high-level resource for an existing evaluator plugin job."""
        response = self._http_client.get(
            http_utils.url(
                self._platform,
                f"/v2/workspaces/{{workspace}}/evaluate/jobs/{quote(job_name, safe='')}",
                workspace,
            ),
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return EvaluatorJobResource(
            job=EvaluatorJob.model_validate(response.json()),
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=http_utils.resolve_workspace(self._platform, workspace),
            headers=http_utils.platform_default_headers(self._platform),
        )

    @overload
    def submit(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfig | None = None,
        target: None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> EvaluatorJobResource: ...

    @overload
    def submit(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfigOnlineModel,
        target: Model | ModelRef,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> EvaluatorJobResource: ...

    @overload
    def submit(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfigOnline,
        target: Agent,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any],
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> EvaluatorJobResource: ...

    def submit(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: SubmitTargetSpec | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> EvaluatorJobResource:
        """Submit a metric job through the evaluator plugin executor."""
        if metric_bundle_packager is None:
            raise ValueError(
                "metric_bundle_packager is required for submit(); "
                "pass CloudpickleMetricBundlePackager() to enable metric bundling."
            )
        return self._executor.submit(
            metric=metric,
            dataset=dataset,
            params=config,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=metric_bundle_packager,
        )

    @overload
    def run(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfig | None = None,
        target: None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult: ...

    @overload
    def run(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfigOnlineModel,
        target: Model,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult: ...

    @overload
    def run(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfigOnline,
        target: Agent,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any],
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult: ...

    def run(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult:
        """Run one metric through the evaluator plugin executor's local execution path."""
        return self._executor.evaluate(
            metric=metric,
            dataset=dataset,
            params=config,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            aggregate_fields=aggregate_fields,
        )


class AsyncEvaluator:
    """Async SDK namespace mounted as ``client.evaluator``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        """Store the async platform client used for evaluator plugin HTTP calls."""
        self._platform = platform
        self._http_client = platform._client
        self._executor = _AsyncEvaluatorPluginExecutor(platform=platform)
        self.metrics = AsyncEvaluatorMetricsResource(platform)

    async def plugin_status(self) -> dict[str, object]:
        """Return evaluator plugin health information from the service."""
        response = await self._http_client.get(
            http_utils.url(self._platform, "/v1/healthz"),
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Evaluator plugin status response must be a JSON object.")
        return {str(key): value for key, value in payload.items()}

    async def get_job_resource(self, job_name: str, workspace: str | None = None) -> AsyncEvaluatorJobResource:
        """Get a high-level async resource for an existing evaluator plugin job."""
        response = await self._http_client.get(
            http_utils.url(
                self._platform,
                f"/v2/workspaces/{{workspace}}/evaluate/jobs/{quote(job_name, safe='')}",
                workspace,
            ),
            headers=http_utils.platform_default_headers(self._platform),
        )
        response.raise_for_status()
        return AsyncEvaluatorJobResource(
            job=EvaluatorJob.model_validate(response.json()),
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=http_utils.resolve_workspace(self._platform, workspace),
            headers=http_utils.platform_default_headers(self._platform),
        )

    @overload
    async def run(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfig | None = None,
        target: None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult: ...

    @overload
    async def run(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfigOnlineModel,
        target: Model,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult: ...

    @overload
    async def run(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfigOnline,
        target: Agent,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any],
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult: ...

    async def run(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
    ) -> EvaluationResult:
        """Run one metric through the evaluator plugin executor's local execution path."""
        return await self._executor.evaluate(
            metric=metric,
            dataset=dataset,
            params=config,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            aggregate_fields=aggregate_fields,
        )

    @overload
    async def submit(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfig | None = None,
        target: None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> AsyncEvaluatorJobResource: ...

    @overload
    async def submit(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfigOnlineModel,
        target: Model | ModelRef,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> AsyncEvaluatorJobResource: ...

    @overload
    async def submit(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfigOnline,
        target: Agent,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any],
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> AsyncEvaluatorJobResource: ...

    async def submit(
        self,
        *,
        metric: Metric,
        dataset: PluginDatasetInput,
        config: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: SubmitTargetSpec | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> AsyncEvaluatorJobResource:
        """Submit a metric job through the evaluator plugin executor."""
        if metric_bundle_packager is None:
            raise ValueError(
                "metric_bundle_packager is required for submit(); "
                "pass CloudpickleMetricBundlePackager() to enable metric bundling."
            )
        return await self._executor.submit(
            metric=metric,
            dataset=dataset,
            params=config,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=metric_bundle_packager,
        )


evaluator_sdk_resources = NemoPluginSDKResources(
    sync_resource=Evaluator,
    async_resource=AsyncEvaluator,
)
