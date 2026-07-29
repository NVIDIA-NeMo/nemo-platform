# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import builtins
import hashlib
import importlib
import json
import logging
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import ModuleType

import pytest
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (
    HarborAgentTaskRunner,
    HarborRewardMetric,
    HarborRuntimeConfig,
    HarborTasksetLoader,
    _build_native_job,
    build_trials_from_job_dir,
    discover_harbor_tasks,
    reward_payload_from_result,
    scoped_harbor_agent_import,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrialStatus
from nemo_evaluator_sdk.metrics.utils import metric_type_name
from pydantic import BaseModel, ValidationError

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


def _cached_task(dataset_path: Path, task_dir: Path, task_id: str = "t") -> AgentEvalTask:
    """A task whose dataset and on-disk directory the cache stamp can resolve."""
    return AgentEvalTask(
        id=task_id,
        intent="x",
        inputs={"instruction": "x"},
        metrics=[HarborRewardMetric()],
        metadata={"harbor_dataset_path": str(dataset_path), "harbor_task_dir": str(task_dir)},
    )


def _seed_cached_job(tmp_path: Path, *, task_id: str = "t") -> tuple[HarborRuntimeConfig, Path, AgentEvalTask]:
    """A complete job dir plus the config/task that produced it, stamped as a real run would."""
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _cache_stamp, _write_cache_stamp

    dataset_path = tmp_path / "dataset"
    task_dir = dataset_path / task_id
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(f'[task]\nname = "{task_id}"\n')

    # jobs_dir deliberately nested under the dataset dir: the digest must exclude it,
    # or it would hash its own growing results tree and never stabilize.
    jobs_dir = dataset_path / "jobs"
    job_dir = jobs_dir / "cached-job"
    job_dir.mkdir(parents=True)
    _write_trial(job_dir, f"{task_id}__aaa", task_id, reward=1.0)

    config = HarborRuntimeConfig(jobs_dir=jobs_dir, job_name="cached-job")
    task = _cached_task(dataset_path, task_dir, task_id)
    _write_cache_stamp(job_dir, _cache_stamp(config, dataset_path, [task]))
    return config, job_dir, task


@pytest.mark.asyncio
async def test_native_runner_uses_job_dir_as_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A native run whose job_dir covers every requested task AND carries a matching
    # cache stamp is re-adapted, not re-run: run_job is never awaited, so Harbor is
    # never imported here (which is why this test needs no harbor install).
    config, _job_dir, task = _seed_cached_job(tmp_path)
    # Watch the lazy import directly instead of mutating sys.modules: popping only
    # "harbor" would leave already-imported harbor.* submodules parentless and
    # corrupt the module identity other suites monkeypatch.
    imported: list[str] = []
    real_import = builtins.__import__

    def recording_import(name, *args, **kwargs):
        if name == "harbor" or name.startswith("harbor."):
            imported.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", recording_import)
    trials = await HarborAgentTaskRunner(config=config).run_tasks([task])
    monkeypatch.undo()

    assert [trial.task_id for trial in trials] == ["t"]
    assert trials[0].metadata["reward"] == 1.0
    assert imported == [], f"a cache hit must not import harbor, but imported {imported}"


def _stamp_for(config: HarborRuntimeConfig, task: AgentEvalTask, job_dir: Path) -> None:
    """Stamp ``job_dir`` as though ``config`` had just produced it."""
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _cache_stamp, _write_cache_stamp

    dataset_path = Path(str(task.metadata["harbor_dataset_path"]))
    _write_cache_stamp(job_dir, _cache_stamp(config, dataset_path, [task]))


def _spy_on_run_job(monkeypatch: pytest.MonkeyPatch, calls: list[bool]) -> None:
    """Replace the native job build so run_tasks is observable without Harbor.

    Records whether the run was attempted and what force_rerun it was built with.
    """
    from nemo_evaluator_sdk.agent_eval.runtimes import harbor_runtime

    def fake(config, _dataset_path, _task_names, *, job_name=None, force_rerun=None):
        async def run_job() -> None:
            calls.append(bool(force_rerun))

        return config.jobs_dir / (job_name or "job"), run_job

    monkeypatch.setattr(harbor_runtime, "_build_native_job", fake)


@pytest.mark.asyncio
async def test_unstamped_job_dir_is_not_trusted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A complete job dir with no stamp predates this check, or was written by plain
    # Harbor. Re-running is the safe reading.
    config, job_dir, task = _seed_cached_job(tmp_path)
    (job_dir / ".nemo-eval-harbor-cache.json").unlink()
    calls: list[bool] = []
    _spy_on_run_job(monkeypatch, calls)

    await HarborAgentTaskRunner(config=config).run_tasks([task])

    assert calls == [True], "an unstamped dir must be re-run, and discarded rather than resumed"


@pytest.mark.asyncio
async def test_changed_inputs_discard_the_job_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A stamp mismatch means the surviving results were produced by different
    # inputs, so they must be deleted rather than resumed onto.
    config, _job_dir, task = _seed_cached_job(tmp_path)
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "wrapper.py").write_text("x = 1\n")
    config = config.model_copy(update={"agent_import_path": "wrapper:Agent", "agent_dir": agent_dir})
    calls: list[bool] = []
    _spy_on_run_job(monkeypatch, calls)

    await HarborAgentTaskRunner(config=config).run_tasks([task])

    assert calls == [True], "changed inputs must discard, not resume"


