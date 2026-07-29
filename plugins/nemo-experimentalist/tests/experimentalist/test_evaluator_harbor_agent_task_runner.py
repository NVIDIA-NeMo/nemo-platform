# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression coverage for the SDK-backed Harbor evaluator.

Nothing here starts Docker: Harbor's ``Job`` is replaced with a fake that writes
the same on-disk tree a real run would, which is exactly the seam both evaluator
types read their results from.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import EvaluatorConfig
from nemo_experimentalist_plugin.experimentalist.components.evaluator.factory import EvaluatorFactory
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
    HarborEvaluator,
    HarborEvaluatorConfig,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor_agent_task_runner import (
    HarborRunnerConfig,
    HarborRunnerEvaluator,
    HarborTaskNameError,
    harbor_task_names,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import local_path_from_uri
from nemo_experimentalist_plugin.experimentalist.deps import ExperimentalistDeps
from nemo_experimentalist_plugin.resolve import EvolutionaryOptimizerConfig
from pydantic import ValidationError


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


pytestmark = pytest.mark.asyncio


def _dataset_root(dataset: HarborDataset) -> Path:
    assert dataset.source is not None
    return local_path_from_uri(dataset.source.uri, context="dataset").resolve()


def _write_task(task_dir: Path, full_name: str | None = None) -> None:
    """Write a minimal Harbor task whose ``[task].name`` differs from its directory."""
    name_block = f'\n[task]\nname = "{full_name}"\n' if full_name is not None else ""
    _write(task_dir / "task.toml", f'schema_version = "1.3"\n{name_block}')
    _write(task_dir / "instruction.md", f"do {task_dir.name}")
    _write(task_dir / "tests" / "test.sh", "echo reward")


def _write_trial(
    job_dir: Path,
    *,
    trial_name: str,
    task_name: str,
    task_dir: Path,
    rewards: dict[str, float] | None = None,
    exception_info: dict[str, str] | None = None,
) -> None:
    trial_dir = job_dir / trial_name
    _write(
        trial_dir / "result.json",
        json.dumps(
            {
                "trial_name": trial_name,
                "task_name": task_name,
                "task_id": {"path": str(task_dir.resolve())},
                "verifier_result": {"rewards": rewards if rewards is not None else {}},
                "exception_info": exception_info,
            }
        ),
    )


class _FakeJob:
    """Stand-in for Harbor's ``Job`` that records its config and writes trials."""

    calls: list[Any] = []
    on_run: Any = None

    def __init__(self, config: Any) -> None:
        self.config = config

    @classmethod
    async def create(cls, config: Any) -> _FakeJob:
        cls.calls.append(config)
        # Harbor's Job.create lays down the job dir before any trial runs.
        (Path(config.jobs_dir) / config.job_name).mkdir(parents=True, exist_ok=True)
        return cls(config)

    async def run(self) -> None:
        if type(self).on_run is not None:
            type(self).on_run(self.config)


@pytest.fixture
def fake_job(monkeypatch: pytest.MonkeyPatch) -> type[_FakeJob]:
    """Replace Harbor's ``Job`` for the duration of a test.

    The SDK imports ``Job`` inside its ``run_job`` closure, so patching the
    module attribute is enough — and it is the only Harbor piece faked, so the
    real ``JobConfig`` still validates everything the runtime builds.
    """
    pytest.importorskip("harbor")
    import harbor.job

    _FakeJob.calls = []
    _FakeJob.on_run = None
    monkeypatch.setattr(harbor.job, "Job", _FakeJob)
    return _FakeJob


@pytest.fixture
def dataset(tmp_path: Path) -> HarborDataset:
    """Two tasks whose full Harbor names are namespaced and share a basename prefix."""
    dataset_dir = tmp_path / "dataset" / "validation"
    _write_task(dataset_dir / "sum-two", "hello/sum-two")
    _write_task(dataset_dir / "sum-three", "hello/sum-three")
    return HarborDataset.from_path(dataset_dir)


@pytest.fixture
async def cached_job_dir(
    tmp_path: Path,
    dataset: HarborDataset,
    agent_dir: Path,
    fake_job: type[_FakeJob],
) -> Path:
    """A complete, all-successful cached job dir left by a genuine prior run.

    Driven through ``_run`` rather than hand-built so the SDK stamps its own cache
    key exactly as it would in production. Hand-stamping here would couple the test
    to the plugin-config → ``HarborRuntimeConfig`` mapping, and an *unstamped* dir is
    correctly untrusted — which would make every test using this fixture pass for
    the wrong reason.
    """
    job_dir = tmp_path / "jobs" / f"{agent_dir.name}-{dataset.id}"

    def write_complete_results(config: Any) -> None:
        for task in dataset.tasks:
            _write_trial(
                Path(config.jobs_dir) / config.job_name,
                trial_name=f"{task.id}__0",
                task_name=f"hello/{task.id}",
                task_dir=_dataset_root(dataset) / task.id,
                rewards={"reward": 1.0},
            )

    fake_job.on_run = write_complete_results
    await HarborRunnerEvaluator(experiment_dir=tmp_path)._run(
        agent_dir, dataset, HarborRunnerConfig(jobs_dir=Path("jobs"))
    )
    fake_job.calls = []
    fake_job.on_run = None
    return job_dir


@pytest.fixture
def agent_dir(tmp_path: Path) -> Path:
    path = tmp_path / "agents" / "agent-0"
    _write(path / "harbor_wrapper.py", "class WrappedAgent: ...\n")
    return path


# --------------------------------------------------------------------------
# Factory and configuration
# --------------------------------------------------------------------------


async def test_optimizer_config_defaults_to_the_sdk_runner() -> None:
    assert EvolutionaryOptimizerConfig().evaluator_type == "harbor_agent_task_runner"


async def test_deps_default_matches_the_optimizer_config_default() -> None:
    """The two defaults must not drift: run.py threads one into the other."""
    assert ExperimentalistDeps.model_fields["evaluator_type"].default == (
        EvolutionaryOptimizerConfig.model_fields["evaluator_type"].default
    )


async def test_optimizer_config_still_accepts_plain_harbor() -> None:
    """Plain Harbor stays selectable — it is the A/B baseline and the SDK-less fallback."""
    config = EvolutionaryOptimizerConfig.model_validate({"evaluator_type": "harbor"})
    assert config.evaluator_type == "harbor"


async def test_optimizer_config_rejects_unknown_evaluator_type() -> None:
    with pytest.raises(ValidationError):
        EvolutionaryOptimizerConfig.model_validate({"evaluator_type": "not-an-evaluator"})


async def test_factory_builds_sdk_evaluator(tmp_path: Path) -> None:
    evaluator = EvaluatorFactory().build_evaluator(
        "harbor_agent_task_runner",
        {"n_attempts": 3, "quiet": True},
        experiment_dir=tmp_path,
    )

    assert isinstance(evaluator, HarborRunnerEvaluator)
    assert evaluator.evaluator_type == "harbor_agent_task_runner"
    assert isinstance(evaluator.options, HarborRunnerConfig)
    assert evaluator.options.n_attempts == 3
    assert evaluator.experiment_dir == tmp_path


@pytest.mark.parametrize(
    "unsupported",
    [
        {"retry": {"max_retries": 2}},  # plain-Harbor RetryConfig has no SDK equivalent
        {"agent_dir": "/somewhere/else"},  # always derived from the candidate
        {"typo_option": 1},
    ],
)
async def test_sdk_config_rejects_unsupported_options(unsupported: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        HarborRunnerConfig.model_validate(unsupported)


async def test_plain_harbor_still_builds_when_sdk_runtime_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fallback must survive a broken SDK install.

    Now that ``harbor_agent_task_runner`` is the default, this is the escape
    hatch: a missing or partial SDK must still leave ``evaluator_type: harbor``
    constructible, and must fail with an actionable error rather than an
    AttributeError deep in the run.
    """
    monkeypatch.setitem(sys.modules, "nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime", None)

    assert isinstance(EvaluatorFactory().build_evaluator("harbor", {}), HarborEvaluator)
    with pytest.raises(ImportError, match="nemo-evaluator-sdk"):
        from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor_agent_task_runner import (
            _import_harbor_runtime,
        )

        _import_harbor_runtime()


# --------------------------------------------------------------------------
# Task-name mapping
# --------------------------------------------------------------------------


async def test_short_ids_map_to_full_harbor_names(dataset: HarborDataset) -> None:
    assert harbor_task_names(dataset) == {
        "sum-three": "hello/sum-three",
        "sum-two": "hello/sum-two",
    }


async def test_mapping_follows_dataset_subsets(dataset: HarborDataset) -> None:
    assert harbor_task_names(dataset.subset(["sum-two"])) == {"sum-two": "hello/sum-two"}


async def test_mapping_falls_back_to_directory_name_without_task_block(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "unnamed"
    _write_task(dataset_dir / "plain-task", full_name=None)

    assert harbor_task_names(HarborDataset.from_path(dataset_dir)) == {"plain-task": "plain-task"}


async def test_duplicate_full_names_are_rejected(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dupes"
    _write_task(dataset_dir / "task-a", "hello/same")
    _write_task(dataset_dir / "task-b", "hello/same")

    with pytest.raises(HarborTaskNameError, match="both declare"):
        harbor_task_names(HarborDataset.from_path(dataset_dir))


async def test_task_outside_the_dataset_directory_is_rejected(tmp_path: Path, dataset: HarborDataset) -> None:
    stray_dir = tmp_path / "stray" / "sum-four"
    _write_task(stray_dir, "hello/sum-four")
    stray = HarborDataset.from_path(stray_dir.parent).tasks[0]
    dataset.tasks.append(stray)

    with pytest.raises(HarborTaskNameError, match="was not discovered under dataset"):
        harbor_task_names(dataset)


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------


async def test_runner_receives_expected_job_config(
    tmp_path: Path,
    dataset: HarborDataset,
    agent_dir: Path,
    fake_job: type[_FakeJob],
) -> None:
    evaluator = HarborRunnerEvaluator(experiment_dir=tmp_path)
    options = HarborRunnerConfig(
        jobs_dir=Path("jobs"),
        n_attempts=2,
        n_concurrent_trials=3,
        quiet=True,
        max_retries=4,
        trace_dir="/app/traces",
        agent_timeout_multiplier=1.5,
        verifier_timeout_multiplier=2.0,
    )

    await evaluator._run(agent_dir, dataset, options)

    assert len(fake_job.calls) == 1
    config = fake_job.calls[0]
    assert config.job_name == f"{agent_dir.name}-{dataset.id}"
    assert config.jobs_dir == tmp_path / "jobs"
    assert config.n_attempts == 2
    assert config.n_concurrent_trials == 3
    assert config.quiet is True
    assert config.retry.max_retries == 4
    assert config.agent_timeout_multiplier == 1.5
    assert config.verifier_timeout_multiplier == 2.0

    # Harbor's local-dataset filter matches directory names, not [task].name.
    assert config.datasets[0].path == _dataset_root(dataset)
    assert sorted(config.datasets[0].task_names) == ["sum-three", "sum-two"]

    # Traces are collected as the 'traces' artifact so the Analyzer can read them.
    trace_artifacts = [a for a in config.artifacts if getattr(a, "destination", None) == "traces"]
    assert [a.source for a in trace_artifacts] == ["/app/traces"]

    # The wrapper is imported out of the candidate directory under a scoped package.
    import_path = config.agents[0].import_path
    assert import_path.endswith(".harbor_wrapper:WrappedAgent")
    assert import_path.startswith("_nemo_evaluator_harbor_agents.")
    # ...and the scoped package is torn down once the run finishes.
    assert not [name for name in sys.modules if name.startswith("_nemo_evaluator_harbor_agents.")]


async def test_complete_cached_job_is_not_rerun(
    tmp_path: Path,
    dataset: HarborDataset,
    agent_dir: Path,
    cached_job_dir: Path,
    fake_job: type[_FakeJob],
) -> None:
    trials = await HarborRunnerEvaluator(experiment_dir=tmp_path)._run(
        agent_dir, dataset, HarborRunnerConfig(jobs_dir=Path("jobs"))
    )

    assert fake_job.calls == []
    assert {trial.task_id for trial in trials} == {"sum-two", "sum-three"}


async def test_errored_cached_job_is_rerun(
    tmp_path: Path,
    dataset: HarborDataset,
    agent_dir: Path,
    cached_job_dir: Path,
    fake_job: type[_FakeJob],
) -> None:
    """An errored trial must force a rerun even when the cache is otherwise valid.

    Built on the *stamped* `cached_job_dir` on purpose. A hand-rolled job dir has
    no fingerprint, so it is rejected as untrusted and the run happens for that
    reason instead — the assertion would then hold even if error-awareness were
    completely broken. Mutating one trial in place keeps the stamp valid, so the
    error is the only thing left that can trigger the rerun.
    """
    errored = json.loads((cached_job_dir / "sum-three__0" / "result.json").read_text(encoding="utf-8"))
    errored["exception_info"] = {"exception_type": "TimeoutError"}
    _write(cached_job_dir / "sum-three__0" / "result.json", json.dumps(errored))

    await HarborRunnerEvaluator(experiment_dir=tmp_path)._run(
        agent_dir, dataset, HarborRunnerConfig(jobs_dir=Path("jobs"))
    )

    assert len(fake_job.calls) == 1, "an errored cached trial must not be served from cache"


async def test_under_sampled_cached_job_is_rerun(
    tmp_path: Path,
    dataset: HarborDataset,
    agent_dir: Path,
    cached_job_dir: Path,
    fake_job: type[_FakeJob],
) -> None:
    await HarborRunnerEvaluator(experiment_dir=tmp_path)._run(
        agent_dir, dataset, HarborRunnerConfig(jobs_dir=Path("jobs"), n_attempts=2)
    )

    assert len(fake_job.calls) == 1, "one cached attempt must not satisfy n_attempts=2"


async def test_force_rerun_discards_a_complete_cache(
    tmp_path: Path,
    dataset: HarborDataset,
    agent_dir: Path,
    cached_job_dir: Path,
    fake_job: type[_FakeJob],
) -> None:
    trials = await HarborRunnerEvaluator(experiment_dir=tmp_path)._run(
        agent_dir, dataset, HarborRunnerConfig(jobs_dir=Path("jobs"), force_rerun=True)
    )

    assert len(fake_job.calls) == 1
    assert list(cached_job_dir.glob("*/result.json")) == [], "force_rerun must clear the stale results"
    assert trials == []


async def test_concurrent_candidates_use_distinct_job_dirs(
    tmp_path: Path,
    dataset: HarborDataset,
    fake_job: type[_FakeJob],
) -> None:
    evaluator = HarborRunnerEvaluator(experiment_dir=tmp_path)
    options = HarborRunnerConfig(jobs_dir=Path("jobs"))
    for name in ("agent-0", "agent-1"):
        candidate = tmp_path / "agents" / name
        _write(candidate / "harbor_wrapper.py", "class WrappedAgent: ...\n")
        await evaluator._run(candidate, dataset, options)

    job_names = [config.job_name for config in fake_job.calls]
    assert job_names == [f"agent-0-{dataset.id}", f"agent-1-{dataset.id}"]
    assert len(set(job_names)) == 2


async def test_missing_agent_directory_fails_before_docker(
    tmp_path: Path,
    dataset: HarborDataset,
    fake_job: type[_FakeJob],
) -> None:
    with pytest.raises(FileNotFoundError, match="Harbor agent path not found"):
        await HarborRunnerEvaluator(experiment_dir=tmp_path)._run(tmp_path / "nope", dataset, HarborRunnerConfig())
    assert fake_job.calls == []


async def test_broken_verifier_fails_before_docker(
    tmp_path: Path,
    agent_dir: Path,
    fake_job: type[_FakeJob],
) -> None:
    dataset_dir = tmp_path / "broken"
    _write_task(dataset_dir / "task-a", "hello/task-a")
    _write(dataset_dir / "task-a" / "tests" / "test.sh", "if [ ; then\n")

    from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
        HarborVerifierValidationError,
    )

    with pytest.raises(HarborVerifierValidationError):
        await HarborRunnerEvaluator(experiment_dir=tmp_path)._run(
            agent_dir, HarborDataset.from_path(dataset_dir), HarborRunnerConfig()
        )
    assert fake_job.calls == []


async def test_wrong_options_type_is_rejected(tmp_path: Path, dataset: HarborDataset, agent_dir: Path) -> None:
    with pytest.raises(TypeError, match="HarborRunnerConfig"):
        await HarborRunnerEvaluator(experiment_dir=tmp_path)._run(agent_dir, dataset, EvaluatorConfig())


# --------------------------------------------------------------------------
# Result parity with the plain Harbor evaluator
# --------------------------------------------------------------------------


async def test_both_evaluators_produce_equivalent_trials(
    tmp_path: Path,
    dataset: HarborDataset,
    agent_dir: Path,
    fake_job: type[_FakeJob],
    monkeypatch: pytest.MonkeyPatch,
    comparable_trials: Any,
) -> None:
    """The two orchestrators differ; the trials they hand the loop must not."""
    dataset_dir = _dataset_root(dataset)

    def write_results(config: Any) -> None:
        job_dir = Path(config.jobs_dir) / config.job_name
        _write_trial(
            job_dir,
            trial_name="sum-two__0",
            task_name="hello/sum-two",
            task_dir=dataset_dir / "sum-two",
            rewards={"reward": 1.0, "format_ok": 1.0},
        )
        _write_trial(
            job_dir,
            trial_name="sum-three__0",
            task_name="hello/sum-three",
            task_dir=dataset_dir / "sum-three",
            rewards={"reward": 0.0, "format_ok": 1.0},
        )

    fake_job.on_run = write_results
    sdk_result = await HarborRunnerEvaluator(experiment_dir=tmp_path).run(
        agent_dir, dataset, HarborRunnerConfig(jobs_dir=Path("sdk-jobs"))
    )

    # The plain evaluator imports Job into its own module namespace.
    class PlainJob(_FakeJob):
        def __init__(self, config: Any) -> None:
            super().__init__(config)
            self.job_dir = Path(config.jobs_dir) / config.job_name

    monkeypatch.setattr(
        "nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor.Job",
        PlainJob,
    )
    PlainJob.on_run = write_results
    plain_result = await HarborEvaluator(experiment_dir=tmp_path).run(
        agent_dir, dataset, HarborEvaluatorConfig(jobs_dir=Path("plain-jobs"))
    )

    assert comparable_trials(sdk_result.trials, include_id=True) == comparable_trials(
        plain_result.trials, include_id=True
    )
    assert sdk_result.aggregate_metrics == plain_result.aggregate_metrics
    # Every verifier metric survives, not just the primary reward.
    assert sdk_result.aggregate_metrics == {"reward": 0.5, "format_ok": 1.0}


async def test_failed_trials_keep_their_error_shape(
    tmp_path: Path,
    dataset: HarborDataset,
    agent_dir: Path,
    fake_job: type[_FakeJob],
) -> None:
    dataset_dir = _dataset_root(dataset)

    def write_results(config: Any) -> None:
        job_dir = Path(config.jobs_dir) / config.job_name
        _write_trial(
            job_dir,
            trial_name="sum-two__0",
            task_name="hello/sum-two",
            task_dir=dataset_dir / "sum-two",
            rewards={"reward": 1.0},
        )
        _write_trial(
            job_dir,
            trial_name="sum-three__0",
            task_name="hello/sum-three",
            task_dir=dataset_dir / "sum-three",
            exception_info={"exception_type": "TimeoutError", "exception_message": "boom"},
        )

    fake_job.on_run = write_results
    trials = await HarborRunnerEvaluator(experiment_dir=tmp_path)._run(
        agent_dir, dataset, HarborRunnerConfig(jobs_dir=Path("jobs"))
    )

    by_task = {trial.task_id: trial for trial in trials}
    assert by_task["sum-three"].status == "failed"
    assert by_task["sum-three"].error == {"type": "TimeoutError", "message": "boom"}
    assert by_task["sum-two"].status == "completed"
    assert by_task["sum-two"].attempt == 0


# --------------------------------------------------------------------------
# The SDK owns cache identity now — verify the plugin is actually covered by it
# --------------------------------------------------------------------------


async def test_editing_the_candidate_invalidates_the_cache_through_the_sdk(
    tmp_path: Path,
    dataset: HarborDataset,
    agent_dir: Path,
    cached_job_dir: Path,
    fake_job: type[_FakeJob],
) -> None:
    """The staleness guard lives in the SDK; this asserts the plugin inherits it.

    Without it, editing a candidate and re-running in the same experiment directory
    silently returns the previous candidate's scores — which is the whole reason
    AALGO-427 exists.
    """
    _write(agent_dir / "harbor_wrapper.py", "class WrappedAgent:\n    version = 2\n")

    await HarborRunnerEvaluator(experiment_dir=tmp_path)._run(
        agent_dir, dataset, HarborRunnerConfig(jobs_dir=Path("jobs"))
    )

    assert len(fake_job.calls) == 1, "a changed candidate must not be served from cache"


async def test_unchanged_candidate_still_hits_the_cache(
    tmp_path: Path,
    dataset: HarborDataset,
    agent_dir: Path,
    cached_job_dir: Path,
    fake_job: type[_FakeJob],
) -> None:
    """The guard must not be so strict that it defeats caching entirely."""
    await HarborRunnerEvaluator(experiment_dir=tmp_path)._run(
        agent_dir, dataset, HarborRunnerConfig(jobs_dir=Path("jobs"))
    )

    assert fake_job.calls == []
