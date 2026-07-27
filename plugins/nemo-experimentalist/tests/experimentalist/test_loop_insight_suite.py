# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from nemo_experimentalist_plugin.entities import Candidate
from nemo_experimentalist_plugin.experimentalist.components import loop as loop_module
from nemo_experimentalist_plugin.experimentalist.components.evaluator import Dataset, EvaluationResult, Task
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DatasetRef
from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizer
from nemo_experimentalist_plugin.resolve import EvolutionaryOptimizerConfig


class _StopAfterOneRound(Exception):
    pass


@pytest.mark.asyncio
async def test_insight_run_evaluates_and_persists_baseline_and_new_candidate_metrics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    train_dataset = Dataset(id="train")
    validation_dataset = Dataset(id="validation")
    insight_dataset = Dataset(id="insight-suite", tasks=[Task(id="insight-task")])
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
        "agent-0": EvaluationResult(
            id="agent-0-insight",
            aggregate_metrics={"uses_required_tool": 0.0},
        ),
        "agent-1": EvaluationResult(
            id="agent-1-insight",
            aggregate_metrics={"uses_required_tool": 1.0},
        ),
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
        lambda: SimpleNamespace(build_evaluator=lambda *args, **kwargs: object()),
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
    insight_persistence = [
        call.kwargs for call in backend.persist_evaluation.await_args_list if call.kwargs["split"] == "insight"
    ]
    assert insight_persistence == [
        {
            "workspace": "default",
            "result": insight_results["agent-0"],
            "candidate": baseline,
            "split": "insight",
        },
        {
            "workspace": "default",
            "result": insight_results["agent-1"],
            "candidate": new_candidate,
            "split": "insight",
        },
    ]


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
    )
    pending = Candidate(
        run_id="run-1",
        label="agent-1",
        round=1,
        optimization="use the required tool",
    )
    result = EvaluationResult(
        id="agent-1-insight",
        aggregate_metrics={"uses_required_tool": 1.0},
    )
    evaluate_agent = AsyncMock(return_value=(pending, result))
    monkeypatch.setattr(EvolutionaryOptimizer, "_evaluate_agent", evaluate_agent)
    optimizer = object.__new__(EvolutionaryOptimizer)

    evaluated = await optimizer._evaluate_insight_candidates(
        dataset=Dataset(id="insight-suite", tasks=[Task(id="insight-task")]),
        evaluator=object(),  # type: ignore[arg-type]
        candidates=[cached, pending],
    )

    assert evaluated == {"agent-1": result}
    assert evaluate_agent.await_args is not None
    assert evaluate_agent.await_args.args[0] is pending

    empty = await optimizer._evaluate_insight_candidates(
        dataset=Dataset(id="empty-insight-suite"),
        evaluator=object(),  # type: ignore[arg-type]
        candidates=[pending],
    )
    assert empty == {}
    assert evaluate_agent.await_count == 1
