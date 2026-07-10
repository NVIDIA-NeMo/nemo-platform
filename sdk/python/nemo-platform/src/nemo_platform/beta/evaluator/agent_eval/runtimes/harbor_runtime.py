# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Harbor-backed :class:`AgentTaskRunner` for the agent-eval pipeline.

Harbor already runs trials in (Docker) environments, retries them, and writes a
documented results tree: one ``<task>__<hash>/result.json`` per trial under the
job directory. This runtime adapts that tree into SDK :class:`AgentEvalTrial`
objects so an :class:`AgentEvaluator` can score and report Harbor runs through the
same seam as any other runtime.

The module is intentionally dependency-light: it does **not** import ``harbor``.
Job *execution* is injected as the ``run_job`` callback (the caller owns Harbor's
``JobConfig`` build, the import lock, and ``docker network prune`` cleanup), and
trial *adaptation* only reads Harbor's on-disk ``result.json`` files. This mirrors
how :class:`CallableAgentTaskRunner` stays free of any agent SDK, and matches the
design note that Harbor-runtime concerns live with the caller, not the SDK.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from nemo_platform.beta.evaluator.agent_eval.results import AgentEvalResult
from nemo_platform.beta.evaluator.agent_eval.scores import AgentEvalScoreStatus
from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_platform.beta.evaluator.agent_eval.trials import (
    AgentEvalTrial,
    AgentEvalTrialStatus,
    AgentOutput,
    standard_evidence_descriptors,
)
from nemo_platform.beta.evaluator.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_platform.beta.evaluator.values.evidence import CandidateEvidence

logger = logging.getLogger(__name__)

# Default reward key inside Harbor's ``verifier_result.rewards`` mapping.
DEFAULT_REWARD_KEY = "reward"

RunJob = Callable[[], Awaitable[None]]


class HarborRewardMetric:
    """Score the verifier reward Harbor stamped onto trial metadata.

    Reads ``reward`` from the candidate metadata (populated by
    :func:`build_trials_from_job_dir`); a trial with no verifier reward scores
    ``0.0``. This is the Harbor analogue of the example ``VerifierRewardMetric``
    — a reward-off-metadata scorer.
    """

    def __init__(self, *, output_name: str = "reward", metric_type: str = "harbor_reward") -> None:
        self._output_name = output_name
        self._metric_type = metric_type

    @property
    def type(self) -> str:
        return self._metric_type

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score(self._output_name)]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        reward = input.candidate.metadata.get("reward")
        value = float(reward) if reward is not None else 0.0
        return MetricResult(outputs=[MetricOutput(name=self._output_name, value=value)])


class HarborAgentTaskRunner:
    """An :class:`AgentTaskRunner` that runs a Harbor job, then adapts its results.

    ``run_job`` executes the Harbor job (the caller builds the ``JobConfig`` and
    owns any locking/cleanup); it is awaited once before the job directory is
    read. Pass ``run_job=None`` to adapt an already-completed job directory
    (offline re-scoring). ``job_dir`` is the directory Harbor writes its
    per-trial ``<task>__<hash>/result.json`` files into.
    """

    def __init__(
        self,
        *,
        job_dir: str | Path,
        run_job: RunJob | None = None,
        reward_key: str = DEFAULT_REWARD_KEY,
    ) -> None:
        self._job_dir = Path(job_dir)
        self._run_job = run_job
        self._reward_key = reward_key

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalTrial]:
        """Execute the Harbor job (if supplied) and return one trial per Harbor trial."""
        if self._run_job is not None:
            await self._run_job()
        return build_trials_from_job_dir(self._job_dir, tasks, reward_key=self._reward_key)