@pytest.mark.asyncio
async def test_under_covered_job_resumes_with_agent_dir_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression for AALGO-430. This used to discard unconditionally: the scoped
    # import path carried a fresh uuid per run, so Harbor's JobConfig never matched
    # and it raised FileExistsError instead of resuming. Now the path is
    # content-addressed, so an unchanged agent resumes and keeps completed Docker
    # work — the same as the agent_dir-unset case below.
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "wrapper.py").write_text("x = 1\n")
    config, job_dir, task = _seed_cached_job(tmp_path)
    config = config.model_copy(update={"agent_import_path": "wrapper:Agent", "agent_dir": agent_dir, "n_attempts": 2})
    _stamp_for(config, task, job_dir)  # stamp matches; only coverage is short
    calls: list[bool] = []
    _spy_on_run_job(monkeypatch, calls)

    await HarborAgentTaskRunner(config=config).run_tasks([task])

    assert calls == [False], "an unchanged agent must resume, not discard completed trials"


@pytest.mark.asyncio
async def test_under_covered_job_resumes_when_harbor_can(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Inputs unchanged, some attempts missing, agent_dir unset — Harbor's
    # AgentConfig is deterministic, so it resumes per trial. Discarding would throw
    # away completed Docker work for nothing. The agent_dir-set case above now
    # behaves identically (AALGO-430).
    config, job_dir, task = _seed_cached_job(tmp_path)
    config = config.model_copy(update={"n_attempts": 2})
    _stamp_for(config, task, job_dir)  # stamp matches the new config
    calls: list[bool] = []
    _spy_on_run_job(monkeypatch, calls)

    await HarborAgentTaskRunner(config=config).run_tasks([task])

    assert calls == [False], "a resumable miss must not delete completed trials"


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["agent", "task", "option"])
async def test_changed_inputs_invalidate_the_cache(tmp_path: Path, mutation: str) -> None:
    # Each of these changes what a run would produce, so the stamped dir must not be
    # served. Reaching run_job (and failing there) is the observable signal.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _cache_is_stale, _cache_stamp

    config, job_dir, task = _seed_cached_job(tmp_path)
    dataset_path = Path(str(task.metadata["harbor_dataset_path"]))

    if mutation == "agent":
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "wrapper.py").write_text("x = 1\n")
        config = config.model_copy(
            update={"agent_import_path": "wrapper:Agent", "agent_dir": agent_dir},
        )
    elif mutation == "task":
        (dataset_path / "t" / "task.toml").write_text('[task]\nname = "t"\nchanged = true\n')
    else:
        config = config.model_copy(update={"n_attempts": 2})

    assert _cache_is_stale(job_dir, _cache_stamp(config, dataset_path, [task])) is True


@pytest.mark.asyncio
async def test_cosmetic_options_do_not_evict_the_cache(tmp_path: Path) -> None:
    # Presentation and placement knobs change nothing about the results; evicting on
    # them would cost a full Docker re-run for nothing.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _cache_is_stale, _cache_stamp

    config, job_dir, task = _seed_cached_job(tmp_path)
    dataset_path = Path(str(task.metadata["harbor_dataset_path"]))
    relaxed = config.model_copy(update={"quiet": False, "n_concurrent_trials": 1, "reward_key": "other"})

    assert _cache_is_stale(job_dir, _cache_stamp(relaxed, dataset_path, [task])) is False


@pytest.mark.asyncio
async def test_task_subset_of_a_cached_run_still_hits(tmp_path: Path) -> None:
    # Stamping per task (not one job-wide hash) means evaluating a subset of a
    # previously cached job is still a hit.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (
        _cache_is_stale,
        _cache_stamp,
        _write_cache_stamp,
    )

    config, job_dir, task_a = _seed_cached_job(tmp_path, task_id="t")
    dataset_path = Path(str(task_a.metadata["harbor_dataset_path"]))
    task_b_dir = dataset_path / "u"
    task_b_dir.mkdir()
    (task_b_dir / "task.toml").write_text('[task]\nname = "u"\n')
    task_b = _cached_task(dataset_path, task_b_dir, "u")

    _write_cache_stamp(job_dir, _cache_stamp(config, dataset_path, [task_a, task_b]))

    assert _cache_is_stale(job_dir, _cache_stamp(config, dataset_path, [task_a])) is False


def test_unpinned_job_name_writes_no_stamp_and_reads_no_files(tmp_path: Path) -> None:
    # The default timestamped job name can never hit the cache, so the fingerprint
    # must not be computed at all — this is the path plugins/nemo-evaluator takes.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _resolve_job_dir

    config = HarborRuntimeConfig(jobs_dir=tmp_path / "jobs")
    first = _resolve_job_dir(config)[1]

    assert config.job_name is None
    assert first.parent == tmp_path / "jobs"
    assert not list((tmp_path / "jobs").glob("**/.nemo-eval-harbor-cache.json"))


