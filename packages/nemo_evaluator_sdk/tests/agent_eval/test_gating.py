# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the promoted deterministic gate."""

from __future__ import annotations

from pathlib import Path

from nemo_evaluator_sdk.agent_eval.gating import GateThresholds, evaluate_gate, summarize_run, write_gate_report
from nemo_evaluator_sdk.agent_eval.types import (
    AgentEvalAttempt,
    AgentEvalRunResult,
    AgentEvalSummary,
    AgentEvalTask,
    AgentEvalTaskResult,
    AgentOutput,
)
from nemo_evaluator_sdk.metrics.protocol import MetricOutput


def _make_run_result(
    *, reward: float, total_tokens: int, runtime_sec: float, commit: str = "abc123"
) -> AgentEvalRunResult:
    task = AgentEvalTask(id="demo", intent="do it", inputs={})
    attempt = AgentEvalAttempt(
        id="demo:workflow",
        task_id="demo",
        status="completed",
        output=AgentOutput(text="ok"),
        metadata={
            "total_tokens": total_tokens,
            "runtime_sec": runtime_sec,
            "provenance": {"commit_sha": commit, "commit_short": commit[:7]},
        },
    )
    task_result = AgentEvalTaskResult(
        id="demo:workflow:agentic_use_verifier_reward",
        run_id="run-1",
        task_id="demo",
        attempt_id="demo:workflow",
        metric_type="agentic_use_verifier_reward",
        outputs=[MetricOutput(name="verifier_reward", value=reward)],
    )
    return AgentEvalRunResult(
        run_id="run-1",
        tasks=[task],
        attempts=[attempt],
        results=[task_result],
        summary=AgentEvalSummary(),
    )


def test_summarize_run_aggregates_pass_tokens_runtime_provenance() -> None:
    summary = summarize_run(_make_run_result(reward=1.0, total_tokens=120, runtime_sec=4.5))
    assert summary["total_tasks"] == 1
    assert summary["pass_rate"] == 1.0
    assert summary["total_tokens_sum"] == 120
    assert summary["runtime_sec_sum"] == 4.5
    assert summary["token_metrics_coverage"] == 1.0
    assert summary["provenance"]["commit_sha"] == "abc123"


def test_evaluate_gate_passes_then_flags_token_regression(tmp_path: Path) -> None:
    baseline = _make_run_result(reward=1.0, total_tokens=100, runtime_sec=4.0)
    candidate = _make_run_result(reward=1.0, total_tokens=200, runtime_sec=4.0)

    baseline_report = evaluate_gate(baseline, thresholds=GateThresholds())
    assert baseline_report.gate_passed is True

    candidate_report = evaluate_gate(candidate, thresholds=GateThresholds(), baseline_summary=baseline_report.summary)
    assert candidate_report.gate_passed is False
    token_check = next(c for c in candidate_report.checks if c.name == "tokens_not_worse_than_baseline")
    assert token_check.passed is False

    gate_path = write_gate_report(candidate_report, tmp_path)
    assert gate_path.exists() and "gate_passed" in gate_path.read_text(encoding="utf-8")


def test_evaluate_gate_blocks_cross_commit_comparison() -> None:
    baseline = _make_run_result(reward=1.0, total_tokens=100, runtime_sec=4.0, commit="aaa111")
    candidate = _make_run_result(reward=1.0, total_tokens=100, runtime_sec=4.0, commit="bbb222")

    baseline_summary = evaluate_gate(baseline, thresholds=GateThresholds()).summary
    report = evaluate_gate(candidate, thresholds=GateThresholds(), baseline_summary=baseline_summary)
    cross = next(c for c in report.checks if c.name == "commit_sha_matches_baseline")
    assert cross.passed is False and report.gate_passed is False

    allowed = evaluate_gate(
        candidate, thresholds=GateThresholds(allow_cross_commit=True), baseline_summary=baseline_summary
    )
    cross_allowed = next(c for c in allowed.checks if c.name == "commit_sha_matches_baseline")
    assert cross_allowed.passed is True


def test_summarize_run_uses_measurement_fallbacks() -> None:
    # duration_ms -> runtime_sec, and metadata reward when no scored metric output.
    run = _make_run_result(reward=0.0, total_tokens=10, runtime_sec=1.0)
    run.attempts[0].metadata.pop("runtime_sec")
    run.attempts[0].metadata["duration_ms"] = 2500
    run.attempts[0].metadata["reward"] = 1
    run.results.clear()  # no scored metric outputs -> fall back to metadata reward

    summary = summarize_run(run)
    assert summary["runtime_sec_sum"] == 2.5
    assert summary["pass_rate"] == 1.0
