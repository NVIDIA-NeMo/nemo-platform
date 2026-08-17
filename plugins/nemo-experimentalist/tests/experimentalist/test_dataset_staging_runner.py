# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The runner stages Eval Author's inputs before calling it, so the source is untouched."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from doubles import FakeBackend, fake_client
from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.entities import DatasetRef
from nemo_experimentalist_plugin.experimentalist import runner as runner_module
from nemo_experimentalist_plugin.experimentalist.runner import ExperimentRunner
from nemo_insights_plugin.entities import Insight


class _StopAfterStaging:
    """Ends the run as soon as inputs are prepared.

    What is under test is that Eval Author was handed *staged copies* under the
    experiment directory rather than the caller's own dataset, so the run only has to
    get as far as the strategy.
    """

    supports_resume = True
    seen_objectives: list[Any] = []

    async def run(self, ctx: object) -> None:
        type(self).seen_objectives = list(getattr(ctx, "objective_metrics", []))
        raise RuntimeError("stop after eval_author")


def _write_tree(root: Path, content: str) -> None:
    tests = root / "task-1" / "tests"
    tests.mkdir(parents=True)
    (tests / "test.sh").write_text(content, encoding="utf-8")


def _stub_author_model_clients(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Mode 1 now resolves Author-scoped clients; keep staging tests offline."""
    resolve_calls: list[object] = []

    class _Clients:
        async def aclose(self) -> None:
            return None

    async def resolve(client: object, refs: object = None, options: object = None) -> _Clients:
        resolve_calls.append(options)
        return _Clients()

    monkeypatch.setattr(
        "nemo_platform_plugin.nooa_model_client.resolve_model_clients",
        resolve,
    )
    monkeypatch.setattr(
        "nemo_platform_plugin.nooa_model_client.get_configured_model_refs",
        lambda: SimpleNamespace(default="default/m", fast="default/m"),
    )
    return resolve_calls


@pytest.mark.asyncio
async def test_insight_run_stages_inputs_and_stops_at_eval_author_handoff(
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
    build_options: list[dict[str, object]] = []

    class EvalAuthorHandoff:
        def __init__(self, train_dataset: SimpleNamespace, validation_dataset: SimpleNamespace) -> None:
            self.train_dataset = train_dataset
            self.validation_dataset = validation_dataset
            self.insight_suite = None
            self.metric_keys = ("reward",)

    class RecordingDatasetFactory:
        def build_dataset(self, evaluator_type: str, ref: DatasetRef, **options: object) -> SimpleNamespace:
            build_options.append(options)
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
        ) -> EvalAuthorHandoff:
            captured["train"] = Path(train_dataset.ref.uri)
            captured["validation"] = Path(validation_dataset.ref.uri)
            captured["template"] = Path(task_template.uri)
            (captured["train"] / "task-1" / "tests" / "test.sh").write_text("curated", encoding="utf-8")
            (captured["template"].parent / "generated-task").mkdir()
            return EvalAuthorHandoff(train_dataset, validation_dataset)

    monkeypatch.setattr(
        runner_module,
        "EvaluatorFactory",
        lambda: SimpleNamespace(build_evaluator=lambda *args, **kwargs: object()),
    )
    monkeypatch.setattr(runner_module, "DatasetFactory", RecordingDatasetFactory)
    monkeypatch.setattr("nemo_eval_author_plugin.eval_author.agent.EvalAuthor", MutatingEvalAuthor)
    resolve_calls = _stub_author_model_clients(monkeypatch)

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    runner = ExperimentRunner(
        backend=FakeBackend(
            client=fake_client(),
            insight=Insight(workspace="default", agent=str(agent_dir), title="t", description="d"),
        ),
        strategy=_StopAfterStaging(),
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
    # An insight run's splits are empty until the Eval Author fills them, and build_dataset
    # refuses an empty split by default -- so the run cannot start without this.
    assert build_options and all(o.get("allow_empty") is True for o in build_options), (
        f"runner built datasets without allow_empty in insight mode: {build_options}"
    )
    assert not (template.parent / "generated-task").exists()
    assert len(resolve_calls) == 1
    assert getattr(resolve_calls[0], "reasoning_effort", None) == "medium"


@pytest.mark.asyncio
async def test_authored_metrics_and_suite_reach_the_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Mode 1's authored output must change what the run optimizes and evaluates.

    The Eval Author writes verifiers that emit their own metric keys and a suite of
    production-trace tasks. If the keys do not become the objective, selection keeps
    ranking on `reward` — which those verifiers never emit, so nothing is eligible to
    win. If the suite is not distributed into the splits the loop evaluates, the tasks
    it authored are never run.
    """
    source = tmp_path / "source"
    for name in ("train", "validation", "task-template"):
        _write_tree(source / name, f"{name} source")
    experiment = tmp_path / "experiment"
    distributed: dict[str, Any] = {}

    class Authored:
        def __init__(self, train_dataset: SimpleNamespace, validation_dataset: SimpleNamespace) -> None:
            self.train_dataset = train_dataset
            self.validation_dataset = validation_dataset
            self.insight_suite: Any = SimpleNamespace(id="insight-suite")
            self.metric_keys = ("cites_source", "uses_required_tool")

    class Factory:
        def build_dataset(self, evaluator_type: str, ref: DatasetRef, **_options: object) -> SimpleNamespace:
            return SimpleNamespace(ref=ref)

        def build_task_template(self, evaluator_type: str, ref: DatasetRef) -> SimpleNamespace:
            return SimpleNamespace(uri=ref.uri)

    class Author:
        def __init__(self, **kwargs: object) -> None: ...

        async def run(self, *, train_dataset, validation_dataset, **kwargs: object) -> Authored:  # noqa: ANN001
            return Authored(train_dataset, validation_dataset)

    monkeypatch.setattr(
        runner_module, "EvaluatorFactory", lambda: SimpleNamespace(build_evaluator=lambda *a, **k: object())
    )
    monkeypatch.setattr(runner_module, "DatasetFactory", Factory)
    monkeypatch.setattr("nemo_eval_author_plugin.eval_author.agent.EvalAuthor", Author)
    monkeypatch.setattr(
        runner_module,
        "distribute_insight_suite_tasks",
        lambda suite, train, validation: distributed.update(suite=suite, train=train, validation=validation),
    )
    _stub_author_model_clients(monkeypatch)

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    runner = ExperimentRunner(
        backend=FakeBackend(
            client=fake_client(),
            insight=Insight(workspace="default", agent=str(agent_dir), title="t", description="d"),
        ),
        strategy=_StopAfterStaging(),
        config=EvolutionaryOptimizerConfig(),
        workspace="default",
        root=experiment,
        agent=agent_dir,
        insight="insight-1",
        train_dataset=DatasetRef(uri=str(source / "train")),
        validation_dataset=DatasetRef(uri=str(source / "validation")),
        task_template=DatasetRef(uri=str(source / "task-template")),
    )

    with pytest.raises(RuntimeError, match="stop after eval_author"):
        await runner.run()

    assert [t.name for t in runner._config.objective_function] == ["cites_source", "uses_required_tool"]
    assert [t.name for t in _StopAfterStaging.seen_objectives] == ["cites_source", "uses_required_tool"], (
        "the strategy must receive the settled contract through the context"
    )
    assert [t.name for t in runner._config.regression_metrics] == ["reward"], "configured targets demote to guardrails"
    assert cast(Any, distributed["suite"]).id == "insight-suite", (
        "the authored suite must reach the splits the loop evaluates"
    )