def build_trials_from_job_dir(
    job_dir: str | Path,
    tasks: Sequence[AgentEvalTask],
    *,
    reward_key: str = DEFAULT_REWARD_KEY,
) -> list[AgentEvalTrial]:
    """Adapt Harbor's per-trial ``result.json`` files into :class:`AgentEvalTrial` objects.

    Reads ``<job_dir>/<task>__<hash>/result.json`` (the top-level aggregate
    ``<job_dir>/result.json`` is skipped because it is not nested). Each Harbor
    trial whose ``task_name`` matches a supplied task id becomes one trial, with
    the verifier reward, exception type, and token/cost measurements stamped on
    ``metadata`` and standard evidence descriptors pointing at the trial's
    on-disk artifacts.
    """
    job_path = Path(job_dir)
    known_task_ids = {task.id for task in tasks}
    trials: list[AgentEvalTrial] = []
    for result_path in sorted(job_path.glob("*/result.json")):
        try:
            data = json.loads(result_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping unreadable Harbor trial result %s: %s", result_path, exc)
            continue
        task_id = data.get("task_name")
        if task_id not in known_task_ids:
            # Trial for a task we weren't asked to score (e.g. a wider dataset run).
            continue
        trials.append(_trial_from_harbor_result(result_path.parent, data, reward_key=reward_key))

    # Surface tasks that produced no trial loudly: a mis-pointed job_dir or a
    # crashed run would otherwise silently score fewer tasks than requested.
    missing = known_task_ids - {trial.task_id for trial in trials}
    if missing:
        logger.warning("No Harbor trial result found for %d requested task(s): %s", len(missing), sorted(missing))
    if not trials:
        logger.warning(
            "No Harbor trial results under %s matched the requested tasks; nothing will be scored.", job_path
        )
    return trials


def _trial_from_harbor_result(trial_dir: Path, data: Mapping[str, Any], *, reward_key: str) -> AgentEvalTrial:
    task_id = str(data["task_name"])
    trial_id = str(data.get("trial_name") or trial_dir.name)
    rewards = _rewards_mapping(data)
    reward = _primary_reward(rewards, reward_key)
    exception_type = _exception_type(data.get("exception_info"))

    metadata: dict[str, Any] = {
        "reward": reward,
        "reward_details": dict(rewards),
        "harbor_trial_dir": str(trial_dir),
    }
    if exception_type is not None:
        metadata["exception_type"] = exception_type
    metadata.update(_token_measurements(data.get("agent_result")))

    # An errored trial (or one with no reward) stays PARTIAL so it is still scored
    # as 0 and counted in the summary; FAILED would exclude it from scoring.
    status = (
        AgentEvalTrialStatus.COMPLETED
        if exception_type is None and reward is not None
        else AgentEvalTrialStatus.PARTIAL
    )

    trace_path = trial_dir / "agent" / "trajectory.json"
    descriptors = standard_evidence_descriptors(
        logs_dir=trial_dir / "agent",
        final_state_dir=trial_dir / "artifacts",
        trace_path=trace_path if trace_path.exists() else None,
        verifier_logs_dir=trial_dir / "verifier",
    )

    return AgentEvalTrial(
        id=trial_id,
        task_id=task_id,
        status=status,
        output=AgentOutput(metadata={"harbor_trial_dir": str(trial_dir)}),
        evidence=CandidateEvidence(descriptors=descriptors),
        metadata=metadata,
    )


def _rewards_mapping(data: Mapping[str, Any]) -> dict[str, float]:
    verifier_result = data.get("verifier_result")
    if not isinstance(verifier_result, Mapping):
        return {}
    rewards = verifier_result.get("rewards")
    if not isinstance(rewards, Mapping):
        return {}
    out: dict[str, float] = {}
    for key, value in rewards.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _primary_reward(rewards: Mapping[str, float], reward_key: str) -> float | None:
    """Return the single reward a trial is scored on.

    Returns the reward named by ``reward_key`` when the verifier emitted it.
    Returns ``None`` otherwise (the trial is treated as having no reward, so it
    stays PARTIAL rather than scoring a misleading 0.0): if the verifier emitted
    rewards but none matches ``reward_key`` a warning is logged, since we do not
    guess among the emitted rewards (point ``reward_key`` at the intended one, or
    score the others with additional metrics over ``reward_details``).
    """
    if reward_key in rewards:
        return rewards[reward_key]
    if rewards:
        logger.warning(
            "Harbor trial emitted rewards %s but none matches reward_key=%r; treating the trial as having no reward",
            sorted(rewards),
            reward_key,
        )
    return None


def _exception_type(exception_info: Any) -> str | None:
    if exception_info is None:
        return None
    if isinstance(exception_info, Mapping):
        for key in ("exception_type", "type", "name", "class"):
            value = exception_info.get(key)
            if isinstance(value, str) and value:
                return value
        return "UnknownException"
    return str(exception_info)


def _token_measurements(agent_result: Any) -> dict[str, int | float]:
    """Map Harbor's ``agent_result`` token counts onto SDK ``TrialMeasurements`` keys."""
    if not isinstance(agent_result, Mapping):
        return {}
    mapping = {
        "prompt_tokens": "n_input_tokens",
        "completion_tokens": "n_output_tokens",
        "cache_read_tokens": "n_cache_tokens",
    }
    out: dict[str, int | float] = {}
    for sdk_key, harbor_key in mapping.items():
        value = agent_result.get(harbor_key)
        if isinstance(value, int) and not isinstance(value, bool):
            out[sdk_key] = value
    cost = agent_result.get("cost_usd")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        out["cost_usd"] = float(cost)
    return out


def reward_payload_from_result(
    result: AgentEvalResult,
    *,
    reward_key: str = DEFAULT_REWARD_KEY,
) -> dict[str, Any]:
    """Reconstruct the optimizer's legacy ``{reward, reward_details, exceptions}`` payload.

    Phase-1 adapter so consumers that still expect Harbor's aggregate shape can
    read it off an :class:`AgentEvalResult`:

    * ``reward`` — mean of each metric output, keyed ``"<metric_type>.<output>"``.
    * ``reward_details`` — ``{output: {value_str: [task_id, ...]}}`` grouped from
      per-trial scores (Harbor's ``reward_stats`` analogue).
    * ``exceptions`` — ``{exception_type: [task_id, ...]}`` from trial metadata
      (Harbor's ``exception_stats`` analogue).
    """
    reward = {score.name: score.mean for score in result.summary.scores.scores if score.mean is not None}

    reward_details: dict[str, dict[str, list[str]]] = {}
    for score in result.scores:
        if score.status == AgentEvalScoreStatus.FAILED:
            continue
        for output in score.outputs:
            value = output.value
            value_str = (
                str(float(value)) if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)
            )
            reward_details.setdefault(output.name, {}).setdefault(value_str, []).append(score.task_id)

    exceptions: dict[str, list[str]] = {}
    for trial in result.trials:
        exc = trial.metadata.get("exception_type")
        if isinstance(exc, str) and exc:
            exceptions.setdefault(exc, []).append(trial.task_id)

    return {
        "reward": reward,
        "reward_details": reward_details,
        "exceptions": exceptions,
    }


__all__ = [
    "DEFAULT_REWARD_KEY",
    "HarborAgentTaskRunner",
    "HarborRewardMetric",
    "build_trials_from_job_dir",
    "reward_payload_from_result",
]
