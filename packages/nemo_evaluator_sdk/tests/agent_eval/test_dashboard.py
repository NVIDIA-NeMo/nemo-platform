# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from nemo_evaluator_sdk.agent_eval import (
    AgentEvalRunResult,
    AgentEvalSummary,
    AgentEvalTaskResult,
    CriterionScore,
    EvidenceLocator,
    ScoreDeduction,
    render_dashboard,
)


def test_dashboard_contains_scores_deductions_and_atif_line_links() -> None:
    atif = EvidenceLocator(kind="atif", uri="atif://attempt-1/trace", line=42, json_path="$.steps[0]")
    result = AgentEvalRunResult(
        run_id="run-1",
        tasks=[],
        attempts=[],
        results=[
            AgentEvalTaskResult(
                task_id="task-1",
                attempt_id="attempt-1",
                model_id="candidate",
                metric_id="profbench",
                score=0.5,
                earned_points=1,
                max_points=2,
                domain="Finance MBA",
                criterion_scores=[
                    CriterionScore(
                        criterion_id="criterion-1",
                        description="Required item",
                        weight_name="Minor",
                        points=2,
                        fulfilled=False,
                        evidence=[atif],
                    )
                ],
                deductions=[
                    ScoreDeduction(
                        raw_points=2,
                        normalized_impact=0.5,
                        criterion_id="criterion-1",
                        reason="Criterion was not fulfilled",
                        evidence=[atif],
                    )
                ],
            )
        ],
        summary=AgentEvalSummary(
            overall_score=0.5,
            domain_scores={"Finance MBA": 0.5},
            model_scores={"candidate": 0.5},
            task_count=1,
            attempt_count=1,
            deduction_count=1,
        ),
    )

    html = render_dashboard(result)

    assert "50.0%" in html
    assert "Criterion was not fulfilled" in html
    assert "atif://attempt-1/trace#L42" in html
    assert "Export JSON" in html
