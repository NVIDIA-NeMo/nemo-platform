# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The orchestration boundary accepts only authoring inputs."""

import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from nemo_eval_author_plugin.eval_author import run as eval_author_run
from nemo_eval_author_plugin.eval_author.agent import EvalAuthor
from nemo_eval_author_plugin.eval_author.models import (
    ArtifactDescriptor,
    EvalAuthorConfig,
    EvalAuthorResult,
)
from nemo_experimentalist_plugin.entities import DatasetRef, Task
from nemo_insights_plugin.entities import Insight


@dataclass
class ClosingClient:
    closed: bool = False
    files: Any = None

    async def close(self) -> None:
        self.closed = True


class FakeBackend:
    def __init__(self, insight: Insight) -> None:
        self.insight = insight
        self.insight_calls: list[tuple[str, str]] = []
        self.agent_calls: list[tuple[str, str | Path, Path]] = []

    async def get_insight(self, *, workspace: str, insight_id: str) -> Insight:
        self.insight_calls.append((workspace, insight_id))
        return self.insight

    async def get_agent_code(self, *, workspace: str, agent: str | Path, dest: Path) -> None:
        self.agent_calls.append((workspace, agent, dest))


class FakeDatasetFactory:
    def __init__(self) -> None:
        self.template = Task(id="template", uri="file:///template")
        self.calls: list[tuple[str, DatasetRef]] = []

    def build_task_template(self, evaluator_type: str, template_ref: DatasetRef) -> Task:
        self.calls.append((evaluator_type, template_ref))
        return self.template


class FakeEvalAuthor:
    def __init__(self) -> None:
        self.call: tuple[Insight, Path, Task, ClosingClient] | None = None

    async def run(
        self,
        insight: Insight,
        agent_path: Path,
        task_template: Task,
        *,
        client: ClosingClient,
    ) -> EvalAuthorResult:
        self.call = (insight, agent_path, task_template, client)
        return EvalAuthorResult(
            task_set=ArtifactDescriptor(
                uri="file:///artifacts/task-set",
                identity=f"sha256:{'a' * 64}",
            ),
            verifier_bundle=ArtifactDescriptor(
                uri="file:///artifacts/verifier-bundle",
                identity=f"sha256:{'b' * 64}",
            ),
            metric_keys=("uses_correct_tool",),
            summary="Eval Author complete.",
        )


@pytest.mark.asyncio
async def test_run_eval_author_resolves_inputs_and_returns_artifact_refs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = ClosingClient()
    insight = Insight(
        workspace="workspace-a",
        title="failure",
        description="description",
        agent="insight-agent",
        trace_refs=["trace-1"],
    )
    backend = FakeBackend(insight)
    dataset_factory = FakeDatasetFactory()
    eval_author = FakeEvalAuthor()
    monkeypatch.setattr(eval_author_run, "make_client", lambda _: client)
    monkeypatch.setattr(eval_author_run, "make_experimentalist_backend", lambda **_: backend)
    monkeypatch.setattr(eval_author_run, "DatasetFactory", lambda: dataset_factory)
    monkeypatch.setattr(eval_author_run, "build_eval_author_agent", lambda **_: eval_author)
    monkeypatch.setattr(eval_author_run, "_enable_litellm_drop_params", lambda: None)
    template = tmp_path / "template"
    template.mkdir()
    (template / "task.toml").write_text("template\n", encoding="utf-8")

    result = await eval_author_run.run_eval_author(
        insight="insight-123",
        task_template=DatasetRef(uri=str(template)),
        experiment_dir=tmp_path / "experiment",
        workspace="workspace-a",
        base_url="http://platform.test",
        config=EvalAuthorConfig(),
    )

    experiment_dir = (tmp_path / "experiment").resolve()
    assert result.task_set == ArtifactDescriptor(
        uri="file:///artifacts/task-set",
        identity=f"sha256:{'a' * 64}",
    )
    assert result.verifier_bundle == ArtifactDescriptor(
        uri="file:///artifacts/verifier-bundle",
        identity=f"sha256:{'b' * 64}",
    )
    assert result.metric_keys == ("uses_correct_tool",)
    assert backend.insight_calls == [("workspace-a", "insight-123")]
    assert backend.agent_calls == [
        ("workspace-a", "insight-agent", experiment_dir / "eval_author" / "source-agent"),
    ]
    assert dataset_factory.calls[0][0] == "harbor"
    assert eval_author.call == (
        insight,
        experiment_dir / "eval_author" / "source-agent",
        dataset_factory.template,
        client,
    )
    assert client.closed


def test_public_apis_have_no_request_inventory_or_dataset_splits() -> None:
    orchestration = inspect.signature(eval_author_run.run_eval_author).parameters
    agent_run = inspect.signature(EvalAuthor.run).parameters
    agent_private_run = inspect.signature(EvalAuthor._run).parameters

    assert {"insight", "task_template"} <= set(orchestration)
    assert {"request", "train_dataset", "validation_dataset", "reference_task_sets"}.isdisjoint(orchestration)
    assert set(agent_run) == {"self", "insight", "agent_path", "task_template", "client"}
    assert set(agent_private_run) == {"self", "insight", "agent_path", "task_template", "client"}


@pytest.mark.asyncio
async def test_run_eval_author_hydrates_fileset_task_template(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    downloads: list[tuple[str, str, str]] = []

    class FakeFiles:
        async def download(self, *, remote_path: str, local_path: str, workspace: str) -> None:
            downloads.append((remote_path, local_path, workspace))
            destination = Path(local_path)
            destination.mkdir(parents=True)
            (destination / "task.toml").write_text("template\n", encoding="utf-8")

    client = ClosingClient(files=FakeFiles())
    backend = FakeBackend(
        Insight(workspace="workspace-a", title="failure", description="description", agent="insight-agent")
    )
    dataset_factory = FakeDatasetFactory()
    monkeypatch.setattr(eval_author_run, "make_client", lambda _: client)
    monkeypatch.setattr(eval_author_run, "make_experimentalist_backend", lambda **_: backend)
    monkeypatch.setattr(eval_author_run, "DatasetFactory", lambda: dataset_factory)
    monkeypatch.setattr(eval_author_run, "build_eval_author_agent", lambda **_: FakeEvalAuthor())
    monkeypatch.setattr(eval_author_run, "_enable_litellm_drop_params", lambda: None)
    template_ref = DatasetRef(uri="fileset://workspace-a/template")

    await eval_author_run.run_eval_author(
        insight="insight-123",
        task_template=template_ref,
        experiment_dir=tmp_path / "experiment",
        workspace="workspace-a",
        base_url=None,
        config=EvalAuthorConfig(),
    )

    staged = (tmp_path / "experiment").resolve() / "dataset" / "task-template"
    assert downloads == [(template_ref.uri, str(staged), "workspace-a")]
    assert dataset_factory.calls == [("harbor", template_ref.model_copy(update={"uri": str(staged)}))]
    assert client.closed


@pytest.mark.asyncio
async def test_run_eval_author_closes_client_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = ClosingClient()
    monkeypatch.setattr(eval_author_run, "make_client", lambda _: client)
    monkeypatch.setattr(
        eval_author_run,
        "make_experimentalist_backend",
        lambda **_: (_ for _ in ()).throw(RuntimeError("backend failed")),
    )

    with pytest.raises(RuntimeError, match="backend failed"):
        await eval_author_run.run_eval_author(
            insight="insight-123",
            task_template=DatasetRef(uri="template"),
            experiment_dir=tmp_path,
            workspace="workspace-a",
            base_url=None,
            config=EvalAuthorConfig(),
        )

    assert client.closed
