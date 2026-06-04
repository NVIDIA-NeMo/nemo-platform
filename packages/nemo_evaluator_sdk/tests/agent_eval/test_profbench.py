# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval import AgentEvaluator
from nemo_evaluator_sdk.values import Model

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
PROFBENCH_EXAMPLE: Any = None


def _profbench_example() -> Any:
    global PROFBENCH_EXAMPLE
    if PROFBENCH_EXAMPLE is not None:
        return PROFBENCH_EXAMPLE

    spec = importlib.util.spec_from_file_location("profbench_example", EXAMPLES_DIR / "profbench.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load ProfBench example module")
    module = importlib.util.module_from_spec(spec)
    assert isinstance(module, ModuleType)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    PROFBENCH_EXAMPLE = module
    return module


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

    profbench = _profbench_example()
    benchmark = profbench.load_profbench(fixture)

    assert benchmark.metadata["record_count"] == 1
    assert [attempt.metadata["model_id"] for attempt in benchmark.attempts] == ["o3", "r1-0528", "grok4"]

    metric = benchmark.tasks[0].metrics[0]
    assert isinstance(metric, profbench.ProfBenchRubricMetric)
    assert [criterion.points for criterion in metric.criteria] == [
        profbench.PROFBENCH_WEIGHT_POINTS["Critical"],
        profbench.PROFBENCH_WEIGHT_POINTS["Major"],
    ]
    assert [criterion.id for criterion in metric.criteria] == ["pb-1:criterion-1", "pb-1:criterion-2"]
    assert metric.criteria[0].line_number == 1
    assert metric.criteria[0].json_path == "$.rubrics[0]"


def test_profbench_baseline_scoring_creates_traceable_deductions(tmp_path: Path) -> None:
    profbench = _profbench_example()
    benchmark = profbench.load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))

    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, attempts=benchmark.attempts)
    o3_result = next(row for row in result.results if row.attempt_id == "pb-1:o3")
    details_output = next(output for output in o3_result.outputs if output.name == profbench.PROFBENCH_DETAILS_OUTPUT)
    details = profbench.profbench_details(details_output)
    assert details is not None

    assert details.score == 4 / 7
    assert details.earned_points == 4
    assert details.max_points == 7
    assert len(details.deductions) == 1
    deduction = details.deductions[0]
    assert deduction.raw_points == 3
    assert deduction.normalized_impact == 3 / 7
    assert deduction.metadata["score_source"] == "dataset_label"
    assert deduction.evidence[0].line == 1
    assert deduction.evidence[0].json_path == "$.rubrics[1]"
    assert deduction.evidence[0].href().startswith("file://")
    assert all(criterion.judge_reason is None for criterion in details.criterion_scores)
    assert {criterion.metadata["score_source"] for criterion in details.criterion_scores} == {"dataset_label"}


def test_profbench_live_judge_mode_scores_recorded_attempts_without_cached_labels(tmp_path: Path) -> None:
    profbench = _profbench_example()

    class FakeJudge:
        def __init__(self) -> None:
            self.requests: list[Any] = []

        async def judge(self, request: Any) -> Any:
            self.requests.append(request)
            return profbench.ProfBenchJudgeDecision(
                fulfilled=request.criterion_id.endswith("criterion-1"),
                reason=f"judged {request.criterion_id}",
            )

    judge = FakeJudge()
    benchmark = profbench.load_profbench(
        _write_profbench_fixture(tmp_path / "profbench.jsonl"),
        judge=judge,
        include_cached_fulfilments=False,
    )

    assert all("profbench_fulfilments" not in attempt.metadata for attempt in benchmark.attempts)

    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, attempts=benchmark.attempts)
    o3_result = next(row for row in result.results if row.attempt_id == "pb-1:o3")
    details_output = next(output for output in o3_result.outputs if output.name == profbench.PROFBENCH_DETAILS_OUTPUT)
    details = profbench.profbench_details(details_output)
    assert details is not None

    assert details.score == 4 / 7
    assert len(judge.requests) == 6
    assert {criterion.metadata["score_source"] for criterion in details.criterion_scores} == {"judge"}
    assert [criterion.judge_reason for criterion in details.criterion_scores] == [
        "judged pb-1:criterion-1",
        "judged pb-1:criterion-2",
    ]


