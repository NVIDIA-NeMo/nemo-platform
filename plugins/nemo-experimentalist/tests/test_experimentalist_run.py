# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import pytest
from nemo_experimentalist_plugin.experimentalist import run as experimentalist_run
from nemo_experimentalist_plugin.experimentalist.components import loop as loop_module
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DatasetRef
from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.experimentalist.deps import ExperimentalistDeps
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import LocalExperimentalistBackend
from nemo_experimentalist_plugin.experimentalist.result import ExperimentalistResult
from nemo_platform import AsyncNeMoPlatform


@dataclass
class ClosingClient:
    closed: bool = False

    async def close(self) -> None:
        self.closed = True


@dataclass
class ExperimentRunPaths:
    agent: Path
    train: Path
    validation: Path
    experiment: Path


@dataclass
class BackendFactoryCall:
    client: ClosingClient | None
    experiments_output: str
    mode: Literal["local", "remote"]


@dataclass
class AgentFactoryCall:
    working_dir: Path
    config: EvolutionaryOptimizerConfig


@dataclass
class FakeExperimentalist:
    deps: ExperimentalistDeps | None = None

    async def run(self, deps: ExperimentalistDeps) -> ExperimentalistResult:
        self.deps = deps
        return ExperimentalistResult(summary="optimization complete", run_id="run-1", rounds_completed=1)


def test_persistence_warning_includes_exception_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=loop_module.__name__)

    loop_module._warn_persistence_failure("archive", "agent-2", RuntimeError("push rejected by remote"))

    assert "archive" in caplog.text
    assert "agent-2" in caplog.text
    assert "push rejected by remote" in caplog.text


def _make_run_paths(tmp_path: Path) -> ExperimentRunPaths:
    agent = tmp_path / "agent"
    train = tmp_path / "train"
    validation = tmp_path / "validation"
    for path in (agent, train, validation):
        path.mkdir()
    return ExperimentRunPaths(
        agent=agent,
        train=train,
        validation=validation,
        experiment=tmp_path / "experiment",
    )


@pytest.mark.asyncio
async def test_run_experimentalist_builds_and_runs_complete_local_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _make_run_paths(tmp_path)
    client = ClosingClient()
    backend = LocalExperimentalistBackend(path=tmp_path / "backend")
    optimizer_config = EvolutionaryOptimizerConfig(max_rounds=2)
    experimentalist = FakeExperimentalist()
    backend_calls: list[BackendFactoryCall] = []
    agent_calls: list[AgentFactoryCall] = []
    litellm_calls: list[bool] = []

    def make_backend(
        *,
        client: ClosingClient | None,
        experiments_output: str,
        mode: Literal["local", "remote"],
        storage: object = None,
    ) -> LocalExperimentalistBackend:
        backend_calls.append(
            BackendFactoryCall(
                client=client,
                experiments_output=experiments_output,
                mode=mode,
            )
        )
        return backend

    def build_agent(
        *, working_dir: Path, config: EvolutionaryOptimizerConfig, framework_skills_dirs: list[Path] | None
    ) -> FakeExperimentalist:
        assert framework_skills_dirs is None
        agent_calls.append(AgentFactoryCall(working_dir=working_dir, config=config))
        return experimentalist

    monkeypatch.setattr(experimentalist_run, "make_experimentalist_backend", make_backend)
    monkeypatch.setattr(experimentalist_run, "build_experimentalist_agent", build_agent)
    monkeypatch.setattr(experimentalist_run, "_enable_litellm_drop_params", lambda: litellm_calls.append(True))

    train_dataset = DatasetRef(uri=str(paths.train))
    validation_dataset = DatasetRef(uri=str(paths.validation))

    summary = await experimentalist_run.run_experimentalist(
        agent=paths.agent,
        insight=None,
        train_dataset=train_dataset,
        validation_dataset=validation_dataset,
        experiment_dir=paths.experiment,
        workspace="workspace-a",
        client=cast(AsyncNeMoPlatform, client),
        config=optimizer_config,
        mode="local",
    )

    assert summary == "optimization complete"
    assert paths.experiment.is_dir()
    assert backend_calls == [
        BackendFactoryCall(
            client=client,
            experiments_output=str(paths.experiment.resolve()),
            mode="local",
        )
    ]
    assert agent_calls == [AgentFactoryCall(working_dir=paths.experiment.resolve(), config=optimizer_config)]
    assert litellm_calls == [True]
    assert not client.closed
    assert experimentalist.deps is not None
    assert experimentalist.deps.workspace == "workspace-a"
    # ``agent`` is forwarded verbatim (it may be a git url@ref); the loop resolves it.
    assert experimentalist.deps.agent == paths.agent
    assert experimentalist.deps.insight is None
    assert experimentalist.deps.train_dataset == train_dataset
    assert experimentalist.deps.validation_dataset == validation_dataset
    assert experimentalist.deps.backend is backend
    assert experimentalist.deps.config is optimizer_config
    assert experimentalist.deps.agent_spec is None


