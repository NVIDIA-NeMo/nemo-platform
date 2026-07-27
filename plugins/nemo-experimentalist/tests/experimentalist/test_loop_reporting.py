# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nemo_experimentalist_plugin.entities import Candidate
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
