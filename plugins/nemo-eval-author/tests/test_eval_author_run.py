# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from nemo_eval_author_plugin.eval_author import run as eval_author_run
from nemo_eval_author_plugin.eval_author.agent import EvalAuthor
from nemo_eval_author_plugin.eval_author.inventory import ReferenceTaskSetInventory
from nemo_eval_author_plugin.eval_author.models import (
    ArtifactDescriptor,
    AuthoredMetric,
    AuthoredMetricContract,
    EvalAuthorConfig,
    EvalAuthorEvaluationContext,
    EvalAuthorRequest,
    EvalAuthorResult,
    InsightRef,
)
from nemo_experimentalist_plugin.entities import DatasetRef, Task
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
    reference_inventory: ReferenceTaskSetInventory
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
        self.template = Task(id="template-task", uri="file:///template")
        self.template_refs: list[tuple[str, DatasetRef]] = []

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
        reference_inventory: ReferenceTaskSetInventory,
        *,
        client: ClosingClient,
    ) -> EvalAuthorResult:
        self.call = EvalAuthorCall(
            insight=insight,
            agent_path=agent_path,
            task_template=task_template,
            reference_inventory=reference_inventory,
            client=client,
        )
        return EvalAuthorResult(
            task_set=ArtifactDescriptor(
                uri="file:///artifacts/task-set",
                identity=f"sha256:{'a' * 64}",
            ),
            verifier_patch=ArtifactDescriptor(
                uri="file:///artifacts/verifier-patch",
                identity=f"sha256:{'b' * 64}",
            ),
            metric_contract=AuthoredMetricContract(
                metrics=(
                    AuthoredMetric(
                        key="uses_correct_tool",
                        description="Measures whether the current run used the required tool.",
                        runtime_evidence=("Current-run OTLP tool spans",),
                    ),
                )
            ),
            summary="Eval Author complete",
        )


