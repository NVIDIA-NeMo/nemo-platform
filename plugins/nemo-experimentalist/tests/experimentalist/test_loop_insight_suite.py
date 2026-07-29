# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from nemo_experimentalist_plugin.entities import Candidate
from nemo_experimentalist_plugin.experimentalist.components import loop as loop_module
from nemo_experimentalist_plugin.experimentalist.components.evaluator import (
    Dataset,
    EvaluationResult,
    MetricResult,
    Task,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborEvaluatorConfig
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    DatasetRef,
    DataValue,
    ResourceRef,
)
from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizer
from nemo_experimentalist_plugin.resolve import EvolutionaryOptimizerConfig


class _StopAfterOneRound(Exception):
    pass


def _suite_metadata(identity_char: str = "a") -> dict[str, DataValue]:
    identity = f"sha256:{identity_char * 64}"
    return {
        "insight_suite_identity": identity,
        "insight_suite_scorer_identity": f"sha256:{'b' * 64}",
        "insight_suite_task_hashes": {
            "insight-task": {
                "content_hash": f"sha256:{'c' * 64}",
                "verifier_hash": f"sha256:{'d' * 64}",
            }
        },
    }


def _insight_result(label: str, score: float) -> EvaluationResult:
    return EvaluationResult(
        id=f"{label}-insight",
        aggregate_metrics={"uses_required_tool": score},
        trials=[
            TrialResult(
                id=f"{label}-insight-task-1",
                task_id="insight-task",
                attempt=1,
                status="completed",
                metrics={
                    "uses_required_tool": MetricResult(
                        name="uses_required_tool",
                        value=score,
                    )
                },
            )
        ],
    )


