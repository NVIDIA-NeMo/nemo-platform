# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import importlib
import json
import logging
import sys
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (
    HarborAgentTaskRunner,
    HarborRewardMetric,
    HarborRuntimeConfig,
    HarborTasksetLoader,
    build_trials_from_job_dir,
    discover_harbor_tasks,
    reward_payload_from_result,
    scoped_harbor_agent_import,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrialStatus
from nemo_evaluator_sdk.metrics.utils import metric_type_name
from pydantic import ValidationError

_HELLO_WORLD_DATASET = Path(__file__).resolve().parents[2] / "examples" / "harbor" / "hello_world_dataset"


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
        AgentEvalTask(id="pass-task", intent="x", inputs={"instruction": "p"}, metrics=[HarborRewardMetric()]),
        AgentEvalTask(id="fail-task", intent="y", inputs={"instruction": "q"}, metrics=[HarborRewardMetric()]),
        AgentEvalTask(id="noreward-task", intent="z", inputs={"instruction": "r"}, metrics=[HarborRewardMetric()]),
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
    tasks = [AgentEvalTask(id="t", intent="x", inputs={"instruction": "p"}, metrics=[HarborRewardMetric()])]

    with caplog.at_level(logging.WARNING):
        trials = build_trials_from_job_dir(job_dir, tasks, reward_key="missing")

    assert trials[0].metadata["reward"] is None
    assert trials[0].status == AgentEvalTrialStatus.PARTIAL
    assert "none matches reward_key" in caplog.text


def test_task_discovery_and_taskset_loader_over_bundled_dataset() -> None:
    # Discovery reads the bundled hello-world dataset directory the same way Harbor
    # does: id comes from [task] name, and each task is scored by a reward metric.
    tasks = discover_harbor_tasks(_HELLO_WORLD_DATASET)
    assert [task.id for task in tasks] == ["harbor/hello-world"]
    task = tasks[0]
    # `intent` is the human-facing task name (metadata), NOT the instruction; the instruction the
    # agent acts on comes from instruction.md and lives in inputs["instruction"].
    assert task.intent == "harbor/hello-world"
    assert task.inputs["instruction"] == 'Create a file called hello.txt with "Hello, world!" as the content.'
    assert [metric_type_name(metric) for metric in task.metrics] == ["harbor_reward"]
    # The dataset dir and task dir are stamped on the task so a native runner can
    # recover them without a separate dataset_path argument.
    assert task.metadata["harbor_dataset_path"] == str(_HELLO_WORLD_DATASET)
    assert task.metadata["harbor_task_dir"] == str(_HELLO_WORLD_DATASET / "hello-world")

    # The loader wraps discovery as an AgentEvalTaskset and honors `limit`.
    loader = HarborTasksetLoader(_HELLO_WORLD_DATASET)
    assert loader.name == "harbor"
    taskset = loader.load()
    assert [t.id for t in taskset.tasks] == ["harbor/hello-world"]
    assert taskset.metadata["harbor_dataset_path"] == str(_HELLO_WORLD_DATASET)
    # A limit at/above the task count is a no-op (an empty taskset is invalid).
    assert [t.id for t in loader.load(limit=5).tasks] == ["harbor/hello-world"]


def test_discovery_fails_loudly_on_malformed_task(tmp_path: Path) -> None:
    # A malformed task.toml raises a clear, path-named error rather than crashing
    # cryptically or silently dropping the task (which would shrink eval coverage).
    task_dir = tmp_path / "bad-task"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text('[task]\nname = "oops')  # unterminated string
    with pytest.raises(ValueError, match=r"malformed Harbor task config at .*bad-task"):
        discover_harbor_tasks(tmp_path)


def test_runtime_config_defaults_and_runner_requires_a_source() -> None:
    # Config holds only plain fields (importing the module never needs harbor).
    config = HarborRuntimeConfig(jobs_dir=Path("/tmp/jobs"))
    assert config.agent_name == "oracle"
    assert config.reward_key == "reward"

    # A fully under-specified construction is rejected up front.
    with pytest.raises(ValueError):
        HarborAgentTaskRunner()

    # Native mode no longer needs dataset_path at construction; it is recovered from
    # the tasks at run time. Tasks without that metadata (and no override) fail loudly
    # when run (before Harbor is imported, so this needs no harbor install).
    runner = HarborAgentTaskRunner(config=config)
    with pytest.raises(ValueError):
        asyncio.run(runner.run_tasks([AgentEvalTask(id="t", intent="x", inputs={})]))


@pytest.mark.asyncio
async def test_native_runner_uses_job_dir_as_cache(tmp_path: Path) -> None:
    # A native run whose job_dir already covers every requested task is re-adapted,
    # not re-run: run_job is never awaited, so Harbor is never imported here. This
    # also exercises recovering the dataset dir from task metadata (no dataset_path).
    jobs_dir = tmp_path / "jobs"
    job_dir = jobs_dir / "cached-job"
    job_dir.mkdir(parents=True)
    _write_trial(job_dir, "t__aaa", "t", reward=1.0)

    config = HarborRuntimeConfig(jobs_dir=jobs_dir, job_name="cached-job")
    runner = HarborAgentTaskRunner(config=config)
    tasks = [
        AgentEvalTask(
            id="t",
            intent="x",
            inputs={"instruction": "x"},
            metrics=[HarborRewardMetric()],
            metadata={"harbor_dataset_path": str(tmp_path)},
        )
    ]

    trials = await runner.run_tasks(tasks)
    assert [trial.task_id for trial in trials] == ["t"]
    assert trials[0].metadata["reward"] == 1.0


def test_multiple_attempts_map_to_one_trial_each(tmp_path: Path) -> None:
    # n_attempts > 1: Harbor writes one result.json per attempt, and each becomes a
    # distinct trial for the same task id (so the summary can aggregate over attempts).
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    _write_trial(job_dir, "t__aaa", "t", reward=1.0)
    _write_trial(job_dir, "t__bbb", "t", reward=0.0)
    tasks = [AgentEvalTask(id="t", intent="x", inputs={"instruction": "p"}, metrics=[HarborRewardMetric()])]

    trials = build_trials_from_job_dir(job_dir, tasks)
    assert [trial.task_id for trial in trials] == ["t", "t"]
    assert sorted(trial.metadata["reward"] for trial in trials) == [0.0, 1.0]


def test_cache_is_attempt_and_success_aware(tmp_path: Path) -> None:
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _all_tasks_cached

    job_dir = tmp_path / "job"
    job_dir.mkdir()
    tasks = [AgentEvalTask(id="t", intent="x", inputs={"instruction": "p"}, metrics=[HarborRewardMetric()])]

    # One completed attempt: enough for n_attempts=1, not for n_attempts=2.
    _write_trial(job_dir, "t__aaa", "t", reward=1.0)
    assert _all_tasks_cached(job_dir, tasks, n_attempts=1) is True
    assert _all_tasks_cached(job_dir, tasks, n_attempts=2) is False

    # An errored attempt does not count, so the run is not served from a partial cache.
    _write_trial(job_dir, "t__bbb", "t", reward=0.0, exception="NonZeroAgentExitCodeError")
    assert _all_tasks_cached(job_dir, tasks, n_attempts=2) is False

    # A second clean attempt satisfies n_attempts=2.
    _write_trial(job_dir, "t__ccc", "t", reward=1.0)
    assert _all_tasks_cached(job_dir, tasks, n_attempts=2) is True


def test_scoped_agent_import_makes_wrapper_importable_then_cleans_up(tmp_path: Path) -> None:
    # import_path without agent_dir is allowed (Harbor imports an installed module directly);
    # only a dangling agent_dir (no import_path) is rejected.
    HarborRuntimeConfig(jobs_dir=tmp_path, agent_import_path="mypkg.agent:WrappedAgent")
    with pytest.raises(ValidationError):
        HarborRuntimeConfig(jobs_dir=tmp_path, agent_dir=tmp_path)

    # Inside the scope the user's harbor_wrapper.py resolves under a synthetic package,
    # and the yielded path preserves the :attribute suffix Harbor imports.
    (tmp_path / "harbor_wrapper.py").write_text("class WrappedAgent:\n    value = 42\n")
    with scoped_harbor_agent_import(tmp_path, "harbor_wrapper:WrappedAgent") as scoped_import:
        module_name, _, attribute = scoped_import.partition(":")
        assert attribute == "WrappedAgent"
        module = importlib.import_module(module_name)
        assert module.WrappedAgent.value == 42
        package = module_name.rsplit(".", 1)[0]
        assert package in sys.modules

    # On exit the injected module and its synthetic package are gone from sys.modules.
    assert module_name not in sys.modules
    assert package not in sys.modules
