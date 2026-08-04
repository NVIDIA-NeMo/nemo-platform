# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Multi-round guards that every living candidate keeps full Insight signal.

The single-round harness in ``test_loop_insight_suite.py`` never exercises the
multi-candidate path: round 0 has only the baseline, so survivor selection takes
the ``list(candidates)`` branch and no candidate is ever replaced by a slimmed
copy. These tests run the loop for several rounds with the real evaluation,
selection, and caching code so the per-round signal contract is checked where it
can actually break.
"""

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from nemo_experimentalist_plugin.entities import (
    INSIGHT_TRAIN_FIELDS,
    INSIGHT_VALIDATION_FIELDS,
    Candidate,
    InsightSplitFields,
)
from nemo_experimentalist_plugin.experimentalist.components import loop as loop_module
from nemo_experimentalist_plugin.experimentalist.components.evaluator import (
    Dataset,
    EvaluationResult,
    MetricResult,
    Task,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    DatasetRef,
    DataValue,
    ResourceRef,
)
from nemo_experimentalist_plugin.experimentalist.components.holdout_utils import (
    INSIGHT_TRAIN_SPLIT,
    INSIGHT_VALIDATION_SPLIT,
)
from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizer
from nemo_experimentalist_plugin.experimentalist.components.models import (
    INSIGHT_REWARD_PREFIX,
    EvolutionTree,
    selection_rewards,
)
from nemo_experimentalist_plugin.experimentalist.deps import ExperimentalistDeps
from nemo_experimentalist_plugin.resolve import EvolutionaryOptimizerConfig

_ROUNDS = 3
_METRIC = "uses_required_tool"
_TRAIN_TASK = "insight-train-task"
_VALIDATION_TASK = "insight-validation-task"


class _StopAfterRounds(Exception):
    pass


@pytest.fixture(autouse=True)
def _keep_all_ranked_survivors() -> Any:
    """Take the Pareto order as-is instead of calling the LLM diversity strategy.

    ``select_diverse_survivors`` is a public strategy method, so the agent
    metaclass rejects ``monkeypatch.setattr``; swap it the way the framework's
    own class construction does.
    """

    async def keep_top_k(self: EvolutionaryOptimizer, ranked: list[Candidate], k: int) -> list[Candidate]:
        return list(ranked[:k])

    original = EvolutionaryOptimizer.select_diverse_survivors
    type.__setattr__(EvolutionaryOptimizer, "select_diverse_survivors", keep_top_k)
    try:
        yield
    finally:
        type.__setattr__(EvolutionaryOptimizer, "select_diverse_survivors", original)


def _suite_metadata(identity_char: str, task_id: str) -> dict[str, DataValue]:
    return {
        "insight_suite_identity": f"sha256:{identity_char * 64}",
        "insight_suite_scorer_identity": f"sha256:{'b' * 64}",
        "insight_suite_task_hashes": {
            task_id: {
                "content_hash": f"sha256:{'c' * 64}",
                "verifier_hash": f"sha256:{'d' * 64}",
            }
        },
    }


def _result(*, result_id: str, label: str, task_id: str, score: float, attempts: int = 1) -> EvaluationResult:
    return EvaluationResult(
        id=result_id,
        aggregate_metrics={_METRIC: score},
        trials=[
            TrialResult(
                id=f"{label}-{task_id}-{attempt}",
                task_id=task_id,
                attempt=attempt,
                status="completed",
                metrics={_METRIC: MetricResult(name=_METRIC, value=score)},
            )
            for attempt in range(1, attempts + 1)
        ],
    )


@dataclass
class _RoundRecord:
    """What the loop handed the analyzer, and what the candidates carried, in one round."""

    round_num: int
    survivor_labels: list[str]
    analyzer_insight_trials: dict[str, list[str]]
    analyzer_train_trials: dict[str, list[str]]


@dataclass
class _Harness:
    optimizer: EvolutionaryOptimizer
    deps: ExperimentalistDeps
    tree: EvolutionTree
    insight_train_dataset: Dataset
    insight_validation_dataset: Dataset
    rounds: list[_RoundRecord] = field(default_factory=list)
    insight_evaluated: list[tuple[str, str]] = field(default_factory=list)

    def living(self) -> list[Candidate]:
        return [node.candidate for node in self.tree.nodes.values() if node.is_survivor]


def _install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Harness:
    insight_train_dataset = Dataset(
        id="insight-train",
        source=ResourceRef(uri="file:///experiment/dataset/insight-train"),
        tasks=[Task(id=_TRAIN_TASK)],
        metadata=_suite_metadata("a", _TRAIN_TASK),
    )
    insight_validation_dataset = Dataset(
        id="insight-validation",
        source=ResourceRef(uri="file:///experiment/dataset/insight-validation"),
        tasks=[Task(id=_VALIDATION_TASK)],
        metadata=_suite_metadata("e", _VALIDATION_TASK),
    )
    train_dataset = Dataset(id="train", tasks=[Task(id="train-task")])
    validation_dataset = Dataset(id="validation", tasks=[Task(id="validation-task")])
    datasets = {"train": train_dataset, "validation": validation_dataset}

    class _DatasetFactory:
        def build_dataset(self, evaluator_type: str, ref: DatasetRef) -> Dataset:
            return datasets[ref.uri]

        def build_task_template(self, evaluator_type: str, ref: DatasetRef) -> Task:
            return Task(id="template", uri=ref.uri)

    class _EvalAuthor:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def run(self, **kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(
                train_dataset=kwargs["train_dataset"],
                validation_dataset=kwargs["validation_dataset"],
                insight_train_suite=insight_train_dataset,
                insight_validation_suite=insight_validation_dataset,
            )

    baseline = Candidate(run_id="run-1", label="agent-0", round=0, optimization="baseline")
    tree = EvolutionTree()
    tree.add(baseline)

    # Later candidates score higher on every split, so selection always has a
    # reason to keep both the newcomer and an older candidate alive.
    def _score(label: str) -> float:
        return min(1.0, 0.1 * (int(label.split("-")[1]) + 1))

    harness = _Harness(
        optimizer=cast(EvolutionaryOptimizer, None),
        deps=cast(ExperimentalistDeps, None),
        tree=tree,
        insight_train_dataset=insight_train_dataset,
        insight_validation_dataset=insight_validation_dataset,
    )

    async def evaluate_agent(
        self: EvolutionaryOptimizer,
        candidate: Candidate,
        dataset: Dataset,
        evaluator: object,
        task_ids: list[str] | None = None,
        minimum_attempts: int | None = None,
    ) -> tuple[Candidate, EvaluationResult]:
        task_id = {
            "insight-train": _TRAIN_TASK,
            "insight-validation": _VALIDATION_TASK,
            "train": "train-task",
            "validation": "validation-task",
        }[dataset.id]
        if dataset.id.startswith("insight-"):
            harness.insight_evaluated.append((dataset.id, candidate.label))
        return candidate, _result(
            result_id=f"{candidate.label}-{dataset.id}",
            label=candidate.label,
            task_id=task_id,
            score=_score(candidate.label),
            attempts=minimum_attempts or 1,
        )

    async def update_candidate(
        self: EvolutionaryOptimizer,
        candidate: Candidate,
        *,
        updates: dict[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        for key, value in (updates or {}).items():
            setattr(candidate, key, value)

    counter = {"n": 0}

    def create_agent(self: EvolutionaryOptimizer, **kwargs: Any) -> Candidate:
        counter["n"] += 1
        return Candidate(
            run_id="run-1",
            label=f"agent-{counter['n']}",
            ancestor="agent-0",
            round=kwargs["round_num"],
            optimization=f"improvement {counter['n']}",
        )

    async def analyze_round(self: EvolutionaryOptimizer, **kwargs: Any) -> str:
        insight_trials = kwargs.get("insight_trials") or {}
        evaluations = kwargs["evaluations"]
        harness.rounds.append(
            _RoundRecord(
                round_num=kwargs["round_num"],
                survivor_labels=[c.label for c in kwargs["survivors"]],
                analyzer_insight_trials={
                    label: [t.task_id for t in trials] for label, trials in insight_trials.items()
                },
                analyzer_train_trials={
                    label: [t.task_id for t in result.trials] for label, result in evaluations.items()
                },
            )
        )
        return "round analysis"

    class _Terminator:
        calls = 0

        async def run(self, **kwargs: object) -> SimpleNamespace:
            self.calls += 1
            if self.calls > _ROUNDS:
                raise _StopAfterRounds
            return SimpleNamespace(stop=False, reason="continue")

    run_entity = SimpleNamespace(id="run-1", status="running", rounds_completed=0)
    backend = SimpleNamespace(
        client=object(),
        get_insight=AsyncMock(return_value=SimpleNamespace(agent="agent-source")),
        get_agent_code=AsyncMock(),
        persist_evaluation=AsyncMock(),
        update_run=AsyncMock(),
    )

    monkeypatch.setattr(loop_module, "DatasetFactory", _DatasetFactory)
    monkeypatch.setattr(
        loop_module,
        "EvaluatorFactory",
        lambda: SimpleNamespace(build_evaluator=lambda *args, **kwargs: object()),
    )
    monkeypatch.setattr(loop_module, "EvalAuthor", _EvalAuthor)
    monkeypatch.setattr(
        loop_module,
        "stage_eval_author_inputs",
        AsyncMock(side_effect=lambda _, **refs: SimpleNamespace(**refs)),
    )
    monkeypatch.setattr(loop_module.EvolutionTree, "from_dir", lambda path: tree)
    monkeypatch.setattr(EvolutionaryOptimizer, "_detect_last_round", lambda self: None)
    monkeypatch.setattr(EvolutionaryOptimizer, "_create_experiment_run", AsyncMock(return_value=run_entity))
    monkeypatch.setattr(EvolutionaryOptimizer, "_create_baseline_agent", AsyncMock(return_value=baseline))
    monkeypatch.setattr(EvolutionaryOptimizer, "_update_candidate", update_candidate)
    monkeypatch.setattr(EvolutionaryOptimizer, "_evaluate_agent", evaluate_agent)
    monkeypatch.setattr(EvolutionaryOptimizer, "_generate_initial_goal_tree", AsyncMock())
    monkeypatch.setattr(EvolutionaryOptimizer, "_analyze_round", analyze_round)
    monkeypatch.setattr(EvolutionaryOptimizer, "_update_goal_tree", AsyncMock())
    monkeypatch.setattr(EvolutionaryOptimizer, "_propose_improvements", AsyncMock(return_value=[object()]))
    monkeypatch.setattr(EvolutionaryOptimizer, "_create_agent", create_agent)
    monkeypatch.setattr(
        EvolutionaryOptimizer,
        "_implement_candidates",
        AsyncMock(side_effect=lambda **kwargs: kwargs["candidates"]),
    )

    config = EvolutionaryOptimizerConfig(disable_trajectory_scoring=True, max_survivors=3)
    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    optimizer.config = config
    optimizer.shell = SimpleNamespace(close=AsyncMock())
    optimizer.terminator = _Terminator()
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
    harness.optimizer = optimizer
    harness.deps = cast(ExperimentalistDeps, deps)
    return harness


async def _run(harness: _Harness) -> None:
    with pytest.raises(_StopAfterRounds):
        await harness.optimizer.run(harness.deps)


@pytest.mark.asyncio
async def test_the_analyzer_gets_insight_trials_in_every_round_not_just_the_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install(monkeypatch, tmp_path)
    await _run(harness)

    assert len(harness.rounds) == _ROUNDS
    starved = [
        record.round_num
        for record in harness.rounds
        if set(record.analyzer_insight_trials) != set(record.survivor_labels)
    ]
    assert not starved, (
        f"rounds {starved} sent the analyzer no Insight trials for some survivor; "
        f"per round: {[(r.round_num, r.survivor_labels, sorted(r.analyzer_insight_trials)) for r in harness.rounds]}"
    )
    for record in harness.rounds:
        for label, task_ids in record.analyzer_insight_trials.items():
            assert set(task_ids) == {_TRAIN_TASK}, f"round {record.round_num} {label} got {task_ids}"
            assert len(task_ids) == 2, (
                f"round {record.round_num} {label} carried {len(task_ids)} attempts; "
                "Insight scoring runs with minimum_attempts=2 so a single flaky run cannot set the score"
            )


@pytest.mark.asyncio
async def test_the_analyzer_gets_train_trials_for_survivors_it_did_not_re_evaluate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install(monkeypatch, tmp_path)
    await _run(harness)

    starved = [
        (record.round_num, label)
        for record in harness.rounds
        for label, task_ids in record.analyzer_train_trials.items()
        if not task_ids
    ]
    assert not starved, f"the analyzer received an evaluation with no trials for {starved}"


@pytest.mark.asyncio
async def test_every_living_candidate_carries_both_insight_halves(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install(monkeypatch, tmp_path)
    await _run(harness)

    for candidate in harness.living():
        for fields in (INSIGHT_TRAIN_FIELDS, INSIGHT_VALIDATION_FIELDS):
            assert fields.reward_of(candidate) is not None, f"{candidate.label} has no {fields.split} reward"
            assert fields.reward_details_of(candidate), f"{candidate.label} has no {fields.split} trials"
            assert fields.metric_keys_of(candidate) == [_METRIC]
    assert {c.label for c in harness.living()} >= {"agent-0", "agent-1"}


@pytest.mark.asyncio
async def test_each_candidate_is_scored_once_per_insight_half(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install(monkeypatch, tmp_path)
    await _run(harness)

    seen: dict[tuple[str, str], int] = {}
    for entry in harness.insight_evaluated:
        seen[entry] = seen.get(entry, 0) + 1
    repeats = {entry: count for entry, count in seen.items() if count > 1}
    assert not repeats, f"re-scored against an unchanged suite: {repeats}"
    assert {label for _, label in harness.insight_evaluated} == {c.label for c in harness.living()} | {
        node.candidate.label for node in harness.tree.nodes.values()
    }


@pytest.mark.asyncio
async def test_insight_validation_reaches_pareto_selection_for_every_ranked_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install(monkeypatch, tmp_path)
    await _run(harness)

    living = harness.living()
    rewards = selection_rewards(living)
    for candidate in living:
        merged = rewards[candidate.label]
        assert merged, f"{candidate.label} contributed no selection reward"
        assert f"{INSIGHT_REWARD_PREFIX}{_METRIC}" in merged, (
            f"{candidate.label} reached selection without an Insight dimension: {sorted(merged)}"
        )


@pytest.mark.asyncio
async def test_every_candidate_is_pinned_to_the_suite_it_was_scored_against(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install(monkeypatch, tmp_path)
    await _run(harness)

    expectations = {
        INSIGHT_TRAIN_FIELDS: f"sha256:{'a' * 64}",
        INSIGHT_VALIDATION_FIELDS: f"sha256:{'e' * 64}",
    }
    for candidate in harness.living():
        for fields, identity in expectations.items():
            assert fields.suite_identity_of(candidate) == identity, f"{candidate.label} {fields.split} identity drifted"


def _split_of(fields: InsightSplitFields) -> str:
    return fields.split


def test_the_two_halves_are_distinct_splits() -> None:
    assert _split_of(INSIGHT_TRAIN_FIELDS) == INSIGHT_TRAIN_SPLIT
    assert _split_of(INSIGHT_VALIDATION_FIELDS) == INSIGHT_VALIDATION_SPLIT
    assert INSIGHT_TRAIN_SPLIT != INSIGHT_VALIDATION_SPLIT
