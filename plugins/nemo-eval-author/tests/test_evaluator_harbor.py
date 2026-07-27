# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from nemo_eval_author_plugin.evaluator.harbor import (
    _TRACE_ARTIFACT_DESTINATION,
    _TRACE_ARTIFACT_SOURCE,
    HarborDataset,
    HarborDependencyContext,
    HarborDependencyRuntime,
    HarborEvaluator,
    HarborEvaluatorConfig,
    HarborVerifierValidationError,
    _chmod_path_chain,
    _cleanup_scoped_imports,
    _ensure_package,
    _python_syntax_failure,
    _safe_identifier,
    _scoped_import_path,
    _shell_syntax_failure,
    _trial_error,
    _trial_metric_spec,
    _trial_metrics,
    _trial_resources,
    _with_trace_artifact,
)
from nemo_eval_author_plugin.evaluator.models import (
    CommandSpec,
    Dataset,
    DatasetRef,
    DependencyContext,
    DependencyRuntime,
    MetricResult,
    MetricSpec,
    ResourceRef,
    Task,
    TrialResult,
    local_path_from_uri,
    run_dependency_command,
    subset_dataset_id,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    _write(path, json.dumps(data))


def _write_task_config(task_dir: Path, verifier_dir: str = "test") -> None:
    _write(
        task_dir / "task.toml",
        f"""
schema_version = "1.3"
artifacts = ["/tmp/output.txt"]

[task]
name = "harbor/{task_dir.name}"
description = "Synthetic Harbor task."

[metadata]
difficulty = "easy"

[agent]
timeout_sec = 10.0

[environment]
build_timeout_sec = 42.0
cpus = 1
memory_mb = 2048

[verifier]
directory = "{verifier_dir}"
timeout_sec = 5.0
""".lstrip(),
    )


def _recording_job(job_dir: Path):
    class RecordingJob:
        create_calls = 0
        run_calls = 0

        def __init__(self, config) -> None:
            self.config = config
            self.job_dir = job_dir

        @classmethod
        async def create(cls, config):
            cls.create_calls += 1
            job_dir.mkdir(parents=True, exist_ok=True)
            return cls(config)

        async def run(self):
            type(self).run_calls += 1
            return SimpleNamespace(id="job-id", stats=None)

    return RecordingJob


class _BlockingProcess:
    def __init__(self) -> None:
        self.returncode = None
        self.communicate_calls = 0
        self.killed = False
        self.started = asyncio.Event()

    async def communicate(self, _input=None):
        self.communicate_calls += 1
        if self.communicate_calls == 1:
            self.started.set()
            await asyncio.Event().wait()
        self.returncode = -9
        return b"", b""

    def kill(self) -> None:
        self.killed = True


def test_harbor_dataset_from_path_maps_task_output(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "harbor-dataset"
    task_dir = dataset_dir / "task-a"
    _write_task_config(task_dir)
    _write(task_dir / "instruction.md", "Solve the task.\n")
    _write(task_dir / "README.md", "README text.\n")
    _write(task_dir / "environment" / "docker-compose.yaml", "services: {}\n")
    _write(task_dir / "environment" / "nested" / "ignored.txt", "nested\n")
    _write(task_dir / "test" / "test.sh", "echo 1 > /logs/verifier/reward.json\n")
    _write(task_dir / "solution" / "solution.sh", "touch /tmp/output.txt\n")

    dataset = HarborDataset.from_path(dataset_dir)

    environment_description = (
        "Harbor task environment directory. Contains the container definition and supporting files Harbor uses "
        "to create the task environment, such as Dockerfile, docker-compose.yaml, singularity-compose.yaml, "
        "and dependency files."
    )
    verifier_description = (
        "Harbor verifier tests directory. Harbor copies this directory into the task environment at /tests "
        "after the agent phase, discovers test.{sh,ps1,cmd,bat}, and expects rewards under /logs/verifier "
        "as reward.txt or reward.json."
    )
    oracle_description = (
        "Harbor oracle solution directory. Harbor's OracleAgent copies this directory into the task environment "
        "at /solution and discovers solve.{sh,ps1,cmd,bat} as the reference solution script."
    )
    readme_ref = ResourceRef(uri=(task_dir / "README.md").resolve().as_uri(), description="Task README.")
    expected_config = {
        "schema_version": "1.3",
        "artifacts": ["/tmp/output.txt"],
        "task": {
            "name": "harbor/task-a",
            "description": "Synthetic Harbor task.",
        },
        "metadata": {"difficulty": "easy"},
        "agent": {"timeout_sec": 10.0},
        "environment": {
            "build_timeout_sec": 42.0,
            "cpus": 1,
            "memory_mb": 2048,
        },
        "verifier": {
            "directory": "test",
            "timeout_sec": 5.0,
        },
    }
    expected_task = Task(
        uri=task_dir.resolve().as_uri(),
        description="Harbor task root directory.",
        id="task-a",
        inputs={
            "instruction": "Solve the task.\n",
            "config": expected_config,
            "readme": readme_ref,
        },
        resources={
            "instruction": ResourceRef(
                uri=(task_dir / "instruction.md").resolve().as_uri(),
                description="Task instruction shown to the benchmark agent.",
            ),
            "readme": readme_ref,
            "task_dir": ResourceRef(uri=task_dir.resolve().as_uri(), description="Harbor task root directory."),
            "task_config": ResourceRef(
                uri=(task_dir / "task.toml").resolve().as_uri(),
                description="Harbor task configuration file.",
            ),
            "environment_dir": ResourceRef(
                uri=(task_dir / "environment").resolve().as_uri(),
                description=environment_description,
            ),
            "verifier_dir": ResourceRef(uri=(task_dir / "test").resolve().as_uri(), description=verifier_description),
            "oracle_dir": ResourceRef(uri=(task_dir / "solution").resolve().as_uri(), description=oracle_description),
        },
        metric_specs={
            "reward": MetricSpec(
                name="reward",
                description="Harbor verifier reward emitted for harbor/task-a.",
                ref=ResourceRef(uri=(task_dir / "test").resolve().as_uri(), description=verifier_description),
            )
        },
        dependencies=HarborDependencyRuntime(
            task_path=ResourceRef(
                uri=task_dir.resolve().as_uri(),
                description="Harbor task directory to start via Harbor EnvironmentFactory.",
            ),
            build_timeout_sec=42,
        ),
    )

    assert dataset.id == "harbor-dataset"
    assert dataset.source == ResourceRef(
        uri=dataset_dir.resolve().as_uri(),
        description="Harbor dataset root directory.",
    )
    assert dataset.tasks == [expected_task]
    assert dataset.metadata == {}


def test_harbor_dataset_from_plain_path_ref_and_sparse_task_output(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset-root"
    ignored_dir = dataset_dir / "not-a-task"
    ignored_dir.mkdir(parents=True)
    task_dir = dataset_dir / "task-b"
    _write(task_dir / "task.toml", "")
    _write(task_dir / "readme.md", "lowercase readme\n")

    dataset = HarborDataset.from_ref(DatasetRef(uri=str(dataset_dir), metadata={}))

    readme_ref = ResourceRef(uri=(task_dir / "readme.md").resolve().as_uri(), description="Task README.")
    expected_task = Task(
        uri=task_dir.resolve().as_uri(),
        description="Harbor task root directory.",
        id="task-b",
        inputs={"readme": readme_ref},
        resources={
            "readme": readme_ref,
            "task_dir": ResourceRef(uri=task_dir.resolve().as_uri(), description="Harbor task root directory."),
            "task_config": ResourceRef(
                uri=(task_dir / "task.toml").resolve().as_uri(),
                description="Harbor task configuration file.",
            ),
        },
        metric_specs={
            "reward": MetricSpec(
                name="reward",
                description="Harbor verifier reward emitted for this task.",
            )
        },
        dependencies=HarborDependencyRuntime(
            task_path=ResourceRef(
                uri=task_dir.resolve().as_uri(),
                description="Harbor task directory to start via Harbor EnvironmentFactory.",
            ),
        ),
    )

    assert dataset.id == "dataset-root"
    assert dataset.source == ResourceRef(
        uri=dataset_dir.resolve().as_uri(),
        description="Harbor dataset root directory.",
    )
    assert dataset.tasks == [expected_task]
    assert dataset.metadata == {}


def test_harbor_dataset_from_ref_selects_task_ids(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset-root"
    for task_id in ("task-c", "task-a", "task-b"):
        _write(dataset_dir / task_id / "task.toml", "")

    dataset = HarborDataset.from_ref(
        DatasetRef(
            uri=str(dataset_dir),
            metadata={"id": "canonical-suite", "task_ids": ["task-b", "task-a"]},
        )
    )

    assert [task.id for task in dataset.list_tasks()] == ["task-a", "task-b"]
    assert dataset.id == subset_dataset_id("canonical-suite", ["task-a", "task-b"])
    assert dataset.source == ResourceRef(
        uri=dataset_dir.resolve().as_uri(),
        description="Harbor dataset root directory.",
    )


def test_harbor_dataset_from_ref_rejects_missing_task_ids(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset-root"
    _write(dataset_dir / "task-a" / "task.toml", "")

    with pytest.raises(ValueError, match=r"Task id\(s\) not found.*task-missing"):
        HarborDataset.from_ref(
            DatasetRef(
                uri=str(dataset_dir),
                metadata={"task_ids": ["task-a", "task-missing"]},
            )
        )


@pytest.mark.parametrize(
    "task_ids",
    ["task-a", [], ["task-a", 7], [""], ["task-a", "task-a"]],
    ids=["not-list", "empty", "non-string", "empty-string", "duplicate"],
)
def test_harbor_dataset_from_ref_validates_task_ids(tmp_path: Path, task_ids: object) -> None:
    dataset_dir = tmp_path / "dataset-root"
    _write(dataset_dir / "task-a" / "task.toml", "")

    with pytest.raises(ValueError, match="task_ids"):
        HarborDataset.from_ref(
            DatasetRef(
                uri=str(dataset_dir),
                metadata={"task_ids": task_ids},  # type: ignore[dict-item]
            )
        )


def test_harbor_dataset_maps_step_edge_cases(tmp_path: Path) -> None:
    task_dir = tmp_path / "step-edge-task"
    _write(
        task_dir / "task.toml",
        """
[task]
name = "plain-task-name"

[[steps]]

[[steps]]
name = ""

[[steps]]
name = "missing-instruction"
""".lstrip(),
    )

    dataset = HarborDataset.from_path(task_dir)

    expected_task = Task(
        uri=task_dir.resolve().as_uri(),
        description="Harbor task root directory.",
        id="step-edge-task",
        inputs={
            "steps": [
                {
                    "name": "missing-instruction",
                    "instruction": None,
                    "config": {"name": "missing-instruction"},
                }
            ],
            "instruction": "",
            "config": {
                "task": {"name": "plain-task-name"},
                "steps": [{}, {"name": ""}, {"name": "missing-instruction"}],
            },
        },
        resources={
            "task_dir": ResourceRef(uri=task_dir.resolve().as_uri(), description="Harbor task root directory."),
            "task_config": ResourceRef(
                uri=(task_dir / "task.toml").resolve().as_uri(),
                description="Harbor task configuration file.",
            ),
        },
        metric_specs={
            "reward": MetricSpec(
                name="reward",
                description="Harbor verifier reward emitted for plain-task-name.",
            )
        },
        dependencies=HarborDependencyRuntime(
            task_path=ResourceRef(
                uri=task_dir.resolve().as_uri(),
                description="Harbor task directory to start via Harbor EnvironmentFactory.",
            ),
        ),
    )

    assert dataset.tasks == [expected_task]


def test_harbor_dataset_from_ref_and_multistep_output(tmp_path: Path) -> None:
    task_dir = tmp_path / "multi-step-task"
    _write(
        task_dir / "task.toml",
        """
version = "1.0"

[[steps]]
name = "create-file"

[steps.agent]
timeout_sec = 10.0

[[steps]]
name = "append-content"

[steps.verifier]
timeout_sec = 5.0
""".lstrip(),
    )
    _write(task_dir / "steps" / "create-file" / "instruction.md", "Create a file.\n")
    _write(task_dir / "steps" / "append-content" / "instruction.md", "Append content.\n")
    _write(task_dir / "tests" / "test.sh", "echo 1 > /logs/verifier/reward.json\n")

    dataset = HarborDataset.from_ref(
        DatasetRef(
            uri=task_dir.resolve().as_uri(),
            metadata={"id": "custom-id"},
        )
    )

    verifier_description = (
        "Harbor verifier tests directory. Harbor copies this directory into the task environment at /tests "
        "after the agent phase, discovers test.{sh,ps1,cmd,bat}, and expects rewards under /logs/verifier "
        "as reward.txt or reward.json."
    )
    steps_description = (
        "Harbor multi-step task directory. Contains one subdirectory per [[steps]] entry; each step can provide "
        "instruction.md plus step-specific tests/ and solution/ directories that Harbor uses like the top-level "
        "verifier and oracle directories."
    )
    expected_config = {
        "version": "1.0",
        "steps": [
            {"name": "create-file", "agent": {"timeout_sec": 10.0}},
            {"name": "append-content", "verifier": {"timeout_sec": 5.0}},
        ],
    }
    expected_task = Task(
        uri=task_dir.resolve().as_uri(),
        description="Harbor task root directory.",
        id="multi-step-task",
        inputs={
            "steps": [
                {
                    "name": "create-file",
                    "instruction": "Create a file.",
                    "config": {"name": "create-file", "agent": {"timeout_sec": 10.0}},
                },
                {
                    "name": "append-content",
                    "instruction": "Append content.",
                    "config": {"name": "append-content", "verifier": {"timeout_sec": 5.0}},
                },
            ],
            "instruction": (
                "## Step 1: create-file\n\nCreate a file.\n\n---\n\n## Step 2: append-content\n\nAppend content."
            ),
            "config": expected_config,
        },
        resources={
            "step_1_instruction": ResourceRef(
                uri=(task_dir / "steps" / "create-file" / "instruction.md").resolve().as_uri(),
                description="Instruction for Harbor task step create-file.",
            ),
            "step_2_instruction": ResourceRef(
                uri=(task_dir / "steps" / "append-content" / "instruction.md").resolve().as_uri(),
                description="Instruction for Harbor task step append-content.",
            ),
            "task_dir": ResourceRef(uri=task_dir.resolve().as_uri(), description="Harbor task root directory."),
            "task_config": ResourceRef(
                uri=(task_dir / "task.toml").resolve().as_uri(),
                description="Harbor task configuration file.",
            ),
            "verifier_dir": ResourceRef(uri=(task_dir / "tests").resolve().as_uri(), description=verifier_description),
            "steps_dir": ResourceRef(uri=(task_dir / "steps").resolve().as_uri(), description=steps_description),
        },
        metric_specs={
            "reward": MetricSpec(
                name="reward",
                description="Harbor verifier reward emitted for this task.",
                ref=ResourceRef(uri=(task_dir / "tests").resolve().as_uri(), description=verifier_description),
            )
        },
        dependencies=HarborDependencyRuntime(
            task_path=ResourceRef(
                uri=task_dir.resolve().as_uri(),
                description="Harbor task directory to start via Harbor EnvironmentFactory.",
            ),
        ),
    )

    assert dataset.id == "custom-id"
    assert dataset.source == ResourceRef(
        uri=task_dir.resolve().as_uri(),
        description="Harbor dataset root directory.",
    )
    assert dataset.tasks == [expected_task]
    assert dataset.metadata == {}

    subset = dataset.subset(["multi-step-task"])
    assert subset.id == subset_dataset_id("custom-id", ["multi-step-task"])
    assert subset.tasks == [expected_task]


def test_harbor_dataset_rejects_invalid_refs_and_paths(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Harbor dataset path not found"):
        HarborDataset.from_path(tmp_path / "missing")

    file_path = tmp_path / "not-a-directory"
    file_path.write_text("not a dataset", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        HarborDataset.from_path(file_path)

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(ValueError, match="contains no Harbor task directories"):
        HarborDataset.from_path(empty_dir)

    with pytest.raises(ValueError, match="metadata field 'id' must be a string"):
        HarborDataset.from_ref(DatasetRef(uri=str(tmp_path), metadata={"id": 1}))

    with pytest.raises(ValueError, match="Harbor dataset reference file URI must be local"):
        HarborDataset.from_ref(DatasetRef(uri="file://remote-host/tmp/dataset"))

    with pytest.raises(ValueError, match="URI scheme 's3'"):
        HarborDataset.from_ref(DatasetRef(uri="s3://bucket/dataset"))


def test_harbor_dataset_rejects_missing_task_ids(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-a"
    _write(task_dir / "task.toml", "")
    dataset = HarborDataset.from_path(task_dir)

    with pytest.raises(ValueError, match="Task id not found"):
        dataset.get_task("missing")

    with pytest.raises(ValueError, match="Task id\\(s\\) not found"):
        dataset.subset(["missing"])


@pytest.mark.asyncio
async def test_harbor_trial_metric_spec_uses_task_verifier_dir(tmp_path: Path) -> None:
    task_dir = tmp_path / "dataset" / "task-a"
    _write(task_dir / "task.toml", "")
    _write(task_dir / "tests" / "test.sh", "echo reward")

    trial_dir = tmp_path / "job" / "task-a__0"
    _write_json(
        trial_dir / "result.json",
        {
            "task_name": "terminal-bench/task-a",
            "trial_name": "task-a__0",
            "task_id": {"path": str(task_dir.resolve())},
            "verifier_result": {"rewards": {"reward": 0.5}},
            "exception_info": None,
        },
    )
    _write(trial_dir / "verifier" / "reward.txt", "0.5")

    trials = await HarborEvaluator()._trials_from_dir(
        tmp_path / "job",
        [Task(id="task-a", metric_specs={"reward": MetricSpec(name="reward", description="reward")})],
    )

    verifier_description = (
        "Harbor verifier tests directory. Harbor copies this directory into the task environment at /tests "
        "after the agent phase, discovers test.{sh,ps1,cmd,bat}, and expects rewards under /logs/verifier "
        "as reward.txt or reward.json."
    )
    metric_spec = MetricSpec(
        name="reward",
        description="Harbor verifier reward emitted for terminal-bench/task-a.",
        ref=ResourceRef(uri=(task_dir / "tests").resolve().as_uri(), description=verifier_description),
    )
    assert trials == [
        TrialResult(
            id="task-a__0",
            task_id="task-a",
            attempt=0,
            status="completed",
            resources={
                "trial_dir": ResourceRef(
                    uri=trial_dir.resolve().as_uri(),
                    description=(
                        "Harbor trial output directory for one task attempt. Contains config.json, result.json, "
                        "trial.log, agent logs, verifier logs, and collected artifacts."
                    ),
                ),
                "result": ResourceRef(
                    uri=(trial_dir / "result.json").resolve().as_uri(),
                    description=(
                        "Harbor trial result JSON. Contains task and trial identifiers, agent info, verifier rewards, "
                        "exception info, phase timings, and token or cost usage."
                    ),
                ),
                "log:verifier/reward.txt": ResourceRef(
                    uri=(trial_dir / "verifier" / "reward.txt").resolve().as_uri(),
                    description=(
                        "Verifier scalar reward file written under /logs/verifier. Harbor parses this file as the "
                        "reward metric."
                    ),
                ),
            },
            metrics={
                "reward": MetricResult(
                    name="reward",
                    value=0.5,
                    spec=metric_spec,
                )
            },
        )
    ]


@pytest.mark.asyncio
async def test_harbor_evaluator_runs_job_and_maps_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    evaluator = HarborEvaluator()
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    dataset_dir = tmp_path / "dataset"
    task_a = dataset_dir / "task-a"
    task_b = dataset_dir / "task-b"
    _write(task_a / "task.toml", "")
    _write(task_a / "test" / "test.sh", "echo 1")
    _write(task_b / "task.toml", "")
    harbor_dataset = HarborDataset.from_path(dataset_dir)

    job_dir = tmp_path / "jobs" / "agent-0-validation"
    trial_a = job_dir / "task-a__0"
    _write_json(
        trial_a / "result.json",
        {
            "task_name": "harbor/task-a",
            "trial_name": "task-a__0",
            "trial_uri": trial_a.resolve().as_uri(),
            "task_id": {"path": str(task_a.resolve())},
            "verifier_result": {"rewards": {"reward": 1.0}},
            "exception_info": None,
        },
    )
    _write(trial_a / "config.json", "{}")
    _write(trial_a / "trial.log", "ok")
    _write(trial_a / "agent" / "setup" / "stdout.txt", "setup")
    _write(trial_a / "agent" / "command-0" / "stdout.txt", "command")
    _write(trial_a / "verifier" / "reward.txt", "1.0")
    _write(trial_a / "verifier" / "test-stdout.txt", "stdout")
    _write(trial_a / "verifier" / "test-stderr.txt", "stderr")
    trace_path = trial_a / "artifacts" / "traces" / "trace.jsonl"
    _write(trace_path, "{}")
    _write(trial_a / "artifacts" / "logs" / "artifacts" / "output.txt", "published")
    _write(trial_a / "artifacts" / "manifest.json", "[]")

    trial_b = job_dir / "task-b__1"
    _write_json(
        trial_b / "result.json",
        {
            "task_name": "harbor/task-b",
            "trial_name": "task-b__1",
            "trial_uri": trial_b.resolve().as_uri(),
            "verifier_result": None,
            "exception_info": {
                "exception_type": "ValueError",
                "exception_message": "bad task",
                "exception_traceback": "traceback",
            },
        },
    )

    trial_c = job_dir / "task-c__abc"
    _write_json(
        trial_c / "result.json",
        {
            "trial_name": "task-c__abc",
            "trial_uri": trial_c.resolve().as_uri(),
            "verifier_result": None,
            "exception_info": None,
        },
    )
    _write_json(trial_c / "verifier" / "reward.json", {"reward": 0.25})

    trial_d = job_dir / "task-d__2"
    _write_json(
        trial_d / "result.json",
        {
            "task_name": "harbor/task-d",
            "trial_name": "task-d__2",
            "trial_uri": trial_d.resolve().as_uri(),
            "verifier_result": None,
            "exception_info": None,
        },
    )
    _write(trial_d / "verifier" / "reward.txt", "0.75")

    (job_dir / "not-a-trial").mkdir(parents=True)

    class FakeStats:
        def model_dump(self, mode: str) -> dict:
            return {
                "evals": {
                    "agent__dataset": {
                        "metrics": [{"mean": 0.5}],
                        "reward_stats": {},
                        "exception_stats": {},
                    }
                }
            }

    class FakeJob:
        created_config = None

        def __init__(self, config) -> None:
            self.config = config
            self.job_dir = job_dir

        @classmethod
        async def create(cls, config):
            cls.created_config = config
            return cls(config)

        async def run(self):
            return SimpleNamespace(id="job-id", stats=FakeStats())

    monkeypatch.setattr("nemo_eval_author_plugin.evaluator.harbor.Job", FakeJob)

    result = await evaluator.run(
        agent=tmp_path / "agent",
        dataset=harbor_dataset,
        options=HarborEvaluatorConfig(import_path="harbor_wrapper:WrappedAgent", jobs_dir=tmp_path / "jobs"),
    )

    assert result.id == "agent-dataset"
    assert result.aggregate_metrics["reward"] == pytest.approx(2 / 3)
    assert str((tmp_path / "agent").resolve()) not in sys.path
    assert "harbor_wrapper" not in sys.modules
    assert FakeJob.created_config.agents[0].import_path.startswith("_nemo_experimentalist_eval_agents.")
    assert FakeJob.created_config.agents[0].import_path.endswith(".harbor_wrapper:WrappedAgent")
    assert FakeJob.created_config.datasets[0].path == dataset_dir.resolve()
    assert FakeJob.created_config.datasets[0].task_names == ["task-a", "task-b"]

    first_trial = result.trials[0]
    assert first_trial.id == "task-a__0"
    assert first_trial.task_id == "task-a"
    assert first_trial.attempt == 0
    assert first_trial.status == "completed"
    assert first_trial.metrics["reward"].value == 1.0
    assert first_trial.metrics["reward"].spec is not None
    assert first_trial.metrics["reward"].spec.ref is not None
    assert first_trial.metrics["reward"].spec.ref.uri == (task_a / "test").resolve().as_uri()
    assert first_trial.trace is not None
    assert first_trial.trace.uri == trace_path.resolve().as_uri()
    assert set(first_trial.resources) >= {
        "artifact:logs/artifacts/output.txt",
        "artifact:manifest.json",
        "config",
        "log:agent/command-0/stdout.txt",
        "log:agent/setup/stdout.txt",
        "log:trial.log",
        "log:verifier/reward.txt",
        "log:verifier/test-stderr.txt",
        "log:verifier/test-stdout.txt",
        "result",
        "trace:traces/trace.jsonl",
        "trial_dir",
    }
    expected_resource_descriptions = {
        "trial_dir": (
            "Harbor trial output directory for one task attempt. Contains config.json, result.json, trial.log, agent "
            "logs, verifier logs, and collected artifacts."
        ),
        "config": (
            "Harbor trial configuration snapshot. Records the task, agent, environment, verifier, artifact collection, "
            "and job id used for this attempt."
        ),
        "result": (
            "Harbor trial result JSON. Contains task and trial identifiers, agent info, verifier rewards, exception "
            "info, phase timings, and token or cost usage."
        ),
        "trace:traces/trace.jsonl": "Agent execution trace JSONL for traces/trace.jsonl.",
        "log:agent/command-0/stdout.txt": "Agent command stdout captured while Harbor runs the benchmark agent.",
        "log:agent/setup/stdout.txt": (
            "Agent setup stdout captured while Harbor uploads the agent and installs dependencies."
        ),
        "log:trial.log": (
            "Harbor trial orchestration log covering environment setup, agent execution, verifier execution, artifact "
            "collection, and cleanup."
        ),
        "log:verifier/reward.txt": (
            "Verifier scalar reward file written under /logs/verifier. Harbor parses this file as the reward metric."
        ),
        "log:verifier/test-stderr.txt": (
            "Verifier stderr captured while Harbor runs the task tests from the /tests directory."
        ),
        "log:verifier/test-stdout.txt": (
            "Verifier stdout captured while Harbor runs the task tests from the /tests directory."
        ),
        "artifact:manifest.json": (
            "Harbor artifact manifest. Lists collected artifact files and the environment paths they were copied from."
        ),
        "artifact:logs/artifacts/output.txt": "Collected Harbor artifact logs/artifacts/output.txt.",
    }
    assert {key: first_trial.resources[key].description for key in expected_resource_descriptions} == (
        expected_resource_descriptions
    )

    second_trial = result.trials[1]
    assert second_trial.id == "task-b__1"
    assert second_trial.status == "failed"
    assert second_trial.error == {
        "type": "ValueError",
        "message": "bad task",
        "traceback": "traceback",
    }

    third_trial = result.trials[2]
    assert third_trial.id == "task-c__abc"
    assert third_trial.task_id == "task-c"
    assert third_trial.attempt is None
    assert third_trial.metrics["reward"].value == 0.25
    assert third_trial.metrics["reward"].spec is not None
    assert third_trial.metrics["reward"].spec.ref is not None
    assert third_trial.metrics["reward"].spec.ref.uri == (trial_c / "verifier").resolve().as_uri()
    assert (
        third_trial.resources["log:verifier/reward.json"].uri
        == (trial_c / "verifier" / "reward.json").resolve().as_uri()
    )

    fourth_trial = result.trials[3]
    assert fourth_trial.id == "task-d__2"
    assert fourth_trial.metrics["reward"].value == 0.75


@pytest.mark.asyncio
async def test_harbor_evaluator_rejects_invalid_python_verifiers_before_job_create(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    dataset_dir = tmp_path / "dataset"
    invalid_source = "def check():\n    try:\n        pass\n"
    for task_id in ("task-a", "task-b"):
        task_dir = dataset_dir / task_id
        _write(task_dir / "task.toml", "")
        _write(task_dir / "tests" / "check_tool_hallucination.py", invalid_source)

    dataset = HarborDataset.from_path(dataset_dir)
    fake_job = _recording_job(tmp_path / "jobs" / "preflight")
    monkeypatch.setattr("nemo_eval_author_plugin.evaluator.harbor.Job", fake_job)
    compile_calls = 0
    original_compile = compile

    def counting_compile(source, filename, mode):
        nonlocal compile_calls
        compile_calls += 1
        return original_compile(source, filename, mode)

    monkeypatch.setattr("builtins.compile", counting_compile)

    with pytest.raises(HarborVerifierValidationError) as exc_info:
        await HarborEvaluator()._run(agent_dir, dataset, HarborEvaluatorConfig())

    message = str(exc_info.value)
    assert "task 'task-a'" in message
    assert "task 'task-b'" in message
    assert message.count("check_tool_hallucination.py:3:13") == 2
    assert "SyntaxError: expected 'except' or 'finally' block" in message
    assert compile_calls == 1
    assert fake_job.create_calls == 0
    assert fake_job.run_calls == 0


def test_python_syntax_failure_reports_recursion_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_recursion_error(_source, _filename, _mode):
        raise RecursionError("maximum recursion depth exceeded during compilation")

    monkeypatch.setattr("builtins.compile", raise_recursion_error)

    failure = _python_syntax_failure("deeply nested source", tmp_path / "check.py")

    assert failure is not None
    assert failure.error == "RecursionError: maximum recursion depth exceeded during compilation"
    assert failure.line is None
    assert failure.column is None


@pytest.mark.asyncio
async def test_shell_syntax_failure_kills_process_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _BlockingProcess()
    process_args = []
    process_options = {}

    async def create_process(*_args, **_kwargs):
        process_args.extend(_args)
        process_options.update(_kwargs)
        return process

    monkeypatch.setenv("NVIDIA_API_KEY", "secret")
    monkeypatch.setattr("asyncio.create_subprocess_exec", create_process)
    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor._SHELL_SYNTAX_TIMEOUT_SEC",
        0.01,
    )

    with pytest.raises(TimeoutError):
        await _shell_syntax_failure("echo valid\n")

    assert process.killed
    assert process.communicate_calls == 2
    assert "-n" in process_args
    assert process_options["env"] == {"LC_ALL": "C", "PATH": os.defpath, "SHELLOPTS": "noexec"}
    assert "NVIDIA_API_KEY" not in process_options["env"]


@pytest.mark.asyncio
async def test_shell_noexec_environment_prevents_execution_without_n_flag() -> None:
    bash_path = shutil.which("bash", path=os.defpath)
    assert bash_path is not None
    process = await asyncio.create_subprocess_exec(
        bash_path,
        "--noprofile",
        "--norc",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={"LC_ALL": "C", "PATH": os.defpath, "SHELLOPTS": "noexec"},
    )

    stdout, _ = await process.communicate(b"printf 'EXECUTED\\n'\n")

    assert process.returncode == 0
    assert stdout == b""


@pytest.mark.asyncio
async def test_shell_syntax_failure_kills_process_on_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _BlockingProcess()

    async def create_process(*_args, **_kwargs):
        return process

    monkeypatch.setattr("asyncio.create_subprocess_exec", create_process)

    validation = asyncio.create_task(_shell_syntax_failure("echo valid\n"))
    await process.started.wait()
    validation.cancel()

    with pytest.raises(asyncio.CancelledError):
        await validation

    assert process.killed
    assert process.communicate_calls == 2


@pytest.mark.asyncio
async def test_harbor_evaluator_accepts_valid_python_verifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    task_dir = tmp_path / "task-a"
    _write(task_dir / "task.toml", "")
    _write(task_dir / "tests" / "check.py", "def check():\n    return True\n")
    dataset = HarborDataset.from_path(task_dir)
    fake_job = _recording_job(tmp_path / "jobs" / "valid-python")
    monkeypatch.setattr("nemo_eval_author_plugin.evaluator.harbor.Job", fake_job)

    trials = await HarborEvaluator()._run(agent_dir, dataset, HarborEvaluatorConfig())

    assert trials == []
    assert fake_job.create_calls == 1
    assert fake_job.run_calls == 1


@pytest.mark.asyncio
async def test_harbor_evaluator_rejects_invalid_configured_test_sh_before_job_create(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    task_dir = tmp_path / "task-a"
    _write_task_config(task_dir, verifier_dir="test")
    _write(task_dir / "tests" / "test.sh", "echo ignored\n")
    _write(task_dir / "test" / "test.sh", "if true; then\n  echo broken\n")
    dataset = HarborDataset.from_path(task_dir)
    fake_job = _recording_job(tmp_path / "jobs" / "invalid-shell")
    monkeypatch.setattr("nemo_eval_author_plugin.evaluator.harbor.Job", fake_job)

    with pytest.raises(HarborVerifierValidationError) as exc_info:
        await HarborEvaluator()._run(agent_dir, dataset, HarborEvaluatorConfig())

    message = str(exc_info.value)
    assert "task 'task-a'" in message
    assert str((task_dir / "test" / "test.sh").resolve()) in message
    assert "syntax error" in message
    assert fake_job.create_calls == 0
    assert fake_job.run_calls == 0


@pytest.mark.asyncio
async def test_harbor_evaluator_accepts_valid_legacy_test_sh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    task_dir = tmp_path / "task-a"
    _write(task_dir / "task.toml", "")
    _write(task_dir / "test" / "test.sh", "if true; then\n  echo valid\nfi\n")
    dataset = HarborDataset.from_path(task_dir)
    fake_job = _recording_job(tmp_path / "jobs" / "valid-shell")
    monkeypatch.setattr("nemo_eval_author_plugin.evaluator.harbor.Job", fake_job)

    trials = await HarborEvaluator()._run(agent_dir, dataset, HarborEvaluatorConfig())

    assert trials == []
    assert fake_job.create_calls == 1
    assert fake_job.run_calls == 1


@pytest.mark.asyncio
async def test_harbor_evaluator_rejects_invalid_inputs(tmp_path: Path) -> None:
    evaluator = HarborEvaluator()
    task_dir = tmp_path / "task-a"
    _write(task_dir / "task.toml", "")
    harbor_dataset = HarborDataset.from_path(task_dir)

    with pytest.raises(ValueError, match="Dataset must be a Harbor dataset"):
        await evaluator.run(agent=tmp_path, dataset=Dataset(id="base"), options={"import_path": "agent:Agent"})

    with pytest.raises(ValueError, match="Harbor dataset source is required"):
        await evaluator.run(agent=tmp_path, dataset=HarborDataset(id="manual"), options={"import_path": "agent:Agent"})

    with pytest.raises(FileNotFoundError, match="Harbor agent path not found"):
        await evaluator.run(
            agent=tmp_path / "nonexistent",
            dataset=harbor_dataset,
            options=HarborEvaluatorConfig(),
        )


# ── harbor.py additional coverage ────────────────────────────────────────────


def test_harbor_dependency_runtime_context():
    runtime = HarborDependencyRuntime(task_path=ResourceRef(uri="file:///tmp/task", description=""))
    ctx = runtime.context()
    assert isinstance(ctx, HarborDependencyContext)


@pytest.mark.asyncio
async def test_harbor_dependency_context_enter_exit(monkeypatch):
    runtime = HarborDependencyRuntime(task_path=ResourceRef(uri="file:///tmp/task", description=""))

    async def fake_start(self):
        pass

    async def fake_stop(self):
        pass

    monkeypatch.setattr(HarborDependencyContext, "_start_harbor_runtime", fake_start)
    monkeypatch.setattr(HarborDependencyContext, "_stop_started_runtime", fake_stop)

    ctx = HarborDependencyContext(runtime)
    entered = await ctx.__aenter__()
    assert entered is runtime
    result = await ctx.__aexit__(None, None, None)
    assert result is False


@pytest.mark.asyncio
async def test_harbor_dependency_context_enter_failure_calls_stop(monkeypatch):
    runtime = HarborDependencyRuntime(task_path=ResourceRef(uri="file:///tmp/task", description=""))
    stop_called = []

    async def fake_start(self):
        raise RuntimeError("start failed")

    async def fake_stop(self):
        stop_called.append(True)

    monkeypatch.setattr(HarborDependencyContext, "_start_harbor_runtime", fake_start)
    monkeypatch.setattr(HarborDependencyContext, "_stop_started_runtime", fake_stop)

    ctx = HarborDependencyContext(runtime)
    with pytest.raises(RuntimeError, match="start failed"):
        await ctx.__aenter__()
    assert stop_called


@pytest.mark.asyncio
async def test_harbor_dependency_context_aexit_suppresses_stop_error_when_exc_active(monkeypatch):
    runtime = HarborDependencyRuntime(task_path=ResourceRef(uri="file:///tmp/task", description=""))

    async def fake_start(self):
        pass

    async def fake_stop(self):
        raise RuntimeError("stop failed")

    monkeypatch.setattr(HarborDependencyContext, "_start_harbor_runtime", fake_start)
    monkeypatch.setattr(HarborDependencyContext, "_stop_started_runtime", fake_stop)

    ctx = HarborDependencyContext(runtime)
    await ctx.__aenter__()
    result = await ctx.__aexit__(ValueError, ValueError("original"), None)
    assert result is False


@pytest.mark.asyncio
async def test_harbor_dependency_context_stop_started_runtime_no_environment(monkeypatch):
    runtime = HarborDependencyRuntime(task_path=ResourceRef(uri="file:///tmp/task", description=""))
    ctx = HarborDependencyContext(runtime)
    await ctx._stop_started_runtime()


@pytest.mark.asyncio
async def test_harbor_dependency_context_stop_started_runtime_with_environment(monkeypatch):
    runtime = HarborDependencyRuntime(task_path=ResourceRef(uri="file:///tmp/task", description=""), delete=True)
    ctx = HarborDependencyContext(runtime)

    class FakeEnv:
        async def stop(self, delete):
            pass

    ctx._environment = FakeEnv()
    await ctx._stop_started_runtime()
    assert ctx._environment is None


@pytest.mark.asyncio
async def test_harbor_dependency_context_start_runtime(tmp_path, monkeypatch):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    runtime = HarborDependencyRuntime(
        task_path=ResourceRef(uri=task_dir.resolve().as_uri(), description=""),
        build_timeout_sec=None,
        run_healthcheck=False,
    )

    class FakeEnv:
        context_id = None

        class capabilities:
            mounted = False

        async def start(self, force_build):
            pass

        async def stop(self, delete):
            pass

    class FakeEnvPaths:
        verifier_dir = Path("/verifier")
        agent_dir = Path("/agent")
        artifacts_dir = Path("/artifacts")

    class FakeTrialPaths:
        def __init__(self, path):
            self.trial_dir = path
            self.verifier_dir = path / "verifier"
            self.agent_dir = path / "agent"
            self.artifacts_dir = path / "artifacts"

        def mkdir(self):
            pass

        def host_artifact_path(self, service, path):
            result = self.trial_dir / "artifacts" / "main"
            result.mkdir(parents=True, exist_ok=True)
            return result

    class FakeHarborTask:
        short_name = "test-task"
        paths = SimpleNamespace(environment_dir=tmp_path, tests_dir=tmp_path / "tests")
        config = SimpleNamespace(environment=SimpleNamespace(os="linux", healthcheck=None, build_timeout_sec=None))

    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor.HarborTaskModel",
        lambda p: FakeHarborTask(),
    )
    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor.TrialPaths",
        FakeTrialPaths,
    )
    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor.EnvironmentPaths",
        SimpleNamespace(for_os=staticmethod(lambda os: FakeEnvPaths())),
    )
    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor.EnvironmentFactory",
        SimpleNamespace(create_environment=staticmethod(lambda *a, **kw: FakeEnv())),
    )

    ctx = HarborDependencyContext(runtime)
    await ctx._start_harbor_runtime()
    assert ctx._environment is not None


@pytest.mark.asyncio
async def test_harbor_dependency_context_start_runtime_mounted(tmp_path, monkeypatch):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    runtime = HarborDependencyRuntime(
        task_path=ResourceRef(uri=task_dir.resolve().as_uri(), description=""),
        build_timeout_sec=None,
        run_healthcheck=False,
    )

    class FakeEnv:
        context_id = None

        class capabilities:
            mounted = True

        async def start(self, force_build):
            pass

        async def stop(self, delete):
            pass

    class FakeEnvPaths:
        verifier_dir = Path("/verifier")
        agent_dir = Path("/agent")
        artifacts_dir = Path("/artifacts")

    class FakeTrialPaths:
        def __init__(self, path):
            self.trial_dir = path
            self.verifier_dir = path / "verifier"
            self.agent_dir = path / "agent"
            self.artifacts_dir = path / "artifacts"

        def mkdir(self):
            pass

        def chmod_dir(self):
            pass

        def host_artifact_path(self, service, path):
            result = self.trial_dir / "artifacts" / "main"
            result.mkdir(parents=True, exist_ok=True)
            return result

    class FakeHarborTask:
        short_name = "test-task"
        paths = SimpleNamespace(environment_dir=tmp_path, tests_dir=tmp_path / "tests")
        config = SimpleNamespace(environment=SimpleNamespace(os="linux", healthcheck=None, build_timeout_sec=None))

    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor.HarborTaskModel",
        lambda p: FakeHarborTask(),
    )
    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor.TrialPaths",
        FakeTrialPaths,
    )
    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor.EnvironmentPaths",
        SimpleNamespace(for_os=staticmethod(lambda os: FakeEnvPaths())),
    )
    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor.EnvironmentFactory",
        SimpleNamespace(create_environment=staticmethod(lambda *a, **kw: FakeEnv())),
    )

    ctx = HarborDependencyContext(runtime)
    await ctx._start_harbor_runtime()
    assert ctx._environment is not None


def test_chmod_path_chain(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    _chmod_path_chain(deep, tmp_path / "a")


def test_safe_identifier_empty():
    assert _safe_identifier("") == "path"


def test_safe_identifier_starts_with_digit():
    assert _safe_identifier("123abc") == "_123abc"


def test_safe_identifier_normal():
    assert _safe_identifier("hello world") == "hello_world"


def test_scoped_import_path_empty_module(tmp_path):
    with pytest.raises(ValueError, match="import_path module is required"):
        _scoped_import_path(tmp_path, ":SomeClass")


def test_cleanup_scoped_imports_removes_parent_attr():
    _ensure_package("_test_root_xyz.sub")
    assert "_test_root_xyz" in sys.modules
    _cleanup_scoped_imports("_test_root_xyz.sub")
    assert "_test_root_xyz" not in sys.modules


def test_trial_metric_spec_uses_trial_verifier_dir(tmp_path):
    trial_dir = tmp_path / "trial"
    verifier_dir = trial_dir / "verifier"
    verifier_dir.mkdir(parents=True)
    spec = _trial_metric_spec(trial_dir, {})
    assert spec.ref is not None
    assert spec.ref.uri == verifier_dir.resolve().as_uri()


def test_trial_metric_spec_task_dir_verifier(tmp_path):
    task_dir = tmp_path / "task"
    verifier_dir = task_dir / "tests"
    verifier_dir.mkdir(parents=True)
    trial_dir = tmp_path / "trial"
    trial_dir.mkdir()
    trial_data = {"task_id": {"path": str(task_dir)}}
    spec = _trial_metric_spec(trial_dir, trial_data)
    assert spec.ref is not None
    assert spec.ref.uri == verifier_dir.resolve().as_uri()


def test_with_trace_artifact_already_has_source():
    from harbor.models.job.config import ArtifactConfig

    existing = ArtifactConfig(source=_TRACE_ARTIFACT_SOURCE, destination="traces")
    result = _with_trace_artifact([existing], _TRACE_ARTIFACT_SOURCE)
    assert result == [existing]


def test_with_trace_artifact_already_has_destination():
    from harbor.models.job.config import ArtifactConfig

    existing = ArtifactConfig(source="/other", destination=_TRACE_ARTIFACT_DESTINATION)
    result = _with_trace_artifact([existing], _TRACE_ARTIFACT_SOURCE)
    assert result == [existing]


def test_with_trace_artifact_adds_when_missing():
    from harbor.models.job.config import ArtifactConfig

    other = ArtifactConfig(source="/other", destination="other")
    result = _with_trace_artifact([other], _TRACE_ARTIFACT_SOURCE)
    assert len(result) == 2
    assert result[0].source == _TRACE_ARTIFACT_SOURCE


def test_trial_error_non_dict():
    result = _trial_error("some string error")
    assert result == {"exception_info": "some string error"}


def test_trial_metrics_skips_non_numeric(tmp_path):
    spec = MetricSpec(name="reward", description="")
    result = _trial_metrics(
        tmp_path,
        {"verifier_result": {"rewards": {"reward": "not-a-number", "score": 1.0}}},
        spec,
    )
    assert "reward" not in result
    assert result["score"].value == 1.0


def test_trial_resources_fallback_artifact(tmp_path):
    unknown_file = tmp_path / "some_unknown_file.txt"
    unknown_file.write_text("data")
    resources, _trace = _trial_resources(tmp_path)
    assert "artifact:some_unknown_file.txt" in resources


def test_harbor_dataset_get_task_found(tmp_path):
    task_dir = tmp_path / "task-a"
    _write(task_dir / "task.toml", "")
    dataset = HarborDataset.from_path(task_dir)
    task = dataset.get_task("task-a")
    assert task.id == "task-a"


@pytest.mark.asyncio
async def test_harbor_evaluator_force_rerun(tmp_path, monkeypatch):
    evaluator = HarborEvaluator()
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    task_dir = tmp_path / "task-a"
    _write(task_dir / "task.toml", "")
    harbor_dataset = HarborDataset.from_path(task_dir)

    jobs_dir = tmp_path / "jobs"
    job_name = f"agent-{harbor_dataset.id}"
    job_dir = jobs_dir / job_name
    job_dir.mkdir(parents=True)
    (job_dir / "existing_file.txt").write_text("old result")

    rmtree_calls = []

    def fake_rmtree(path, **kwargs):
        rmtree_calls.append(path)

    monkeypatch.setattr("nemo_eval_author_plugin.evaluator.harbor.shutil.rmtree", fake_rmtree)

    class FakeJob:
        created_config = None

        def __init__(self, config):
            self.config = config
            self.job_dir = job_dir

        @classmethod
        async def create(cls, config):
            cls.created_config = config
            return cls(config)

        async def run(self):
            return SimpleNamespace(id="job-id", stats=None)

    monkeypatch.setattr("nemo_eval_author_plugin.evaluator.harbor.Job", FakeJob)

    trials = await evaluator._run(
        agent=agent_dir,
        dataset=harbor_dataset,
        options=HarborEvaluatorConfig(
            import_path="harbor_wrapper:WrappedAgent",
            jobs_dir=jobs_dir,
            force_rerun=True,
        ),
    )
    assert trials == []
    assert len(rmtree_calls) == 1
    assert rmtree_calls[0] == job_dir


@pytest.mark.asyncio
async def test_harbor_trials_from_dir_trial_id_fallback(tmp_path):
    job_dir = tmp_path / "job"
    trial_dir = job_dir / "task-x__0"
    _write_json(
        trial_dir / "result.json",
        {
            "verifier_result": {"rewards": {"reward": 0.5}},
            "exception_info": None,
        },
    )

    evaluator = HarborEvaluator()
    trials = await evaluator._trials_from_dir(job_dir, [Task(id="task-x", metric_specs={})])
    assert trials[0].id == trial_dir.name


# ── models.py additional coverage ────────────────────────────────────────────


def test_dependency_runtime_context():
    runtime = DependencyRuntime()
    ctx = runtime.context()
    assert isinstance(ctx, DependencyContext)


def test_local_path_from_uri_decodes_file_uri(tmp_path: Path):
    path = tmp_path / "directory with spaces"

    assert local_path_from_uri(path.as_uri()) == path


def test_local_path_from_uri_rejects_non_file_scheme():
    with pytest.raises(ValueError, match="URI scheme 's3'"):
        local_path_from_uri("s3://bucket/path")


def test_local_path_from_uri_rejects_remote_file_uri():
    with pytest.raises(ValueError, match="file URI must be local"):
        local_path_from_uri("file://remote-host/path")


@pytest.mark.asyncio
async def test_run_dependency_command_success(tmp_path):
    spec = CommandSpec(argv=["echo", "hello"], cwd=ResourceRef(uri=tmp_path.resolve().as_uri(), description=""))
    await run_dependency_command(spec, "test")


@pytest.mark.asyncio
async def test_run_dependency_command_failure():
    spec = CommandSpec(argv=["false"])
    with pytest.raises(RuntimeError, match="failed with exit code"):
        await run_dependency_command(spec, "test")


@pytest.mark.asyncio
async def test_run_dependency_command_timeout():
    spec = CommandSpec(argv=["sleep", "10"], timeout_sec=0)
    with pytest.raises(TimeoutError):
        await run_dependency_command(spec, "test")


@pytest.mark.asyncio
async def test_run_dependency_command_empty_argv():
    spec = CommandSpec(argv=[])
    with pytest.raises(ValueError, match="empty argv"):
        await run_dependency_command(spec, "test")


@pytest.mark.asyncio
async def test_dependency_context_with_none_runtime():
    ctx = DependencyContext(None)
    assert ctx._runtime is None
    entered = await ctx.__aenter__()
    assert entered is None
    result = await ctx.__aexit__(None, None, None)
    assert result is False


@pytest.mark.asyncio
async def test_dependency_context_with_real_runtime(tmp_path):
    spec_start = CommandSpec(argv=["echo", "start"], cwd=ResourceRef(uri=tmp_path.resolve().as_uri(), description=""))
    spec_stop = CommandSpec(argv=["echo", "stop"], cwd=ResourceRef(uri=tmp_path.resolve().as_uri(), description=""))
    runtime = DependencyRuntime(start=spec_start, stop=spec_stop)
    ctx = DependencyContext(runtime)
    entered = await ctx.__aenter__()
    assert entered is runtime
    result = await ctx.__aexit__(None, None, None)
    assert result is False


@pytest.mark.asyncio
async def test_dependency_context_cleanup_on_start_failure(tmp_path):
    spec_start = CommandSpec(argv=["false"])
    spec_stop = CommandSpec(argv=["echo", "stop"])
    runtime = DependencyRuntime(start=spec_start, stop=spec_stop)
    ctx = DependencyContext(runtime)
    with pytest.raises(RuntimeError):
        await ctx.__aenter__()


@pytest.mark.asyncio
async def test_dependency_context_aexit_stop_raises_no_original_exc(tmp_path):
    spec_start = CommandSpec(argv=["echo", "start"])
    spec_stop = CommandSpec(argv=["false"])
    runtime = DependencyRuntime(start=spec_start, stop=spec_stop)
    ctx = DependencyContext(runtime)
    await ctx.__aenter__()
    with pytest.raises(RuntimeError):
        await ctx.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_dependency_context_aexit_stop_raises_with_original_exc(tmp_path):
    spec_start = CommandSpec(argv=["echo", "start"])
    spec_stop = CommandSpec(argv=["false"])
    runtime = DependencyRuntime(start=spec_start, stop=spec_stop)
    ctx = DependencyContext(runtime)
    await ctx.__aenter__()
    result = await ctx.__aexit__(ValueError, ValueError("orig"), None)
    assert result is False


def test_task_start_deps_with_no_dependencies():
    task = Task(id="t1")
    ctx = task.start_deps()
    assert isinstance(ctx, DependencyContext)


def test_task_start_deps_with_dependencies():
    runtime = DependencyRuntime(start=CommandSpec(argv=["true"]))
    task = Task(id="t1", dependencies=runtime)
    ctx = task.start_deps()
    assert isinstance(ctx, DependencyContext)


def test_dataset_subset_missing_raises():
    class ConcreteDataset(Dataset):
        @classmethod
        def from_ref(cls, ref):
            return cls(id="test")

    ds = ConcreteDataset(id="ds", tasks=[Task(id="t1")])
    with pytest.raises(ValueError, match="not found in dataset"):
        ds.subset(["t1", "missing"])


def test_dataset_from_ref_not_implemented():
    from nemo_eval_author_plugin.evaluator.models import DatasetRef

    class ConcreteDataset(Dataset):
        pass

    with pytest.raises(NotImplementedError):
        ConcreteDataset.from_ref(DatasetRef(uri="/tmp"))


def test_dataset_subset_success():
    class ConcreteDataset(Dataset):
        @classmethod
        def from_ref(cls, ref):
            return cls(id="test")

    ds = ConcreteDataset(id="ds", tasks=[Task(id="t1"), Task(id="t2")])
    sub = ds.subset(["t1"])
    assert len(sub.list_tasks()) == 1
    assert sub.tasks[0].id == "t1"


@pytest.mark.asyncio
async def test_dependency_context_start_none_raises_on_no_start():
    runtime = DependencyRuntime(start=None)
    ctx = DependencyContext(runtime)
    with pytest.raises(ValueError, match="requires start"):
        await ctx.__aenter__()


@pytest.mark.asyncio
async def test_dependency_context_with_readiness(tmp_path):
    spec_start = CommandSpec(argv=["echo", "start"])
    spec_readiness = CommandSpec(argv=["echo", "ready"])
    spec_stop = CommandSpec(argv=["echo", "stop"])
    runtime = DependencyRuntime(start=spec_start, readiness=spec_readiness, stop=spec_stop)
    ctx = DependencyContext(runtime)
    entered = await ctx.__aenter__()
    assert entered is runtime
    await ctx.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_dependency_context_start_failure_stop_also_fails():
    spec_start = CommandSpec(argv=["false"])
    spec_stop = CommandSpec(argv=["false"])
    runtime = DependencyRuntime(start=spec_start, stop=spec_stop)
    ctx = DependencyContext(runtime)
    with pytest.raises(RuntimeError):
        await ctx.__aenter__()


# ── harbor.py additional coverage (round 2) ─────────────────────────────────


@pytest.mark.asyncio
async def test_harbor_dependency_context_aenter_readiness_real(monkeypatch):
    runtime = HarborDependencyRuntime(
        task_path=ResourceRef(uri="file:///tmp/task", description=""),
        readiness=CommandSpec(argv=["echo", "ready"]),
    )

    async def fake_start(self):
        pass

    async def fake_stop(self):
        pass

    monkeypatch.setattr(HarborDependencyContext, "_start_harbor_runtime", fake_start)
    monkeypatch.setattr(HarborDependencyContext, "_stop_started_runtime", fake_stop)

    ctx = HarborDependencyContext(runtime)
    entered = await ctx.__aenter__()
    assert entered is runtime


@pytest.mark.asyncio
async def test_harbor_dependency_context_aenter_start_fails_stop_also_fails(monkeypatch):
    runtime = HarborDependencyRuntime(task_path=ResourceRef(uri="file:///tmp/task", description=""))

    async def fake_start(self):
        raise RuntimeError("start failed")

    async def fake_stop(self):
        raise RuntimeError("stop also failed")

    monkeypatch.setattr(HarborDependencyContext, "_start_harbor_runtime", fake_start)
    monkeypatch.setattr(HarborDependencyContext, "_stop_started_runtime", fake_stop)

    ctx = HarborDependencyContext(runtime)
    with pytest.raises(RuntimeError, match="start failed"):
        await ctx.__aenter__()


@pytest.mark.asyncio
async def test_harbor_dependency_context_aexit_stop_raises_no_exc(monkeypatch):
    runtime = HarborDependencyRuntime(task_path=ResourceRef(uri="file:///tmp/task", description=""))

    async def fake_start(self):
        pass

    async def fake_stop(self):
        raise RuntimeError("stop failed")

    monkeypatch.setattr(HarborDependencyContext, "_start_harbor_runtime", fake_start)
    monkeypatch.setattr(HarborDependencyContext, "_stop_started_runtime", fake_stop)

    ctx = HarborDependencyContext(runtime)
    await ctx.__aenter__()
    with pytest.raises(RuntimeError, match="stop failed"):
        await ctx.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_harbor_dependency_context_stop_runtime_env_raises(monkeypatch):
    runtime = HarborDependencyRuntime(task_path=ResourceRef(uri="file:///tmp/task", description=""), delete=True)
    ctx = HarborDependencyContext(runtime)

    class FakeEnv:
        async def stop(self, delete):
            raise RuntimeError("env stop failed")

    ctx._environment = FakeEnv()
    with pytest.raises(RuntimeError, match="env stop failed"):
        await ctx._stop_started_runtime()
    assert ctx._environment is None


@pytest.mark.asyncio
async def test_harbor_dependency_context_stop_runtime_with_stop_command(tmp_path):
    runtime = HarborDependencyRuntime(
        task_path=ResourceRef(uri="file:///tmp/task", description=""),
        stop=CommandSpec(argv=["echo", "stop"]),
    )
    ctx = HarborDependencyContext(runtime)
    await ctx._stop_started_runtime()


@pytest.mark.asyncio
async def test_harbor_dependency_context_stop_runtime_env_and_stop_command_both_fail():
    runtime = HarborDependencyRuntime(
        task_path=ResourceRef(uri="file:///tmp/task", description=""),
        delete=True,
        stop=CommandSpec(argv=["false"]),
    )
    ctx = HarborDependencyContext(runtime)

    class FakeEnv:
        async def stop(self, delete):
            raise RuntimeError("env stop failed")

    ctx._environment = FakeEnv()
    with pytest.raises(RuntimeError, match="env stop failed"):
        await ctx._stop_started_runtime()
    assert ctx._environment is None


@pytest.mark.asyncio
async def test_harbor_dependency_context_stop_runtime_stop_command_fails_no_env_error():
    runtime = HarborDependencyRuntime(
        task_path=ResourceRef(uri="file:///tmp/task", description=""),
        stop=CommandSpec(argv=["false"]),
    )
    ctx = HarborDependencyContext(runtime)
    with pytest.raises(RuntimeError):
        await ctx._stop_started_runtime()


@pytest.mark.asyncio
async def test_harbor_dependency_context_stop_runtime_with_temp_dir(tmp_path, monkeypatch):
    import tempfile

    runtime = HarborDependencyRuntime(task_path=ResourceRef(uri="file:///tmp/task", description=""))
    ctx = HarborDependencyContext(runtime)
    temp = tempfile.TemporaryDirectory()
    ctx._temp_dir = temp
    await ctx._stop_started_runtime()
    assert ctx._temp_dir is None


@pytest.mark.asyncio
async def test_harbor_dependency_context_start_runtime_with_healthcheck(tmp_path, monkeypatch):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    runtime = HarborDependencyRuntime(
        task_path=ResourceRef(uri=task_dir.resolve().as_uri(), description=""),
        build_timeout_sec=None,
        run_healthcheck=True,
    )

    healthcheck_called = []

    class FakeEnv:
        context_id = None

        class capabilities:
            mounted = False

        async def start(self, force_build):
            pass

        async def run_healthcheck(self):
            healthcheck_called.append(True)

        async def stop(self, delete):
            pass

    class FakeEnvPaths:
        verifier_dir = Path("/verifier")
        agent_dir = Path("/agent")
        artifacts_dir = Path("/artifacts")

    class FakeTrialPaths:
        def __init__(self, path):
            self.trial_dir = path
            self.verifier_dir = path / "verifier"
            self.agent_dir = path / "agent"
            self.artifacts_dir = path / "artifacts"

        def mkdir(self):
            pass

        def host_artifact_path(self, service, path):
            result = self.trial_dir / "artifacts" / "main"
            result.mkdir(parents=True, exist_ok=True)
            return result

    class FakeHarborTask:
        short_name = "test-task"
        paths = SimpleNamespace(environment_dir=tmp_path, tests_dir=tmp_path / "tests")
        config = SimpleNamespace(
            environment=SimpleNamespace(
                os="linux",
                healthcheck=SimpleNamespace(test=["CMD", "echo", "ok"]),
                build_timeout_sec=None,
            )
        )

    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor.HarborTaskModel",
        lambda p: FakeHarborTask(),
    )
    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor.TrialPaths",
        FakeTrialPaths,
    )
    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor.EnvironmentPaths",
        SimpleNamespace(for_os=staticmethod(lambda os: FakeEnvPaths())),
    )
    monkeypatch.setattr(
        "nemo_eval_author_plugin.evaluator.harbor.EnvironmentFactory",
        SimpleNamespace(create_environment=staticmethod(lambda *a, **kw: FakeEnv())),
    )

    ctx = HarborDependencyContext(runtime)
    await ctx._start_harbor_runtime()
    assert healthcheck_called


