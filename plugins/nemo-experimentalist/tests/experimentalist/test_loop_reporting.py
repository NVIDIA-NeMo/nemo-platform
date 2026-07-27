# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from nemo_experimentalist_plugin.entities import Candidate
from nemo_experimentalist_plugin.experimentalist.components.evaluator import (
    Dataset,
    MetricResult,
    Task,
    TrialResult,
    TrialStatus,
)
from nemo_experimentalist_plugin.experimentalist.components.insight_promotion import (
    render_insight_promotion_section,
    select_insight_promotion_suggestions,
    write_insight_promotion_section,
)
from nemo_experimentalist_plugin.experimentalist.components.loop import AnalysisSkill, EvolutionaryOptimizer


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
        _insight_trial("task-a", 0.0),
        _insight_trial("task-b", 0.0),
        _insight_trial("task-c", 0.8),
        _insight_trial("task-flaky", 0.0, attempt=1),
        _insight_trial("task-flaky", 1.0, attempt=2),
        _insight_trial("task-flat", 0.5),
    ]
    winner = _candidate("agent-1", round_num=1)
    winner.insight_reward_details = [
        _insight_trial("task-a", 1.0),
        _insight_trial("task-b", 1.0),
        _insight_trial("task-c", 0.2),
        _insight_trial("task-flaky", 1.0),
        _insight_trial("task-flat", 0.5),
    ]

    suggestions = select_insight_promotion_suggestions(
        Dataset(id="insight", tasks=tasks),
        [baseline, winner],
    )

    assert [suggestion.task_id for suggestion in suggestions] == ["task-a", "task-c"]
    assert suggestions[0].metric_name == "uses_required_tool"
    assert suggestions[0].discrimination == 1.0
    assert suggestions[0].diversity_score is None
    assert suggestions[1].diversity_score == 0.8

    section = render_insight_promotion_section(suggestions)
    assert "Advisory only: these tasks were not copied into the validation dataset." in section
    assert "`task-a`" in section
    assert f"`{tmp_path / 'task-a'}`" in section
    assert "task-b" not in section
    assert "task-flaky" not in section
    assert "task-flat" not in section


def test_insight_promotion_section_explains_when_no_task_qualifies() -> None:
    section = render_insight_promotion_section([])

    assert "## Insight Suite Promotion Suggestions" in section
    assert "No task had complete, repeat-consistent results" in section


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
