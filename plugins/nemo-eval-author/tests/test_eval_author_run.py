# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pytest
from nemo_eval_author_plugin.eval_author import run as eval_author_run
from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig, EvalAuthorResult
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import Dataset, DatasetRef, Task
from nemo_insights_plugin.entities import Insight


@dataclass
class ClosingClient:
    closed: bool = False
    files: Any = None

    async def close(self) -> None:
        self.closed = True


@dataclass
class BackendFactoryCall:
    client: ClosingClient
    experiments_output: str
    mode: Literal["local", "remote"]


@dataclass
class AgentCodeCall:
    workspace: str
    agent: str | Path
    dest: Path


@dataclass
class EvalAuthorFactoryCall:
    experiment_dir: Path
    config: EvalAuthorConfig


@dataclass
class EvalAuthorCall:
    insight: Insight
    agent_path: Path
    task_template: Task
    train_dataset: Dataset
    validation_dataset: Dataset
    client: ClosingClient


class FakeBackend:
    def __init__(self, insight: Insight) -> None:
        self.insight = insight
        self.insight_calls: list[dict[str, str]] = []
        self.agent_code_calls: list[AgentCodeCall] = []

    async def get_insight(self, *, workspace: str, insight_id: str) -> Insight:
        self.insight_calls.append({"workspace": workspace, "insight_id": insight_id})
        return self.insight

    async def get_agent_code(self, *, workspace: str, agent: str | Path, dest: Path) -> None:
        self.agent_code_calls.append(AgentCodeCall(workspace=workspace, agent=agent, dest=dest))


class FakeDatasetFactory:
    def __init__(self) -> None:
        self.train = Dataset(id="train")
        self.validation = Dataset(id="validation")
        self.template = Task(id="template-task", uri="file:///template")
        self.dataset_refs: list[tuple[str, DatasetRef]] = []
        self.template_refs: list[tuple[str, DatasetRef]] = []

    def build_dataset(self, evaluator_type: str, dataset_ref: DatasetRef) -> Dataset:
        self.dataset_refs.append((evaluator_type, dataset_ref))
        if dataset_ref.metadata.get("id") == "validation":
            return self.validation
        return self.train

    def build_task_template(self, evaluator_type: str, template_ref: DatasetRef) -> Task:
        self.template_refs.append((evaluator_type, template_ref))
        return self.template


class FakeEvalAuthor:
    def __init__(self) -> None:
        self.call: EvalAuthorCall | None = None

    async def run(
        self,
        insight: Insight,
        agent_path: Path,
        task_template: Task,
        train_dataset: Dataset,
        validation_dataset: Dataset,
        *,
        client: ClosingClient,
    ) -> EvalAuthorResult:
        self.call = EvalAuthorCall(
            insight=insight,
            agent_path=agent_path,
            task_template=task_template,
            train_dataset=train_dataset,
            validation_dataset=validation_dataset,
            client=client,
        )
        return EvalAuthorResult(
            train_dataset=train_dataset,
            validation_dataset=validation_dataset,
            summary="Eval Author complete",
        )


@pytest.mark.asyncio
async def test_run_eval_author_builds_and_runs_complete_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = ClosingClient()
    insight = Insight(
        workspace="workspace-a",
        title="failure",
        description="description",
        agent=str(tmp_path / "agent-src"),
        trace_refs=["trace-1"],
    )
    backend = FakeBackend(insight)
    dataset_factory = FakeDatasetFactory()
    eval_author = FakeEvalAuthor()
    backend_calls: list[BackendFactoryCall] = []
    eval_author_calls: list[EvalAuthorFactoryCall] = []
    litellm_calls: list[bool] = []

    def make_backend(
        *,
        client: ClosingClient,
        experiments_output: str,
        mode: Literal["local", "remote"],
    ) -> FakeBackend:
        backend_calls.append(BackendFactoryCall(client=client, experiments_output=experiments_output, mode=mode))
        return backend

    def build_eval_author_agent(*, experiment_dir: Path, config: EvalAuthorConfig) -> FakeEvalAuthor:
        eval_author_calls.append(EvalAuthorFactoryCall(experiment_dir=experiment_dir, config=config))
        return eval_author

    monkeypatch.setattr(eval_author_run, "make_client", lambda base_url: client)
    monkeypatch.setattr(eval_author_run, "make_experimentalist_backend", make_backend)
    monkeypatch.setattr(eval_author_run, "DatasetFactory", lambda: dataset_factory)
    monkeypatch.setattr(eval_author_run, "build_eval_author_agent", build_eval_author_agent)
    monkeypatch.setattr(eval_author_run, "_enable_litellm_drop_params", lambda: litellm_calls.append(True))

    config = EvalAuthorConfig(max_traces=2)
    train_ref = DatasetRef(uri=str(tmp_path / "train"), metadata={"id": "train"})
    validation_ref = DatasetRef(uri=str(tmp_path / "validation"), metadata={"id": "validation"})
    template_path = tmp_path / "template"
    template_path.mkdir()
    template_ref = DatasetRef(uri=str(template_path), metadata={"id": "task-template"})

    result = await eval_author_run.run_eval_author(
        insight="insight-remote-123",
        train_dataset=train_ref,
        validation_dataset=validation_ref,
        task_template=template_ref,
        experiment_dir=tmp_path / "eval_author",
        workspace="workspace-a",
        base_url="http://platform.test",
        config=config,
        mode="local",
    )

    experiment_dir = (tmp_path / "eval_author").resolve()
    assert result.summary == "Eval Author complete"
    assert result.train_dataset is dataset_factory.train
    assert result.validation_dataset is dataset_factory.validation
    assert litellm_calls == [True]
    assert backend_calls == [
        BackendFactoryCall(client=client, experiments_output=str(experiment_dir), mode="local"),
    ]
    assert backend.insight_calls == [{"workspace": "workspace-a", "insight_id": "insight-remote-123"}]
    assert backend.agent_code_calls == [
        AgentCodeCall(
            workspace="workspace-a",
            agent=insight.agent,
            dest=experiment_dir / "eval_author" / "source-agent",
        )
    ]
    assert dataset_factory.dataset_refs == [("harbor", train_ref), ("harbor", validation_ref)]
    assert dataset_factory.template_refs == [
        (
            "harbor",
            template_ref.model_copy(update={"uri": str(experiment_dir / "dataset" / "task-template")}),
        )
    ]
    assert eval_author_calls == [EvalAuthorFactoryCall(experiment_dir=experiment_dir, config=config)]
    assert eval_author.call == EvalAuthorCall(
        insight=insight,
        agent_path=experiment_dir / "eval_author" / "source-agent",
        task_template=dataset_factory.template,
        train_dataset=dataset_factory.train,
        validation_dataset=dataset_factory.validation,
        client=client,
    )
    assert client.closed


