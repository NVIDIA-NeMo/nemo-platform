# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Private evaluator plugin executor implementation shared by SDK resources."""

from __future__ import annotations

import asyncio
import json
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast, overload

import httpx
from nemo_evaluator.api.schemas import MetadataItem, MetricInline, TaskInputs
from nemo_evaluator.filesets import FilesetRef
from nemo_evaluator.jobs.agent_evaluate import DEFAULT_RESULT_NAME as AGENT_EVAL_RESULT_NAME
from nemo_evaluator.jobs.agent_spec import AgentEvalInputSpec, AgentEvalTaskInput, AgentTarget, ModelTarget, Target
from nemo_evaluator.jobs.evaluate import DEFAULT_RESULT_NAME as DATASET_RESULT_NAME
from nemo_evaluator.jobs.evaluate import EvaluateInputSpec, TargetSpec
from nemo_evaluator.jobs.runner_targets import runner_to_target
from nemo_evaluator.resolvers import PlatformModelResolver
from nemo_evaluator.sdk import http_utils
from nemo_evaluator.sdk.job_resources import (
    AgentEvaluatorJob,
    AsyncEvaluatorJobResource,
    EvaluatorJob,
    EvaluatorJobResource,
)
from nemo_evaluator.sdk.types import PluginDatasetInput
from nemo_evaluator.sdk.utils import filter_benchmark_result, filter_evaluation_result
from nemo_evaluator.shared.metric_bundles.bundles import (
    MetricBundle,
    MetricBundlePackager,
    MetricBundlePackagerPolicyError,
    bundle_metric,
)
from nemo_evaluator.shared.metric_bundles.defaults import resolve_default_metric_bundle_packager
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalTaskScore
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTarget, AgentEvalTrial, AgentTaskRunner
from nemo_evaluator_sdk.datasets.loader import prepare_dataset_rows
from nemo_evaluator_sdk.execution.config import resolve_params
from nemo_evaluator_sdk.execution.metric_execution import run_sync
from nemo_evaluator_sdk.execution.utils import is_metric, is_metric_sequence
from nemo_evaluator_sdk.inference import PostprocessResponse, PreprocessRequest
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.values import (
    Agent,
    AgentBase,
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

_DEFAULT_POLL_INTERVAL_SECONDS = 10.0
_DEFAULT_JOB_TIMEOUT_SECONDS = 3600.0
_DEFAULT_PENDING_TIMEOUT_SECONDS = 600.0

SubmitTargetSpec = TargetSpec | ModelRef


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


def _reject_local_hooks(
    preprocess_hooks: tuple[PreprocessRequest, ...] | None,
    postprocess_hooks: tuple[PostprocessResponse, ...] | None,
) -> None:
    """Reject local Python hooks: the plugin backend runs out-of-process and can't execute them."""
    if preprocess_hooks or postprocess_hooks:
        raise NotImplementedError(
            "The evaluator plugin backend runs metrics out-of-process and cannot execute local "
            "preprocess/postprocess hooks; use Evaluator() (the in-process LocalBackend) for hook-based runs."
        )


def _agent_eval_target_to_spec(target: AgentEvalTarget | None, config: AgentEvalRunConfig | None) -> Target | None:
    """Convert a runtime agent-eval target (+ its run config) into a serializable wire ``Target``.

    ``Model``/``Agent`` endpoints map to ``ModelTarget``/``AgentTarget`` (folding the run config's
    prompt template and inference params into the target spec, as the wire contract expects).

    A live ``AgentTaskRunner`` is described by :func:`runner_to_target`, which owns the
    runtime-to-spec mapping (the inverse of ``_resolve_target``) and refuses runners whose
    configuration would not survive the trip.
    """
    if target is None:
        return None
    params = config.params if config is not None else None
    prompt_template = config.prompt_template if config is not None else None
    if isinstance(target, Model):
        return ModelTarget(
            model=target,
            prompt_template=prompt_template,
            params=params if isinstance(params, RunConfigOnlineModel) else None,
        )
    if isinstance(target, AgentBase):
        return AgentTarget(agent=cast(Agent, target), params=params if isinstance(params, RunConfigOnline) else None)
    return runner_to_target(cast(AgentTaskRunner, target))


def _agent_task_to_input(task: AgentEvalTask, *, metric_bundle_packager: MetricBundlePackager) -> AgentEvalTaskInput:
    """Convert a runtime ``AgentEvalTask`` (live metrics) into the submitter-facing wire DTO.

    The inverse of :func:`nemo_evaluator.jobs.agent_evaluate._to_runtime_task`. Live metrics are
    bundled inline; only the wire-recognized input fields survive (the wire ``TaskInputs`` schema is
    narrower than the runtime input mapping).
    """
    bundles = bundle_metrics_for_spec(task.metrics, metric_bundle_packager=metric_bundle_packager)
    recognized_inputs = {key: value for key, value in task.inputs.items() if key in TaskInputs.model_fields}
    return AgentEvalTaskInput(
        id=task.id,
        intent=task.intent,
        inputs=TaskInputs.model_validate(recognized_inputs),
        reference=task.reference,
        metrics=[MetricInline.model_validate_json(bundle.model_dump_json()) for bundle in bundles],
        views=task.views,
        metadata=[MetadataItem(key=key, value=str(value)) for key, value in task.metadata.items()],
    )


def _build_agent_eval_input_spec(
    *,
    tasks: Sequence[AgentEvalTask],
    target: AgentEvalTarget | None,
    trials: Sequence[AgentEvalTrial] | None,
    config: AgentEvalRunConfig | None,
    metric_bundle_packager: MetricBundlePackager,
) -> AgentEvalInputSpec:
    """Build the agent-eval plugin input spec from runtime tasks/target/trials/config."""
    return AgentEvalInputSpec(
        tasks=[_agent_task_to_input(task, metric_bundle_packager=metric_bundle_packager) for task in tasks],
        target=_agent_eval_target_to_spec(target, config),
        trials=list(trials) if trials is not None else None,
        max_concurrent_tasks=config.parallelism if config is not None else 4,
        fail_fast=config.fail_fast if config is not None else False,
        benchmark=config.benchmark if config is not None else {},
    )


def _all_task_metrics(tasks: Sequence[AgentEvalTask]) -> list[Metric]:
    """Flatten every task's metrics (used to select a default metric-bundle packager)."""
    return [metric for task in tasks for metric in task.metrics]


def _read_jsonl(path: Path) -> list[str]:
    """Read the non-empty lines of a JSONL bundle file."""
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _parse_dataset_result(
    result_text: str,
    *,
    metrics: Metric | Sequence[Metric],
    aggregate_fields: tuple[AggregateFieldName, ...] | None,
) -> EvaluationResult | BenchmarkEvaluationResult:
    """Parse the dataset job's own result JSON into the shape the caller's metrics imply.

    That single file is used rather than the aggregate/row-score routes because it is the one
    representation covering *both* shapes — a single metric's ``EvaluationResult`` and a metric
    sequence's ``BenchmarkEvaluationResult`` — so a submitted run returns exactly what in-process
    execution produced. (:meth:`evaluate_remote` still uses the dedicated single-metric routes.)
    """
    if is_metric_sequence(metrics):
        return filter_benchmark_result(BenchmarkEvaluationResult.model_validate_json(result_text), aggregate_fields)
    return filter_evaluation_result(EvaluationResult.model_validate_json(result_text), aggregate_fields)


def _find_agent_eval_bundle(root: Path) -> Path:
    """Locate the agent-eval bundle inside a downloaded artifacts tree.

    A submitted job's artifacts arrive as a tarball whose internal nesting is owned by the Jobs
    result serializer, so the bundle is found by its contents (the run manifest beside the trials
    stream) rather than by assuming a fixed depth. ``root`` itself is checked first, which is the
    shape the local path produces.
    """
    for candidate in (root, *sorted(path for path in root.rglob("run.json") if path.is_file())):
        bundle = candidate if candidate.is_dir() else candidate.parent
        if (bundle / "run.json").is_file() and (bundle / "trials.jsonl").is_file():
            return bundle
    raise RuntimeError(f"no agent-eval bundle (run.json + trials.jsonl) found under {root}")


def _read_agent_eval_bundle(bundle_dir: Path, *, tasks: Sequence[AgentEvalTask]) -> AgentEvalResult:
    """Reconstruct an ``AgentEvalResult`` from a persisted agent-eval bundle directory.

    Trials/scores/summary/benchmark are read back from the bundle; the caller's original ``tasks``
    are reused for the result (the bundle serializes tasks with type-only metric descriptors that do
    not round-trip to live ``Metric`` objects).
    """
    trials = [AgentEvalTrial.model_validate_json(line) for line in _read_jsonl(bundle_dir / "trials.jsonl")]
    scores = [AgentEvalTaskScore.model_validate_json(line) for line in _read_jsonl(bundle_dir / "scores.jsonl")]
    summary = AgentEvalSummary.model_validate_json((bundle_dir / "summary.json").read_text(encoding="utf-8"))
    benchmark = json.loads((bundle_dir / "benchmark.json").read_text(encoding="utf-8"))
    run_manifest = json.loads((bundle_dir / "run.json").read_text(encoding="utf-8"))
    return AgentEvalResult(
        run_id=run_manifest["run_id"],
        tasks=list(tasks),
        trials=trials,
        scores=scores,
        summary=summary,
        benchmark=benchmark,
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

    def create_taskset_job(
        self,
        *,
        spec: AgentEvalInputSpec,
        workspace: str | None = None,
        wait_until_done: bool = False,
    ) -> EvaluatorJobResource:
        """Create an agent-evaluation job with a sync platform client.

        The task-driven sibling of :meth:`create`. Agent-eval jobs are a separate collection on the
        plugin API, so the returned resource is bound to it — a job name is only resolvable within
        its own collection.
        """
        resolved_workspace = http_utils.resolve_workspace(self._platform, workspace)
        response = self._http_client.post(
            http_utils.job_collection_url(
                raw_base_url=str(self._platform.base_url),
                workspace=resolved_workspace,
                collection=http_utils.TASKSET_JOB_COLLECTION,
            ),
            json=http_utils.create_job_payload(spec),
            headers=http_utils.platform_default_headers(self._platform),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()

        job_resource = EvaluatorJobResource(
            job=AgentEvaluatorJob.model_validate(response.json()),
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=resolved_workspace,
            headers=http_utils.platform_default_headers(self._platform),
            collection=http_utils.TASKSET_JOB_COLLECTION,
        )

        if wait_until_done:
            job_resource.wait_until_done(
                poll_interval_seconds=self._poll_interval_seconds,
                job_timeout_seconds=self._job_timeout_seconds,
                pending_timeout_seconds=self._pending_timeout_seconds,
            )
        return job_resource

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

    @overload
    def evaluate_dataset(
        self,
        *,
        metrics: Metric,
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
    ) -> EvaluationResult: ...

    @overload
    def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
    ) -> BenchmarkEvaluationResult: ...

    def evaluate_dataset(
        self,
        *,
        metrics: Metric | Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
    ) -> EvaluationResult | BenchmarkEvaluationResult:
        """Submit a dataset evaluation (one metric or a sequence) to the platform and return its result.

        Implements the SDK's ``SyncEvaluationBackend`` protocol so this executor can be injected into
        ``Evaluator`` (see :meth:`Evaluator.as_backend`). The plugin backend is remote by
        construction — in-process evaluation is what ``Evaluator()``'s default ``LocalBackend`` is
        for — so local Python hooks, which cannot cross the job boundary, are rejected.
        """
        _reject_local_hooks(preprocess_hooks, postprocess_hooks)
        normalized_params = resolve_params(params, target)
        spec = _build_evaluate_spec(
            metrics=metrics,
            dataset=dataset,
            params=normalized_params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=resolve_default_metric_bundle_packager(
                metrics, None, allow_cloudpickle_fallback=True, action="Submitting"
            ),
        )
        job = self.create(
            spec=spec, workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True)
        )
        job.wait_until_done(
            poll_interval_seconds=self._poll_interval_seconds,
            job_timeout_seconds=self._job_timeout_seconds,
            pending_timeout_seconds=self._pending_timeout_seconds,
        )
        return _parse_dataset_result(
            job.read_result_text(DATASET_RESULT_NAME), metrics=metrics, aggregate_fields=aggregate_fields
        )

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

    def evaluate_taskset(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        """Submit a task-driven (agent) evaluation to the platform, poll it, and return its result.

        Implements the SDK's ``SyncEvaluationBackend`` protocol for task-driven evaluation, so
        ``Evaluator(client.evaluator.as_backend()).run_taskset_eval(...)`` runs the taskset *on the
        platform*: the spec is submitted to the agent-evaluate job collection and the completed run
        bundle is read back from the job's artifacts.

        Targets must be serializable — a ``Model``/``Agent`` endpoint, precomputed ``trials``, or a
        runner that implements ``SerializableAgentTaskRunner``. Local Python seams that cannot cross
        the job boundary are rejected at conversion time rather than silently dropped.
        """
        task_list = list(taskset)
        spec = _build_agent_eval_input_spec(
            tasks=task_list,
            target=target,
            trials=trials,
            config=config,
            metric_bundle_packager=resolve_default_metric_bundle_packager(
                _all_task_metrics(task_list), None, allow_cloudpickle_fallback=True, action="Submitting"
            ),
        )
        job = self.create_taskset_job(
            spec=spec, workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True)
        )
        job.wait_until_done(
            poll_interval_seconds=self._poll_interval_seconds,
            job_timeout_seconds=self._job_timeout_seconds,
            pending_timeout_seconds=self._pending_timeout_seconds,
        )
        with tempfile.TemporaryDirectory() as artifacts_root:
            downloaded = job.download_result(AGENT_EVAL_RESULT_NAME, artifacts_root)
            return _read_agent_eval_bundle(_find_agent_eval_bundle(downloaded), tasks=task_list)


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

    async def create_taskset_job(
        self,
        *,
        spec: AgentEvalInputSpec,
        workspace: str | None = None,
        wait_until_done: bool = False,
    ) -> AsyncEvaluatorJobResource:
        """Create an agent-evaluation job and return a high-level async job resource.

        The task-driven sibling of :meth:`create`; see the sync executor for why the resource is
        bound to the agent-evaluate collection.
        """
        resolved_workspace = http_utils.resolve_workspace(self._platform, workspace)
        response = await self._http_client.post(
            http_utils.job_collection_url(
                raw_base_url=str(self._platform.base_url),
                workspace=resolved_workspace,
                collection=http_utils.TASKSET_JOB_COLLECTION,
            ),
            json=http_utils.create_job_payload(spec),
            headers=http_utils.platform_default_headers(self._platform),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()

        job_resource = AsyncEvaluatorJobResource(
            job=AgentEvaluatorJob.model_validate(response.json()),
            http_client=self._http_client,
            base_url=http_utils.base_url(str(self._platform.base_url)),
            workspace=resolved_workspace,
            headers=http_utils.platform_default_headers(self._platform),
            collection=http_utils.TASKSET_JOB_COLLECTION,
        )

        if wait_until_done:
            await job_resource.wait_until_done(
                poll_interval_seconds=self._poll_interval_seconds,
                job_timeout_seconds=self._job_timeout_seconds,
                pending_timeout_seconds=self._pending_timeout_seconds,
            )
        return job_resource

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

    @overload
    async def evaluate_dataset(
        self,
        *,
        metrics: Metric,
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
    ) -> EvaluationResult: ...

    @overload
    async def evaluate_dataset(
        self,
        *,
        metrics: Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
    ) -> BenchmarkEvaluationResult: ...

    async def evaluate_dataset(
        self,
        *,
        metrics: Metric | Sequence[Metric],
        dataset: PluginDatasetInput,
        params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
        target: Model | Agent | None = None,
        field_mapping: FieldMapping | None = None,
        prompt_template: str | dict[str, Any] | None = None,
        aggregate_fields: tuple[AggregateFieldName, ...] | None = None,
        preprocess_hooks: tuple[PreprocessRequest, ...] | None = None,
        postprocess_hooks: tuple[PostprocessResponse, ...] | None = None,
    ) -> EvaluationResult | BenchmarkEvaluationResult:
        """Submit a dataset evaluation (one metric or a sequence) to the platform and return its result.

        Implements the SDK's ``EvaluationBackend`` protocol so this executor can be injected into
        ``Evaluator`` (see :meth:`AsyncEvaluator.as_backend`). The plugin backend is remote by
        construction — in-process evaluation is what ``Evaluator()``'s default ``LocalBackend`` is
        for — so local Python hooks, which cannot cross the job boundary, are rejected.
        """
        _reject_local_hooks(preprocess_hooks, postprocess_hooks)
        normalized_params = resolve_params(params, target)
        spec = _build_evaluate_spec(
            metrics=metrics,
            dataset=dataset,
            params=normalized_params,
            target=target,
            field_mapping=field_mapping,
            prompt_template=prompt_template,
            metric_bundle_packager=resolve_default_metric_bundle_packager(
                metrics, None, allow_cloudpickle_fallback=True, action="Submitting"
            ),
        )
        job = await self.create(
            spec=spec, workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True)
        )
        await job.wait_until_done(
            poll_interval_seconds=self._poll_interval_seconds,
            job_timeout_seconds=self._job_timeout_seconds,
            pending_timeout_seconds=self._pending_timeout_seconds,
        )
        return _parse_dataset_result(
            await job.read_result_text(DATASET_RESULT_NAME), metrics=metrics, aggregate_fields=aggregate_fields
        )

    async def evaluate_taskset(
        self,
        *,
        taskset: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        """Submit a task-driven (agent) evaluation to the platform, poll it, and return its result.

        Implements the SDK's ``EvaluationBackend`` protocol for task-driven evaluation, so
        ``Evaluator(client.evaluator.as_backend()).run_taskset_eval(...)`` runs the taskset *on the
        platform*: the spec is submitted to the agent-evaluate job collection and the completed run
        bundle is read back from the job's artifacts.

        Targets must be serializable — a ``Model``/``Agent`` endpoint, precomputed ``trials``, or a
        runner that implements ``SerializableAgentTaskRunner``. Local Python seams that cannot cross
        the job boundary are rejected at conversion time rather than silently dropped.
        """
        task_list = list(taskset)
        spec = _build_agent_eval_input_spec(
            tasks=task_list,
            target=target,
            trials=trials,
            config=config,
            metric_bundle_packager=resolve_default_metric_bundle_packager(
                _all_task_metrics(task_list), None, allow_cloudpickle_fallback=True, action="Submitting"
            ),
        )
        job = await self.create_taskset_job(
            spec=spec, workspace=http_utils.resolve_workspace(self._platform, self._workspace, strict=True)
        )
        await job.wait_until_done(
            poll_interval_seconds=self._poll_interval_seconds,
            job_timeout_seconds=self._job_timeout_seconds,
            pending_timeout_seconds=self._pending_timeout_seconds,
        )
        with tempfile.TemporaryDirectory() as artifacts_root:
            downloaded = await job.download_result(AGENT_EVAL_RESULT_NAME, artifacts_root)
            return await asyncio.to_thread(
                lambda: _read_agent_eval_bundle(_find_agent_eval_bundle(downloaded), tasks=task_list)
            )


def bundle_metrics_for_spec(
    metrics: Metric | Sequence[Metric], *, metric_bundle_packager: MetricBundlePackager
) -> list[MetricBundle]:
    """Package one metric or a benchmark metric sequence for an evaluator plugin spec."""
    if is_metric(metrics):
        return [bundle_metric(metrics, metric_bundle_packager)]
    if is_metric_sequence(metrics):
        return [bundle_metric(metric, metric_bundle_packager) for metric in metrics]
    raise TypeError("metrics must be a Metric or a sequence of Metric objects")
