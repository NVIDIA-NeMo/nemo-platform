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
async def test_scoped_agent_import_always_discards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # With agent_dir set, scoped_harbor_agent_import bakes a fresh uuid into the
    # import path, so Harbor's own JobConfig never matches on a rerun and it raises
    # FileExistsError instead of resuming. Discard even when the stamp matches.
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "wrapper.py").write_text("x = 1\n")
    config, job_dir, task = _seed_cached_job(tmp_path)
    config = config.model_copy(update={"agent_import_path": "wrapper:Agent", "agent_dir": agent_dir, "n_attempts": 2})
    _stamp_for(config, task, job_dir)  # stamp matches; only coverage is short
    calls: list[bool] = []
    _spy_on_run_job(monkeypatch, calls)

    await HarborAgentTaskRunner(config=config).run_tasks([task])

    assert calls == [True]


@pytest.mark.asyncio
async def test_under_covered_job_resumes_when_harbor_can(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Inputs unchanged, some attempts missing, and agent_dir unset — Harbor's
    # AgentConfig is deterministic here, so it can resume per trial. Discarding
    # would throw away completed Docker work for nothing.
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
