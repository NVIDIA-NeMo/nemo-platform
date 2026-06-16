# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standalone agent evaluation orchestration."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from logging import getLogger
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import httpx
import nemo_evaluator_sdk.inference as inference
from nemo_evaluator_sdk.agent_eval.dashboard import write_dashboard
from nemo_evaluator_sdk.agent_eval.persistence import persist_run
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.scores import (
    AgentEvalDiagnostic,
    AgentEvalDiagnosticSeverity,
    AgentEvalScoreStatus,
    AgentEvalTaskScore,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import (
    AgentEvalTarget,
    AgentEvalTrial,
    AgentEvalTrialStatus,
    AgentOutput,
    AgentTaskRunner,
)
from nemo_evaluator_sdk.agent_inference import (
    AgentInferenceFn,
    make_agent_inference_request,
    new_agent_inference_client,
)
from nemo_evaluator_sdk.execution.metric_execution import generate_online_sample, run_sync
from nemo_evaluator_sdk.execution.samples import build_metric_input
from nemo_evaluator_sdk.inference import InferenceFn
from nemo_evaluator_sdk.metrics.protocol import Metric, validate_metric_result
from nemo_evaluator_sdk.metrics.utils import metric_type_name
from nemo_evaluator_sdk.values import Agent, Model, RunConfig, RunConfigOnline, RunConfigOnlineModel
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor
from openai import AsyncOpenAI

log = getLogger(__name__)


class AgentEvaluator:
    """Run stored-trial or live-target agent evaluations.

    The online inference seam (an optional ``inference_fn``, transport ``client``, and
    ``default_headers``) is injected on the evaluator instance rather than the run config,
    because these are runtime transport concerns rather than declarative run settings. A
    single ``inference_fn``/``client`` pair serves both model and agent targets; leave them
    unset to let the evaluator build a default client for the resolved target type.
    """

    def __init__(
        self,
        *,
        inference_fn: InferenceFn | AgentInferenceFn | None = None,
        client: AsyncOpenAI | httpx.AsyncClient | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.inference_fn = inference_fn
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
        benchmark = {**_benchmark_metadata(task_list), **runtime_config.benchmark}
        result = AgentEvalResult(
            run_id=run_id,
            tasks=task_list,
            trials=trial_list,
            scores=scores,
            summary=AgentEvalSummary.from_scores(scores, tasks=task_list),
            benchmark=benchmark,
        )

        if runtime_config.output_dir is not None:
            result = _persist_with_optional_dashboard(result, runtime_config.output_dir, runtime_config.write_dashboard)
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
                            details={"trial_status": trial.status.value},
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
        if not isinstance(target, (Model, Agent)):
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
                    try:
                        sample = await _generate_sample(
                            target=target,
                            row=_task_row(task),
                            index=index,
                            prompt_template=prompt_template,
                            params=params,
                            inference_fn=self.inference_fn,
                            client=client,
                            default_headers=self.default_headers,
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
) -> dict[str, Any]:
    # InferenceFn and AgentInferenceFn are callable protocols, so isinstance cannot discriminate
    # the injected fn; narrow it per target type with a cast (matching execution/benchmark_execution).
    # The transport client is a real class union, so isinstance narrowing is enough there.
    if isinstance(target, Model):
        model_params = cast(RunConfigOnlineModel, params)
        preprocess_hooks, postprocess_hooks = inference.new_hooks(model_params, model_format=target.format)
        model_inference_fn = (
            cast(InferenceFn, inference_fn) if inference_fn is not None else inference.make_inference_request
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
        )

    agent_inference_fn = (
        cast(AgentInferenceFn, inference_fn) if inference_fn is not None else make_agent_inference_request
    )
    return await generate_online_sample(
        target=target,
        row=row,
        index=index,
        prompt_template=prompt_template,
        params=params,
        inference_fn=agent_inference_fn,
        client=client if isinstance(client, httpx.AsyncClient) else None,
        default_headers=default_headers,
    )


def _trial_from_sample(task: AgentEvalTask, target: Model | Agent, sample: dict[str, Any]) -> AgentEvalTrial:
    output_text = sample.get("output_text")
    if "trajectory" in sample:
        trace = EvidenceDescriptor(kind="trace", format="json", data=sample["trajectory"])
    else:
        trace = EvidenceDescriptor(kind="sdk_online_generation", data={"task_id": task.id, "target": target.name})

    return AgentEvalTrial(
        id=f"{task.id}:{target.name}",
        task_id=task.id,
        status=AgentEvalTrialStatus.COMPLETED,
        output=AgentOutput(
            output_text=output_text if isinstance(output_text, str) else None,
            response=sample.get("response"),
            metadata={
                key: value for key, value in sample.items() if key not in {"output_text", "response", "trajectory"}
            },
        ),
        evidence=CandidateEvidence(descriptors={"trace": trace}),
        metadata={
            "model_id": target.name,
            "target_name": target.name,
            "generated": True,
        },
    )


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


def _default_prompt_template(target: Model | Agent) -> dict[str, Any]:
    if isinstance(target, Model) and _is_completions_endpoint(target.url):
        return {"prompt": "{{item.prompt}}"}
    return {"messages": [{"role": "user", "content": "{{item.prompt}}"}]}


def _task_row(task: AgentEvalTask) -> dict[str, Any]:
    return {
        **task.inputs,
        "task_id": task.id,
        "prompt": task.inputs.get("prompt") or task.inputs.get("instruction") or task.intent,
    }


def _metric_row(task: AgentEvalTask, trial: AgentEvalTrial) -> dict[str, Any]:
    return {
        "task": {
            "id": task.id,
            "intent": task.intent,
            "metadata": task.metadata,
        },
        "inputs": task.inputs,
        "trial": {
            "id": trial.id,
            "task_id": trial.task_id,
            "status": trial.status.value,
            "metadata": trial.metadata,
        },
    }


def _is_completions_endpoint(url: str) -> bool:
    path = urlparse(url).path.rstrip("/")
    return path.endswith("/completions") and not path.endswith("/chat/completions")


def _benchmark_metadata(tasks: list[AgentEvalTask]) -> dict[str, Any]:
    benchmarks = sorted({str(task.metadata.get("benchmark")) for task in tasks if task.metadata.get("benchmark")})
    if not benchmarks:
        return {}
    return {"benchmark": benchmarks[0] if len(benchmarks) == 1 else benchmarks}


def _persist_with_optional_dashboard(
    result: AgentEvalResult,
    output_dir: Path,
    write_html: bool,
) -> AgentEvalResult:
    path = Path(output_dir)
    dashboard_path = None
    if write_html:
        dashboard_path = write_dashboard(result.model_copy(update={"output_dir": path}), path / "report.html")
    return persist_run(result.model_copy(update={"output_dir": path, "dashboard_path": dashboard_path}), path)


def _new_run_id() -> str:
    return f"agent-eval-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
