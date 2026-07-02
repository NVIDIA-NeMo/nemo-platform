# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK-backed agent-evaluation job for the evaluator plugin.

Runs :class:`AgentEvaluator` over a set of tasks against a Model/Agent endpoint
or an agent runner (e.g. Codex CLI), producing an ``AgentEvalResult`` (trials +
per-trial scores + summary). The row-based counterpart is
:class:`~nemo_evaluator.jobs.evaluate.EvaluateJob`.

Per-task metrics may be given inline or as references to stored metrics;
references are resolved into inline metrics during ``to_spec`` via the shared
:mod:`nemo_evaluator.jobs.metric_resolution` helper. The full result bundle (trials +
scores + summary) is persisted as job artifacts, and a concise, queryable result entity
is written via :func:`~nemo_evaluator.jobs.result_persistence.persist_agent_eval_result`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlsplit

from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.jobs.agent_compiler import compile_agent_eval_job
from nemo_evaluator.jobs.agent_spec import (
    AgentEvalInputSpec,
    AgentEvalSpec,
    AgentEvalTaskSpec,
    AgentTarget,
    CodexRunnerTarget,
    ModelTarget,
    Target,
)
from nemo_evaluator.jobs.metric_resolution import resolve_metrics_to_inline, to_runtime_bundle
from nemo_evaluator.jobs.result_persistence import persist_agent_eval_result
from nemo_evaluator.shared.metric_bundles.bundles import unbundle_metric
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.persistence import persist_run
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult
from nemo_evaluator_sdk.agent_eval.runtimes.codex.runtime import CodexCliAgentRuntime
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTarget
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.values import RunConfigOnline, RunConfigOnlineModel
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from pydantic import BaseModel

logger = logging.getLogger(__name__)

#: Job-result artifact names + the on-disk bundle directory.
DEFAULT_RESULT_NAME = "agent-eval-results"
SUMMARY_RESULT_NAME = "summary"
AGENT_BUNDLE_DIR = "agent-eval"
SUMMARY_FILE_NAME = "summary.json"

#: Identity headers forwarded from the job's platform SDK to online inference so a platform-routed
#: target authenticates as the job's principal (``get_task_sdk`` emits these). An explicit allowlist
#: — not an ``X-NMP-*`` prefix match — so trace/metadata headers the SDK may add later never leak to
#: a third-party model/agent endpoint. ``X-NMP-Principal-Id`` is the header the PDP authorizes on
#: (verified against an auth-enabled platform); the rest carry the delegated on-behalf-of identity.
_FORWARDED_IDENTITY_HEADERS = frozenset(
    {
        "X-NMP-Principal-Id",
        "X-NMP-Principal-Email",
        "X-NMP-Principal-Groups",
        "X-NMP-Principal-On-Behalf-Of",
        "X-NMP-Principal-On-Behalf-Of-Email",
        "X-NMP-Principal-On-Behalf-Of-Groups",
        "X-NMP-Internal",
    }
)


@dataclass(frozen=True)
class AgentEvalResultFiles:
    """Filesystem layout for a persisted agent-eval bundle."""

    bundle_dir: Path
    summary: Path


def _runtime_metric(metric: MetricInline) -> Metric:
    """Reconstruct a runtime ``Metric`` from its inline bundle DTO."""
    return unbundle_metric(to_runtime_bundle(metric))


def _to_runtime_task(task: AgentEvalTaskSpec) -> AgentEvalTask:
    """Reconstruct a runtime ``AgentEvalTask`` (live metrics) from its canonical DTO."""
    return AgentEvalTask(
        id=task.id,
        intent=task.intent,
        inputs=task.inputs,
        metrics=[_runtime_metric(metric) for metric in task.metrics],
        views=task.views,
        metadata=task.metadata,
    )


