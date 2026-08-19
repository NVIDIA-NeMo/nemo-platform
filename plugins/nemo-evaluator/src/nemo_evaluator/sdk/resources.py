# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for the evaluator plugin scaffold."""

from __future__ import annotations

from typing import Any, overload
from urllib.parse import quote

from nemo_evaluator.api.schemas import TasksetRef
from nemo_evaluator.sdk import http_utils
from nemo_evaluator.sdk._executor import (
    SubmitTargetSpec,
    _AsyncEvaluatorPluginExecutor,
    _SyncEvaluatorPluginExecutor,
)
from nemo_evaluator.sdk.job_resources import (
    AgentEvaluatorJobResource,
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
from nemo_evaluator_sdk.agent_eval.trials import AgentTaskRunner
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

    @overload
    def submit(
        self,
        *,
        tasks: TasksetRef,
        target: AgentTaskRunner,
        metric: None = None,
        dataset: None = None,
    ) -> AgentEvaluatorJobResource: ...

    def submit(
        self,
        *,
        metric: Metric | None = None,
        dataset: PluginDatasetInput | None = None,
        tasks: TasksetRef | None = None,
        config: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: SubmitTargetSpec | AgentTaskRunner | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        metric_bundle_packager: MetricBundlePackager | None = None,
    ) -> EvaluatorJobResource | AgentEvaluatorJobResource:
        """Submit an evaluation job through the evaluator plugin executor.

        Two shapes, discriminated by what you supply: ``metric`` + ``dataset`` evaluates rows, and
        ``tasks`` + ``target`` evaluates a stored taskset with a live agent runner. They are one
        method because they are one concept — the split is a property of how the work is described
        today, not of what the caller is asking for.
        """
        if tasks is not None:
            if metric is not None or dataset is not None:
                raise TypeError(
                    "submit() takes either `tasks` (a taskset evaluation) or `metric` + `dataset` "
                    "(a row evaluation), not both. Drop whichever does not describe this run."
                )
            if not isinstance(target, AgentTaskRunner):
                raise TypeError(
                    "submit(tasks=...) evaluates a taskset with an agent runner, so `target` must be "
                    f"an AgentTaskRunner; got {type(target).__name__}. Pass a runner such as "
                    "GymAgentTaskRunner(config=...)."
                )
            # Everything below configures a *row* evaluation. The taskset path cannot honour any of
            # it, so accepting it silently would run a job that ignores what the caller asked for.
            row_only = {
                "config": config,
                "field_mapping": field_mapping,
                "prompt_template": prompt_template,
                "metric_bundle_packager": metric_bundle_packager,
            }
            supplied = sorted(name for name, value in row_only.items() if value is not None)
            if supplied:
                raise TypeError(
                    f"submit(tasks=...) does not use {', '.join(supplied)} — those configure a row "
                    "evaluation. A taskset evaluation is configured by the runner passed as "
                    "`target`, so supplying them here would have no effect."
                )
            return self._executor.submit_agent_eval(tasks=tasks, target=target)
        if metric is None or dataset is None:
            raise TypeError(
                "submit() needs either `tasks` + `target` for a taskset evaluation, or `metric` + "
                "`dataset` for a row evaluation; neither was supplied."
            )
        if isinstance(target, AgentTaskRunner):
            # The mirror of the check above: a runner is only meaningful for a taskset evaluation,
            # so this is a caller who meant to pass `tasks` and passed a dataset instead. Reaching
            # the row path with it would fail much deeper, describing the runner as a model endpoint.
            raise TypeError(
                f"{type(target).__name__} is an agent runner, which runs a taskset rather than "
                "rows. Pass `tasks=TasksetRef(...)` instead of `metric` + `dataset`."
            )
        return self._executor.submit(
            metric=metric,
            dataset=dataset,
            params=config,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=resolve_default_metric_bundle_packager(
                metric, metric_bundle_packager, allow_cloudpickle_fallback=False, action="Submitting"
            ),
        )


class AsyncEvaluator:
    """Async SDK namespace mounted as ``client.evaluator``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        """Store the async platform client used for evaluator plugin HTTP calls."""
        self._platform = platform
        self._http_client = platform._client
        self._executor = _AsyncEvaluatorPluginExecutor(platform=platform)
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
        return await self._executor.submit(
            metric=metric,
            dataset=dataset,
            params=config,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=resolve_default_metric_bundle_packager(
                metric, metric_bundle_packager, allow_cloudpickle_fallback=False, action="Submitting"
            ),
        )


evaluator_sdk_resources = NemoPluginSDKResources(
    sync_resource=Evaluator,
    async_resource=AsyncEvaluator,
)
