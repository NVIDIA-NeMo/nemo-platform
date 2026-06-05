# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from nemo_evaluator_sdk.agent_eval import (
    AgentEvalRunResult,
    AgentEvalSummary,
    AgentEvalTaskResult,
    render_dashboard,
)
from nemo_evaluator_sdk.metrics.protocol import MetricOutput


def test_dashboard_contains_metric_rollups_and_outputs() -> None:
    result = AgentEvalRunResult(
        run_id="run-1",
        tasks=[],
        attempts=[],
        results=[
            AgentEvalTaskResult(
                id="run-1:task-1:attempt-1:example_metric",
                run_id="run-1",
                task_id="task-1",
                attempt_id="attempt-1",
                metric_type="example_metric",
                outputs=[
                    MetricOutput(name="score", value=0.5),
                    MetricOutput(name="label", value="partial"),
                ],
            )
        ],
        summary=AgentEvalSummary(
            overall_score=0.5,
            metric_scores={"example_metric": {"score": 0.5}},
            task_count=1,
            attempt_count=1,
            result_count=1,
        ),
    )

    html = render_dashboard(result)

    assert "0.500" in html
    assert "example_metric" in html
    assert "attempt-1" in html
    assert "partial" in html
    assert "Results" in html
