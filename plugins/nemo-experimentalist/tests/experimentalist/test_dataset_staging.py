# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from nemo_experimentalist_plugin.experimentalist.components import loop as loop_module
from nemo_experimentalist_plugin.experimentalist.components.dataset_staging import (
    stage_eval_author_inputs,
    stage_task_template,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DatasetRef
from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizer
from nemo_experimentalist_plugin.resolve import EvolutionaryOptimizerConfig
from nemo_platform import AsyncNeMoPlatform


def _write_tree(root: Path, content: str) -> None:
    tests = root / "task-1" / "tests"
    tests.mkdir(parents=True)
    (tests / "test.sh").write_text(content, encoding="utf-8")


@pytest.mark.asyncio
async def test_stage_eval_author_inputs_isolates_all_mutable_sources(tmp_path: Path) -> None:
    source = tmp_path / "source"
    train = source / "train"
    validation = source / "validation"
    template = source / "task-template"
    _write_tree(train, "train source")
    _write_tree(validation, "validation source")
    _write_tree(template, "template source")

    experiment = tmp_path / "experiment"
    staged = await stage_eval_author_inputs(
        experiment,
        train_dataset=DatasetRef(uri=str(train), metadata={"id": "train"}),
        validation_dataset=DatasetRef(uri=str(validation), metadata={"id": "validation"}),
        task_template=DatasetRef(uri=template.as_uri(), metadata={"id": "template"}),
        client=cast(AsyncNeMoPlatform, object()),
        workspace="default",
    )

    staged_train = Path(staged.train_dataset.uri)
    staged_validation = Path(staged.validation_dataset.uri)
    staged_template = Path(staged.task_template.uri)
    (staged_train / "task-1" / "tests" / "test.sh").write_text("curated train", encoding="utf-8")
    (staged_validation / "task-1" / "tests" / "test.sh").write_text("curated validation", encoding="utf-8")
    generated = staged_template.parent / "generated-task"
    generated.mkdir()

    assert (train / "task-1" / "tests" / "test.sh").read_text(encoding="utf-8") == "train source"
    assert (validation / "task-1" / "tests" / "test.sh").read_text(encoding="utf-8") == "validation source"
    assert not (template.parent / "generated-task").exists()
    assert staged_train == experiment / "dataset" / "train"
    assert staged_validation == experiment / "dataset" / "validation"
    assert staged_template == experiment / "dataset" / "task-template"
    assert staged.train_dataset.metadata == {"id": "train"}
    assert staged.validation_dataset.metadata == {"id": "validation"}
    assert staged.task_template.metadata == {"id": "template"}


@pytest.mark.asyncio
async def test_stage_eval_author_inputs_keeps_train_and_validation_isolated_when_source_is_shared(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared"
    template = tmp_path / "template"
    _write_tree(shared, "shared source")
    _write_tree(template, "template source")
    shared_ref = DatasetRef(uri=str(shared))

    staged = await stage_eval_author_inputs(
        tmp_path / "experiment",
        train_dataset=shared_ref,
        validation_dataset=shared_ref,
        task_template=DatasetRef(uri=str(template)),
        client=cast(AsyncNeMoPlatform, object()),
        workspace="default",
    )
    staged_train_test = Path(staged.train_dataset.uri) / "task-1" / "tests" / "test.sh"
    staged_validation_test = Path(staged.validation_dataset.uri) / "task-1" / "tests" / "test.sh"
    staged_train_test.write_text("train only", encoding="utf-8")

    assert staged_validation_test.read_text(encoding="utf-8") == "shared source"
    assert (shared / "task-1" / "tests" / "test.sh").read_text(encoding="utf-8") == "shared source"


@pytest.mark.asyncio
async def test_stage_eval_author_inputs_reuses_dataset_destinations_but_refreshes_template(tmp_path: Path) -> None:
    source = tmp_path / "source"
    template = tmp_path / "template"
    experiment = tmp_path / "experiment"
    _write_tree(source, "source")
    _write_tree(template, "template")
    staged = await stage_eval_author_inputs(
        experiment,
        train_dataset=DatasetRef(uri=str(source)),
        validation_dataset=DatasetRef(uri=str(source)),
        task_template=DatasetRef(uri=str(template)),
        client=cast(AsyncNeMoPlatform, object()),
        workspace="default",
    )
    (Path(staged.train_dataset.uri) / "task-1" / "tests" / "test.sh").write_text("curated", encoding="utf-8")
    (template / "task-1" / "tests" / "test.sh").write_text("updated template", encoding="utf-8")

    restaged = await stage_eval_author_inputs(
        experiment,
        train_dataset=DatasetRef(uri=str(source)),
        validation_dataset=DatasetRef(uri=str(source)),
        task_template=DatasetRef(uri=str(template)),
        client=cast(AsyncNeMoPlatform, object()),
        workspace="default",
    )

    staged_test = Path(restaged.train_dataset.uri) / "task-1" / "tests" / "test.sh"
    assert staged_test.read_text(encoding="utf-8") == "curated"
    staged_template_test = Path(restaged.task_template.uri) / "task-1" / "tests" / "test.sh"
    assert staged_template_test.read_text(encoding="utf-8") == "updated template"


@pytest.mark.asyncio
async def test_stage_task_template_hydrates_and_refreshes_fileset_reference(tmp_path: Path) -> None:
    calls: list[dict[str, str]] = []
    content = "first fileset template"

    class FakeFiles:
        async def download(self, *, remote_path: str, local_path: str, workspace: str) -> None:
            assert Path(local_path).parent.is_dir()
            calls.append({"remote_path": remote_path, "local_path": local_path, "workspace": workspace})
            _write_tree(Path(local_path), content)

    client = cast(AsyncNeMoPlatform, SimpleNamespace(files=FakeFiles()))
    ref = DatasetRef(uri="fileset://workspace-a/task-template", metadata={"id": "template-fileset"})

    first = await stage_task_template(tmp_path / "experiment", ref, client=client, workspace="workspace-a")
    content = "second fileset template"
    second = await stage_task_template(tmp_path / "experiment", ref, client=client, workspace="workspace-a")

    expected_path = tmp_path / "experiment" / "dataset" / "task-template"
    assert first.uri == str(expected_path)
    assert second.uri == str(expected_path)
    assert second.metadata == {"id": "template-fileset"}
    assert (expected_path / "task-1" / "tests" / "test.sh").read_text(encoding="utf-8") == content
    assert calls == [
        {
            "remote_path": ref.uri,
            "local_path": str(expected_path),
            "workspace": "workspace-a",
        },
        {
            "remote_path": ref.uri,
            "local_path": str(expected_path),
            "workspace": "workspace-a",
        },
    ]


@pytest.mark.asyncio
async def test_insight_run_stages_inputs_before_eval_author(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    train = source / "train"
    validation = source / "validation"
    template = source / "task-template"
    _write_tree(train, "train source")
    _write_tree(validation, "validation source")
    _write_tree(template, "template source")
    experiment = tmp_path / "experiment"
    captured: dict[str, Path] = {}

    class RecordingDatasetFactory:
        def build_dataset(self, evaluator_type: str, ref: DatasetRef) -> SimpleNamespace:
            return SimpleNamespace(ref=ref)

        def build_task_template(self, evaluator_type: str, ref: DatasetRef) -> SimpleNamespace:
            return SimpleNamespace(uri=ref.uri)

    class MutatingEvalAuthor:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def run(
            self,
            *,
            task_template: SimpleNamespace,
            train_dataset: SimpleNamespace,
            validation_dataset: SimpleNamespace,
            **kwargs: object,
        ) -> None:
            captured["train"] = Path(train_dataset.ref.uri)
            captured["validation"] = Path(validation_dataset.ref.uri)
            captured["template"] = Path(task_template.uri)
            (captured["train"] / "task-1" / "tests" / "test.sh").write_text("curated", encoding="utf-8")
            (captured["template"].parent / "generated-task").mkdir()
            raise RuntimeError("stop after eval_author")

    monkeypatch.setattr(
        loop_module,
        "EvaluatorFactory",
        lambda: SimpleNamespace(
            build_evaluator=lambda *args, **kwargs: SimpleNamespace(prepare_dataset=lambda dataset: dataset)
        ),
    )
    monkeypatch.setattr(loop_module, "DatasetFactory", RecordingDatasetFactory)
    monkeypatch.setattr(loop_module, "EvalAuthor", MutatingEvalAuthor)
    monkeypatch.setattr(
        EvolutionaryOptimizer,
        "_init_structure",
        lambda self: (experiment / "agents", experiment / "analysis", experiment / "results"),
    )

    backend = SimpleNamespace(
        client=object(),
        get_insight=AsyncMock(return_value=SimpleNamespace(agent=str(tmp_path / "agent"))),
        get_agent_code=AsyncMock(),
    )
    config = EvolutionaryOptimizerConfig()
    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = experiment
    optimizer.config = config
    optimizer.shell = SimpleNamespace(close=AsyncMock())
    deps = SimpleNamespace(
        backend=backend,
        workspace="default",
        config=config,
        evaluator_type="harbor",
        train_dataset=DatasetRef(uri=str(train)),
        validation_dataset=DatasetRef(uri=str(validation)),
        task_template=DatasetRef(uri=str(template)),
        insight="insight-1",
        agent=tmp_path / "agent",
        agent_spec=None,
    )

    with pytest.raises(RuntimeError, match="stop after eval_author"):
        await optimizer.run(deps)

    optimizer.shell.close.assert_awaited_once()
    assert captured == {
        "train": experiment / "dataset" / "train",
        "validation": experiment / "dataset" / "validation",
        "template": experiment / "dataset" / "task-template",
    }
    assert (train / "task-1" / "tests" / "test.sh").read_text(encoding="utf-8") == "train source"
    assert not (template.parent / "generated-task").exists()
