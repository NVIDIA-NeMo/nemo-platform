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
from datetime import timedelta

from nemo_evaluator.intake import mapping
from nemo_evaluator.sdk import http_utils
from nemo_evaluator_sdk.agent_eval.metrics import TrialMeasurements
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalTaskScore
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial
from nemo_platform import AsyncNeMoPlatform
from nemo_platform.types.intake.ingest.atif_final_metrics_param import AtifFinalMetricsParam
from nemo_platform.types.intake.trace_filter_param import TraceFilterParam
from pydantic import BaseModel, ConfigDict, Field

#: Default ceiling on concurrent per-trial publishes.
DEFAULT_MAX_CONCURRENCY = 8


class PublishError(RuntimeError):
    """Raised when one or more trials fail to publish (or a span never resolves).

    Carries the partial :class:`PublishReport` of trials that *did* publish, so the
    caller can see what landed before re-running.
    """

    def __init__(self, message: str, *, report: PublishReport | None = None) -> None:
        super().__init__(message)
        self.report = report


class PublishedTrial(BaseModel):
    """Record of one Trial written to Intake."""

    model_config = ConfigDict(extra="forbid")

    trial_id: str = Field(description="Identifier of the published trial.")
    session_id: str = Field(description="Intake session id minted for the trajectory.")
    span_id: str = Field(description="Resolved root AGENT span id the scores were attached to.")
    evaluator_result_count: int = Field(description="Number of evaluator-result rows written for this trial.")


class SkippedScore(BaseModel):
    """A score output omitted from publish because Intake can't represent it yet (cross-team ask X6)."""

    model_config = ConfigDict(extra="forbid")

    trial_id: str = Field(description="Trial whose score output was omitted.")
    name: str = Field(description='"{metric_type}.{output}" of the omitted output.')
    reason: str = Field(description="Why it was omitted (e.g. 'scoring failed', 'non-finite value').")


