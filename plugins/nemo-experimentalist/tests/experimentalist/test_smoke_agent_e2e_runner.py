# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the smoke-agent parallel test runner."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def _runner():
    path = Path(__file__).resolve().parents[2] / "examples" / "smoke-agent" / "scripts" / "run_e2e_tests.py"
    spec = importlib.util.spec_from_file_location("_smoke_agent_e2e_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[spec.name]
    return module


def test_classify_node_identifies_mode_group_and_e2e() -> None:
    """Check that collected pytest nodes are assigned to the correct run stage."""
    runner = _runner()
    mode_1 = runner.classify_node(
        "tests/experimentalist/test_smoke_agent_mode_1_loop_e2e.py::test_insight_driven_loop_uses_only_generated_tasks[g2-name-patterns]"
    )
    mode_2 = runner.classify_node(
        "tests/experimentalist/test_smoke_agent_mode_2_loop_e2e.py::test_g4_rejects_a_non_generalizing_fix"
    )
    asset = runner.classify_node("tests/experimentalist/test_smoke_agent_assets.py::test_assets_are_current")
    assert (mode_1.mode, mode_1.group, mode_1.e2e) == ("mode-1", "g2-name-patterns", True)
    assert (mode_2.mode, mode_2.group, mode_2.e2e) == ("mode-2", "g4-dispatch-order", True)
    assert (asset.mode, asset.group, asset.e2e) == ("structural", "fixture", False)


def test_collect_cases_finds_the_full_smoke_matrix() -> None:
    """Check that the runner collects static and E2E smoke-agent tests."""
    cases = _runner().collect_cases()
    assert any(case.mode == "structural" for case in cases)
    assert any(case.mode == "mode-1" and case.e2e for case in cases)
    assert any(case.mode == "mode-2" and case.e2e for case in cases)


def test_enrich_from_experiment_reads_winner_metrics(tmp_path: Path) -> None:
    """Check that the report reads baseline and winner metrics from saved artifacts."""
    runner = _runner()
    experiment = tmp_path / "pytest" / "case" / "experiment" / "eval-and-optimize"
    for label, metrics in {
        "agent-0": {"reward": 0.5, "shape_ok": 1.0},
        "agent-1": {"reward": 1.0, "shape_ok": 1.0},
    }.items():
        path = experiment / "agents" / label / "metadata.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"rewards": {"validation": {"metrics": metrics}}}), encoding="utf-8")
    (experiment / "run.json").write_text(
        json.dumps(
            {
                "winner_agent": "agent-1",
                "config_snapshot": {
                    "objective_function": [{"name": "reward", "direction": "maximize"}],
                    "regression_metrics": [{"name": "shape_ok", "direction": "maximize"}],
                },
            }
        ),
        encoding="utf-8",
    )
    result = runner.CaseResult(case=runner.Case("node", "mode-1", "g1-aggregation", True), artifact_dir=tmp_path)
    runner.enrich_from_experiment(result)
    assert result.winner == "agent-1"
    assert result.objective_metrics == {"reward": (0.5, 1.0)}
    assert result.regression_metrics == {"shape_ok": (1.0, 1.0)}


def test_classify_failure_explains_known_metric_problem() -> None:
    """Check that the report gives the known generated-metric failure a useful name."""
    runner = _runner()
    assert runner.classify_failure("generated task verifier results dropped authored metric keys: coverage") == (
        "generated metrics were not written into final verifier rewards"
    )


def test_classify_failure_explains_a_missing_recorded_trace() -> None:
    """Check that the report identifies a Harbor trial that produced no trace."""
    runner = _runner()
    assert runner.classify_failure("RuntimeError: Trial g2 produced no trace") == (
        "a Harbor trial did not write the required trace"
    )


def test_render_report_includes_metrics_and_failure_reason() -> None:
    """Check that the live Markdown report contains pass and failure details."""
    runner = _runner()
    passed = runner.CaseResult(
        case=runner.Case("passed", "mode-1", "g1-aggregation", True),
        status="passed",
        elapsed_seconds=12.0,
        winner="agent-1",
        objective_metrics={"reward": (0.5, 1.0)},
    )
    failed = runner.CaseResult(
        case=runner.Case("failed", "mode-2", "g4-dispatch-order", True),
        status="failed",
        reason="the selected winner worsened a regression guardrail",
    )
    report = runner.render_report([passed, failed], datetime(2026, 8, 11, tzinfo=UTC))
    assert "1 | 1" in report
    assert "reward: 0.5 → 1.0" in report
    assert "the selected winner worsened a regression guardrail" in report
