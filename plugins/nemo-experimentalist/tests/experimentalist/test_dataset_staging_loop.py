# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Loop integration: Experimentalist stages Eval Author inputs before calling Eval Author."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nemo_eval_author_plugin.evaluator.models import DatasetRef
from nemo_experimentalist_plugin.experimentalist.components import loop as loop_module
from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizer
from nemo_experimentalist_plugin.resolve import EvolutionaryOptimizerConfig


def _write_tree(root: Path, content: str) -> None:
    tests = root / "task-1" / "tests"
    tests.mkdir(parents=True)
    (tests / "test.sh").write_text(content, encoding="utf-8")


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
        lambda: SimpleNamespace(build_evaluator=lambda *args, **kwargs: object()),
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
