# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval import AgentEvaluator, ProfBenchRubricMetric, load_profbench, summarize_results
from nemo_evaluator_sdk.agent_eval.profbench import PROFBENCH_WEIGHT_POINTS, criteria_from_task


def _write_profbench_fixture(path: Path) -> Path:
    row = {
        "task_id": "pb-1",
        "domain": "Chemistry PhD",
        "prompt": "Explain the result.",
        "o3_response": "Response A",
        "r1-0528_response": "Response B",
        "grok4_response": "Response C",
        "rubrics": [
            {
                "criterion_description": "Includes the main mechanism.",
                "criterion_weight": "Critical",
                "criterion_type": ["Correctness", "Reasoning"],
                "o3_fulfilment": True,
                "r1-0528_fulfilment": False,
                "grok4_fulfilment": True,
            },
            {
                "criterion_description": "Mentions the limitation.",
                "criterion_weight": "Major",
                "criterion_type": "Completeness",
                "o3_fulfilment": False,
                "r1-0528_fulfilment": True,
                "grok4_fulfilment": True,
            },
        ],
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


def test_load_profbench_expands_tasks_attempts_and_line_index(tmp_path: Path) -> None:
    fixture = _write_profbench_fixture(tmp_path / "profbench.jsonl")

    benchmark = load_profbench(fixture)

    assert benchmark.metadata["record_count"] == 1
    assert [attempt.metadata["model_id"] for attempt in benchmark.attempts] == ["o3", "r1-0528", "grok4"]

    criteria = criteria_from_task(benchmark.tasks[0])
    assert [criterion.points for criterion in criteria] == [
        PROFBENCH_WEIGHT_POINTS["Critical"],
        PROFBENCH_WEIGHT_POINTS["Major"],
    ]
    assert criteria[0].line_number == 1
    assert criteria[0].json_path == "$.rubrics[0]"


@pytest.mark.asyncio
async def test_profbench_baseline_scoring_creates_traceable_deductions(tmp_path: Path) -> None:
    benchmark = load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))
    task = benchmark.tasks[0]
    attempt = next(attempt for attempt in benchmark.attempts if attempt.metadata["model_id"] == "o3")

    result = await ProfBenchRubricMetric().score_attempt(task, attempt)

    assert result.score == 4 / 7
    assert result.earned_points == 4
    assert result.max_points == 7
    assert len(result.deductions) == 1
    deduction = result.deductions[0]
    assert deduction.raw_points == 3
    assert deduction.normalized_impact == 3 / 7
    assert deduction.evidence[0].line == 1
    assert deduction.evidence[0].json_path == "$.rubrics[1]"
    assert deduction.evidence[0].href().startswith("file://")

    summary = summarize_results([result])
    assert summary.overall_score == 4 / 7
    assert summary.domain_scores == {"Chemistry PhD": 4 / 7}
    assert summary.criterion_type_fulfilment == {"Completeness": 0.0, "Correctness": 1.0, "Reasoning": 1.0}


def test_agent_evaluator_scores_loaded_profbench_baselines(tmp_path: Path) -> None:
    benchmark = load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))

    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, attempts=benchmark.attempts)

    assert result.summary.task_count == 1
    assert result.summary.attempt_count == 3
    assert result.summary.model_scores == {"grok4": 1.0, "o3": 4 / 7, "r1-0528": 3 / 7}