def test_cache_stamp_survives_harbors_stray_directory_sweep(tmp_path: Path) -> None:
    # Harbor rmtree's any *directory* in a job dir lacking result.json. The stamp must
    # therefore be a file, or it would be silently deleted on the next Harbor run.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import CACHE_STAMP_FILENAME

    _config, job_dir, _task = _seed_cached_job(tmp_path)
    stamp = job_dir / CACHE_STAMP_FILENAME

    assert stamp.is_file()
    assert not stamp.is_dir()


def test_cache_stamp_handles_a_missing_agent_dir(tmp_path: Path) -> None:
    # agent_dir is None for every built-in-agent caller (including nemo-evaluator).
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _cache_stamp

    config, _job_dir, task = _seed_cached_job(tmp_path)
    stamp = _cache_stamp(config, Path(str(task.metadata["harbor_dataset_path"])), [task])

    assert config.agent_dir is None
    assert stamp["agent"] == "<none>"


def test_unresolvable_task_dir_is_always_stale(tmp_path: Path) -> None:
    # A task we cannot locate on disk must never be silently omitted from the
    # fingerprint — that would be a stale-cache hole.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _cache_is_stale, _cache_stamp

    config, job_dir, _task = _seed_cached_job(tmp_path)
    orphan = AgentEvalTask(id="ghost", intent="x", inputs={"instruction": "x"}, metrics=[HarborRewardMetric()])
    stamp = _cache_stamp(config, tmp_path / "nonexistent-dataset", [orphan])

    assert stamp["tasks"]["ghost"] == "<unresolved>"
    assert _cache_is_stale(job_dir, stamp) is True


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


def test_digest_ignores_an_exclusion_that_contains_the_whole_tree(tmp_path: Path) -> None:
    # jobs_dir sitting *above* the agent/task dir is a legitimate layout. Applying the
    # exclusion there would match every entry and yield an empty digest, silently
    # disabling invalidation for the entire directory.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _digest_directory

    work = tmp_path / "work"
    (work / "agent").mkdir(parents=True)
    (work / "agent" / "a.py").write_text("v1")

    before = _digest_directory(work / "agent", exclude=frozenset({work}))
    assert before != hashlib.sha256().hexdigest(), "an ancestor exclusion must not empty the digest"

    (work / "agent" / "a.py").write_text("v2-DIFFERENT")
    assert _digest_directory(work / "agent", exclude=frozenset({work})) != before


def test_digest_still_ignores_a_jobs_dir_nested_inside_the_tree(tmp_path: Path) -> None:
    # The case the exclusion actually exists for: results written under the hashed
    # tree must not make the fingerprint move on every run.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _digest_directory

    agent = tmp_path / "agent"
    (agent / "jobs").mkdir(parents=True)
    (agent / "a.py").write_text("src")
    (agent / "jobs" / "result.json").write_text("{}")

    before = _digest_directory(agent, exclude=frozenset({agent / "jobs"}))
    (agent / "jobs" / "result.json").write_text('{"more": "output"}')
    assert _digest_directory(agent, exclude=frozenset({agent / "jobs"})) == before


def test_task_dir_outside_the_active_dataset_is_rediscovered(tmp_path: Path) -> None:
    # `dataset_path` can be overridden on the runner, so a task stamped during
    # discovery under dataset A must not be fingerprinted when Harbor runs dataset B.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _task_dirs_for

    dataset_a, dataset_b = tmp_path / "dsA", tmp_path / "dsB"
    for dataset in (dataset_a, dataset_b):
        (dataset / "t").mkdir(parents=True)
        (dataset / "t" / "task.toml").write_text('[task]\nname = "t"\n')

    task = AgentEvalTask(
        id="t",
        intent="x",
        inputs={"instruction": "x"},
        metadata={"harbor_dataset_path": str(dataset_a), "harbor_task_dir": str(dataset_a / "t")},
    )

    resolved = _task_dirs_for(dataset_b, [task])["t"]
    assert resolved is not None
    assert resolved.resolve().is_relative_to(dataset_b.resolve()), "must fingerprint the dataset Harbor runs"


def test_vanished_task_dir_is_rediscovered(tmp_path: Path) -> None:
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _task_dirs_for

    dataset = tmp_path / "ds"
    (dataset / "t").mkdir(parents=True)
    (dataset / "t" / "task.toml").write_text('[task]\nname = "t"\n')
    task = AgentEvalTask(
        id="t",
        intent="x",
        inputs={"instruction": "x"},
        metadata={"harbor_task_dir": str(tmp_path / "gone" / "t")},
    )

    assert _task_dirs_for(dataset, [task])["t"] == dataset / "t"