@pytest.mark.asyncio
async def test_run_eval_author_hydrates_fileset_task_template(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    download_calls: list[dict[str, str]] = []

    class FakeFiles:
        async def download(self, *, remote_path: str, local_path: str, workspace: str) -> None:
            download_calls.append({"remote_path": remote_path, "local_path": local_path, "workspace": workspace})
            destination = Path(local_path)
            destination.mkdir(parents=True)
            (destination / "task.toml").write_text("template", encoding="utf-8")

    client = ClosingClient(files=FakeFiles())
    insight = Insight(workspace="workspace-a", title="failure", description="description", agent="insight-agent")
    backend = FakeBackend(insight)
    dataset_factory = FakeDatasetFactory()
    eval_author = FakeEvalAuthor()

    monkeypatch.setattr(eval_author_run, "make_client", lambda base_url: client)
    monkeypatch.setattr(eval_author_run, "make_experimentalist_backend", lambda **_: backend)
    monkeypatch.setattr(eval_author_run, "DatasetFactory", lambda: dataset_factory)
    monkeypatch.setattr(eval_author_run, "build_eval_author_agent", lambda **_: eval_author)
    monkeypatch.setattr(eval_author_run, "_enable_litellm_drop_params", lambda: None)

    template_ref = DatasetRef(uri="fileset://workspace-a/task-template", metadata={"id": "task-template"})
    experiment_dir = (tmp_path / "eval_author").resolve()
    await eval_author_run.run_eval_author(
        insight="insight-remote-123",
        train_dataset=DatasetRef(uri="train", metadata={"id": "train"}),
        validation_dataset=DatasetRef(uri="validation", metadata={"id": "validation"}),
        task_template=template_ref,
        experiment_dir=experiment_dir,
        workspace="workspace-a",
        base_url="http://platform.test",
        config=EvalAuthorConfig(),
    )

    staged_path = experiment_dir / "dataset" / "task-template"
    assert download_calls == [
        {
            "remote_path": template_ref.uri,
            "local_path": str(staged_path),
            "workspace": "workspace-a",
        }
    ]
    assert dataset_factory.template_refs == [("harbor", template_ref.model_copy(update={"uri": str(staged_path)}))]
    assert client.closed


@pytest.mark.asyncio
async def test_run_eval_author_uses_agent_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = ClosingClient()
    insight = Insight(workspace="workspace-a", title="failure", description="description", agent="insight-agent")
    backend = FakeBackend(insight)
    dataset_factory = FakeDatasetFactory()
    eval_author = FakeEvalAuthor()

    monkeypatch.setattr(eval_author_run, "make_client", lambda base_url: client)
    monkeypatch.setattr(eval_author_run, "make_experimentalist_backend", lambda **_: backend)
    monkeypatch.setattr(eval_author_run, "DatasetFactory", lambda: dataset_factory)
    monkeypatch.setattr(eval_author_run, "build_eval_author_agent", lambda **_: eval_author)
    monkeypatch.setattr(eval_author_run, "_enable_litellm_drop_params", lambda: None)

    override = tmp_path / "override-agent"
    template = tmp_path / "template"
    template.mkdir()
    await eval_author_run.run_eval_author(
        insight="insight-remote-123",
        agent=override,
        train_dataset=DatasetRef(uri="train", metadata={"id": "train"}),
        validation_dataset=DatasetRef(uri="validation", metadata={"id": "validation"}),
        task_template=DatasetRef(uri=str(template)),
        experiment_dir=tmp_path / "eval_author",
        workspace="workspace-a",
        base_url="http://platform.test",
        config=EvalAuthorConfig(),
    )

    assert backend.agent_code_calls[0].agent == override
    assert client.closed


@pytest.mark.asyncio
async def test_run_eval_author_closes_client_when_backend_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = ClosingClient()

    def fail_backend_creation(**_: object) -> object:
        raise RuntimeError("backend creation failed")

    monkeypatch.setattr(eval_author_run, "make_client", lambda base_url: client)
    monkeypatch.setattr(eval_author_run, "make_experimentalist_backend", fail_backend_creation)

    with pytest.raises(RuntimeError, match="backend creation failed"):
        await eval_author_run.run_eval_author(
            insight="insight-remote-123",
            train_dataset=DatasetRef(uri="train"),
            validation_dataset=DatasetRef(uri="validation"),
            task_template=DatasetRef(uri="template"),
            experiment_dir=tmp_path / "eval_author",
            workspace="workspace-a",
            base_url="http://platform.test",
            config=EvalAuthorConfig(),
        )

    assert client.closed
