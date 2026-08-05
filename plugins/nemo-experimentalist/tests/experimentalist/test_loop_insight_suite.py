# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from doubles import FakeBackend, FakeEvaluator, make_candidate, make_context
from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.entities import (
    Candidate,
    Dataset,
    DataValue,
    EvaluationResult,
    MetricResult,
    ResourceRef,
    RewardRecord,
    Task,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components import loop as loop_module
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import EvaluatorConfig
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborEvaluatorConfig
from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizer


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
    """The insight suite is scored once for the baseline and once per new candidate."""
    insight_dataset = Dataset(
        id="insight-suite",
        source=ResourceRef(uri="file:///experiment/eval-and-optimize/eval_author/insight-1/insight-suite"),
        tasks=[Task(id="insight-task")],
        metadata=_suite_metadata(),
    )
    baseline = make_candidate(run_id="run-1", label="agent-0", generation=0, description="baseline")
    new_candidate = make_candidate(
        run_id="run-1",
        label="agent-1",
        ancestor="agent-0",
        generation=1,
        description="use the required tool",
    )
    insight_results = {
        "agent-0": _insight_result("agent-0", 0.0),
        "agent-1": _insight_result("agent-1", 1.0),
    }
    insight_evaluations: list[tuple[Dataset, list[Candidate]]] = []

    async def evaluate_insight_candidates(
        self: EvolutionaryOptimizer,
        *,
        ctx: object,
        dataset: Dataset,
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
            if "validation" not in candidate.rewards
        }

    evolution_tree = SimpleNamespace(survivors=lambda round_num: [baseline], add=lambda candidate: None)

    class StopAfterOneRoundTerminator:
        calls = 0

        async def run(self, **kwargs: object) -> SimpleNamespace:
            self.calls += 1
            if self.calls > 1:
                raise _StopAfterOneRound
            return SimpleNamespace(stop=False, reason="continue")

    monkeypatch.setattr(loop_module.EvolutionTree, "from_candidates", lambda candidates: evolution_tree)
    monkeypatch.setattr(EvolutionaryOptimizer, "_detect_last_round", lambda self: None)
    monkeypatch.setattr(EvolutionaryOptimizer, "_create_baseline_agent", AsyncMock(return_value=baseline))
    monkeypatch.setattr(
        EvolutionaryOptimizer,
        "_build_candidates",
        AsyncMock(return_value=[new_candidate]),
    )
    monkeypatch.setattr(
        EvolutionaryOptimizer,
        "_evaluate_validation_candidates",
        evaluate_validation_candidates,
    )
    monkeypatch.setattr(
        EvolutionaryOptimizer,
        "_evaluate_insight_candidates",
        evaluate_insight_candidates,
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

    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    optimizer.config = EvolutionaryOptimizerConfig(disable_trajectory_scoring=True)
    optimizer.shell = SimpleNamespace(close=AsyncMock())
    optimizer.terminator = StopAfterOneRoundTerminator()
    backend = FakeBackend()
    ctx = make_context(
        root=tmp_path,
        backend=backend,
        datasets={
            "train": Dataset(id="train"),
            "validation": Dataset(id="validation"),
            "insight": insight_dataset,
        },
    )

    with pytest.raises(_StopAfterOneRound):
        await optimizer.run(ctx)

    assert insight_evaluations == [
        (insight_dataset, [baseline]),
        (insight_dataset, [new_candidate]),
    ]
    assert baseline.rewards["insight"].metrics == {"uses_required_tool": 0.0}
    assert new_candidate.rewards["insight"].metrics == {"uses_required_tool": 1.0}
    assert baseline.rewards["insight"].metadata["suite_identity"] == f"sha256:{'a' * 64}"
    assert new_candidate.rewards["insight"].metadata["suite_identity"] == f"sha256:{'a' * 64}"
    assert baseline.rewards["insight"].metadata["metric_keys"] == ["uses_required_tool"]
    insight_persistence = [call for call in backend.evaluations if call["split"] == "insight"]
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
    tmp_path: Path,
) -> None:
    cached = make_candidate(
        run_id="run-1",
        label="agent-0",
        generation=0,
        description="baseline",
        rewards={
            "insight": RewardRecord(
                metrics={"uses_required_tool": 0.0},
                trials=[],
                metadata={"suite_identity": f"sha256:{'a' * 64}", "metric_keys": ["uses_required_tool"]},
            )
        },
    )
    pending = make_candidate(
        run_id="run-1",
        label="agent-1",
        generation=1,
        description="use the required tool",
    )
    result = _insight_result("agent-1", 1.0)
    evaluate_agent = AsyncMock(return_value=(pending, result))
    monkeypatch.setattr(EvolutionaryOptimizer, "_evaluate_agent", evaluate_agent)
    optimizer = object.__new__(EvolutionaryOptimizer)

    ctx = make_context(root=tmp_path)
    evaluated = await optimizer._evaluate_insight_candidates(
        ctx=ctx,
        dataset=Dataset(
            id="insight-suite",
            source=ResourceRef(uri="file:///experiment/eval-and-optimize/eval_author/insight-1/insight-suite"),
            tasks=[Task(id="insight-task")],
            metadata=_suite_metadata(),
        ),
        candidates=[cached, pending],
    )

    assert evaluated == {"agent-1": result}
    assert evaluate_agent.await_args is not None
    assert evaluate_agent.await_args.args[1] is pending
    assert evaluate_agent.await_args.kwargs["minimum_attempts"] == 2

    empty = await optimizer._evaluate_insight_candidates(
        ctx=ctx,
        dataset=Dataset(id="empty-insight-suite"),
        candidates=[pending],
    )
    assert empty == {}
    assert evaluate_agent.await_count == 1


@pytest.mark.asyncio
async def test_insight_evaluation_reuses_only_matching_suite_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cached = make_candidate(
        run_id="run-1",
        label="agent-0",
        generation=0,
        description="baseline",
        rewards={
            "insight": RewardRecord(
                metrics={"uses_required_tool": 0.0},
                trials=[],
                metadata={"suite_identity": f"sha256:{'a' * 64}", "metric_keys": ["uses_required_tool"]},
            )
        },
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

    ctx = make_context(root=tmp_path)
    assert (
        await optimizer._evaluate_insight_candidates(
            ctx=ctx,
            dataset=matching,
            candidates=[cached],
        )
        == {}
    )
    assert await optimizer._evaluate_insight_candidates(
        ctx=ctx,
        dataset=changed,
        candidates=[cached],
    ) == {"agent-0": result}
    evaluate_agent.assert_awaited_once()


@pytest.mark.asyncio
async def test_cached_insight_metric_keys_are_order_independent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    identity = f"sha256:{'a' * 64}"
    candidates = [
        make_candidate(
            run_id="run-1",
            label="agent-0",
            generation=0,
            description="baseline",
            rewards={
                "insight": RewardRecord(
                    metrics={"reward": 0.5, "uses_required_tool": 0.0},
                    trials=[],
                    metadata={"suite_identity": identity, "metric_keys": ["uses_required_tool", "reward"]},
                )
            },
        ),
        make_candidate(
            run_id="run-1",
            label="agent-1",
            generation=1,
            description="improve tool use",
            rewards={
                "insight": RewardRecord(
                    metrics={"reward": 0.75, "uses_required_tool": 1.0},
                    trials=[],
                    metadata={"suite_identity": identity, "metric_keys": ["reward", "uses_required_tool"]},
                )
            },
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
        ctx=make_context(root=tmp_path),
        dataset=dataset,
        candidates=candidates,
    )

    assert dataset.metadata["insight_metric_keys"] == ["reward", "uses_required_tool"]


@pytest.mark.asyncio
async def test_insight_evaluation_uses_at_least_two_attempts_without_changing_other_splits(
    tmp_path: Path,
) -> None:
    candidate = make_candidate(
        run_id="run-1",
        label="agent-0",
        generation=0,
        description="baseline",
    )
    received_attempts: list[int] = []

    class RecordingEvaluator(FakeEvaluator):
        async def _run(self, agent: Path, dataset: Dataset, options: EvaluatorConfig) -> Sequence[TrialResult]:
            assert isinstance(options, HarborEvaluatorConfig)
            received_attempts.append(options.n_attempts)
            return _insight_result(candidate.label, 0.5).trials

    configured = HarborEvaluatorConfig(n_attempts=1)
    evaluator = RecordingEvaluator(options=configured)
    ctx = make_context(
        root=tmp_path,
        evaluator=evaluator,
        datasets={"validation": Dataset(id="validation"), "insight": Dataset(id="insight-suite")},
    )

    await ctx.evaluate(candidate, split="validation")
    await ctx.evaluate(candidate, split="insight", minimum_attempts=2)

    assert received_attempts == [1, 2]
    assert configured.n_attempts == 1


@pytest.mark.asyncio
async def test_rollback_clears_evaluator_scratch_for_the_rolled_back_candidate(tmp_path: Path) -> None:
    """Which candidates to roll back comes from the store, not from a directory walk.

    Scratch is keyed by label, so leaving it would let the re-run read the previous
    round's results. The candidate itself is discarded rather than deleted.
    """
    root = tmp_path / "eval-and-optimize"
    agents_dir = root / "agents"
    results_dir = root / "results"
    for directory in (agents_dir, results_dir, root / "analysis", root / "smoke-dataset", root / "smoke-results"):
        directory.mkdir(parents=True)

    removed_dir = agents_dir / "agent-2"
    removed_dir.mkdir()
    surviving_dir = agents_dir / "agent-20"
    surviving_dir.mkdir()
    removed_results = [
        results_dir / "agent-2-train",
        results_dir / "agent-2-validation",
        results_dir / "agent-2-insight-abcdef123456",
    ]
    for result_dir in removed_results:
        result_dir.mkdir()
    surviving_result = results_dir / "agent-20-insight-abcdef123456"
    surviving_result.mkdir()

    backend = FakeBackend()
    ctx = make_context(root=tmp_path, backend=backend)
    for label, generation, directory in (("agent-2", 2, removed_dir), ("agent-20", 1, surviving_dir)):
        await backend.create_candidate(
            workspace="default",
            candidate=make_candidate(
                label=label,
                ancestor="agent-0",
                generation=generation,
                artifact=directory.as_uri(),
            ),
        )

    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    await optimizer._roll_back_to(ctx=ctx, from_round=1)

    assert removed_dir.exists(), "the artifact is kept; only the record is marked"
    assert all(not result_dir.exists() for result_dir in removed_results)
    assert surviving_dir.is_dir()
    assert surviving_result.is_dir()


@pytest.mark.asyncio
async def test_rollback_revives_a_survivor_whose_killing_round_was_itself_rolled_back(tmp_path: Path) -> None:
    backend = FakeBackend()
    ctx = make_context(root=tmp_path, backend=backend)
    artifact = tmp_path / "eval-and-optimize" / "agents" / "agent-1"
    artifact.mkdir(parents=True)
    await backend.create_candidate(
        workspace="default",
        candidate=make_candidate(
            label="agent-1",
            ancestor="agent-0",
            generation=1,
            killed_generation=3,
            artifact=artifact.as_uri(),
        ),
    )

    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    await optimizer._roll_back_to(ctx=ctx, from_round=2)

    assert backend.by_label["agent-1"].killed_generation is None


@pytest.mark.asyncio
async def test_rollback_hides_the_record_so_nothing_downstream_sees_it(tmp_path: Path) -> None:
    """A rolled-back candidate must not survive into the rebuilt tree.

    If it did it would be offered to the Proposer as a branchable survivor and could be
    selected as the Pareto winner. Discarding hides it from `candidates()` while leaving
    both halves on disk.
    """
    root = tmp_path / "eval-and-optimize"
    for sub in ("agents", "results", "analysis", "smoke-dataset", "smoke-results"):
        (root / sub).mkdir(parents=True)

    backend = FakeBackend()
    ctx = make_context(root=tmp_path, backend=backend)
    rolled_back = root / "agents" / "agent-2"
    rolled_back.mkdir()
    kept = root / "agents" / "agent-1"
    kept.mkdir()
    for label, generation, directory in (("agent-2", 2, rolled_back), ("agent-1", 1, kept)):
        await backend.create_candidate(
            workspace="default",
            candidate=make_candidate(
                label=label, ancestor="id-agent-0", generation=generation, artifact=directory.as_uri()
            ),
        )

    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    await optimizer._roll_back_to(ctx=ctx, from_round=1)

    assert sorted(c.label for c in await ctx.candidates()) == ["agent-1"]
    assert rolled_back.exists(), "kept on disk; the rollback is auditable and reversible"
    assert sorted(c.label for c in await ctx.candidates(include_discarded=True)) == ["agent-1", "agent-2"]


@pytest.mark.asyncio
async def test_an_interrupted_round_zero_does_not_mint_a_second_baseline(monkeypatch, tmp_path) -> None:
    """Ids are uuids now, so re-committing the baseline no longer overwrites idempotently.

    A crash during round-0 evaluation leaves run.json but no round analysis, so the
    runner resumes and the loop re-enters its fresh-start branch.
    """
    ctx = make_context(root=tmp_path, backend=FakeBackend())
    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    created = 0

    async def _commit_baseline(self, *, ctx, config):
        nonlocal created
        created += 1
        return await ctx.import_baseline("baseline")

    monkeypatch.setattr(EvolutionaryOptimizer, "_create_baseline_agent", _commit_baseline)
    config = EvolutionaryOptimizerConfig()

    await optimizer._ensure_baseline(ctx=ctx, config=config)
    await optimizer._ensure_baseline(ctx=ctx, config=config)  # the resumed pass

    assert created == 1
    assert len([c for c in await ctx.candidates() if c.is_baseline]) == 1
