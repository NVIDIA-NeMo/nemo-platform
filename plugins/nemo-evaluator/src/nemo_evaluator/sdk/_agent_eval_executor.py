# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Private agent-evaluation executor shared by the SDK resources.

Everything between an SDK-native call and a finished platform run lives here: translating live
values into the wire spec, creating the job, polling it, and reassembling the result from the run
bundle. ``Evaluator.evaluate`` in :mod:`nemo_evaluator.sdk.resources` is the public surface over
this and holds no logic of its own — the same split the row-evaluation path uses with
:mod:`nemo_evaluator.sdk._executor`. Waiting and result reassembly live on the job handle in
:mod:`nemo_evaluator.sdk.agent_eval_job_resources`.

Stored-entity references (``MetricRef``, ``TasksetRef``) are out of scope: everything is sent inline.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar, overload

from nemo_evaluator.api.schemas import MetadataItem, MetricInline, TaskInputs
from nemo_evaluator.jobs.agent_spec import (
    AgentEvalInputSpec,
    AgentEvalTaskInput,
    AgentTarget,
    ModelTarget,
    Target,
)
from nemo_evaluator.sdk import http_utils
from nemo_evaluator.sdk.agent_eval_job_resources import (
    COLLECTION,
    AgentEvalJobResource,
    AsyncAgentEvalJobResource,
    _JobAddress,
)
from nemo_evaluator.shared.metric_bundles.bundles import MetricBundlePackager, bundle_metric
from nemo_evaluator.shared.metric_bundles.defaults import resolve_default_metric_bundle_packager
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTarget, AgentEvalTrial
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.values import (
    GenericAgent,
    Model,
    NemoAgentToolkitAgent,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform

#: See :mod:`nemo_evaluator_sdk.execution.jobs` — PEP 695 syntax would break Python 3.11.
_ParamsT = TypeVar("_ParamsT", bound=RunConfigOnline)

# --- spec construction --------------------------------------------------------


def build_spec(
    *,
    taskset: Sequence[AgentEvalTask],
    target: AgentEvalTarget | None,
    trials: Sequence[AgentEvalTrial] | None,
    config: AgentEvalRunConfig | None,
    metric_bundle_packager: MetricBundlePackager | None,
) -> AgentEvalInputSpec:
    """Build the submitter-facing spec from SDK-native values."""
    tasks = list(taskset)
    if not tasks:
        raise ValueError("provide at least one task")
    packager = resolve_default_metric_bundle_packager(
        [metric for task in tasks for metric in task.metrics],
        metric_bundle_packager,
        allow_cloudpickle_fallback=False,
        action="Submitting",
    )
    return AgentEvalInputSpec(
        tasks=[_task_input(task, packager) for task in tasks],
        target=_target_spec(target, config),
        trials=list(trials) if trials is not None else None,
        max_concurrent_tasks=config.parallelism if config is not None else 4,
        fail_fast=config.fail_fast if config is not None else False,
        labels=dict(config.labels) if config is not None else {},
    )


def _task_input(task: AgentEvalTask, packager: MetricBundlePackager) -> AgentEvalTaskInput:
    """Convert one SDK task into the wire DTO, packaging its metrics."""
    unsupported = sorted(set(task.inputs) - {"instruction"})
    if unsupported:
        raise ValueError(
            f"task {task.id!r} cannot be submitted with inputs {unsupported}: the task input schema "
            "carries only 'instruction'. Run it in-process with AgentEvaluator instead."
        )
    instruction = task.inputs.get("instruction")
    if not instruction:
        # The wire schema allows a null instruction, so this is the last place to catch it before a
        # job create, a poll loop, and a bundle download report an agent that was told nothing.
        raise ValueError(f"task {task.id!r} has no 'instruction' input; there is nothing to send the agent.")
    metadata: list[MetadataItem] = []
    for key, value in task.metadata.items():
        if not isinstance(value, str):
            raise ValueError(
                f"task {task.id!r} metadata {key!r} is {type(value).__name__}; task metadata is a "
                "string map on the wire."
            )
        metadata.append(MetadataItem(key=key, value=value))
    return AgentEvalTaskInput(
        id=task.id,
        intent=task.intent,
        inputs=TaskInputs(instruction=instruction),
        reference=task.reference,
        metrics=[_bundled(metric, packager) for metric in task.metrics],
        views=task.views,
        metadata=metadata,
    )


def _bundled(metric: Metric, packager: MetricBundlePackager) -> MetricInline:
    """Package one runtime metric as the inline bundle the spec carries."""
    return MetricInline.model_validate_json(bundle_metric(metric, packager).model_dump_json())


def _params_for(params: Any, expected: type[_ParamsT], target: object) -> _ParamsT | None:
    """Return the run params if they match the target kind, raising if they do not.

    Matched on exact type rather than ``isinstance``: ``RunConfigOnlineModel`` subclasses
    ``RunConfigOnline``, so an ``isinstance`` check on an agent target would silently accept a
    model's request config.
    """
    if params is None or type(params) is expected:
        return params
    raise TypeError(
        f"{type(target).__name__} target requires {expected.__name__} params, got "
        f"{type(params).__name__}. Set config.params to {expected.__name__} or leave it unset."
    )


def _target_spec(target: AgentEvalTarget | None, config: AgentEvalRunConfig | None) -> Target | None:
    """Describe a live target as the spec that reproduces it job-side.

    A ``Model`` carries its request shape (prompt template, inference params), which live on the
    run config SDK-side but on the target spec wire-side; they are moved here rather than dropped.
    """
    if target is None:
        # ``params`` and ``prompt_template`` describe how to generate trials. With no target there
        # is nothing to generate, and the wire spec has nowhere to carry them, so accepting them
        # here would drop them silently.
        carried = (
            []
            if config is None
            else [
                name
                for name, value in (("params", config.params), ("prompt_template", config.prompt_template))
                if value is not None
            ]
        )
        if carried:
            raise ValueError(
                f"config carries {', '.join(carried)} but no target was supplied. Those describe how "
                "to generate trials; drop them when scoring precomputed trials."
            )
        return None
    if isinstance(target, ModelTarget | AgentTarget):
        return target
    params = config.params if config is not None else None
    if isinstance(target, Model):
        return ModelTarget(
            model=target,
            prompt_template=config.prompt_template if config is not None else None,
            params=_params_for(params, RunConfigOnlineModel, target),
        )
    # Narrower than ``AgentBase`` on purpose: a runner can subclass it, and only these two are
    # valid ``AgentTarget.agent`` values.
    if isinstance(target, GenericAgent | NemoAgentToolkitAgent):
        return AgentTarget(agent=target, params=_params_for(params, RunConfigOnline, target))
    raise TypeError(
        f"unsupported agent-evaluation target: {type(target).__name__}. Pass a Model, an Agent, or "
        "a runner target spec (CodexRunnerTarget, FabricRunnerTarget, HarborRunnerTarget)."
    )


# --- job creation -------------------------------------------------------------


def _job_name(payload: Mapping[str, Any]) -> str:
    name = payload.get("name") or payload.get("id")
    if not name:
        raise ValueError(f"agent-eval submit response carried no job name: {payload}")
    return str(name)


def _create_payload(spec: AgentEvalInputSpec) -> dict[str, Any]:
    return {"spec": spec.model_dump(mode="json")}


def _address(platform: NeMoPlatform | AsyncNeMoPlatform, job_name: str, workspace: str) -> _JobAddress:
    return _JobAddress(
        name=job_name,
        base_url=http_utils.base_url(str(platform.base_url)),
        workspace=workspace,
        headers=http_utils.platform_default_headers(platform),
        timeout=platform.timeout,
    )


def _collection_url(platform: NeMoPlatform | AsyncNeMoPlatform, workspace: str) -> str:
    return http_utils.url(platform, f"/v2/workspaces/{{workspace}}/{COLLECTION}", workspace)


class _SyncAgentEvalExecutor:
    """Sync agent-evaluation executor used by the sync SDK resource."""

    def __init__(self, *, platform: NeMoPlatform) -> None:
        """Store the sync platform client used for agent-evaluation calls."""
        self._platform = platform
        self._http_client = platform._client

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
        """Create the platform job and return a handle on it.

        The handle carries ``taskset`` because rebuilding the result needs the caller's live tasks.
        """
        spec = build_spec(
            taskset=taskset,
            target=target,
            trials=trials,
            config=config,
            metric_bundle_packager=metric_bundle_packager,
        )
        resolved = http_utils.resolve_workspace(self._platform, workspace, strict=True)
        response = self._http_client.post(
            _collection_url(self._platform, resolved),
            json=_create_payload(spec),
            headers=http_utils.platform_default_headers(self._platform),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return AgentEvalJobResource(
            address=_address(self._platform, _job_name(response.json()), resolved),
            http_client=self._http_client,
            taskset=taskset,
        )


class _AsyncAgentEvalExecutor:
    """Async agent-evaluation executor used by the async SDK resource."""

    def __init__(self, *, platform: AsyncNeMoPlatform) -> None:
        """Store the async platform client used for agent-evaluation calls."""
        self._platform = platform
        self._http_client = platform._client

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
        """Create the platform job and return a handle on it.

        See :meth:`_SyncAgentEvalExecutor.evaluate`.
        """
        spec = build_spec(
            taskset=taskset,
            target=target,
            trials=trials,
            config=config,
            metric_bundle_packager=metric_bundle_packager,
        )
        resolved = http_utils.resolve_workspace(self._platform, workspace, strict=True)
        response = await self._http_client.post(
            _collection_url(self._platform, resolved),
            json=_create_payload(spec),
            headers=http_utils.platform_default_headers(self._platform),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return AsyncAgentEvalJobResource(
            address=_address(self._platform, _job_name(response.json()), resolved),
            http_client=self._http_client,
            taskset=taskset,
        )
