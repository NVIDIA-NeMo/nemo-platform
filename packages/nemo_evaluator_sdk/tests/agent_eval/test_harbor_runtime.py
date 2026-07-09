# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import logging
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (
    HarborAgentTaskRunner,
    HarborRewardMetric,
    build_trials_from_job_dir,
    reward_payload_from_result,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrialStatus


def _write_trial(
    job_dir: Path, trial_name: str, task_name: str, *, reward: float | None, exception: str | None = None
) -> None:
    trial_dir = job_dir / trial_name
    (trial_dir / "agent").mkdir(parents=True)
    (trial_dir / "verifier").mkdir(parents=True)
    (trial_dir / "agent" / "trajectory.json").write_text("{}")
    payload = {
        "task_name": task_name,
        "trial_name": trial_name,
        "verifier_result": None if reward is None else {"rewards": {"reward": reward}},
        "exception_info": exception,
        "agent_result": {"n_input_tokens": 100, "n_output_tokens": 10, "n_cache_tokens": 5, "cost_usd": 0.25},
    }
    (trial_dir / "result.json").write_text(json.dumps(payload))


@pytest.mark.asyncio
async def test_harbor_runner_scores_through_agent_evaluator_and_adapts_legacy_payload(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    # Top-level aggregate result.json must be ignored (only */result.json are trials).
    (job_dir / "result.json").write_text(json.dumps({"stats": {}}))
    _write_trial(job_dir, "pass-task__aaa", "pass-task", reward=1.0)
    _write_trial(job_dir, "fail-task__bbb", "fail-task", reward=0.0, exception="NonZeroAgentExitCodeError")
    # A trial whose verifier emitted no reward at all (verifier_result=None).
    _write_trial(job_dir, "noreward-task__ccc", "noreward-task", reward=None)

    tasks = [
        AgentEvalTask(id="pass-task", intent="x", inputs={"prompt": "p"}, metrics=[HarborRewardMetric()]),
        AgentEvalTask(id="fail-task", intent="y", inputs={"prompt": "q"}, metrics=[HarborRewardMetric()]),
        AgentEvalTask(id="noreward-task", intent="z", inputs={"prompt": "r"}, metrics=[HarborRewardMetric()]),
    ]

    # Direct adaptation: reward + tokens land on metadata, exception flips status to PARTIAL, evidence present.
    trials = {t.task_id: t for t in build_trials_from_job_dir(job_dir, tasks)}
    assert trials["pass-task"].status == AgentEvalTrialStatus.COMPLETED
    assert trials["pass-task"].metadata["reward"] == 1.0
    assert trials["pass-task"].metadata["prompt_tokens"] == 100
    assert trials["pass-task"].evidence is not None
    assert trials["fail-task"].status == AgentEvalTrialStatus.PARTIAL
    assert trials["fail-task"].metadata["exception_type"] == "NonZeroAgentExitCodeError"
    # Missing reward: no explicit reward -> PARTIAL, metadata reward is None, scores as 0.0.
    assert trials["noreward-task"].status == AgentEvalTrialStatus.PARTIAL
    assert trials["noreward-task"].metadata["reward"] is None

    # run_job is awaited exactly once, then the job dir is adapted and scored end-to-end.
    calls = []
    runner = HarborAgentTaskRunner(job_dir=job_dir, run_job=lambda: _record(calls))
    result = await AgentEvaluator().run(tasks=tasks, target=runner, config=AgentEvalRunConfig(write_dashboard=False))
    assert calls == ["ran"]

    rewards_by_task = {score.task_id: score.outputs[0].value for score in result.scores if score.outputs}
    assert rewards_by_task == {"pass-task": 1.0, "fail-task": 0.0, "noreward-task": 0.0}

    # Phase-1 legacy adapter reproduces the {reward, reward_details, exceptions} contract.
    payload = reward_payload_from_result(result)
    assert payload["reward"]["harbor_reward.reward"] == pytest.approx(1.0 / 3)
    assert payload["reward_details"]["reward"]["1.0"] == ["pass-task"]
    assert payload["exceptions"] == {"NonZeroAgentExitCodeError": ["fail-task"]}


async def _record(calls: list[str]) -> None:
    calls.append("ran")


def test_reward_with_no_matching_reward_key_is_partial_and_warns(tmp_path: Path, caplog) -> None:
    # Verifier emitted a reward, but under a key we didn't ask for: no guessing —
    # the trial is treated as having no reward (None -> PARTIAL, scores 0.0) and warns.
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    _write_trial(job_dir, "t__aaa", "t", reward=1.0)  # emitted under "reward"
    tasks = [AgentEvalTask(id="t", intent="x", inputs={"prompt": "p"}, metrics=[HarborRewardMetric()])]

    with caplog.at_level(logging.WARNING):
        trials = build_trials_from_job_dir(job_dir, tasks, reward_key="missing")

    assert trials[0].metadata["reward"] is None
    assert trials[0].status == AgentEvalTrialStatus.PARTIAL
    assert "none matches reward_key" in caplog.text