class AgentEvalJob(NemoJob):
    """Run agent evaluation (``AgentEvaluator``) over tasks against a Model/Agent endpoint or runner."""

    name: ClassVar[str] = "agent-evaluate"
    description: ClassVar[str] = "Run agent evaluation over tasks against a model, agent, or runner."
    container: ClassVar[str] = "cpu-tasks"
    input_spec_schema: ClassVar[type[BaseModel] | None] = AgentEvalInputSpec
    spec_schema: ClassVar[type[BaseModel] | None] = AgentEvalSpec
    job_collection_path: ClassVar[str | None] = "/agent-evaluate/jobs"

    @classmethod
    async def to_spec(
        cls,
        input_spec: BaseModel,
        *,
        workspace: str,
        entity_client: object,
        async_sdk: AsyncNeMoPlatform | None,
        is_local: bool,
    ) -> BaseModel:
        """Resolve each task's metric references into inline metrics for the canonical spec."""
        del is_local
        submit_spec = (
            input_spec.model_copy(deep=True)
            if isinstance(input_spec, AgentEvalInputSpec)
            else AgentEvalInputSpec.model_validate_json(input_spec.model_dump_json())
        )
        resolved_tasks: list[AgentEvalTaskSpec] = []
        for task in submit_spec.tasks:
            metrics = await resolve_metrics_to_inline(
                task.metrics,
                workspace=workspace,
                entity_client=entity_client,
                async_sdk=async_sdk,
            )
            resolved_tasks.append(
                AgentEvalTaskSpec(
                    id=task.id,
                    intent=task.intent,
                    inputs=task.inputs,
                    metrics=metrics,
                    views=task.views,
                    metadata=task.metadata,
                )
            )
        return AgentEvalSpec(
            tasks=resolved_tasks,
            target=submit_spec.target,
            trials=submit_spec.trials,
            max_concurrent_tasks=submit_spec.max_concurrent_tasks,
            fail_fast=submit_spec.fail_fast,
            benchmark=submit_spec.benchmark,
        )

    @classmethod
    async def compile(
        cls,
        *,
        workspace: str,
        spec: BaseModel,
        entity_client: object,
        job_name: str | None,
        async_sdk: AsyncNeMoPlatform | None,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        """Compile the canonical spec into a plugin-native agent-evaluation job."""
        del workspace, entity_client, job_name, async_sdk, options
        canonical_spec = spec if isinstance(spec, AgentEvalSpec) else AgentEvalSpec.model_validate(spec.model_dump())
        return compile_agent_eval_job(canonical_spec, profile=profile)

    @staticmethod
    def _endpoint_url(target: Target | None) -> str | None:
        """The HTTP endpoint a Model/Agent target generates against; ``None`` for a runner/offline."""
        if isinstance(target, ModelTarget):
            return str(target.model.url)
        if isinstance(target, AgentTarget):
            return str(target.agent.url)
        return None

    @staticmethod
    def _is_platform_routed(url: str, platform: NeMoPlatform | AsyncNeMoPlatform) -> bool:
        """True when *url* points at the platform itself (e.g. an IGW route under its base URL).

        Compared by origin (host + port): the platform serves IGW under its own base URL, so a target
        whose host matches is in-platform. A third-party endpoint the user configured does not match —
        and must not receive the job's on-behalf-of identity (id/email/groups is PII).
        """
        target, base = urlsplit(url), urlsplit(str(platform.base_url))
        return (target.hostname, target.port) == (base.hostname, base.port)

    @staticmethod
    def _build_evaluator(platform: NeMoPlatform | AsyncNeMoPlatform | None, target: Target | None) -> AgentEvaluator:
        """Construct the evaluator, forwarding the job's platform identity to online inference.

        Online generation against a *platform-routed* Model/Agent target must act as the job's
        principal, so the task SDK's identity headers (:data:`_FORWARDED_IDENTITY_HEADERS`, e.g. the
        service principal id and on-behalf-of) are forwarded to the evaluator's inference client.

        Forwarding is gated on the target being platform-routed (:meth:`_is_platform_routed`): a
        third-party endpoint (or a runner with no HTTP endpoint) gets *no* identity headers, so the
        delegated identity — which includes the user's email and group PII — never leaves the platform.
        External providers authenticate via their own api key and don't need it anyway. Isolated so
        tests can inject a fake inference seam.

        ``platform`` is the SDK handle injected into ``run`` — a real ``NeMoPlatform`` in a submitted
        job (built by ``get_task_sdk``, threading ``NMP_PRINCIPAL`` as on-behalf-of). It is ``None``
        only for a platformless local run (e.g. offline ``run_local``), which has no identity to
        forward.

        NOTE: bearer-token auth for platform routes in an auth-enabled deployment is not yet
        forwarded (the local/internal path relies on the ``X-NMP-*`` identity headers); see
        AALGO-297 follow-ups.
        """
        identity_headers: dict[str, str] = {}
        url = AgentEvalJob._endpoint_url(target)
        if platform is not None and url is not None and AgentEvalJob._is_platform_routed(url, platform):
            identity_headers = {
                key: value
                for key, value in platform.default_headers.items()
                if key in _FORWARDED_IDENTITY_HEADERS and isinstance(value, str)
            }
        return AgentEvaluator(default_headers=identity_headers or None)

    @staticmethod
    def _resolve_target(
        target: Target | None, ctx: JobContext
    ) -> tuple[AgentEvalTarget | None, str | dict[str, Any] | None, RunConfigOnline | RunConfigOnlineModel | None]:
        """Resolve a target spec to ``(runtime target, prompt_template, params)`` for the SDK run config.

        Endpoint targets carry their own request config; a runner is instantiated to its runtime and
        shapes its own request, so it contributes neither a prompt template nor inference params.
        """
        if isinstance(target, ModelTarget):
            return target.model, target.prompt_template, target.params or RunConfigOnlineModel()
        if isinstance(target, AgentTarget):
            return target.agent, None, target.params or RunConfigOnline()
        if isinstance(target, CodexRunnerTarget):
            runtime = CodexCliAgentRuntime(
                model=target.model,
                timeout_s=target.timeout_s,
                work_root=ctx.storage.persistent / "codex",
            )
            return runtime, None, None
        return None, None, None

    @staticmethod
    def _write_result_files(result: AgentEvalResult, persistent_dir: Path) -> AgentEvalResultFiles:
        """Persist the run bundle (trials/scores/tasks/summary) under the job's storage."""
        bundle_dir = persistent_dir / AGENT_BUNDLE_DIR
        persist_run(result, bundle_dir)
        return AgentEvalResultFiles(bundle_dir=bundle_dir, summary=bundle_dir / SUMMARY_FILE_NAME)

    def run(
        self,
        config: dict,
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
        async_sdk: AsyncNeMoPlatform | None = None,
    ) -> dict:
        """Run the agent evaluation locally and persist its result bundle as artifacts."""
        spec = AgentEvalSpec.model_validate(config)
        tasks = [_to_runtime_task(task) for task in spec.tasks]
        target, prompt_template, params = self._resolve_target(spec.target, ctx)
        run_config = AgentEvalRunConfig(
            params=params,
            prompt_template=prompt_template,
            parallelism=spec.max_concurrent_tasks,
            benchmark=spec.benchmark,
            fail_fast=spec.fail_fast,
            write_dashboard=False,
        )
        # `run` may be injected a sync `sdk` (submitted jobs, via get_task_sdk) and/or an
        # `async_sdk`; forward whichever identity is present, preferring async when both are — the
        # same precedence the SDK-backed dataset resolver uses.
        evaluator = self._build_evaluator(async_sdk or sdk, spec.target)
        result = evaluator.run_sync(tasks=tasks, trials=spec.trials, target=target, config=run_config)

        files = self._write_result_files(result, ctx.storage.persistent)
        artifact = ctx.results.save(DEFAULT_RESULT_NAME, files.bundle_dir)
        ctx.results.save(SUMMARY_RESULT_NAME, files.summary)

        # Persist the queryable result record (aggregates + coverage); the full bundle (trials) lives
        # in the fileset referenced by `artifact`. Best-effort: the authoritative output (bundle +
        # summary artifacts) is already saved above, so a persistence failure must not fail an
        # otherwise-successful eval — log and continue.
        try:
            persist_agent_eval_result(
                result, target=spec.target, ctx=ctx, bundle_ref=artifact.artifact_url, async_sdk=async_sdk
            )
        except Exception:
            logger.warning(
                "Failed to persist agent-eval result record; the result bundle artifact is unaffected",
                exc_info=True,
            )

        return {"status": "completed", "artifact": artifact.model_dump()}