@pytest.mark.asyncio
async def test_inputs_changing_mid_run_leaves_the_job_unstamped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If the candidate is edited while Harbor is running, the results came from the
    # OLD sources. Stamping the new fingerprint onto them would let a later run serve
    # them as if they matched — so the job dir is deliberately left unstamped.
    from nemo_evaluator_sdk.agent_eval.runtimes import harbor_runtime

    config, job_dir, task = _seed_cached_job(tmp_path)
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "wrapper.py").write_text("v1\n")
    config = config.model_copy(update={"agent_import_path": "wrapper:Agent", "agent_dir": agent_dir})
    (job_dir / harbor_runtime.CACHE_STAMP_FILENAME).unlink()

    def fake(cfg, _dataset_path, _task_names, *, job_name=None, force_rerun=None):
        async def run_job() -> None:
            (agent_dir / "wrapper.py").write_text("v2-EDITED-MID-RUN\n")

        return cfg.jobs_dir / (job_name or "job"), run_job

    monkeypatch.setattr(harbor_runtime, "_build_native_job", fake)

    await HarborAgentTaskRunner(config=config).run_tasks([task])

    assert not (job_dir / harbor_runtime.CACHE_STAMP_FILENAME).exists(), (
        "results produced from pre-edit sources must not be stamped with the post-edit fingerprint"
    )


def test_digest_is_injective_over_separator_bearing_contents(tmp_path: Path) -> None:
    """Distinct trees must never share a digest, even when contents embed the framing.

    A collision here fails CLOSED - the digest matches, so stale results are served.
    The historical bug was concatenating ``name \\0 content \\0`` with no length
    framing: because file *contents* may contain NUL, ``{a: b"", b: b"Z"}`` and
    ``{a: b"\\0b\\0Z"}`` produced an identical byte stream.

    Rather than pin one hand-built pair to one encoding, this asserts the property:
    every tree below is structurally different, so every digest must differ. The
    contents are chosen to embed the separators an unframed encoding would rely on.
    """
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _digest_directory

    trees: dict[str, dict[str, bytes]] = {
        "two_files_empty_then_z": {"a": b"", "b": b"Z"},
        "one_file_absorbing_nul": {"a": b"\0b\0Z"},
        "one_file_absorbing_nul_and_mode": {"a": b"\0b\0-\0Z"},
        "three_files": {"a": b"", "b": b"", "c": b"Z"},
        "two_files_swapped": {"a": b"Z", "b": b""},
        "one_file_named_b": {"b": b"Z"},
    }

    digests: dict[str, str] = {}
    for name, files in trees.items():
        root = tmp_path / name
        root.mkdir()
        for filename, content in files.items():
            (root / filename).write_bytes(content)
        digests[name] = _digest_directory(root)

    collisions = {
        (left, right) for left in digests for right in digests if left < right and digests[left] == digests[right]
    }
    assert not collisions, f"distinct trees produced identical digests: {sorted(collisions)}"


def test_digest_tracks_the_execute_bit(tmp_path: Path) -> None:
    # Harbor discovers and runs tests/test.sh; flipping +x changes what happens
    # without changing a single byte of content.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _digest_directory

    task = tmp_path / "task"
    task.mkdir()
    script = task / "test.sh"
    script.write_text("#!/bin/sh\necho hi\n")

    script.chmod(0o644)
    non_executable = _digest_directory(task)
    script.chmod(0o755)
    assert _digest_directory(task) != non_executable, "+x must invalidate"


def test_digest_ignores_read_write_permission_noise(tmp_path: Path) -> None:
    # Only the execute bit is tracked, mirroring git: umask differences between two
    # checkouts of the same sources must not evict a usable cache.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _digest_directory

    task = tmp_path / "task"
    task.mkdir()
    source = task / "a.py"
    source.write_text("x = 1\n")

    source.chmod(0o644)
    before = _digest_directory(task)
    source.chmod(0o600)
    assert _digest_directory(task) == before


def test_digest_covers_vendored_dependencies_but_not_the_environment(tmp_path: Path) -> None:
    # node_modules ships with the agent and changes what it does, so it counts.
    # .venv is environment the Harbor wrapper never uploads, so it does not.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _digest_directory

    agent = tmp_path / "agent"
    (agent / "node_modules" / "lib").mkdir(parents=True)
    (agent / ".venv").mkdir()
    (agent / "main.js").write_text("x")
    (agent / "node_modules" / "lib" / "index.js").write_text("v1")
    (agent / ".venv" / "marker").write_text("1")

    before = _digest_directory(agent)
    (agent / "node_modules" / "lib" / "index.js").write_text("v2-DIFFERENT")
    assert _digest_directory(agent) != before, "a vendored dependency change must invalidate"

    after_dep = _digest_directory(agent)
    (agent / ".venv" / "marker").write_text("2")
    assert _digest_directory(agent) == after_dep, ".venv churn must not evict the cache"


def test_digest_survives_a_dangling_symlink(tmp_path: Path) -> None:
    # A link whose *target* is missing: is_dir()/is_file() are both False, so it is
    # recorded as a marker. (readlink still succeeds here - see the test below for
    # the case where readlink itself fails.)
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _digest_directory

    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "real.py").write_text("x")
    (agent / "dangling").symlink_to(tmp_path / "does-not-exist")

    assert _digest_directory(agent)  # no raise


def test_digest_distinguishes_a_file_from_a_directory_of_the_same_name(tmp_path: Path) -> None:
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _digest_directory

    as_file = tmp_path / "as_file"
    as_file.mkdir()
    (as_file / "thing").write_text("")

    as_dir = tmp_path / "as_dir"
    as_dir.mkdir()
    (as_dir / "thing").mkdir()

    assert _digest_directory(as_file) != _digest_directory(as_dir)