class PublishReport(BaseModel):
    """Summary of a ``publish_to_intake`` run."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(description="Experiment the results were published under.")
    workspace: str = Field(description="Workspace the writes targeted.")
    run_id: str = Field(description="Source AgentEvalResult run id.")
    published_trials: list[PublishedTrial] = Field(
        default_factory=list, description="Per-trial records of what was written."
    )
    skipped: list[SkippedScore] = Field(
        default_factory=list,
        description="Score outputs omitted because Intake can't represent failed/non-finite scores (cross-team ask X6).",
    )

    @property
    def trial_count(self) -> int:
        """Number of trials published."""
        return len(self.published_trials)

    @property
    def evaluator_result_count(self) -> int:
        """Total evaluator-result rows written across all trials."""
        return sum(trial.evaluator_result_count for trial in self.published_trials)


def _token_final_metrics(measurements: TrialMeasurements) -> AtifFinalMetricsParam | None:
    """Project the trial's recorded token usage onto ATIF ``final_metrics``.

    Intake promotes these root totals onto the trajectory's root span, where the evaluation rollup
    reads them — so publishing them is what makes token counts show up under the Evaluation. Only the
    token fields the trial actually recorded are set; a trial whose harness recorded no usage yields
    ``None`` (no ``final_metrics`` block). Cost is not captured here.
    """
    final_metrics: AtifFinalMetricsParam = {}
    if measurements.prompt_tokens is not None:
        final_metrics["total_prompt_tokens"] = measurements.prompt_tokens
    if measurements.completion_tokens is not None:
        final_metrics["total_completion_tokens"] = measurements.completion_tokens
    if measurements.cache_read_tokens is not None:
        final_metrics["total_cached_tokens"] = measurements.cache_read_tokens
    return final_metrics or None


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
    ``max_concurrency``.

    Publishing is **not atomic** and Intake has no rollback, so a per-trial failure
    must not abort the others: every trial that can land does, and the failures are
    collected and raised together as a :class:`PublishError` (carrying the partial
    report). The evaluation's local bundle is the system of record and is never
    touched, so the caller can re-run ``publish_to_intake`` once the issue is fixed
    to publish the remaining trials.

    Re-publish is **idempotent**: the session id is derived from the run and trial
    (``mapping.session_id_for``), the step timestamp from the run's ``started_at``,
    and each evaluator-result id from its target — so every key Intake replaces on is
    a function of the result, not of when it was published. Re-sending a trial that
    already landed replaces its rows instead of duplicating them, which is what makes
    a worker retry after a partial publish safe.

    ``experiment_id`` must reference an Experiment that already exists — ATIF ingest
    rejects unknown experiments with HTTP 400. Creating the Experiment/group is a
    separate, caller-side step via the platform Experiments SDK.

    Agent identity (``agent_name``/``agent_version``/``model_name``) is taken as
    arguments because it lives on the run *target*, which ``AgentEvalResult`` does
    not carry (design §3.9 #6).
    """
    resolved_workspace = http_utils.resolve_workspace(platform, workspace, strict=True)

    # Required, not defaulted to "now": a fallback would silently reintroduce the
    # publish-time clock that makes re-ingest duplicate rows (see the ingest note on
    # ``mapping.trial_to_atif_ingest``). A real run always sets it; a hand-built result
    # must say when it ran.
    started_at = result.metadata.started_at
    if started_at is None:
        raise PublishError(
            f"Cannot publish run {result.run_id!r}: metadata.started_at is unset, and publishing "
            "without it would write trajectories that duplicate on re-publish."
        )

    scores_by_trial: dict[str, list[AgentEvalTaskScore]] = defaultdict(list)
    for score in result.scores:
        scores_by_trial[score.trial_id].append(score)

    semaphore = asyncio.Semaphore(max_concurrency)
    skipped: list[SkippedScore] = []

    async def _publish_trial(trial: AgentEvalTrial) -> PublishedTrial:
        async with semaphore:
            measurements = TrialMeasurements.from_metadata(trial.metadata)
            # A recorded runtime gives the trajectory a real end so Intake's latency rollup sees the
            # trial's wall-clock duration instead of 0; absent → no window, latency stays unmeasured.
            ended_at = (
                started_at + timedelta(seconds=measurements.runtime_sec)
                if measurements.runtime_sec is not None
                else None
            )
            body = mapping.trial_to_atif_ingest(
                trial,
                run_id=result.run_id,
                experiment_id=experiment_id,
                agent_name=agent_name,
                started_at=started_at,
                agent_version=agent_version,
                model_name=model_name,
                final_metrics=_token_final_metrics(measurements),
                ended_at=ended_at,
            )
            body["workspace"] = resolved_workspace
            await platform.intake.ingest.atif.create(**body)

            session_id = mapping.session_id_for(result.run_id, trial.id)
            span_id = await _resolve_root_span_id(platform, workspace=resolved_workspace, session_id=session_id)

            written = 0
            for score in scores_by_trial.get(trial.id, []):
                rows, omitted = mapping.score_to_evaluator_results(score, session_id=session_id, span_id=span_id)
                for row in rows:
                    row["workspace"] = resolved_workspace
                    await platform.intake.evaluator_results.create(**row)
                    written += 1
                skipped.extend(SkippedScore(trial_id=trial.id, name=item.name, reason=item.reason) for item in omitted)

            return PublishedTrial(
                trial_id=trial.id,
                session_id=session_id,
                span_id=span_id,
                evaluator_result_count=written,
            )

    outcomes = await asyncio.gather(*(_publish_trial(trial) for trial in result.trials), return_exceptions=True)

    published: list[PublishedTrial] = []
    failures: list[tuple[str, BaseException]] = []
    for trial, outcome in zip(result.trials, outcomes, strict=True):
        if isinstance(outcome, PublishedTrial):
            published.append(outcome)
        else:
            failures.append((trial.id, outcome))

    report = PublishReport(
        experiment_id=experiment_id,
        workspace=resolved_workspace,
        run_id=result.run_id,
        published_trials=published,
        skipped=skipped,
    )
    if failures:
        raise PublishError(_publish_failure_message(result, report, failures), report=report)
    return report


def _publish_failure_message(
    result: AgentEvalResult,
    report: PublishReport,
    failures: list[tuple[str, BaseException]],
) -> str:
    """Build an actionable error: what failed, what survives locally, how to recover."""
    # work_dir is where the runtimes wrote trial evidence, NOT a bundle location: a bundle exists only
    # if the caller chose to persist(), and persist() can be pointed elsewhere. Say only what is true.
    location = (
        f"still in memory, and the run's trial evidence is under {result.work_dir}"
        if result.work_dir is not None
        else "still in memory and have not been written to disk (call result.persist() to keep them)"
    )
    detail = "\n  ".join(f"{trial_id}: {type(error).__name__}: {error}" for trial_id, error in failures)
    return (
        f"publish_to_intake: {len(failures)} of {len(result.trials)} trial(s) failed to publish "
        f"({report.trial_count} succeeded). The evaluation results are {location}; re-run "
        f"publish_to_intake(result, ...) once the issue is resolved to publish the rest.\n"
        f"Failed trials:\n  {detail}"
    )


async def _resolve_root_span_id(platform: AsyncNeMoPlatform, *, workspace: str, session_id: str) -> str:
    """Return the root AGENT span id for a freshly-ingested trajectory (design §3.5, option 1)."""
    trace_filter: TraceFilterParam = {"session_id": session_id}
    async for trace in platform.intake.traces.list(workspace=workspace, filter=trace_filter):
        if trace.root_span_id:
            return trace.root_span_id
    raise PublishError(f"No root span resolved for session {session_id!r} after ATIF ingest")