@pytest.mark.asyncio
async def test_run_experimentalist_forwards_platform_insight_id_verbatim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _make_run_paths(tmp_path)
    client = ClosingClient()
    backend = LocalExperimentalistBackend(path=tmp_path / "backend")
    experimentalist = FakeExperimentalist()

    monkeypatch.setattr(
        experimentalist_run,
        "make_experimentalist_backend",
        lambda **_: backend,
    )
    monkeypatch.setattr(
        experimentalist_run,
        "build_experimentalist_agent",
        lambda **_: experimentalist,
    )
    monkeypatch.setattr(experimentalist_run, "_enable_litellm_drop_params", lambda: None)

    await experimentalist_run.run_experimentalist(
        insight="insight-remote-123",
        train_dataset=DatasetRef(uri=str(paths.train)),
        validation_dataset=DatasetRef(uri=str(paths.validation)),
        task_template=DatasetRef(uri=str(paths.train)),
        experiment_dir=paths.experiment,
        workspace="workspace-a",
        client=cast(AsyncNeMoPlatform, client),
        config=EvolutionaryOptimizerConfig(),
        mode="remote",
    )

    assert experimentalist.deps is not None
    # A str id is not resolved to a Path — it flows through untouched to the backend.
    assert experimentalist.deps.insight == "insight-remote-123"


@pytest.mark.asyncio
async def test_run_experimentalist_forwards_agent_spec_uri_to_deps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _make_run_paths(tmp_path)
    backend = LocalExperimentalistBackend(path=tmp_path / "backend")
    experimentalist = FakeExperimentalist()

    monkeypatch.setattr(experimentalist_run, "make_experimentalist_backend", lambda **_: backend)
    monkeypatch.setattr(experimentalist_run, "build_experimentalist_agent", lambda **_: experimentalist)
    monkeypatch.setattr(experimentalist_run, "_enable_litellm_drop_params", lambda: None)

    spec_uri = "/path/to/AGENT-SPEC.md"
    await experimentalist_run.run_experimentalist(
        agent=paths.agent,
        agent_spec=spec_uri,
        insight=None,
        train_dataset=DatasetRef(uri=str(paths.train)),
        validation_dataset=DatasetRef(uri=str(paths.validation)),
        experiment_dir=paths.experiment,
        workspace="default",
        client=None,
        config=EvolutionaryOptimizerConfig(),
    )

    assert experimentalist.deps is not None
    assert experimentalist.deps.agent_spec == spec_uri


@pytest.mark.asyncio
async def test_run_experimentalist_does_not_close_caller_client_when_backend_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _make_run_paths(tmp_path)
    client = ClosingClient()

    def fail_backend_creation(**_: object) -> object:
        raise RuntimeError("backend creation failed")

    monkeypatch.setattr(experimentalist_run, "make_experimentalist_backend", fail_backend_creation)

    with pytest.raises(RuntimeError, match="backend creation failed"):
        await experimentalist_run.run_experimentalist(
            agent=paths.agent,
            insight=None,
            train_dataset=DatasetRef(uri=str(paths.train)),
            validation_dataset=DatasetRef(uri=str(paths.validation)),
            experiment_dir=paths.experiment,
            workspace="default",
            client=cast(AsyncNeMoPlatform, client),
            config=EvolutionaryOptimizerConfig(),
            mode="remote",
        )

    assert not client.closed
