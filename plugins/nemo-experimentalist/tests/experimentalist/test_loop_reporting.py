# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nemo_experimentalist_plugin.entities import Candidate
from nemo_experimentalist_plugin.experimentalist.components.evaluator import (
    Dataset,
    EvaluationResult,
    MetricResult,
    Task,
    TrialResult,
    TrialStatus,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import ResourceRef
from nemo_experimentalist_plugin.experimentalist.components.insight_promotion import (
    _task_evidence,
    insight_suite_provenance,
    render_insight_promotion_section,
    select_insight_promotion_suggestions,
    validate_insight_evaluation_result,
    write_insight_comparison_section,
    write_insight_promotion_section,
)
from nemo_experimentalist_plugin.experimentalist.components.loop import AnalysisSkill, EvolutionaryOptimizer
from nemo_experimentalist_plugin.experimentalist.components.models import EvolutionTree

_SUITE_IDENTITY = f"sha256:{'a' * 64}"
_SUITE_PATH = Path("/experiment/eval-and-optimize/eval_author/insight-1/insight-suite")


def _candidate(
    label: str,
    *,
    round_num: int,
    insight_reward: dict[str, float] | None = None,
    validation_reward: dict[str, float] | None = None,
) -> Candidate:
    return Candidate(
        run_id="run-1",
        label=label,
        round=round_num,
        optimization="baseline" if round_num == 0 else "improve required tool use",
        insight_reward=insight_reward,
        validation_reward=validation_reward,
        insight_suite_identity=_SUITE_IDENTITY,
        insight_metric_keys=["reward", "uses_required_tool"],
    )


def _insight_dataset(tasks: list[Task]) -> Dataset:
    local_tasks = [
        task if task.uri else task.model_copy(update={"uri": (_SUITE_PATH / task.id).as_uri()}) for task in tasks
    ]
    return Dataset(
        id="insight",
        source=ResourceRef(uri=_SUITE_PATH.as_uri()),
        tasks=local_tasks,
        metadata={
            "insight_suite_identity": _SUITE_IDENTITY,
            "insight_suite_scorer_identity": f"sha256:{'b' * 64}",
            "insight_suite_task_hashes": {
                task.id: {
                    "content_hash": f"sha256:{'c' * 64}",
                    "verifier_hash": f"sha256:{'d' * 64}",
                }
                for task in local_tasks
            },
        },
    )


def test_round_analysis_contract_requires_separate_insight_suite_dimensions() -> None:
    skill_prompt = " ".join((AnalysisSkill.__doc__ or "").split())
    merge_prompt = " ".join((EvolutionaryOptimizer.merge_analysis.__doc__ or "").split())

    assert "Insight Suite Reward" in skill_prompt
    assert "candidate.insight_reward" in skill_prompt
    assert "separate from train and validation rewards" in skill_prompt
    assert "insight_dim_keys" in merge_prompt
    assert "candidate.round == 0" in merge_prompt
    assert "must name every available Insight Suite dimension" in merge_prompt
    assert "Never blend those metrics into train/validation rewards" in merge_prompt
    assert "adaptive/development feedback" in merge_prompt
    assert "never present them as independent validation evidence" in merge_prompt


def test_final_report_contract_requires_baseline_winner_insight_comparison() -> None:
    report_prompt = " ".join((EvolutionaryOptimizer.write_final_report.__doc__ or "").split())

    assert "Insight Suite Metrics table" in report_prompt
    assert "baseline, winner, and signed delta columns" in report_prompt
    assert "Keep this table separate from generic train and validation rewards" in report_prompt


def test_terminal_summary_includes_baseline_and_winner_insight_metrics() -> None:
    baseline = _candidate(
        "agent-0",
        round_num=0,
        insight_reward={"uses_required_tool": 0.0},
    )
    winner = _candidate(
        "agent-1",
        round_num=1,
        insight_reward={"uses_required_tool": 1.0},
        validation_reward={"reward": 0.75},
    )
    optimizer = object.__new__(EvolutionaryOptimizer)

    summary = optimizer._render_summary(rounds_completed=1, baseline=baseline, winner=winner)

    assert "validation_reward={'reward': 0.75}" in summary
    assert "insight_suite=(baseline={'uses_required_tool': 0.0}" in summary
    assert "winner={'uses_required_tool': 1.0})" in summary


def test_terminal_summary_omits_insight_comparison_when_unavailable() -> None:
    baseline = _candidate("agent-0", round_num=0)
    winner = _candidate("agent-1", round_num=1, validation_reward={"reward": 0.75})
    optimizer = object.__new__(EvolutionaryOptimizer)

    summary = optimizer._render_summary(rounds_completed=1, baseline=baseline, winner=winner)

    assert "insight_suite" not in summary


def _insight_trial(
    task_id: str,
    score: float,
    *,
    attempt: int = 1,
    status: TrialStatus = "completed",
) -> TrialResult:
    return TrialResult(
        id=f"{task_id}-{attempt}",
        task_id=task_id,
        attempt=attempt,
        status=status,
        metrics={
            "reward": MetricResult(name="reward", value=1.0),
            "uses_required_tool": MetricResult(name="uses_required_tool", value=score),
        },
    )


def test_insight_promotion_suggestions_are_stable_discriminative_and_diverse(
    tmp_path: Path,
) -> None:
    tasks = [
        Task(id="task-a", uri=(tmp_path / "task-a").as_uri()),
        Task(id="task-b", uri=(tmp_path / "task-b").as_uri()),
        Task(id="task-c", uri=(tmp_path / "task-c").as_uri()),
        Task(id="task-flaky", uri=(tmp_path / "task-flaky").as_uri()),
        Task(id="task-flat", uri=(tmp_path / "task-flat").as_uri()),
    ]
    baseline = _candidate("agent-0", round_num=0)
    baseline.insight_reward_details = [
        _insight_trial("task-a", 0.0, attempt=1),
        _insight_trial("task-a", 0.0, attempt=2),
        _insight_trial("task-b", 0.0, attempt=1),
        _insight_trial("task-b", 0.0, attempt=2),
        _insight_trial("task-c", 0.8, attempt=1),
        _insight_trial("task-c", 0.8, attempt=2),
        _insight_trial("task-flaky", 0.0, attempt=1),
        _insight_trial("task-flaky", 1.0, attempt=2),
        _insight_trial("task-flat", 0.5, attempt=1),
        _insight_trial("task-flat", 0.5, attempt=2),
    ]
    winner = _candidate("agent-1", round_num=1)
    winner.insight_metric_keys = ["uses_required_tool", "reward"]
    winner.insight_reward_details = [
        _insight_trial("task-a", 1.0, attempt=1),
        _insight_trial("task-a", 1.0, attempt=2),
        _insight_trial("task-b", 1.0, attempt=1),
        _insight_trial("task-b", 1.0, attempt=2),
        _insight_trial("task-c", 0.9, attempt=1),
        _insight_trial("task-c", 0.9, attempt=2),
        _insight_trial("task-flaky", 1.0, attempt=1),
        _insight_trial("task-flaky", 1.0, attempt=2),
        _insight_trial("task-flat", 0.5, attempt=1),
        _insight_trial("task-flat", 0.5, attempt=2),
    ]

    suggestions = select_insight_promotion_suggestions(
        _insight_dataset(tasks),
        [baseline, winner],
        winner=winner,
    )

    assert [suggestion.task_id for suggestion in suggestions] == ["task-a", "task-c"]
    assert suggestions[0].metric_name == "uses_required_tool"
    assert suggestions[0].discrimination == 1.0
    assert suggestions[0].diversity_score is None
    assert suggestions[1].diversity_score == pytest.approx(0.45)

    section = render_insight_promotion_section(suggestions)
    assert "Advisory adaptive/development evidence only" in section
    assert "`task-a`" in section
    assert str(tmp_path / "task-a") in section
    assert _SUITE_IDENTITY in section
    assert "baseline 0.00 → winner 1.00" in section
    assert f"task sha256:{'c' * 64}" in section
    assert "task-b" not in section
    assert "task-flaky" not in section
    assert "task-flat" not in section


def test_task_evidence_excludes_candidates_from_other_suites(tmp_path: Path) -> None:
    dataset = _insight_dataset([Task(id="task-a", uri=(tmp_path / "task-a").as_uri())])
    task = dataset.list_tasks()[0]
    baseline = _candidate("agent-0", round_num=0)
    winner = _candidate("agent-1", round_num=1)
    stale = _candidate("agent-stale", round_num=1)
    stale.insight_suite_identity = f"sha256:{'e' * 64}"
    for candidate, score in ((baseline, 0.0), (winner, 1.0), (stale, 0.5)):
        candidate.insight_reward_details = [
            _insight_trial(task.id, score, attempt=1),
            _insight_trial(task.id, score, attempt=2),
        ]

    evidence = _task_evidence(
        task,
        [baseline, winner, stale],
        baseline=baseline,
        winner=winner,
        provenance=insight_suite_provenance(dataset),
    )

    assert evidence is not None
    assert evidence.suggestion.candidate_count == 2
    assert evidence.suggestion.total_attempts == 4
    assert set(candidate_label for candidate_label, _ in evidence.profile) == {
        baseline.label,
        winner.label,
    }


def test_insight_promotion_section_explains_when_no_task_qualifies() -> None:
    section = render_insight_promotion_section([])

    assert "## Insight Suite Promotion Suggestions" in section
    assert "No task had complete repeated evidence" in section


def test_insight_promotion_section_is_appended_without_rewriting_report(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "eval-and-optimize" / "OPTIMIZATION.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Optimization\n\nExisting analysis.\n")

    write_insight_promotion_section(report_path, [])
    first_report = report_path.read_text()
    write_insight_promotion_section(report_path, [])

    assert report_path.read_text() == first_report
    assert first_report.startswith("# Optimization\n\nExisting analysis.")
    assert first_report.count("## Insight Suite Promotion Suggestions") == 1


@pytest.mark.parametrize("score", [1.1, -0.1, math.inf, -math.inf, math.nan])
def test_runtime_insight_metrics_reject_out_of_range_and_non_finite_values(score: float) -> None:
    result = EvaluationResult(
        id="invalid",
        aggregate_metrics={"reward": 1.0, "uses_required_tool": score},
        trials=[_insight_trial("task-a", score)],
    )

    with pytest.raises(ValueError, match=r"finite and within \[0, 1\]"):
        validate_insight_evaluation_result(result)


def test_runtime_insight_metrics_reject_missing_or_inconsistent_keys() -> None:
    missing_trial_key = EvaluationResult(
        id="missing",
        aggregate_metrics={"reward": 1.0, "uses_required_tool": 0.5},
        trials=[
            TrialResult(
                id="task-a-1",
                task_id="task-a",
                status="completed",
                metrics={"reward": MetricResult(name="reward", value=1.0)},
            )
        ],
    )

    with pytest.raises(ValueError, match="metric keys are inconsistent"):
        validate_insight_evaluation_result(missing_trial_key)

    with pytest.raises(ValueError, match="aggregate metric keys are inconsistent"):
        validate_insight_evaluation_result(
            EvaluationResult(
                id="changed",
                aggregate_metrics={"reward": 1.0, "different_metric": 0.5},
                trials=[
                    TrialResult(
                        id="task-a-1",
                        task_id="task-a",
                        status="completed",
                        metrics={
                            "reward": MetricResult(name="reward", value=1.0),
                            "different_metric": MetricResult(name="different_metric", value=0.5),
                        },
                    )
                ],
            ),
            expected_metric_keys=["reward", "uses_required_tool"],
        )


@pytest.mark.parametrize(
    ("invalid_score", "missing_key"),
    [(1.1, False), (math.nan, False), (0.5, True)],
)
def test_invalid_runtime_metrics_cannot_be_promotion_evidence(
    invalid_score: float,
    missing_key: bool,
) -> None:
    task = Task(id="task-a")
    baseline = _candidate("agent-0", round_num=0)
    winner = _candidate("agent-1", round_num=1)
    baseline.insight_reward_details = [
        _insight_trial("task-a", 0.0, attempt=1),
        _insight_trial("task-a", 0.0, attempt=2),
    ]
    invalid_trial = _insight_trial("task-a", invalid_score, attempt=1)
    if missing_key:
        invalid_trial.metrics.pop("uses_required_tool")
    winner.insight_reward_details = [
        invalid_trial,
        _insight_trial("task-a", 1.0, attempt=2),
    ]

    assert (
        select_insight_promotion_suggestions(
            _insight_dataset([task]),
            [baseline, winner],
            winner=winner,
        )
        == []
    )


def test_one_attempt_failed_and_incomplete_evidence_do_not_qualify_as_stable() -> None:
    task = Task(id="task-a")
    baseline = _candidate("agent-0", round_num=0)
    winner = _candidate("agent-1", round_num=1)
    baseline.insight_reward_details = [_insight_trial("task-a", 0.0)]
    winner.insight_reward_details = [_insight_trial("task-a", 1.0)]

    assert (
        select_insight_promotion_suggestions(
            _insight_dataset([task]),
            [baseline, winner],
            winner=winner,
        )
        == []
    )

    baseline.insight_reward_details.append(_insight_trial("task-a", 0.0, attempt=2))
    winner.insight_reward_details.append(_insight_trial("task-a", 1.0, attempt=2, status="failed"))
    assert (
        select_insight_promotion_suggestions(
            _insight_dataset([task]),
            [baseline, winner],
            winner=winner,
        )
        == []
    )

    winner.insight_reward_details = []
    assert (
        select_insight_promotion_suggestions(
            _insight_dataset([task]),
            [baseline, winner],
            winner=winner,
        )
        == []
    )


@pytest.mark.parametrize(
    ("baseline_score", "winner_score", "bad_score"),
    [
        (0.5, 0.5, None),
        (0.8, 0.2, None),
        (0.5, 0.5, 0.0),
    ],
)
def test_promotion_requires_baseline_to_winner_improvement(
    baseline_score: float,
    winner_score: float,
    bad_score: float | None,
) -> None:
    task = Task(id="task-a")
    baseline = _candidate("agent-0", round_num=0)
    winner = _candidate("agent-1", round_num=1)
    candidates = [baseline, winner]
    baseline.insight_reward_details = [
        _insight_trial("task-a", baseline_score, attempt=1),
        _insight_trial("task-a", baseline_score, attempt=2),
    ]
    winner.insight_reward_details = [
        _insight_trial("task-a", winner_score, attempt=1),
        _insight_trial("task-a", winner_score, attempt=2),
    ]
    if bad_score is not None:
        bad = _candidate("agent-bad", round_num=1)
        bad.insight_reward_details = [
            _insight_trial("task-a", bad_score, attempt=1),
            _insight_trial("task-a", bad_score, attempt=2),
        ]
        candidates.append(bad)

    assert (
        select_insight_promotion_suggestions(
            _insight_dataset([task]),
            candidates,
            winner=winner,
        )
        == []
    )


def test_deterministic_insight_comparison_section_uses_local_suite_identity(
    tmp_path: Path,
) -> None:
    baseline = _candidate(
        "agent-0",
        round_num=0,
        insight_reward={"reward": 0.5, "uses_required_tool": 0.0},
    )
    winner = _candidate(
        "agent-1",
        round_num=1,
        insight_reward={"reward": 0.75, "uses_required_tool": 1.0},
    )
    report_path = tmp_path / "OPTIMIZATION.md"
    provenance = insight_suite_provenance(_insight_dataset([Task(id="task-a")]))

    write_insight_comparison_section(report_path, baseline, winner, provenance)
    report = report_path.read_text()

    assert "## Deterministic Insight Suite Comparison" in report
    assert str(_SUITE_PATH) in report
    assert _SUITE_IDENTITY in report
    assert "| `uses_required_tool` | 0.000 | 1.000 | +1.000 |" in report


@pytest.mark.asyncio
async def test_final_report_failure_preserves_compact_summary_and_deterministic_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _candidate(
        "agent-0",
        round_num=0,
        insight_reward={"reward": 0.5, "uses_required_tool": 0.0},
        validation_reward={"reward": 0.5},
    )
    winner = _candidate(
        "agent-1",
        round_num=1,
        insight_reward={"reward": 0.75, "uses_required_tool": 1.0},
        validation_reward={"reward": 0.75},
    )
    tree = EvolutionTree()
    tree.add(baseline)
    tree.add(winner)
    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    (tmp_path / "eval-and-optimize").mkdir()
    monkeypatch.setattr(optimizer, "_copy_best_to_workspace", lambda best_id: None)
    original_report_writer = EvolutionaryOptimizer.write_final_report
    type.__setattr__(
        EvolutionaryOptimizer,
        "write_final_report",
        AsyncMock(side_effect=RuntimeError("LLM report failed")),
    )
    run = SimpleNamespace(status="running", winner_agent=None, rounds_completed=1)
    backend = SimpleNamespace(update_run=AsyncMock())

    try:
        finalized = await optimizer._finalize(
            workspace="default",
            backend=backend,
            agents_dir=tmp_path / "eval-and-optimize" / "agents",
            run_entity=run,
            evolution_tree=tree,
            agent_name="agent",
            insight_dataset=_insight_dataset([Task(id="task-a")]),
        )
    finally:
        type.__setattr__(
            EvolutionaryOptimizer,
            "write_final_report",
            original_report_writer,
        )

    report = (tmp_path / "eval-and-optimize" / "OPTIMIZATION.md").read_text()
    assert finalized is winner
    assert "## Compact Run Summary" in report
    assert "Optimization complete: 1 round(s) completed" in report
    assert "## Deterministic Insight Suite Comparison" in report
    assert "## Insight Suite Promotion Suggestions" in report


@pytest.mark.asyncio
async def test_insight_report_mismatch_does_not_fail_completed_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    baseline = _candidate(
        "agent-0",
        round_num=0,
        insight_reward={"reward": 0.5, "uses_required_tool": 0.0},
        validation_reward={"reward": 0.5},
    )
    winner = _candidate(
        "agent-1",
        round_num=1,
        insight_reward={"reward": 0.75, "uses_required_tool": 1.0},
        validation_reward={"reward": 0.75},
    )
    winner.insight_suite_identity = f"sha256:{'e' * 64}"
    tree = EvolutionTree()
    tree.add(baseline)
    tree.add(winner)
    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    (tmp_path / "eval-and-optimize").mkdir()
    monkeypatch.setattr(optimizer, "_copy_best_to_workspace", lambda best_id: None)
    original_report_writer = EvolutionaryOptimizer.write_final_report
    type.__setattr__(EvolutionaryOptimizer, "write_final_report", AsyncMock())
    run = SimpleNamespace(status="running", winner_agent=None, rounds_completed=1)
    backend = SimpleNamespace(update_run=AsyncMock())

    try:
        with caplog.at_level("WARNING"):
            finalized = await optimizer._finalize(
                workspace="default",
                backend=backend,
                agents_dir=tmp_path / "eval-and-optimize" / "agents",
                run_entity=run,
                evolution_tree=tree,
                agent_name="agent",
                insight_dataset=_insight_dataset([Task(id="task-a")]),
            )
    finally:
        type.__setattr__(
            EvolutionaryOptimizer,
            "write_final_report",
            original_report_writer,
        )

    assert finalized is winner
    assert run.status == "completed"
    assert run.winner_agent == winner.label
    backend.update_run.assert_awaited_once()
    assert "Skipping Insight Suite report sections" in caplog.text