def _request(
    *,
    insight: str = "insight-remote-123",
    task_template: DatasetRef,
    reference_task_sets: tuple[DatasetRef, ...],
) -> EvalAuthorRequest:
    return EvalAuthorRequest(
        insight=InsightRef(uri=insight),
        evaluation_context=EvalAuthorEvaluationContext(
            task_template=task_template,
            reference_task_sets=reference_task_sets,
        ),
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
    inventory_calls: list[tuple[DatasetRef, ...]] = []
    reference_inventory = ReferenceTaskSetInventory.empty()

    def make_backend(
        *,
        client: ClosingClient,
        experiments_output: str,
    ) -> FakeBackend:
        backend_calls.append(BackendFactoryCall(client=client, experiments_output=experiments_output))
        return backend

    def build_eval_author_agent(*, experiment_dir: Path, config: EvalAuthorConfig) -> FakeEvalAuthor:
        eval_author_calls.append(EvalAuthorFactoryCall(experiment_dir=experiment_dir, config=config))
        return eval_author

    def build_inventory(reference_task_sets: tuple[DatasetRef, ...]) -> ReferenceTaskSetInventory:
        inventory_calls.append(reference_task_sets)
        return reference_inventory

    monkeypatch.setattr(eval_author_run, "make_client", lambda base_url: client)
    monkeypatch.setattr(eval_author_run, "make_experimentalist_backend", make_backend)
    monkeypatch.setattr(eval_author_run, "DatasetFactory", lambda: dataset_factory)
    monkeypatch.setattr(eval_author_run, "build_eval_author_agent", build_eval_author_agent)
    monkeypatch.setattr(
        eval_author_run,
        "build_reference_task_set_inventory",
        build_inventory,
        raising=False,
    )
    monkeypatch.setattr(eval_author_run, "_enable_litellm_drop_params", lambda: litellm_calls.append(True))

    config = EvalAuthorConfig(max_traces=2)
    train_ref = DatasetRef(uri=str(tmp_path / "train"), metadata={"id": "train"})
    validation_ref = DatasetRef(uri=str(tmp_path / "validation"), metadata={"id": "validation"})
    template_path = tmp_path / "template"
    template_path.mkdir()
    template_ref = DatasetRef(uri=str(template_path), metadata={"id": "task-template"})
    request = _request(
        insight="insight://workspace-a/insight-remote-123",
        task_template=template_ref,
        reference_task_sets=(train_ref, validation_ref),
    )

    result = await eval_author_run.run_eval_author(
        request=request,
        experiment_dir=tmp_path / "eval_author",
        workspace="workspace-a",
        base_url="http://platform.test",
        config=config,
    )

    experiment_dir = (tmp_path / "eval_author").resolve()
    assert result.summary == "Eval Author complete"
    assert result.task_set is not None
    assert result.task_set.uri == "file:///artifacts/task-set"
    assert result.verifier_patch is not None
    assert result.verifier_patch.uri == "file:///artifacts/verifier-patch"
    assert result.metric_contract is not None
    assert result.metric_contract.keys == ("uses_correct_tool",)
    assert litellm_calls == [True]
    assert backend_calls == [
        BackendFactoryCall(client=client, experiments_output=str(experiment_dir)),
    ]
    assert backend.insight_calls == [{"workspace": "workspace-a", "insight_id": "insight-remote-123"}]
    assert backend.agent_code_calls == [
        AgentCodeCall(
            workspace="workspace-a",
            agent=insight.agent,
            dest=experiment_dir / "eval_author" / "source-agent",
        )
    ]
    assert [(reference.uri, reference.metadata["id"]) for reference in inventory_calls[0]] == [
        (train_ref.uri, "train"),
        (validation_ref.uri, "validation"),
    ]
    assert [
        (evaluator_type, reference.uri, reference.metadata["id"])
        for evaluator_type, reference in dataset_factory.template_refs
    ] == [
        (
            "harbor",
            str(experiment_dir / "dataset" / "task-template"),
            "task-template",
        )
    ]
    assert eval_author_calls == [EvalAuthorFactoryCall(experiment_dir=experiment_dir, config=config)]
    assert eval_author.call == EvalAuthorCall(
        insight=insight,
        agent_path=experiment_dir / "eval_author" / "source-agent",
        task_template=dataset_factory.template,
        reference_inventory=reference_inventory,
        client=client,
    )
    assert client.closed


def test_public_run_boundaries_do_not_expose_split_specific_inputs() -> None:
    orchestration_parameters = inspect.signature(eval_author_run.run_eval_author).parameters
    agent_parameters = inspect.signature(EvalAuthor.run).parameters

    assert "request" in orchestration_parameters
    assert "task_template" not in orchestration_parameters
    assert "train_dataset" not in orchestration_parameters
    assert "validation_dataset" not in orchestration_parameters
    assert "reference_inventory" in agent_parameters
    assert "train_dataset" not in agent_parameters
    assert "validation_dataset" not in agent_parameters


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
    inventory_refs: list[tuple[DatasetRef, ...]] = []

    monkeypatch.setattr(eval_author_run, "make_client", lambda base_url: client)
    monkeypatch.setattr(eval_author_run, "make_experimentalist_backend", lambda **_: backend)
    monkeypatch.setattr(eval_author_run, "DatasetFactory", lambda: dataset_factory)
    monkeypatch.setattr(eval_author_run, "build_eval_author_agent", lambda **_: eval_author)
    monkeypatch.setattr(
        eval_author_run,
        "build_reference_task_set_inventory",
        lambda refs: inventory_refs.append(refs) or ReferenceTaskSetInventory.empty(),
        raising=False,
    )
    monkeypatch.setattr(eval_author_run, "_enable_litellm_drop_params", lambda: None)

    template_ref = DatasetRef(uri="fileset://workspace-a/task-template", metadata={"id": "task-template"})
    reference_ref = DatasetRef(uri="fileset://workspace-a/reference-task-set", metadata={"id": "reference"})
    experiment_dir = (tmp_path / "eval_author").resolve()
    await eval_author_run.run_eval_author(
        request=_request(
            task_template=template_ref,
            reference_task_sets=(reference_ref,),
        ),
        experiment_dir=experiment_dir,
        workspace="workspace-a",
        base_url="http://platform.test",
        config=EvalAuthorConfig(),
    )

    staged_path = experiment_dir / "dataset" / "task-template"
    staged_reference_path = experiment_dir / "dataset" / "reference-task-sets" / "001"
    assert download_calls == [
        {
            "remote_path": template_ref.uri,
            "local_path": str(staged_path),
            "workspace": "workspace-a",
        },
        {
            "remote_path": reference_ref.uri,
            "local_path": str(staged_reference_path),
            "workspace": "workspace-a",
        },
    ]
    assert [(evaluator_type, reference.uri) for evaluator_type, reference in dataset_factory.template_refs] == [
        ("harbor", str(staged_path))
    ]
    assert [(reference.uri, reference.metadata["id"]) for reference in inventory_refs[0]] == [
        (str(staged_reference_path), "reference")
    ]
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
    monkeypatch.setattr(
        eval_author_run,
        "build_reference_task_set_inventory",
        lambda refs: ReferenceTaskSetInventory.empty(),
        raising=False,
    )
    monkeypatch.setattr(eval_author_run, "_enable_litellm_drop_params", lambda: None)

    override = tmp_path / "override-agent"
    template = tmp_path / "template"
    template.mkdir()
    await eval_author_run.run_eval_author(
        request=_request(
            insight="insight-remote-123",
            task_template=DatasetRef(uri=str(template)),
            reference_task_sets=(DatasetRef(uri="reference"),),
        ),
        agent=override,
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
            request=_request(
                task_template=DatasetRef(uri="template"),
                reference_task_sets=(),
            ),
            experiment_dir=tmp_path / "eval_author",
            workspace="workspace-a",
            base_url="http://platform.test",
            config=EvalAuthorConfig(),
        )

    assert client.closed