def test_digest_survives_readlink_failing_mid_walk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The link itself disappearing between is_symlink() and readlink is a real race
    # against any process cleaning up the tree. It must degrade to a marker rather
    # than raise out of run_tasks and kill an otherwise-good evaluation.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _digest_directory

    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "real.py").write_text("x")
    (agent / "link").symlink_to(agent / "real.py")

    def exploding_readlink(*_args: object, **_kwargs: object) -> str:
        raise OSError(2, "No such file or directory")

    monkeypatch.setattr(os, "readlink", exploding_readlink)

    assert _digest_directory(agent)  # must not raise


def _scoped_path(agent_dir: Path) -> str:
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import scoped_harbor_agent_import

    with scoped_harbor_agent_import(agent_dir, "wrapper:Agent") as scoped:
        return scoped


def test_scoped_import_path_is_stable_for_unchanged_contents(tmp_path: Path) -> None:
    # The import path lands in Harbor's JobConfig, which Harbor compares field-by-field
    # when deciding whether a job dir may be resumed. A per-run random suffix made that
    # comparison fail every time, so Harbor could never resume (AALGO-430).
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "wrapper.py").write_text("x = 1\n")

    assert _scoped_path(agent_dir) == _scoped_path(agent_dir)


def test_scoped_import_path_changes_when_the_agent_changes(tmp_path: Path) -> None:
    # The flip side: an edited agent must NOT resume a job dir built from the old one.
    # Harbor's own config check now catches that without help from the cache stamp.
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "wrapper.py").write_text("x = 1\n")
    before = _scoped_path(agent_dir)

    (agent_dir / "wrapper.py").write_text("x = 2\n")

    assert _scoped_path(agent_dir) != before


def test_distinct_agents_do_not_share_a_scoped_package(tmp_path: Path) -> None:
    # Content-addressing must not collapse different agents onto one sys.modules entry.
    first = tmp_path / "a"
    second = tmp_path / "b"
    for path, body in ((first, "x = 1\n"), (second, "x = 2\n")):
        path.mkdir()
        (path / "wrapper.py").write_text(body)

    assert _scoped_path(first) != _scoped_path(second)


def test_overlapping_scopes_on_one_agent_survive_the_inner_exit(tmp_path: Path) -> None:
    # Identical contents now share a package name, so teardown is refcounted: the inner
    # scope exiting must not strip sys.modules out from under the outer one.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import scoped_harbor_agent_import

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "wrapper.py").write_text("VALUE = 7\n")

    with scoped_harbor_agent_import(agent_dir, "wrapper:Agent") as outer:
        package = outer.split(":")[0].rsplit(".", 1)[0]
        with scoped_harbor_agent_import(agent_dir, "wrapper:Agent"):
            pass
        # Inner scope closed; the outer one is still open and must still resolve.
        assert package in sys.modules
        assert importlib.import_module(f"{package}.wrapper").VALUE == 7

    assert package not in sys.modules, "the last scope to exit must clean up"


def test_scoped_import_teardown_is_complete_after_overlap(tmp_path: Path) -> None:
    # Refcounting must not leak: no stray refcount entries or sys.modules residue.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (
        _AGENT_IMPORT_ROOT,
        _AGENT_PACKAGE_REFCOUNTS,
        scoped_harbor_agent_import,
    )

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "wrapper.py").write_text("x = 1\n")

    with scoped_harbor_agent_import(agent_dir, "wrapper:Agent"):
        with scoped_harbor_agent_import(agent_dir, "wrapper:Agent"):
            pass

    assert _AGENT_PACKAGE_REFCOUNTS == {}
    assert not [name for name in sys.modules if name.startswith(f"{_AGENT_IMPORT_ROOT}.")]


def test_scoped_import_path_ignores_a_jobs_dir_nested_under_the_agent(tmp_path: Path) -> None:
    # jobs_dir is caller-chosen and may sit *under* agent_dir. Without the same
    # exclusion the cache stamp applies, Harbor's own results would feed the package
    # name, so the import path would move every run and the resume this whole change
    # exists to enable could never happen.
    agent_dir = tmp_path / "agent"
    jobs_dir = agent_dir / "results"
    jobs_dir.mkdir(parents=True)
    (agent_dir / "wrapper.py").write_text("x = 1\n")
    excluded = frozenset({jobs_dir.resolve()})

    with scoped_harbor_agent_import(agent_dir, "wrapper:Agent", exclude=excluded) as before:
        pass
    (jobs_dir / "trial-a").mkdir()
    (jobs_dir / "trial-a" / "result.json").write_text("{}")
    with scoped_harbor_agent_import(agent_dir, "wrapper:Agent", exclude=excluded) as after:
        pass

    assert before == after, "accumulating results must not move the agent's import path"


