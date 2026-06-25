# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Publish a completed agent evaluation to Intake.

``publish_to_intake`` is the explicit, post-run consumer of ``AgentEvalResult``
(see AALGO-290). It is **not** a side effect of ``AgentEvaluator.run()`` and
there is no feature flag — optionality is structural: you make the call or you
don't, and the platform client is a required argument.

It references an **existing** Experiment (created by the caller via the platform
Experiments SDK) and never creates one. Per Trial it: POSTs the ATIF trajectory,
resolves the trajectory's root span, then POSTs one evaluator-result per metric
output. All request shapes come from :mod:`nemo_evaluator.intake.mapping`; the
HTTP calls go through the generated platform SDK's ``intake`` resources.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from nemo_evaluator.intake import mapping
from nemo_evaluator.sdk import http_utils
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalTaskScore
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial
from nemo_platform import AsyncNeMoPlatform
from nemo_platform.types.intake.trace_filter_param import TraceFilterParam
from pydantic import BaseModel, ConfigDict, Field

#: Default ceiling on concurrent per-trial publishes.
DEFAULT_MAX_CONCURRENCY = 8


class PublishError(RuntimeError):
    """Raised when publishing cannot complete (e.g. a trajectory's span never resolves)."""


class PublishedTrial(BaseModel):
    """Record of one Trial written to Intake."""

    model_config = ConfigDict(extra="forbid")

    trial_id: str = Field(description="Identifier of the published trial.")
    session_id: str = Field(description="Intake session id minted for the trajectory.")
    span_id: str = Field(description="Resolved root AGENT span id the scores were attached to.")
    evaluator_result_count: int = Field(description="Number of evaluator-result rows written for this trial.")


class PublishReport(BaseModel):
    """Summary of a ``publish_to_intake`` run."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(description="Experiment the results were published under.")
    workspace: str = Field(description="Workspace the writes targeted.")
    run_id: str = Field(description="Source AgentEvalResult run id.")
    published_trials: list[PublishedTrial] = Field(
        default_factory=list, description="Per-trial records of what was written."
    )

    @property
    def trial_count(self) -> int:
        """Number of trials published."""
        return len(self.published_trials)

    @property
    def evaluator_result_count(self) -> int:
        """Total evaluator-result rows written across all trials."""
        return sum(trial.evaluator_result_count for trial in self.published_trials)


async def publish_to_intake(
    result: AgentEvalResult,
    *,
    platform: AsyncNeMoPlatform,
    experiment_id: str,
    workspace: str | None = None,
    agent_name: str = "agent",
    agent_version: str = mapping.DEFAULT_AGENT_VERSION,
    model_name: str | None = None,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
) -> PublishReport:
    """Publish a completed ``AgentEvalResult`` to Intake under an existing Experiment.

    For each trial: POST the ATIF trajectory, resolve its root span, then POST one
    evaluator-result per metric output. Trials are published concurrently up to
    ``max_concurrency``; any HTTP/validation failure propagates to the caller (the
    caller chose to publish). The already-written local bundle is never touched.

    ``experiment_id`` must reference an Experiment that already exists — ATIF ingest
    rejects unknown experiments with HTTP 400. Creating the Experiment/group is a
    separate, caller-side step via the platform Experiments SDK.

    Agent identity (``agent_name``/``agent_version``/``model_name``) is taken as
    arguments because it lives on the run *target*, which ``AgentEvalResult`` does
    not carry (design §3.9 #6).
    """
    resolved_workspace = http_utils.resolve_workspace(platform, workspace, strict=True)

    scores_by_trial: dict[str, list[AgentEvalTaskScore]] = defaultdict(list)
    for score in result.scores:
        scores_by_trial[score.trial_id].append(score)

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _publish_trial(trial: AgentEvalTrial) -> PublishedTrial:
        async with semaphore:
            body = mapping.trial_to_atif_ingest(
                trial,
                run_id=result.run_id,
                experiment_id=experiment_id,
                agent_name=agent_name,
                agent_version=agent_version,
                model_name=model_name,
            )
            body["workspace"] = resolved_workspace
            await platform.intake.ingest.atif.create(**body)

            session_id = mapping.session_id_for(result.run_id, trial.id)
            span_id = await _resolve_root_span_id(platform, workspace=resolved_workspace, session_id=session_id)

            written = 0
            for score in scores_by_trial.get(trial.id, []):
                for row in mapping.score_to_evaluator_results(score, session_id=session_id, span_id=span_id):
                    row["workspace"] = resolved_workspace
                    await platform.intake.evaluator_results.create(**row)
                    written += 1

            return PublishedTrial(
                trial_id=trial.id,
                session_id=session_id,
                span_id=span_id,
                evaluator_result_count=written,
            )

    published = await asyncio.gather(*(_publish_trial(trial) for trial in result.trials))

    return PublishReport(
        experiment_id=experiment_id,
        workspace=resolved_workspace,
        run_id=result.run_id,
        published_trials=list(published),
    )


async def _resolve_root_span_id(platform: AsyncNeMoPlatform, *, workspace: str, session_id: str) -> str:
    """Return the root AGENT span id for a freshly-ingested trajectory (design §3.5, option 1)."""
    trace_filter: TraceFilterParam = {"session_id": session_id}
    async for trace in platform.intake.traces.list(workspace=workspace, filter=trace_filter):
        if trace.root_span_id:
            return trace.root_span_id
    raise PublishError(f"No root span resolved for session {session_id!r} after ATIF ingest")
