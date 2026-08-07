# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for the evaluator plugin scaffold."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, overload
from urllib.parse import quote

from nemo_evaluator.sdk import http_utils
from nemo_evaluator.sdk._agent_eval_executor import (
    _AsyncAgentEvalExecutor,
    _SyncAgentEvalExecutor,
)
from nemo_evaluator.sdk._executor import (
    SubmitTargetSpec,
    _AsyncEvaluatorPluginExecutor,
    _SyncEvaluatorPluginExecutor,
)
from nemo_evaluator.sdk.agent_eval_job_resources import (
    AgentEvalJobResource,
    AsyncAgentEvalJobResource,
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
from nemo_evaluator.sdk.result_resources import (
    AsyncEvaluatorAgentEvalResultsResource,
    AsyncEvaluatorEvalResultsResource,
    EvaluatorAgentEvalResultsResource,
    EvaluatorEvalResultsResource,
)
from nemo_evaluator.sdk.task_resources import (
    AsyncEvaluatorTasksResource,
    EvaluatorTasksResource,
)
from nemo_evaluator.sdk.taskset_resources import (
    AsyncEvaluatorTasksetsResource,
    EvaluatorTasksetsResource,
)
from nemo_evaluator.sdk.types import (
    PluginDatasetInput,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from nemo_evaluator.shared.metric_bundles.bundles import MetricBundlePackager
from nemo_evaluator.shared.metric_bundles.defaults import resolve_default_metric_bundle_packager
from nemo_evaluator_sdk.agent_eval.evaluator import validate_run_inputs
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTarget, AgentEvalTrial
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.values import (
    Agent,
    FieldMapping,
    Model,
    ModelRef,
)
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.sdk import NemoPluginSDKResources


class Evaluator:
    """Sync SDK namespace mounted as ``client.evaluator``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        """Store the platform client used for evaluator plugin HTTP calls."""
        self._platform = platform
        self._http_client = platform._client
        self._executor = _SyncEvaluatorPluginExecutor(platform=platform)
        self._agent_eval_executor = _SyncAgentEvalExecutor(platform=platform)
        self.metrics = EvaluatorMetricsResource(platform)
        self.agent_eval_results = EvaluatorAgentEvalResultsResource(platform)
        self.eval_results = EvaluatorEvalResultsResource(platform)
        self.tasks = EvaluatorTasksResource(platform)
        self.tasksets = EvaluatorTasksetsResource(platform)

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
    def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfig | None = None,
        target: None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> EvaluatorJobResource: ...

    @overload
    def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfigOnlineModel,
        target: Model | ModelRef,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> EvaluatorJobResource: ...

    @overload
    def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfigOnline,
        target: Agent,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any],
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> EvaluatorJobResource: ...

    def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: SubmitTargetSpec | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> EvaluatorJobResource:
        """Submit a dataset metric job to the platform and return its job handle.

        Takes the metric list the SDK
        :class:`~nemo_evaluator_sdk.execution.backends.base.EvaluationBackend` contract spells, but
        still returns a job handle where that contract returns a completed
        :class:`~nemo_evaluator_sdk.values.multi_metric_results.BenchmarkEvaluationResult`, so it
        does not satisfy the contract yet.
        """
        return self._executor.evaluate_dataset(
            metrics=metrics,
            dataset=dataset,
            params=params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=resolve_default_metric_bundle_packager(
                metrics, metric_bundle_packager, allow_cloudpickle_fallback=False, action="Submitting"
            ),
        )

    @overload
    def evaluate(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget,
        config: AgentEvalRunConfig | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
        workspace: str | None = None,
    ) -> AgentEvalJobResource: ...

    @overload
    def evaluate(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial],
        config: AgentEvalRunConfig | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
        workspace: str | None = None,
    ) -> AgentEvalJobResource: ...

    def evaluate(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget | None = None,
        trials: Sequence[AgentEvalTrial] | None = None,
        config: AgentEvalRunConfig | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
        workspace: str | None = None,
    ) -> AgentEvalJobResource:
        """Start a taskset evaluation on the platform and return its job handle.

        Returns a handle rather than a result, matching
        :meth:`~nemo_evaluator_sdk.execution.backends.base.EvaluationBackend.evaluate` and its
        sibling :meth:`evaluate_dataset`. Await it with ``wait_until_done()`` then ``get_result()``,
        or let :meth:`nemo_evaluator_sdk.execution.evaluator.Evaluator.submit` do both for you.

        The handle carries the taskset, so rebuilding the result does not ask the caller to hand
        their live tasks back.

        Args:
            taskset: Tasks to evaluate, each carrying its own metrics.
            target: What generates trials — a model, agent, or runner target spec. Mutually
                exclusive with ``trials``.
            trials: Precomputed trials to score instead of generating them. Mutually exclusive
                with ``target``.
            config: Run-level execution settings.
            metric_bundle_packager: How task metrics are serialized for the wire. Built-in metrics
                default to the declarative packager; anything needing cloudpickle must opt in.
            workspace: Workspace to submit into. Defaults to the client's workspace.

        Returns:
            The job handle.
        """
        # Validate before branching: branching alone would let a call carrying both seams
        # silently drop one.
        validate_run_inputs(tasks=taskset, trials=trials, target=target)
        if trials is not None:
            return self._agent_eval_executor.evaluate(
                taskset=taskset,
                trials=trials,
                config=config,
                metric_bundle_packager=metric_bundle_packager,
                workspace=workspace,
            )
        if target is not None:
            return self._agent_eval_executor.evaluate(
                taskset=taskset,
                target=target,
                config=config,
                metric_bundle_packager=metric_bundle_packager,
                workspace=workspace,
            )
        raise ValueError("provide exactly one of trials or target")


class AsyncEvaluator:
    """Async SDK namespace mounted as ``client.evaluator``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        """Store the async platform client used for evaluator plugin HTTP calls."""
        self._platform = platform
        self._http_client = platform._client
        self._executor = _AsyncEvaluatorPluginExecutor(platform=platform)
        self._agent_eval_executor = _AsyncAgentEvalExecutor(platform=platform)
        self.metrics = AsyncEvaluatorMetricsResource(platform)
        self.agent_eval_results = AsyncEvaluatorAgentEvalResultsResource(platform)
        self.eval_results = AsyncEvaluatorEvalResultsResource(platform)
        self.tasks = AsyncEvaluatorTasksResource(platform)
        self.tasksets = AsyncEvaluatorTasksetsResource(platform)

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
    async def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfig | None = None,
        target: None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> AsyncEvaluatorJobResource: ...

    @overload
    async def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfigOnlineModel,
        target: Model | ModelRef,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> AsyncEvaluatorJobResource: ...

    @overload
    async def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfigOnline,
        target: Agent,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any],
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> AsyncEvaluatorJobResource: ...

    async def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: SubmitTargetSpec | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> AsyncEvaluatorJobResource:
        """Submit a dataset metric job to the platform and return its job handle.

        See :meth:`Evaluator.evaluate_dataset`.
        """
        return await self._executor.evaluate_dataset(
            metrics=metrics,
            dataset=dataset,
            params=params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=resolve_default_metric_bundle_packager(
                metrics, metric_bundle_packager, allow_cloudpickle_fallback=False, action="Submitting"
            ),
        )

    @overload
    async def evaluate(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget,
        config: AgentEvalRunConfig | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
        workspace: str | None = None,
    ) -> AsyncAgentEvalJobResource: ...

    @overload
    async def evaluate(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial],
        config: AgentEvalRunConfig | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
        workspace: str | None = None,
    ) -> AsyncAgentEvalJobResource: ...

    async def evaluate(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        target: AgentEvalTarget | None = None,
        trials: Sequence[AgentEvalTrial] | None = None,
        config: AgentEvalRunConfig | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
        workspace: str | None = None,
    ) -> AsyncAgentEvalJobResource:
        """Start a taskset evaluation on the platform and return its job handle.

        See :meth:`Evaluator.evaluate`.
        """
        # Validate before branching: branching alone would let a call carrying both seams
        # silently drop one.
        validate_run_inputs(tasks=taskset, trials=trials, target=target)
        if trials is not None:
            return await self._agent_eval_executor.evaluate(
                taskset=taskset,
                trials=trials,
                config=config,
                metric_bundle_packager=metric_bundle_packager,
                workspace=workspace,
            )
        if target is not None:
            return await self._agent_eval_executor.evaluate(
                taskset=taskset,
                target=target,
                config=config,
                metric_bundle_packager=metric_bundle_packager,
                workspace=workspace,
            )
        raise ValueError("provide exactly one of trials or target")


evaluator_sdk_resources = NemoPluginSDKResources(
    sync_resource=Evaluator,
    async_resource=AsyncEvaluator,
)
