# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standalone agent evaluation orchestration."""

# ruff: noqa: I001 - the vendored SDK mirror uses different import-order settings.

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from logging import getLogger
from pathlib import Path
from typing import Any, cast, overload
from urllib.parse import urlparse

import httpx
import nemo_evaluator_sdk.inference as inference
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary, RunMetadata
from nemo_evaluator_sdk.agent_eval.scores import (
    AgentEvalDiagnostic,
    AgentEvalDiagnosticSeverity,
    AgentEvalScoreStatus,
    AgentEvalTaskScore,
    TRIAL_STATUS_DETAIL,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import (
    AgentEvalTarget,
    AgentEvalTrial,
    AgentEvalTrialStatus,
    AgentOutput,
    AgentTaskRunner,
    RunAggregationsProvider,
    RunnerInfo,
)
from nemo_evaluator_sdk.agent_inference import (
    AgentInferenceContext,
    AgentInferenceFn,
    AgentInferenceFnFactory,
    make_agent_inference_fn,
    new_agent_inference_client,
)
from nemo_evaluator_sdk.execution.metric_execution import (
    generate_online_sample,
    resolve_target_structured_output_mode,
    run_sync,
)
from nemo_evaluator_sdk.session import begin_evaluation_session
from nemo_evaluator_sdk.execution.samples import build_metric_input
from nemo_evaluator_sdk.inference import InferenceFn
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricWithPreflight, validate_metric_result
from nemo_evaluator_sdk.metrics.utils import metric_type_name
from nemo_evaluator_sdk.values import (
    Agent,
    AgentBase,
    GenericAgent,
    Model,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from nemo_evaluator_sdk.values.results import AggregateScore
from nemo_evaluator_sdk.values.evidence import (
    EVIDENCE_FORMAT_JSON,
    EVIDENCE_TRACE,
    CandidateEvidence,
    EvidenceDescriptor,
)
from openai import AsyncOpenAI

log = getLogger(__name__)

_SAMPLE_KEYS_EXCLUDED_FROM_OUTPUT_METADATA = frozenset(
    {
        "evidence",
        "invocation_metadata",
        "invocation_status",
        "output_text",
        "response",
        "trajectory",
    }
)


class AgentEvaluator:
    """Run stored-trial or live-target agent evaluations.

    The online inference seam (an optional ``inference_fn``, transport ``client``, and
    ``default_headers``) is injected on the evaluator instance rather than the run config,
    because these are runtime transport concerns rather than declarative run settings. A
    single ``inference_fn``/``client`` pair serves both model and agent targets; leave them
    unset to let the evaluator build a default client for the resolved target type.
    """

    @overload
    def __init__(
        self,
        *,
        inference_fn: InferenceFn | AgentInferenceFn | None = None,
        agent_inference_fn_factory: None = None,
        client: AsyncOpenAI | httpx.AsyncClient | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        inference_fn: None = None,
        agent_inference_fn_factory: AgentInferenceFnFactory,
        client: AsyncOpenAI | httpx.AsyncClient | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None: ...

    def __init__(
        self,
        *,
        inference_fn: InferenceFn | AgentInferenceFn | None = None,
        agent_inference_fn_factory: AgentInferenceFnFactory | None = None,
        client: AsyncOpenAI | httpx.AsyncClient | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        """Configure runtime dependencies for live target generation.

        Args:
            inference_fn: Optional model or agent inference override. When omitted, the
                evaluator selects the default implementation for the target type.
            agent_inference_fn_factory: Optional per-task factory for agent inference.
                The evaluator supplies persistence and invocation identity through an
                :class:`AgentInferenceContext`.
            client: Optional transport client matching the target type: ``AsyncOpenAI`` for
                models or ``httpx.AsyncClient`` for agents.
            default_headers: Additional HTTP headers forwarded to live inference requests.
        """
        if inference_fn is not None and agent_inference_fn_factory is not None:
            raise ValueError("provide either inference_fn or agent_inference_fn_factory, not both")
        self.inference_fn = inference_fn
        self.agent_inference_fn_factory = agent_inference_fn_factory
        self.client = client
        self.default_headers = default_headers

    async def run(
        self,
        *,
        tasks: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        """Evaluate imported trials or generate live trials before scoring.

        Exactly one of ``trials`` or ``target`` must be provided.
        """
        resolved_config = config or AgentEvalRunConfig()
        task_list = list(tasks)
        if not task_list:
            raise ValueError("at least one task is required")

        run_id = resolved_config.run_id or _new_run_id()
        runtime_config = resolved_config.model_copy(update={"run_id": run_id})
        started_at = datetime.now(UTC)

        async with begin_evaluation_session():
            # Branch on which seam was supplied so the type checker can narrow ``target`` to a
            # concrete ``AgentEvalTarget`` without a cast.
            if trials is not None:
                if target is not None:
                    raise ValueError("provide exactly one of trials or target")
                trial_list = list(trials)
            elif target is not None:
                trial_list = await self._generate_trials(tasks=task_list, target=target, config=runtime_config)
            else:
                raise ValueError("provide exactly one of trials or target")
            scores = await self._score_trials(
                tasks=task_list,
                trials=trial_list,
                config=runtime_config,
                run_id=run_id,
            )
        runner_scores = _collect_runner_aggregate_scores(target) if target is not None else []
        finished_at = datetime.now(UTC)
        metadata = RunMetadata(
            labels=dict(runtime_config.labels),
            target=_describe_target(target, runtime_config.params),
            started_at=started_at,
            finished_at=finished_at,
            duration_sec=(finished_at - started_at).total_seconds(),
            sdk_version=_sdk_version(),
        )
        result = AgentEvalResult(
            run_id=run_id,
            tasks=task_list,
            trials=trial_list,
            scores=scores,
            summary=AgentEvalSummary.from_scores(
                scores, tasks=task_list, trials=trial_list, extra_scores=runner_scores
            ),
            metadata=metadata,
            work_dir=runtime_config.work_dir,
        )

        return result

    def run_sync(
        self,
        *,
        tasks: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        """Synchronous bridge for :meth:`run`."""
        return run_sync(lambda: self.run(tasks=tasks, trials=trials, target=target, config=config))

    async def _score_trials(
        self,
        *,
        tasks: list[AgentEvalTask],
        trials: list[AgentEvalTrial],
        config: AgentEvalRunConfig,
        run_id: str,
    ) -> list[AgentEvalTaskScore]:
        tasks_by_id = {task.id: task for task in tasks}
        task_index_by_id = {task.id: index for index, task in enumerate(tasks)}
        trials_by_task: dict[str, list[AgentEvalTrial]] = defaultdict(list)
        for trial in trials:
            if trial.task_id not in tasks_by_id:
                raise ValueError(f"trial {trial.id!r} references unknown task {trial.task_id!r}")
            trials_by_task[trial.task_id].append(trial)

        # Fail loudly when a task produced no trial. Imported trials or an AgentTaskRunner may omit a
        # task entirely; without this an incomplete run would look successful aside from lower summary
        # counts. (A richer alternative is to emit a "missing trial" failed score per metric.)
        tasks_without_trials = [task.id for task in tasks if not trials_by_task.get(task.id)]
        if tasks_without_trials:
            raise ValueError(f"no trials produced for tasks: {sorted(tasks_without_trials)}")

        for task in tasks:
            if not task.metrics:
                raise ValueError(f"task {task.id!r} does not declare any metrics")

        await _preflight_task_metrics(tasks)

        semaphore = asyncio.Semaphore(config.parallelism)

        async def guarded_score(task: AgentEvalTask, trial: AgentEvalTrial, metric: Metric) -> AgentEvalTaskScore:
            async with semaphore:
                row_index = task_index_by_id[task.id]
                if trial.status == AgentEvalTrialStatus.FAILED:
                    return _failed_metric_score(
                        run_id=run_id,
                        task=task,
                        trial=trial,
                        metric=metric,
                        row_index=row_index,
                        diagnostic=AgentEvalDiagnostic(
                            severity=AgentEvalDiagnosticSeverity.ERROR,
                            message=f"trial {trial.id!r} is failed",
                            source=metric_type_name(metric),
                            # The key pass@k reads to tell "the agent produced nothing" (a failed
                            # attempt) from "the metric raised" (an unusable measurement).
                            details={TRIAL_STATUS_DETAIL: trial.status.value},
                        ),
                    )
                try:
                    return await _score_metric(
                        run_id=run_id,
                        task=task,
                        trial=trial,
                        metric=metric,
                        row_index=row_index,
                    )
                except Exception as exc:
                    if config.fail_fast:
                        raise
                    log.warning(
                        "metric %s failed for trial %r (task %r): %s",
                        metric_type_name(metric),
                        trial.id,
                        task.id,
                        exc,
                    )
                    return _failed_metric_score(
                        run_id=run_id,
                        task=task,
                        trial=trial,
                        metric=metric,
                        row_index=row_index,
                        diagnostic=_exception_diagnostic(exc, metric_type_name(metric)),
                    )

        return await asyncio.gather(
            *[
                guarded_score(task, trial, metric)
                for task in tasks
                for trial in trials_by_task.get(task.id, [])
                for metric in task.metrics
            ]
        )

    async def _generate_trials(
        self,
        *,
        tasks: list[AgentEvalTask],
        target: AgentEvalTarget,
        config: AgentEvalRunConfig,
    ) -> list[AgentEvalTrial]:
        if isinstance(target, AgentTaskRunner):
            return list(await target.run_tasks(tasks, config=config))
        if not isinstance(target, (Model, AgentBase)):
            raise NotImplementedError(f"unsupported agent-eval target type: {type(target).__name__}")

        params = _resolve_live_params(config, target)
        prompt_template = config.prompt_template or _default_prompt_template(target)
        semaphore = asyncio.Semaphore(params.parallelism)

        # Use the injected transport client when provided; otherwise build a default for the
        # resolved target type and close it when generation finishes.
        client = self.client
        close_client: Callable[[], Awaitable[Any]] | None = None
        if client is None and self.inference_fn is None:
            if isinstance(target, Model):
                client = inference.new_inference_client(target)
                close_client = client.close
            else:
                client = new_agent_inference_client()
                close_client = client.aclose

        try:
            # When config.params.ignore_request_failure is set, convert a failed generation request
            # into a FAILED trial (which the scorer turns into failed metric scores) instead of
            # aborting the whole run. This matches the existing online-evaluator contract.
            async def generate_one(index: int, task: AgentEvalTask) -> AgentEvalTrial:
                async with semaphore:
                    # Keep evaluator-owned runtime identity separate from task inputs.
                    # ``_generate_sample`` exposes these values to request templates under
                    # ``agent_eval``. For agent targets, the same values are supplied to the
                    # inference factory so stream translators and evidence can carry stable
                    # evaluation identifiers without coupling them to this evaluator.
                    agent_eval_context = {
                        "run_id": config.run_id,
                        "task_id": task.id,
                        "invocation_id": f"{config.run_id}:{task.id}:{target.name}",
                    }
                    evidence_dir = (
                        _task_evidence_dir(Path(config.work_dir), index=index, task_id=task.id)
                        if config.work_dir is not None and isinstance(target, AgentBase)
                        else None
                    )
                    resolved_inference_fn = self.inference_fn
                    if isinstance(target, AgentBase) and resolved_inference_fn is None:
                        factory = self.agent_inference_fn_factory or make_agent_inference_fn
                        resolved_inference_fn = factory(
                            AgentInferenceContext(
                                evidence_dir=evidence_dir,
                                metadata=agent_eval_context,
                            )
                        )
                    try:
                        sample = await _generate_sample(
                            target=target,
                            row=_task_row(task),
                            index=index,
                            prompt_template=prompt_template,
                            params=params,
                            inference_fn=resolved_inference_fn,
                            client=client,
                            default_headers=self.default_headers,
                            agent_eval_context=agent_eval_context,
                        )
                    except Exception as exc:
                        if params.ignore_request_failure:
                            return _failed_generation_trial(task, target, exc)
                        raise
                    return _trial_from_sample(task, target, sample)

            return await asyncio.gather(*(generate_one(index, task) for index, task in enumerate(tasks)))
        finally:
            if close_client is not None:
                await close_client()


async def _preflight_task_metrics(tasks: Sequence[AgentEvalTask]) -> None:
    """Run each distinct metric's preflight once.

    Agent-eval scores metrics directly rather than through ``prepare_metric_for_execution``, so
    nothing else runs their preflight.
    """
    preflighted: set[int] = set()
    for task in tasks:
        for metric in task.metrics:
            if isinstance(metric, MetricWithPreflight) and id(metric) not in preflighted:
                preflighted.add(id(metric))
                await metric.preflight()


async def _generate_sample(
    *,
    target: Model | Agent,
    row: dict[str, Any],
    index: int,
    prompt_template: str | dict[str, Any],
    params: RunConfigOnline | RunConfigOnlineModel,
    inference_fn: InferenceFn | AgentInferenceFn | None,
    client: AsyncOpenAI | httpx.AsyncClient | None,
    default_headers: dict[str, str] | None,
    agent_eval_context: dict[str, Any],
) -> dict[str, Any]:
    # InferenceFn and AgentInferenceFn are callable protocols, so isinstance cannot discriminate
    # the injected fn; narrow it per target type with a cast (matching execution/benchmark_execution).
    # The transport client is a real class union, so isinstance narrowing is enough there.
    if isinstance(target, Model):
        model_params = cast(RunConfigOnlineModel, params)
        preprocess_hooks, postprocess_hooks = inference.new_hooks(model_params)
        model_inference_fn = (
            cast(InferenceFn, inference_fn) if inference_fn is not None else inference.make_inference_request
        )
        await resolve_target_structured_output_mode(
            preprocess_hooks=preprocess_hooks,
            model=target,
            inference_fn=model_inference_fn,
            params=model_params,
        )
        return await generate_online_sample(
            target=target,
            row=row,
            index=index,
            prompt_template=prompt_template,
            params=model_params,
            inference_fn=model_inference_fn,
            client=client if isinstance(client, AsyncOpenAI) else None,
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
            default_headers=default_headers,
            template_context={"agent_eval": agent_eval_context},
        )

    if inference_fn is None:
        raise TypeError("expected AgentInferenceFn for Agent target")
    agent_inference_fn = cast(AgentInferenceFn, inference_fn)
    return await generate_online_sample(
        target=target,
        row=row,
        index=index,
        prompt_template=prompt_template,
        params=params,
        inference_fn=agent_inference_fn,
        client=client if isinstance(client, httpx.AsyncClient) else None,
        default_headers=default_headers,
        template_context={"agent_eval": agent_eval_context},
    )


def _trial_from_sample(task: AgentEvalTask, target: Model | Agent, sample: dict[str, Any]) -> AgentEvalTrial:
    output_text = sample.get("output_text")
    if not (isinstance(output_text, str) and output_text.strip()):
        # Reasoning models that exhaust the token budget can return only
        # `reasoning_content` with empty `content`. Fall back to that text so the
        # trial stays scorable instead of being dropped as empty output.
        output_text = _reasoning_content_fallback(sample.get("response"))
    evidence = sample.get("evidence")
    if evidence is not None and not isinstance(evidence, CandidateEvidence):
        evidence = CandidateEvidence.model_validate(evidence)

    # Evidence precedence:
    # - trajectory exists: merge it without replacing a typed trace.
    # - no trajectory, but typed evidence exists: preserve that evidence unchanged.
    # - neither exists: synthesize the fallback trace.
    if "trajectory" in sample:
        trace = EvidenceDescriptor(kind=EVIDENCE_TRACE, format=EVIDENCE_FORMAT_JSON, data=sample["trajectory"])
        descriptors = dict(evidence.descriptors) if evidence is not None else {}
        descriptors.setdefault(EVIDENCE_TRACE, trace)
        evidence = CandidateEvidence(
            descriptors=descriptors,
            metadata=dict(evidence.metadata) if evidence is not None else {},
        )
    elif evidence is None:
        evidence = CandidateEvidence(
            descriptors={
                EVIDENCE_TRACE: EvidenceDescriptor(
                    kind=EVIDENCE_TRACE,
                    format=EVIDENCE_FORMAT_JSON,
                    data={"task_id": task.id, "target": target.name},
                )
            }
        )

    status_value = sample.get("invocation_status", AgentEvalTrialStatus.COMPLETED.value)
    status = AgentEvalTrialStatus(status_value)
    invocation_metadata = sample.get("invocation_metadata")
    if not isinstance(invocation_metadata, dict):
        invocation_metadata = {}

    return AgentEvalTrial(
        id=f"{task.id}:{target.name}",
        task_id=task.id,
        status=status,
        output=AgentOutput(
            output_text=output_text if isinstance(output_text, str) else None,
            response=sample.get("response"),
            metadata={
                **invocation_metadata,
                **{
                    key: value for key, value in sample.items() if key not in _SAMPLE_KEYS_EXCLUDED_FROM_OUTPUT_METADATA
                },
            },
        ),
        evidence=evidence,
        metadata={
            **invocation_metadata,
            "model_id": target.name,
            "target_name": target.name,
            "generated": True,
        },
    )


def _reasoning_content_fallback(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    choices = response.get("choices")
    if not isinstance(choices, list):
        return None
    for choice in choices:
        message = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(message, dict):
            continue
        reasoning = message.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning
    return None


def _failed_generation_trial(task: AgentEvalTask, target: Model | Agent, exc: Exception) -> AgentEvalTrial:
    return AgentEvalTrial(
        id=f"{task.id}:{target.name}",
        task_id=task.id,
        status=AgentEvalTrialStatus.FAILED,
        output=None,
        evidence=CandidateEvidence(
            descriptors={
                "error": EvidenceDescriptor(
                    kind="error",
                    data={"error_type": exc.__class__.__name__, "error": str(exc)},
                )
            }
        ),
        metadata={
            "model_id": target.name,
            "target_name": target.name,
            "generated": True,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        },
    )


async def _score_metric(
    *,
    run_id: str,
    task: AgentEvalTask,
    trial: AgentEvalTrial,
    metric: Metric,
    row_index: int,
) -> AgentEvalTaskScore:
    output_spec = metric.output_spec()
    metric_result = validate_metric_result(
        await metric.compute_scores(build_metric_input(_metric_row(task, trial), _trial_sample(trial), row_index)),
        output_spec,
    )
    metric_type = metric_type_name(metric)
    return AgentEvalTaskScore(
        id=_score_id(run_id, task.id, trial.id, metric_type),
        run_id=run_id,
        task_id=task.id,
        trial_id=trial.id,
        metric_type=metric_type,
        status=AgentEvalScoreStatus.COMPLETED,
        outputs=metric_result.outputs,
        # Persist the metric's own diagnostics (e.g. per-criterion judge verdicts) — the failure path
        # already records diagnostics; the success path dropped them.
        diagnostics=[
            AgentEvalDiagnostic(
                severity=AgentEvalDiagnosticSeverity.INFO,
                message=diagnostic.message,
                source=metric_type,
                details=diagnostic.details or {},
            )
            for diagnostic in metric_result.diagnostics
        ],
        metadata={
            "row_index": row_index,
            "trial_metadata": trial.metadata,
        },
    )


def _failed_metric_score(
    *,
    run_id: str,
    task: AgentEvalTask,
    trial: AgentEvalTrial,
    metric: Metric,
    row_index: int,
    diagnostic: AgentEvalDiagnostic,
) -> AgentEvalTaskScore:
    metric_type = metric_type_name(metric)
    return AgentEvalTaskScore(
        id=_score_id(run_id, task.id, trial.id, metric_type),
        run_id=run_id,
        task_id=task.id,
        trial_id=trial.id,
        metric_type=metric_type,
        status=AgentEvalScoreStatus.FAILED,
        outputs=[],
        diagnostics=[diagnostic],
        metadata={
            "row_index": row_index,
            "trial_metadata": trial.metadata,
        },
    )


def _exception_diagnostic(exc: Exception, metric_type: str) -> AgentEvalDiagnostic:
    return AgentEvalDiagnostic(
        severity=AgentEvalDiagnosticSeverity.ERROR,
        message=str(exc) or exc.__class__.__name__,
        source=metric_type,
        details={"exception_type": exc.__class__.__name__},
    )


def _score_id(run_id: str, task_id: str, trial_id: str, metric_type: str) -> str:
    return f"{run_id}:{task_id}:{trial_id}:{metric_type}"


def _trial_sample(trial: AgentEvalTrial) -> dict[str, Any]:
    if trial.output is None:
        return {}
    sample: dict[str, Any] = {
        **trial.metadata,
        **trial.output.metadata,
    }
    if trial.output.output_text is not None:
        sample["output_text"] = trial.output.output_text
    if trial.output.response is not None:
        sample["response"] = trial.output.response
    if trial.evidence is not None:
        sample["evidence"] = trial.evidence
    return sample


def _resolve_live_params(
    config: AgentEvalRunConfig,
    target: Model | Agent,
) -> RunConfigOnline | RunConfigOnlineModel:
    params = config.params
    if isinstance(target, Model):
        if params is None:
            return RunConfigOnlineModel(parallelism=config.parallelism)
        if isinstance(params, RunConfigOnlineModel):
            return params
        if isinstance(params, RunConfigOnline):
            return RunConfigOnlineModel(**params.model_dump(mode="python"))
        if isinstance(params, RunConfig):
            return RunConfigOnlineModel(**params.model_dump(mode="python"))

    if params is None:
        return RunConfigOnline(parallelism=config.parallelism)
    if isinstance(params, RunConfigOnlineModel):
        return RunConfigOnline(
            **params.model_dump(
                mode="python",
                exclude={"inference", "system_prompt", "reasoning", "structured_output"},
            )
        )
    if isinstance(params, RunConfigOnline):
        return params
    return RunConfigOnline(**params.model_dump(mode="python"))


def _default_prompt_template(target: Model | Agent) -> dict[str, Any] | str:
    # Every default renders against the single canonical task input, ``instruction`` (see
    # ``AgentEvalTask.agent_prompt``); no other input key is special.
    if isinstance(target, GenericAgent):
        # A generic HTTP agent defines its own request entirely through its `body` template, which
        # renders against the task inputs (e.g. `{{ instruction }}`). Pass the task row through
        # unchanged so `body` — not a chat/completions assumption — shapes the payload. See
        # `_resolve_http_agent_invocation`, which renders `body` against this request.
        return "{{ item }}"
    if isinstance(target, Model) and _is_completions_endpoint(target.url):
        return {"prompt": "{{item.instruction}}"}
    return {"messages": [{"role": "user", "content": "{{item.instruction}}"}]}


def _task_row(task: AgentEvalTask) -> dict[str, Any]:
    # The task inputs verbatim, plus the task id. `instruction` is the single canonical input the
    # target is prompted with (see `AgentEvalTask.agent_prompt` and `_default_prompt_template`); no
    # input key is synthesized or aliased here.
    return {**task.inputs, "task_id": task.id}


def _metric_row(task: AgentEvalTask, trial: AgentEvalTrial) -> dict[str, Any]:
    return {
        "task": {
            "id": task.id,
            "intent": task.intent,
            "metadata": task.metadata,
        },
        "inputs": task.inputs,
        # Grader-only ground truth: available to metrics here but never seeded into the agent's
        # workspace (see AgentEvalTask.reference), so a metric can grade against held-out artifacts.
        "reference": task.reference,
        "trial": {
            "id": trial.id,
            "task_id": trial.task_id,
            "status": trial.status.value,
            # How the trial failed, for a metric that grades on it. None when the producer reported no failure.
            "error": trial.error.model_dump(mode="json") if trial.error is not None else None,
            "metadata": trial.metadata,
        },
    }


def _is_completions_endpoint(url: str) -> bool:
    path = urlparse(url).path.rstrip("/")
    return path.endswith("/completions") and not path.endswith("/chat/completions")


def _sdk_version() -> str | None:
    try:
        return package_version("nemo-evaluator-sdk")
    except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
        return None


def _describe_target(
    target: AgentEvalTarget | None,
    params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None,
) -> RunnerInfo:
    """Identify what produced the trials, for the run's provenance.

    Runners identify themselves via the required :meth:`AgentTaskRunner.runner_info`; trials supplied
    directly have no runner.

    Models and agents are described by name *and* the settings they were invoked with — the endpoint
    ``url``, plus the whole ``params`` object (temperature, max_tokens, reasoning effort, system prompt,
    retries, ...). A name alone is not an identity: the same model name served from two different URLs,
    or at two different temperatures, would otherwise record identical provenance. ``params`` is dumped
    whole rather than cherry-picked, because a filtered subset is what bites you later when the omitted
    field turns out to be the one that mattered. It carries no credentials — ``Model.api_key_secret`` is
    a reference on the model, and ``default_headers`` is excluded from serialization.
    """
    if target is None:
        return RunnerInfo(name="imported", kind="imported")
    if isinstance(target, (Model, AgentBase)):
        config: dict[str, Any] = {"url": getattr(target, "url", None)}
        if params is not None:
            config["params"] = params.model_dump(mode="json", exclude_none=True)
        return RunnerInfo(name=target.name, kind="model" if isinstance(target, Model) else "agent", config=config)
    return target.runner_info()


def _collect_runner_aggregate_scores(target: object) -> list[AggregateScore]:
    """The typed subset of a runner's own aggregations, for merging into ``summary.scores``.

    A runner that maps its numbers onto aggregate scores namespaces them under ``runner.<name>.``, so
    they sit alongside the SDK's own without being mistaken for them. That namespace is *enforced*, not
    merely documented: ``RunAggregationsProvider`` is a public extension point, ``summary.scores`` is a
    flat list, and a third-party runner returning ``gym_reward.reward`` would not overwrite the SDK's
    own aggregate but sit next to it under the same name, leaving any lookup to pick one arbitrarily.

    Offending entries are dropped with a warning rather than raised on. This runs *after* ``run_tasks``,
    so raising would sink a completed run — potentially hours of collection — over a naming bug, while
    the numbers themselves remain in the runner's own files inside the bundle.
    """
    if not isinstance(target, RunAggregationsProvider):
        return []
    runner_info = getattr(target, "runner_info", None)  # structurally optional: the protocol is a companion
    runner_name = runner_info().name if callable(runner_info) else None
    prefix = f"runner.{runner_name}." if runner_name else "runner."
    collected: list[AggregateScore] = []
    for score in target.run_aggregate_scores():
        if not score.name.startswith(prefix):
            log.warning(
                "Dropping runner-contributed aggregate %r: RunAggregationsProvider names must be "
                "namespaced %r so an imported figure is never mistaken for one the SDK computed.",
                score.name,
                prefix,
            )
            continue
        collected.append(score)
    return collected


def _new_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"agent-eval-{timestamp}-{uuid.uuid4().hex[:8]}"


def _task_evidence_dir(output_dir: Path, *, index: int, task_id: str) -> Path:
    safe_task_id = _safe_path_component(task_id)
    task_dir = f"{index:06d}-{safe_task_id}" if safe_task_id else f"task-{index:06d}"
    return output_dir / "evidence" / task_dir


def _safe_path_component(value: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in "-_." else "-" for char in value)
    return sanitized.strip("-_.")[:120]