def test_failed_scoped_import_install_does_not_wedge_the_refcount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The refcount is taken only once the sys.modules injection has succeeded. Taking
    # it first would strand the count at 1 when the injection raises — no scope ever
    # opened, so nothing decrements it, and the package could never be torn down again.
    from nemo_evaluator_sdk.agent_eval.runtimes import harbor_runtime
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _AGENT_IMPORT_ROOT, _AGENT_PACKAGE_REFCOUNTS

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "wrapper.py").write_text("x = 1\n")

    def explode(_name: str) -> ModuleType:
        raise RuntimeError("synthetic package could not be built")

    with monkeypatch.context() as patched:
        patched.setattr(harbor_runtime, "ModuleType", explode)
        with pytest.raises(RuntimeError, match="synthetic package"):
            with scoped_harbor_agent_import(agent_dir, "wrapper:Agent"):
                pass

    assert _AGENT_PACKAGE_REFCOUNTS == {}, "a failed install must not leave a refcount behind"
    # And a later scope must still install and then fully tear down.
    with scoped_harbor_agent_import(agent_dir, "wrapper:Agent"):
        pass
    assert _AGENT_PACKAGE_REFCOUNTS == {}
    assert not [name for name in sys.modules if name.startswith(f"{_AGENT_IMPORT_ROOT}.")]


class _DriftConfig(BaseModel):
    """Stands in for Harbor's JobConfig: a field it ignores, one it compares, one defaulted."""

    job_name: str = "job"
    n_concurrent_trials: int = 4
    quiet: bool = True


def _stub_harbor(monkeypatch: pytest.MonkeyPatch, job_create: Callable[[object], Awaitable[object]]) -> None:
    """Install a minimal fake ``harbor`` package so ``run_job`` can execute.

    Only the names ``_build_native_job``'s ``run_job`` imports are provided.
    ``job_create`` becomes ``Job.create``; every config class is a permissive stub,
    since what is under test is the control flow around Harbor, not the payload.
    """

    def _module(name: str, **attrs: object) -> None:
        module = ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        monkeypatch.setitem(sys.modules, name, module)

    def _anything(*_args: object, **_kwargs: object) -> object:
        return object()

    class _Job:
        create = staticmethod(job_create)

    _module("harbor")
    # JobConfig is a real model, not `_anything`: the resume-refusal path reads and
    # re-validates the persisted one to report what differed. Pydantic ignores the
    # kwargs _build_native_job passes that this stand-in doesn't declare.
    _module("harbor.job", DatasetConfig=_anything, Job=_Job, JobConfig=_DriftConfig)
    _module("harbor.models")
    _module("harbor.models.job")
    _module("harbor.models.job.config", RetryConfig=_anything)
    _module("harbor.models.trial")
    _module("harbor.models.trial.config", AgentConfig=_anything, ArtifactConfig=_anything)


class _FakeJob:
    async def run(self) -> None:
        return None


@pytest.mark.asyncio
async def test_harbor_refusing_to_resume_discards_and_reruns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Harbor compares its whole persisted JobConfig (and lock.json) before resuming and
    # raises FileExistsError on any mismatch. The SDK cache stamp is looser on purpose:
    # `quiet`, `n_concurrent_trials` and the `task_names` filter change the JobConfig
    # without changing the results, so a job dir that passes the stamp — and is
    # therefore handed over with force_rerun=False — can still be rejected by Harbor.
    # That must degrade to a clean re-run rather than crash the evaluation.
    jobs_dir = tmp_path / "jobs"
    job_dir = jobs_dir / "pinned"
    (job_dir / "old-trial").mkdir(parents=True)
    # The dir was produced on a 10-core box; this run defaults to 4. Nothing about the
    # results changed, so the SDK stamp would still call it fresh — Harbor won't.
    (job_dir / "config.json").write_text(
        _DriftConfig(job_name="pinned", n_concurrent_trials=10).model_dump_json(exclude_defaults=True),
        encoding="utf-8",
    )
    dir_existed_at_attempt: list[bool] = []

    async def create(_config: object) -> _FakeJob:
        dir_existed_at_attempt.append(job_dir.exists())
        if len(dir_existed_at_attempt) == 1:
            raise FileExistsError(
                f"Job directory {job_dir} already exists and cannot be resumed with a different config."
            )
        return _FakeJob()

    _stub_harbor(monkeypatch, create)
    config = HarborRuntimeConfig(jobs_dir=jobs_dir, job_name="pinned")
    _built, run_job = _build_native_job(config, tmp_path / "dataset", None, job_name="pinned", force_rerun=False)

    with caplog.at_level(logging.WARNING):
        await run_job()

    assert dir_existed_at_attempt == [True, False], "the refused dir must be discarded before the retry"
    assert not (job_dir / "old-trial").exists(), "the stale trial must be gone, not resumed onto"
    assert "refused to resume" in caplog.text, "silently deleting completed trials must be visible"
    assert "n_concurrent_trials: 10 -> 4" in caplog.text, "the warning must name what forced the discard"


@pytest.mark.asyncio
async def test_file_exists_error_without_a_job_dir_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The retry is scoped to Harbor's resume refusal. A FileExistsError raised with no
    # job dir to discard is something else entirely and must not be swallowed, nor
    # turned into a second Docker run.
    attempts: list[int] = []

    async def create(_config: object) -> _FakeJob:
        attempts.append(1)
        raise FileExistsError("something unrelated")

    _stub_harbor(monkeypatch, create)
    config = HarborRuntimeConfig(jobs_dir=tmp_path / "jobs", job_name="pinned")
    _built, run_job = _build_native_job(config, tmp_path / "dataset", None, job_name="pinned", force_rerun=False)

    with pytest.raises(FileExistsError, match="something unrelated"):
        await run_job()

    assert attempts == [1], "an unrelated FileExistsError must not be retried"