@pytest.mark.asyncio
async def test_insight_run_evaluates_and_persists_baseline_and_new_candidate_metrics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    train_dataset = Dataset(id="train")
    validation_dataset = Dataset(id="validation")
    insight_dataset = Dataset(
        id="insight-suite",
        source=ResourceRef(uri="file:///experiment/eval-and-optimize/eval_author/insight-1/insight-suite"),
        tasks=[Task(id="insight-task")],
        metadata=_suite_metadata(),
    )
    datasets = {
        "train": train_dataset,
        "validation": validation_dataset,
    }

    class RecordingDatasetFactory:
        def build_dataset(self, evaluator_type: str, ref: DatasetRef) -> Dataset:
            return datasets[ref.uri]

        def build_task_template(self, evaluator_type: str, ref: DatasetRef) -> Task:
            return Task(id="template", uri=ref.uri)

    class ReturningEvalAuthor:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def run(self, **kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(
                train_dataset=kwargs["train_dataset"],
                validation_dataset=kwargs["validation_dataset"],
                insight_suite=insight_dataset,
            )

    baseline = Candidate(run_id="run-1", label="agent-0", round=0, optimization="baseline")
    new_candidate = Candidate(
        run_id="run-1",
        label="agent-1",
        ancestor="agent-0",
        round=1,
        optimization="use the required tool",
    )
    insight_results = {
        "agent-0": _insight_result("agent-0", 0.0),
        "agent-1": _insight_result("agent-1", 1.0),
    }
    insight_evaluations: list[tuple[Dataset, list[Candidate]]] = []

    async def evaluate_insight_candidates(
        self: EvolutionaryOptimizer,
        *,
        dataset: Dataset,
        evaluator: object,
        candidates: list[Candidate],
    ) -> dict[str, EvaluationResult]:
        insight_evaluations.append((dataset, candidates))
        return {candidate.label: insight_results[candidate.label] for candidate in candidates}

    async def evaluate_validation_candidates(
        self: EvolutionaryOptimizer,
        *,
        candidates: list[Candidate],
        **kwargs: object,
    ) -> dict[str, EvaluationResult]:
        return {
            candidate.label: EvaluationResult(
                id=f"{candidate.label}-validation",
                aggregate_metrics={"reward": 0.5},
            )
            for candidate in candidates
            if candidate.validation_reward is None
        }

    async def update_candidate(
        self: EvolutionaryOptimizer,
        candidate: Candidate,
        *,
        updates: dict[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        for key, value in (updates or {}).items():
            setattr(candidate, key, value)

    run_entity = SimpleNamespace(id="run-1", status="running", rounds_completed=0)
    backend = SimpleNamespace(
        client=object(),
        get_insight=AsyncMock(return_value=SimpleNamespace(agent="agent-source")),
        get_agent_code=AsyncMock(),
        persist_evaluation=AsyncMock(),
        update_run=AsyncMock(),
    )
    evolution_tree = SimpleNamespace(survivors=lambda round_num: [baseline], add=lambda candidate: None)

    class StopAfterOneRoundTerminator:
        calls = 0

        async def run(self, **kwargs: object) -> SimpleNamespace:
            self.calls += 1
            if self.calls > 1:
                raise _StopAfterOneRound
            return SimpleNamespace(stop=False, reason="continue")

    monkeypatch.setattr(loop_module, "DatasetFactory", RecordingDatasetFactory)
    monkeypatch.setattr(
        loop_module,
        "EvaluatorFactory",
        lambda: SimpleNamespace(
            build_evaluator=lambda *args, **kwargs: SimpleNamespace(prepare_dataset=lambda dataset: dataset)
        ),
    )
    monkeypatch.setattr(loop_module, "EvalAuthor", ReturningEvalAuthor)
    monkeypatch.setattr(
        loop_module,
        "stage_eval_author_inputs",
        AsyncMock(side_effect=lambda _, **refs: SimpleNamespace(**refs)),
    )
    monkeypatch.setattr(loop_module.EvolutionTree, "from_dir", lambda path: evolution_tree)
    monkeypatch.setattr(EvolutionaryOptimizer, "_detect_last_round", lambda self: None)
    monkeypatch.setattr(EvolutionaryOptimizer, "_create_experiment_run", AsyncMock(return_value=run_entity))
    monkeypatch.setattr(EvolutionaryOptimizer, "_create_baseline_agent", AsyncMock(return_value=baseline))
    monkeypatch.setattr(EvolutionaryOptimizer, "_update_candidate", update_candidate)
    monkeypatch.setattr(
        EvolutionaryOptimizer,
        "_evaluate_validation_candidates",
        evaluate_validation_candidates,
    )
    monkeypatch.setattr(
        EvolutionaryOptimizer,
        "_evaluate_insight_candidates",
        evaluate_insight_candidates,
        raising=False,
    )
    monkeypatch.setattr(EvolutionaryOptimizer, "_generate_initial_goal_tree", AsyncMock())
    monkeypatch.setattr(
        EvolutionaryOptimizer,
        "_evaluate_train_candidates",
        AsyncMock(
            return_value={
                "agent-0": EvaluationResult(id="agent-0-train", aggregate_metrics={"reward": 0.5}),
            }
        ),
    )
    monkeypatch.setattr(EvolutionaryOptimizer, "_analyze_round", AsyncMock(return_value="round analysis"))
    monkeypatch.setattr(EvolutionaryOptimizer, "_update_goal_tree", AsyncMock())
    monkeypatch.setattr(EvolutionaryOptimizer, "_propose_improvements", AsyncMock(return_value=[object()]))
    monkeypatch.setattr(EvolutionaryOptimizer, "_create_agent", lambda self, **kwargs: new_candidate)
    monkeypatch.setattr(
        EvolutionaryOptimizer,
        "_implement_candidates",
        AsyncMock(side_effect=lambda **kwargs: kwargs["candidates"]),
    )

    config = EvolutionaryOptimizerConfig(disable_trajectory_scoring=True)
    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    optimizer.config = config
    optimizer.shell = SimpleNamespace(close=AsyncMock())
    optimizer.terminator = StopAfterOneRoundTerminator()
    deps = SimpleNamespace(
        backend=backend,
        workspace="default",
        config=config,
        evaluator_type="harbor",
        train_dataset=DatasetRef(uri="train"),
        validation_dataset=DatasetRef(uri="validation"),
        task_template=DatasetRef(uri="template"),
        insight="insight-1",
        agent=None,
        agent_spec=None,
    )

    with pytest.raises(_StopAfterOneRound):
        await optimizer.run(deps)

    assert insight_evaluations == [
        (insight_dataset, [baseline]),
        (insight_dataset, [new_candidate]),
    ]
    assert baseline.insight_reward == {"uses_required_tool": 0.0}
    assert new_candidate.insight_reward == {"uses_required_tool": 1.0}
    assert baseline.insight_suite_identity == f"sha256:{'a' * 64}"
    assert new_candidate.insight_suite_identity == f"sha256:{'a' * 64}"
    assert baseline.insight_metric_keys == ["uses_required_tool"]
    insight_persistence = [
        call.kwargs for call in backend.persist_evaluation.await_args_list if call.kwargs["split"] == "insight"
    ]
    assert [call["candidate"] for call in insight_persistence] == [baseline, new_candidate]
    assert [call["result"].id for call in insight_persistence] == [
        insight_results["agent-0"].id,
        insight_results["agent-1"].id,
    ]
    assert all(
        call["result"].metadata["insight_suite_identity"] == f"sha256:{'a' * 64}" for call in insight_persistence
    )
    assert all(
        trial.metadata["insight_suite_scorer_identity"] == f"sha256:{'b' * 64}"
        for call in insight_persistence
        for trial in call["result"].trials
    )


@pytest.mark.asyncio
async def test_insight_evaluation_skips_cached_candidates_and_empty_suites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached = Candidate(
        run_id="run-1",
        label="agent-0",
        round=0,
        optimization="baseline",
        insight_reward={"uses_required_tool": 0.0},
        insight_reward_details=[],
        insight_suite_identity=f"sha256:{'a' * 64}",
        insight_metric_keys=["uses_required_tool"],
    )
    pending = Candidate(
        run_id="run-1",
        label="agent-1",
        round=1,
        optimization="use the required tool",
    )
    result = _insight_result("agent-1", 1.0)
    evaluate_agent = AsyncMock(return_value=(pending, result))
    monkeypatch.setattr(EvolutionaryOptimizer, "_evaluate_agent", evaluate_agent)
    optimizer = object.__new__(EvolutionaryOptimizer)

    evaluated = await optimizer._evaluate_insight_candidates(
        dataset=Dataset(
            id="insight-suite",
            source=ResourceRef(uri="file:///experiment/eval-and-optimize/eval_author/insight-1/insight-suite"),
            tasks=[Task(id="insight-task")],
            metadata=_suite_metadata(),
        ),
        evaluator=object(),  # type: ignore[arg-type]
        candidates=[cached, pending],
    )

    assert evaluated == {"agent-1": result}
    assert evaluate_agent.await_args is not None
    assert evaluate_agent.await_args.args[0] is pending
    assert evaluate_agent.await_args.kwargs["minimum_attempts"] == 2

    empty = await optimizer._evaluate_insight_candidates(
        dataset=Dataset(id="empty-insight-suite"),
        evaluator=object(),  # type: ignore[arg-type]
        candidates=[pending],
    )
    assert empty == {}
    assert evaluate_agent.await_count == 1


@pytest.mark.asyncio
async def test_insight_evaluation_reuses_only_matching_suite_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached = Candidate(
        run_id="run-1",
        label="agent-0",
        round=0,
        optimization="baseline",
        insight_reward={"uses_required_tool": 0.0},
        insight_reward_details=[],
        insight_suite_identity=f"sha256:{'a' * 64}",
        insight_metric_keys=["uses_required_tool"],
    )
    result = _insight_result("agent-0", 0.5)
    evaluate_agent = AsyncMock(return_value=(cached, result))
    monkeypatch.setattr(EvolutionaryOptimizer, "_evaluate_agent", evaluate_agent)
    optimizer = object.__new__(EvolutionaryOptimizer)

    matching = Dataset(
        id="insight-suite",
        source=ResourceRef(uri="file:///experiment/eval-and-optimize/eval_author/insight-1/insight-suite"),
        tasks=[Task(id="insight-task")],
        metadata=_suite_metadata("a"),
    )
    changed = Dataset(
        id="insight-suite",
        source=ResourceRef(uri="file:///experiment/eval-and-optimize/eval_author/insight-1/insight-suite"),
        tasks=[Task(id="insight-task")],
        metadata=_suite_metadata("e"),
    )

    assert (
        await optimizer._evaluate_insight_candidates(
            dataset=matching,
            evaluator=object(),  # type: ignore[arg-type]
            candidates=[cached],
        )
        == {}
    )
    assert await optimizer._evaluate_insight_candidates(
        dataset=changed,
        evaluator=object(),  # type: ignore[arg-type]
        candidates=[cached],
    ) == {"agent-0": result}
    evaluate_agent.assert_awaited_once()


@pytest.mark.asyncio
async def test_cached_insight_metric_keys_are_order_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = f"sha256:{'a' * 64}"
    candidates = [
        Candidate(
            run_id="run-1",
            label="agent-0",
            round=0,
            optimization="baseline",
            insight_reward={"reward": 0.5, "uses_required_tool": 0.0},
            insight_reward_details=[],
            insight_suite_identity=identity,
            insight_metric_keys=["uses_required_tool", "reward"],
        ),
        Candidate(
            run_id="run-1",
            label="agent-1",
            round=1,
            optimization="improve tool use",
            insight_reward={"reward": 0.75, "uses_required_tool": 1.0},
            insight_reward_details=[],
            insight_suite_identity=identity,
            insight_metric_keys=["reward", "uses_required_tool"],
        ),
    ]
    dataset = Dataset(
        id="insight-suite",
        source=ResourceRef(uri="file:///experiment/eval-and-optimize/eval_author/insight-1/insight-suite"),
        tasks=[Task(id="insight-task")],
        metadata={
            **_suite_metadata(),
            "insight_metric_keys": ["uses_required_tool", "reward"],
        },
    )
    optimizer = object.__new__(EvolutionaryOptimizer)
    monkeypatch.setattr(
        optimizer,
        "_evaluate_insight_candidates",
        AsyncMock(return_value={}),
    )

    await optimizer._evaluate_and_persist_insight_candidates(
        dataset=dataset,
        evaluator=object(),  # type: ignore[arg-type]
        candidates=candidates,
        workspace="default",
        backend=SimpleNamespace(),
        run_id="run-1",
    )

    assert dataset.metadata["insight_metric_keys"] == ["reward", "uses_required_tool"]


@pytest.mark.asyncio
async def test_insight_evaluation_uses_at_least_two_attempts_without_changing_other_splits(
    tmp_path: Path,
) -> None:
    candidate = Candidate(
        run_id="run-1",
        label="agent-0",
        round=0,
        optimization="baseline",
    )
    received_attempts: list[int] = []

    class RecordingEvaluator:
        options = HarborEvaluatorConfig(n_attempts=1)

        async def run(self, **kwargs: object) -> EvaluationResult:
            options = kwargs["options"]
            assert isinstance(options, HarborEvaluatorConfig)
            received_attempts.append(options.n_attempts)
            return _insight_result(candidate.label, 0.5)

    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    evaluator = RecordingEvaluator()
    dataset = Dataset(id="insight-suite")

    await optimizer._evaluate_agent(candidate, dataset, evaluator)  # type: ignore[arg-type]
    await optimizer._evaluate_agent(
        candidate,
        dataset,
        evaluator,  # type: ignore[arg-type]
        minimum_attempts=2,
    )

    assert received_attempts == [1, 2]
    assert evaluator.options.n_attempts == 1


def test_rollback_removes_digest_named_insight_results(tmp_path: Path) -> None:
    root = tmp_path / "eval-and-optimize"
    agents_dir = root / "agents"
    results_dir = root / "results"
    analysis_dir = root / "analysis"
    smoke_dataset_dir = root / "smoke-dataset"
    smoke_results_dir = root / "smoke-results"
    for directory in (agents_dir, results_dir, analysis_dir, smoke_dataset_dir, smoke_results_dir):
        directory.mkdir(parents=True)

    removed_agent = agents_dir / "agent-2"
    removed_agent.mkdir()
    (removed_agent / "metadata.json").write_text('{"round": 2}\n')
    surviving_agent = agents_dir / "agent-20"
    surviving_agent.mkdir()
    (surviving_agent / "metadata.json").write_text('{"round": 1}\n')

    removed_results = [
        results_dir / "agent-2-train",
        results_dir / "agent-2-validation",
        results_dir / "agent-2-insight-abcdef123456",
    ]
    for result_dir in removed_results:
        result_dir.mkdir()
    surviving_result = results_dir / "agent-20-insight-abcdef123456"
    surviving_result.mkdir()

    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    optimizer._delete_all_artifacts(from_round=1)

    assert not removed_agent.exists()
    assert all(not result_dir.exists() for result_dir in removed_results)
    assert surviving_agent.is_dir()
    assert surviving_result.is_dir()