def test_cleanup_scoped_imports_with_sibling_prevents_parent_removal():
    _ensure_package("_test_multi_abc.child1")
    _ensure_package("_test_multi_abc.child2")
    assert "_test_multi_abc" in sys.modules
    _cleanup_scoped_imports("_test_multi_abc.child1")
    assert "_test_multi_abc" in sys.modules
    _cleanup_scoped_imports("_test_multi_abc.child2")
    assert "_test_multi_abc" not in sys.modules


def test_trial_task_path_from_config_dict():
    from nemo_eval_author_plugin.evaluator.harbor import _trial_task_path

    trial_data = {"config": {"task": {"path": "/tmp/task-x"}}}
    result = _trial_task_path(trial_data)
    assert result is not None
    assert result.name == "task-x"


def test_resolve_trial_task_id_invalid_uri_in_task(tmp_path):
    from nemo_eval_author_plugin.evaluator.harbor import _resolve_trial_task_id

    task_map = {"task-x": Task(id="task-x", uri="s3://bad-uri/task-x")}
    trial_data = {"task_id": {"path": str(tmp_path / "task-x")}}
    result = _resolve_trial_task_id("task-x__0", trial_data, task_map)
    assert result == "task-x"


def test_resolve_trial_task_id_fallback_to_trial_base():
    from nemo_eval_author_plugin.evaluator.harbor import _resolve_trial_task_id

    task_map = {"task-x": Task(id="task-x")}
    trial_data = {"task_name": "unknown/nonexistent"}
    result = _resolve_trial_task_id("task-x__0", trial_data, task_map)
    assert result == "task-x"


def test_with_trace_artifact_string_match():
    result = _with_trace_artifact([_TRACE_ARTIFACT_SOURCE], _TRACE_ARTIFACT_SOURCE)
    assert result == [_TRACE_ARTIFACT_SOURCE]


def test_with_trace_artifact_string_destination_match():
    result = _with_trace_artifact([_TRACE_ARTIFACT_DESTINATION], _TRACE_ARTIFACT_SOURCE)
    assert result == [_TRACE_ARTIFACT_DESTINATION]