def test_agent_evaluator_scores_loaded_profbench_baselines(tmp_path: Path) -> None:
    profbench = _profbench_example()
    benchmark = profbench.load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))

    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, attempts=benchmark.attempts)

    assert result.summary.task_count == 1
    assert result.summary.attempt_count == 3
    assert result.summary.metric_scores == {"profbench_rubric": {"profbench": 2 / 3}}


def test_profbench_dashboard_renders_rubric_report(tmp_path: Path) -> None:
    profbench = _profbench_example()
    benchmark = profbench.load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))
    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, attempts=benchmark.attempts)

    html = profbench.render_profbench_dashboard(result)

    assert "ProfBench Agent Eval Report" in html
    assert "Highest-Impact Failures" in html
    assert "Task Details" in html
    assert "criterion-2" in html
    assert "Criterion was not fulfilled" in html
    assert "Chemistry PhD" in html
    assert "Dataset fulfilment label" not in html
    assert "dataset_label" in html

    report_path = profbench.write_profbench_dashboard(result, tmp_path / "report.html")
    assert report_path.read_text(encoding="utf-8") == html


def test_profbench_example_writes_sdk_and_profbench_dashboards(tmp_path: Path) -> None:
    profbench = _profbench_example()
    benchmark = profbench.load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))
    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, attempts=benchmark.attempts)

    sdk_path, profbench_path, default_path = profbench.write_example_dashboards(result, tmp_path)

    assert "Agent Eval Report" in sdk_path.read_text(encoding="utf-8")
    assert "ProfBench Agent Eval Report" in profbench_path.read_text(encoding="utf-8")
    assert default_path.read_text(encoding="utf-8") == profbench_path.read_text(encoding="utf-8")


def test_profbench_judge_parser_accepts_embedded_json_and_yes_no_fallback() -> None:
    profbench = _profbench_example()

    embedded = profbench._parse_yes_no_decision('```json\n{"fulfilled": true, "reason": "matched"}\n```')
    assert embedded.fulfilled is True
    assert embedded.reason == "matched"

    loose = profbench._parse_yes_no_decision("The criterion is satisfied. {'fulfilled': false, 'reason': 'missing'}")
    assert loose.fulfilled is False

    boxed = profbench._parse_yes_no_decision(r"\boxed{fulfilled: true, reason: matches the criterion}")
    assert boxed.fulfilled is True
    assert boxed.reason == "matches the criterion"

    yes = profbench._parse_yes_no_decision("Yes - the answer includes the required definition.")
    assert yes.fulfilled is True


def test_profbench_judge_parser_conservatively_scores_unparseable_output() -> None:
    profbench = _profbench_example()

    decision = profbench._parse_yes_no_decision(
        r"\boxed{\begin{aligned}&\text{Liouville equation instead of judge JSON}\end{aligned}}"
    )

    assert decision.fulfilled is False
    assert "not parseable" in decision.reason
    assert "treating criterion as unfulfilled" in decision.reason

    missing_field = profbench._parse_yes_no_decision('{"reason": "missing explicit boolean"}')
    assert missing_field.fulfilled is False
    assert "boolean 'fulfilled'" in missing_field.reason


@pytest.mark.asyncio
async def test_profbench_model_judge_uses_short_structured_params() -> None:
    profbench = _profbench_example()
    captured: dict[str, Any] = {}

    async def fake_inference(
        model: Model,
        request: dict[str, Any],
        max_retries: int | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del model, max_retries, kwargs
        captured.update(request)
        return {"choices": [{"message": {"role": "assistant", "content": '{"fulfilled": true, "reason": "ok"}'}}]}

    judge = profbench.ProfBenchModelJudge(
        model=Model(url="https://model.test/v1/chat/completions", name="judge-model"),
        inference_fn=fake_inference,
    )

    decision = await judge.judge(
        profbench.ProfBenchJudgeRequest(
            task_id="pb-1",
            prompt="Task prompt",
            response="Candidate response",
            criterion_id="pb-1:criterion-1",
            criterion_description="Criterion text",
            weight_name="Minor",
        )
    )

    assert decision.fulfilled is True
    assert captured["temperature"] == 0.0
    assert captured["max_tokens"] == 256
    guided_json = captured["extra_body"]["nvext"]["guided_json"]
    assert guided_json["required"] == ["fulfilled", "reason"]
