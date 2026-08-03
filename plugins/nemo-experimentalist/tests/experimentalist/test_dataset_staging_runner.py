# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The runner stages Eval Author's inputs before calling it, so the source is untouched."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from doubles import FakeBackend, fake_client
from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.entities import DatasetRef
from nemo_experimentalist_plugin.experimentalist import runner as runner_module
from nemo_experimentalist_plugin.experimentalist.runner import ExperimentRunner
from nemo_insights_plugin.entities import Insight


class _UnreachedStrategy:
    """Never runs: Eval Author raises while the runner is still preparing inputs."""

    supports_resume = True

    async def run(self, ctx: object) -> None:
        raise AssertionError("the strategy must not start when input preparation fails")


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
        runner_module,
        "EvaluatorFactory",
        lambda: SimpleNamespace(build_evaluator=lambda *args, **kwargs: object()),
    )
    monkeypatch.setattr(runner_module, "DatasetFactory", RecordingDatasetFactory)
    monkeypatch.setattr("nemo_eval_author_plugin.eval_author.agent.EvalAuthor", MutatingEvalAuthor)

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    runner = ExperimentRunner(
        backend=FakeBackend(
            client=fake_client(),
            insight=Insight(workspace="default", agent=str(agent_dir), title="t", description="d"),
        ),
        strategy=_UnreachedStrategy(),
        config=EvolutionaryOptimizerConfig(),
        workspace="default",
        root=experiment,
        agent=agent_dir,
        insight="insight-1",
        train_dataset=DatasetRef(uri=str(train)),
        validation_dataset=DatasetRef(uri=str(validation)),
        task_template=DatasetRef(uri=str(template)),
    )

    with pytest.raises(RuntimeError, match="stop after eval_author"):
        await runner.run()

    assert captured == {
        "train": experiment / "dataset" / "train",
        "validation": experiment / "dataset" / "validation",
        "template": experiment / "dataset" / "task-template",
    }
    assert (train / "task-1" / "tests" / "test.sh").read_text(encoding="utf-8") == "train source"
    assert not (template.parent / "generated-task").exists()
