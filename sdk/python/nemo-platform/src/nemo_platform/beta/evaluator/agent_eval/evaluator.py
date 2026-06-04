# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standalone agent evaluation orchestration."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from pydantic import BaseModel

import nemo_platform.beta.evaluator.inference as inference
from nemo_platform.beta.evaluator.agent_eval.dashboard import write_dashboard
from nemo_platform.beta.evaluator.agent_eval.persistence import persist_run
from nemo_platform.beta.evaluator.agent_eval.types import (
    AgentAttemptRuntime,
    AgentEvalAttempt,
    AgentEvalRunConfig,
    AgentEvalRunResult,
    AgentEvalSummary,
    AgentEvalTarget,
    AgentEvalTask,
    AgentEvalTaskResult,
    AgentOutput,
    mean_numeric,
)
from nemo_platform.beta.evaluator.agent_inference import make_agent_inference_request, new_agent_inference_client
from nemo_platform.beta.evaluator.execution.metric_execution import generate_online_sample, run_sync
from nemo_platform.beta.evaluator.execution.samples import build_metric_input
from nemo_platform.beta.evaluator.metrics.protocol import Metric, MetricOutput, validate_metric_result
from nemo_platform.beta.evaluator.metrics.utils import metric_type_name
from nemo_platform.beta.evaluator.values import Agent, Model, RunConfig, RunConfigOnline, RunConfigOnlineModel
from nemo_platform.beta.evaluator.values.evidence import CandidateEvidence, EvidenceDescriptor


