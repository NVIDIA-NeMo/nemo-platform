# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nemo_evaluator_sdk.agent_eval.dashboard import render_dashboard
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalScoreStatus, AgentEvalTaskScore
from nemo_evaluator_sdk.metrics.protocol import MetricOutput
from nemo_evaluator_sdk.values.results import AggregatedMetricResult, AggregateRangeScore


def test_dashboard_contains_metric_rollups_and_outputs() -> None:
    result = AgentEvalResult(
        run_id="run-1",
        tasks=[],
        trials=[],
        scores=[
            AgentEvalTaskScore(
                id="run-1:task-1:trial-1:example_metric",
                run_id="run-1",
                task_id="task-1",
                trial_id="trial-1",
                metric_type="example_metric",
                status=AgentEvalScoreStatus.COMPLETED,
                outputs=[
                    MetricOutput(name="score", value=0.5),
                    MetricOutput(name="label", value="partial"),
                ],
            )
        ],
        summary=AgentEvalSummary(
            scores=AggregatedMetricResult(
                scores=[AggregateRangeScore(name="example_metric.score", count=1, nan_count=0, mean=0.5)]
            ),
            task_count=1,
            trial_count=1,
            score_count=1,
        ),
    )

    html = render_dashboard(result)

    assert "0.500" in html
    assert "example_metric" in html
    assert "trial-1" in html
    assert "partial" in html
    assert "Scores" in html