@pytest.mark.asyncio
async def test_unrelated_file_exists_error_mid_run_leaves_the_job_dir_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The dangerous shape: a job dir that *does* exist, and a FileExistsError raised
    # from inside the run rather than by Harbor's resume check — a trial, a hook, an
    # environment build. Treating that as drift would delete completed work and re-run
    # for an error that has nothing to do with the config.
    jobs_dir = tmp_path / "jobs"
    job_dir = jobs_dir / "pinned"
    (job_dir / "finished-trial").mkdir(parents=True)
    attempts: list[int] = []

    class _ExplodingJob:
        async def run(self) -> None:
            attempts.append(1)
            raise FileExistsError(17, "File exists", str(tmp_path / "scratch" / "artifact.tar"))

    async def create(_config: object) -> _ExplodingJob:
        return _ExplodingJob()

    _stub_harbor(monkeypatch, create)
    config = HarborRuntimeConfig(jobs_dir=jobs_dir, job_name="pinned")
    _built, run_job = _build_native_job(config, tmp_path / "dataset", None, job_name="pinned", force_rerun=False)

    with pytest.raises(FileExistsError):
        await run_job()

    assert attempts == [1], "an unrelated failure must not be retried"
    assert (job_dir / "finished-trial").exists(), "completed work must survive an error that is not resume drift"


@pytest.mark.parametrize(
    ("message", "errno", "expected"),
    [
        ("Job directory {job_dir} already exists and cannot be resumed with a different config.", None, True),
        ("Job directory {job_dir} already has a lock.json that does not match the resolved job lock.", None, True),
        # Same words, but an OS-level EEXIST: errno is set, so it is not Harbor's refusal.
        ("Job directory {job_dir} already exists and cannot be resumed with a different config.", 17, False),
        # A refusal naming a *different* job dir is not ours to act on.
        ("Job directory /somewhere/else already exists and cannot be resumed with a different config.", None, False),
        ("[Errno 17] File exists: '{job_dir}/trial/artifact.tar'", None, False),
    ],
)
def test_only_harbors_resume_refusal_authorises_deleting_the_job_dir(
    tmp_path: Path, message: str, errno: int | None, expected: bool
) -> None:
    # Deleting a job dir is the one irreversible thing this runtime does, so the
    # predicate that authorises it is pinned directly. Anything unrecognised must
    # answer False and let the error propagate — the safe direction if Harbor rewords.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _is_harbor_resume_refusal

    job_dir = tmp_path / "jobs" / "pinned"
    rendered = message.format(job_dir=job_dir)
    exc = FileExistsError(rendered) if errno is None else FileExistsError(errno, "File exists", rendered)

    assert _is_harbor_resume_refusal(exc, job_dir) is expected


def test_job_config_drift_names_the_field_that_forced_the_discard(tmp_path: Path) -> None:
    # Harbor says only *that* a config differs, so the discard looks arbitrary in the
    # log. This pins three things at once: the differing field is named, a field Harbor
    # ignores is not, and a field left at its default is not — the last only holds
    # because the persisted JSON (written with exclude_defaults=True) is re-validated
    # rather than compared raw, which would see a missing key as a difference.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _describe_job_config_drift

    job_dir = tmp_path / "job"
    job_dir.mkdir()
    stored = _DriftConfig(job_name="pinned", n_concurrent_trials=10)
    (job_dir / "config.json").write_text(stored.model_dump_json(exclude_defaults=True), encoding="utf-8")

    drift = _describe_job_config_drift(job_dir, _DriftConfig(job_name="renamed", n_concurrent_trials=4))

    assert drift == "n_concurrent_trials: 10 -> 4"


def test_job_config_drift_is_silent_when_it_cannot_tell(tmp_path: Path) -> None:
    # No config.json is the lock.json-refusal case: there is no JobConfig difference to
    # report. Diagnostics must degrade to silence, never to a raised exception that
    # would mask the FileExistsError being explained.
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _describe_job_config_drift

    job_dir = tmp_path / "job"
    job_dir.mkdir()

    assert _describe_job_config_drift(job_dir, _DriftConfig()) == ""
    (job_dir / "config.json").write_text("{not json", encoding="utf-8")
    assert _describe_job_config_drift(job_dir, _DriftConfig()) == ""