class AgentEvaluator:
    """Run stored-attempt or live-target agent evaluations."""

    async def run(
        self,
        *,
        tasks: Sequence[AgentEvalTask],
        attempts: Sequence[AgentEvalAttempt] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalRunResult:
        """Evaluate imported attempts or generate live attempts before scoring.

        Exactly one of ``attempts`` or ``target`` must be provided.
        """
        resolved_config = config or AgentEvalRunConfig()
        task_list = list(tasks)
        if (attempts is not None) == (target is not None):
            raise ValueError("provide exactly one of attempts or target")
        if not task_list:
            raise ValueError("at least one task is required")

        run_id = resolved_config.run_id or _new_run_id()
        attempt_list = (
            list(attempts)
            if attempts is not None
            else await self._generate_attempts(
                tasks=task_list,
                target=cast(AgentEvalTarget, target),
                config=resolved_config,
            )
        )
        results = await self._score_attempts(tasks=task_list, attempts=attempt_list, config=resolved_config)
        benchmark = {"run_id": run_id, **_benchmark_metadata(task_list), **resolved_config.benchmark}
        result = AgentEvalRunResult(
            run_id=run_id,
            tasks=task_list,
            attempts=attempt_list,
            results=results,
            summary=summarize_results(results),
            benchmark=benchmark,
        )

        if resolved_config.output_dir is not None:
            result = _persist_with_optional_dashboard(
                result, resolved_config.output_dir, resolved_config.write_dashboard
            )
        return result

    def run_sync(
        self,
        *,
        tasks: Sequence[AgentEvalTask],
        attempts: Sequence[AgentEvalAttempt] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalRunResult:
        """Synchronous bridge for :meth:`run`."""
        return run_sync(lambda: self.run(tasks=tasks, attempts=attempts, target=target, config=config))

    async def _score_attempts(
        self,
        *,
        tasks: list[AgentEvalTask],
        attempts: list[AgentEvalAttempt],
        config: AgentEvalRunConfig,
    ) -> list[AgentEvalTaskResult]:
        tasks_by_id = {task.id: task for task in tasks}
        task_index_by_id = {task.id: index for index, task in enumerate(tasks)}
        attempts_by_task: dict[str, list[AgentEvalAttempt]] = defaultdict(list)
        for attempt in attempts:
            if attempt.task_id not in tasks_by_id:
                raise ValueError(f"attempt {attempt.id!r} references unknown task {attempt.task_id!r}")
            if attempt.status == "failed":
                raise ValueError(f"attempt {attempt.id!r} is failed")
            attempts_by_task[attempt.task_id].append(attempt)

        for task in tasks:
            if not task.metrics:
                raise ValueError(f"task {task.id!r} does not declare any metrics")

        semaphore = asyncio.Semaphore(config.parallelism)

        async def guarded_score(task: AgentEvalTask, attempt: AgentEvalAttempt, metric: Metric) -> AgentEvalTaskResult:
            async with semaphore:
                return await _score_metric(
                    task=task,
                    attempt=attempt,
                    metric=metric,
                    row_index=task_index_by_id[task.id],
                )

        return await asyncio.gather(
            *[
                guarded_score(task, attempt, metric)
                for task in tasks
                for attempt in attempts_by_task.get(task.id, [])
                for metric in task.metrics
            ]
        )

    async def _generate_attempts(
        self,
        *,
        tasks: list[AgentEvalTask],
        target: AgentEvalTarget,
        config: AgentEvalRunConfig,
    ) -> list[AgentEvalAttempt]:
        if isinstance(target, AgentAttemptRuntime):
            return list(await target.run_tasks(tasks, config=config))

        generation_target = cast(Model | Agent, target)
        params = _resolve_live_params(config, generation_target)
        prompt_template = config.prompt_template or _default_prompt_template(generation_target)
        semaphore = asyncio.Semaphore(params.parallelism)

        client: Any | None = None
        close_client = None
        if isinstance(generation_target, Model) and config.model_client is None and config.model_inference_fn is None:
            client = inference.new_inference_client(generation_target)
            close_client = client.close
        elif isinstance(generation_target, Agent) and config.agent_client is None and config.agent_inference_fn is None:
            client = new_agent_inference_client()
            close_client = client.aclose

        try:

            async def generate_one(index: int, task: AgentEvalTask) -> AgentEvalAttempt:
                async with semaphore:
                    sample = await _generate_sample(
                        target=generation_target,
                        row=_task_row(task),
                        index=index,
                        prompt_template=prompt_template,
                        params=params,
                        config=config,
                        client=client,
                    )
                    return _attempt_from_sample(task, generation_target, sample)

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
    config: AgentEvalRunConfig,
    client: Any | None,
) -> dict[str, Any]:
    if isinstance(target, Model):
        model_params = cast(RunConfigOnlineModel, params)
        preprocess_hooks, postprocess_hooks = inference.new_hooks(model_params, model_format=target.format)
        return await generate_online_sample(
            target=target,
            row=row,
            index=index,
            prompt_template=prompt_template,
            params=model_params,
            inference_fn=config.model_inference_fn or inference.make_inference_request,
            client=config.model_client or client,
            preprocess_hooks=preprocess_hooks,
            postprocess_hooks=postprocess_hooks,
            default_headers=config.default_headers,
        )

    return await generate_online_sample(
        target=target,
        row=row,
        index=index,
        prompt_template=prompt_template,
        params=params,
        inference_fn=config.agent_inference_fn or make_agent_inference_request,
        client=config.agent_client or client,
        default_headers=config.default_headers,
    )


def _attempt_from_sample(task: AgentEvalTask, target: Model | Agent, sample: dict[str, Any]) -> AgentEvalAttempt:
    output_text = sample.get("output_text")
    trace = None
    if "trajectory" in sample:
        trace = EvidenceDescriptor(kind="trace", format="json", data=sample["trajectory"])
    else:
        trace = EvidenceDescriptor(kind="sdk_online_generation", data={"task_id": task.id, "target": target.name})

    return AgentEvalAttempt(
        id=f"{task.id}:{target.name}",
        task_id=task.id,
        output=AgentOutput(
            text=output_text if isinstance(output_text, str) else None,
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


async def _score_metric(
    *,
    task: AgentEvalTask,
    attempt: AgentEvalAttempt,
    metric: Metric,
    row_index: int,
) -> AgentEvalTaskResult:
    output_spec = metric.output_spec()
    metric_result = validate_metric_result(
        await metric.compute_scores(
            build_metric_input(_metric_row(task, attempt), _attempt_sample(attempt), row_index)
        ),
        output_spec,
    )
    return AgentEvalTaskResult(
        task_id=task.id,
        attempt_id=attempt.id,
        metric_type=metric_type_name(metric),
        outputs=metric_result.outputs,
        metadata={
            "row_index": row_index,
            "attempt_metadata": attempt.metadata,
        },
    )


def _attempt_sample(attempt: AgentEvalAttempt) -> dict[str, Any]:
    if attempt.output is None:
        return {}
    sample = {
        **attempt.metadata,
        **attempt.output.metadata,
    }
    if attempt.output.output_text is not None:
        sample["output_text"] = attempt.output.output_text
    if attempt.output.response is not None:
        sample["response"] = attempt.output.response
    if attempt.evidence is not None:
        sample["evidence"] = attempt.evidence
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
        "prompt": task.inputs.get("prompt") or task.intent,
    }


def _metric_row(task: AgentEvalTask, attempt: AgentEvalAttempt) -> dict[str, Any]:
    return {
        "task": {
            "id": task.id,
            "intent": task.intent,
            "metadata": task.metadata,
        },
        "inputs": task.inputs,
        "attempt": {
            "id": attempt.id,
            "task_id": attempt.task_id,
            "status": attempt.status,
            "metadata": attempt.metadata,
        },
    }


def summarize_results(results: Sequence[AgentEvalTaskResult]) -> AgentEvalSummary:
    metric_values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for result in results:
        for output in result.outputs:
            value = _numeric_value(output)
            if value is not None:
                metric_values[result.metric_type][output.name].append(value)

    metric_scores: dict[str, dict[str, float]] = {}
    for metric_type, outputs in sorted(metric_values.items()):
        output_scores = {
            output_name: score
            for output_name, values in sorted(outputs.items())
            if (score := mean_numeric(values)) is not None
        }
        if output_scores:
            metric_scores[metric_type] = output_scores

    rollup_values = [score for output_scores in metric_scores.values() for score in output_scores.values()]
    return AgentEvalSummary(
        overall_score=mean_numeric(rollup_values),
        metric_scores=metric_scores,
        task_count=len({result.task_id for result in results}),
        attempt_count=len({result.attempt_id for result in results}),
        result_count=len(results),
    )


def _numeric_value(output: MetricOutput) -> float | None:
    value = output.value
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, BaseModel):
        root = getattr(value, "root", None)
        if isinstance(root, bool):
            return None
        if isinstance(root, int | float):
            return float(root)
    return None


def _is_completions_endpoint(url: str) -> bool:
    path = urlparse(url).path.rstrip("/")
    return path.endswith("/completions") and not path.endswith("/chat/completions")


def _benchmark_metadata(tasks: list[AgentEvalTask]) -> dict[str, Any]:
    benchmarks = sorted({str(task.metadata.get("benchmark")) for task in tasks if task.metadata.get("benchmark")})
    if not benchmarks:
        return {}
    return {"benchmark": benchmarks[0] if len(benchmarks) == 1 else benchmarks}


def _persist_with_optional_dashboard(
    result: AgentEvalRunResult,
    output_dir: Path,
    write_html: bool,
) -> AgentEvalRunResult:
    path = Path(output_dir)
    dashboard_path = None
    if write_html:
        dashboard_path = write_dashboard(result.model_copy(update={"output_dir": path}), path / "report.html")
    return persist_run(result.model_copy(update={"output_dir": path, "dashboard_path": dashboard_path}), path)


def _new_run_id() -> str:
    return f"agent-eval-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