# Harbor JobConfig field -> the HarborRuntimeConfig fields that feed it. Each of these
# must sit inside the cache fingerprint: if one drops out, the stamp could call a job
# dir reusable that Harbor will then reject. `agents` also carries the agent contents,
# which the stamp digests separately (that is why `agent_dir` itself is irrelevant).
_STAMP_COVERED_HARBOR_FIELDS = {
    "n_attempts": {"n_attempts"},
    "artifacts": {"artifacts", "trace_dir"},
    "retry": {"max_retries"},
    "agents": {"agent_name", "agent_import_path", "agent_model_name"},
    "timeout_multiplier": {"timeout_multiplier"},
    "agent_timeout_multiplier": {"agent_timeout_multiplier"},
    "verifier_timeout_multiplier": {"verifier_timeout_multiplier"},
    "agent_setup_timeout_multiplier": {"agent_setup_timeout_multiplier"},
    "environment_build_timeout_multiplier": {"environment_build_timeout_multiplier"},
}
# Left at Harbor's defaults by _build_native_job, so two SDK-built configs can never
# disagree on them. (A dir written by the Harbor CLI could, but it carries no SDK cache
# stamp, so it is stale and gets discarded before Harbor ever sees it.)
_SDK_NEVER_SETS = {"install_only", "environment", "verifier", "metrics", "tasks", "extra_instruction_paths"}
# Compared by Harbor, deliberately *not* keyed by the SDK stamp. Harbor asks "can I
# resume this directory?"; the stamp asks "did these inputs produce these results?".
# Where the answers diverge, _build_native_job absorbs Harbor's refusal.
_KNOWINGLY_LOOSER = {
    "jobs_dir": "implied by having found the job dir at all",
    "n_concurrent_trials": "scheduling only; keying it would discard a cached run on a box with a different core count",
    "quiet": "display only; changes nothing about the results",
    "datasets": "`path` is covered by the per-task digests; the `task_names` filter is left unkeyed so a subset of a "
    "cached job still hits (see _stamp_coverage)",
}


def test_harbor_still_words_its_resume_refusals_the_way_we_match_them() -> None:
    # The predicate that authorises deleting a job dir keys off Harbor's message text.
    # If Harbor rewords, the predicate stops matching and the refusal propagates as a
    # crash — the safe direction, but a silent loss of the graceful re-run. Catch that
    # at upgrade time here instead of in someone's failed experiment.
    pytest.importorskip("harbor.job", reason="harbor needs python >= 3.12")
    import inspect

    from harbor.job import Job
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import _HARBOR_RESUME_REFUSALS

    source = inspect.getsource(Job)
    for phrase in _HARBOR_RESUME_REFUSALS:
        assert phrase in source, (
            f"Harbor no longer raises its resume refusal with {phrase!r}. Re-read Job._maybe_init_existing_job "
            "and Job._write_job_lock, then update _HARBOR_RESUME_REFUSALS. Keep each phrase inside a single "
            "source string literal — one spanning an implicit concatenation will not be found here."
        )


def test_harbor_job_config_equality_still_behaves_as_the_retry_assumes() -> None:
    # The FileExistsError retry exists because Harbor compares its whole JobConfig and
    # ignores only identity/logging fields. Pin that behaviourally, so a Harbor upgrade
    # that changes the rule surfaces here rather than as a mystery re-run in production.
    job_config = pytest.importorskip("harbor.models.job.config", reason="harbor needs python >= 3.12")

    baseline = job_config.JobConfig(job_name="a")
    assert baseline == job_config.JobConfig(job_name="b"), "job_name must stay outside Harbor's comparison"
    assert baseline != job_config.JobConfig(job_name="a", n_concurrent_trials=99), (
        "n_concurrent_trials must stay inside it — that is the case the retry absorbs"
    )


def test_every_harbor_job_config_field_is_classified_against_the_sdk_stamp() -> None:
    # Drift guard. The SDK's fingerprint is deliberately looser than Harbor's
    # comparison, but only in ways we have reasoned about. A Harbor upgrade that adds a
    # compared field would silently widen that gap into unexplained full re-runs, so
    # every field must land in exactly one bucket before it can ship.
    job_config = pytest.importorskip("harbor.models.job.config", reason="harbor needs python >= 3.12")
    from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (
        _CACHE_IRRELEVANT_OPTIONS,
        _HARBOR_EQ_IGNORED_FIELDS,
    )

    # Derived, not hardcoded: dropping a field into _CACHE_IRRELEVANT_OPTIONS re-checks
    # here instead of quietly diverging from a copied list.
    fingerprinted = set(HarborRuntimeConfig.model_fields) - set(_CACHE_IRRELEVANT_OPTIONS)
    for harbor_field, sdk_fields in _STAMP_COVERED_HARBOR_FIELDS.items():
        missing = sdk_fields - fingerprinted
        assert not missing, (
            f"Harbor compares {harbor_field!r}, but {sorted(missing)} left the cache fingerprint. "
            "Either restore it, or move the field to _KNOWINGLY_LOOSER with a reason."
        )

    classified = (
        set(_HARBOR_EQ_IGNORED_FIELDS) | _SDK_NEVER_SETS | set(_STAMP_COVERED_HARBOR_FIELDS) | set(_KNOWINGLY_LOOSER)
    )
    actual = set(job_config.JobConfig.model_fields)
    assert not actual - classified, (
        f"Harbor's JobConfig grew {sorted(actual - classified)}. Classify each one: covered by the cache stamp "
        "(_STAMP_COVERED_HARBOR_FIELDS), never set by the SDK (_SDK_NEVER_SETS), or knowingly unkeyed "
        "(_KNOWINGLY_LOOSER, with a reason)."
    )
    assert not classified - actual, (
        f"{sorted(classified - actual)} no longer exist on Harbor's JobConfig; drop them from the classification."
    )
