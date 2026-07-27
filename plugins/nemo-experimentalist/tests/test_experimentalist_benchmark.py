# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    EvaluationResult,
    MetricResult,
    ResourceRef,
    TrialResult,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = PLUGIN_ROOT / "benchmarks"


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("canonical_benchmark_runner", BENCHMARK_ROOT / "run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shipped_suite_covers_canonical_count_and_fast_subset() -> None:
    runner = _load_runner()
    suite = runner.load_suite(BENCHMARK_ROOT / "suites" / "terminal-bench-2.1.yaml")
    canonical_ids = set(suite.partitions.quality.all_ids())

    runner.validate_canonical_suite(
        suite,
        canonical_task_ids=canonical_ids,
        resolved_ref=suite.dataset.resolved_ref,
    )

    assert len(suite.partitions.quality.train) == 38
    assert len(suite.partitions.quality.validation) == 25
    assert len(suite.partitions.quality.test) == 26
    assert len(suite.partitions.fast.train) == 35
    assert len(suite.partitions.fast.validation) == 12
    assert len(suite.partitions.fast.test) == 12
    assert "install-windows-3.11" in canonical_ids
    assert "install-windows-3-11" not in canonical_ids


@pytest.mark.parametrize("name", ["smoke.yaml", "quality.yaml"])
def test_shipped_benchmark_configs_use_current_contracts(name: str) -> None:
    runner = _load_runner()

    config = runner.load_benchmark_config(BENCHMARK_ROOT / "configs" / name)

    assert config.optimizer.evaluator["n_attempts"] >= 1
    assert config.optimizer.eval_author.max_validation_repair_attempts >= 0


def test_suite_validation_rejects_changed_dataset_revision() -> None:
    runner = _load_runner()
    suite = runner.load_suite(BENCHMARK_ROOT / "suites" / "terminal-bench-2.1.yaml")

    with pytest.raises(ValueError, match="resolved to"):
        runner.validate_canonical_suite(
            suite,
            canonical_task_ids=set(suite.partitions.quality.all_ids()),
            resolved_ref="sha256:changed",
        )


def test_evaluation_summary_counts_errors_and_missing_trials_as_zero(tmp_path: Path) -> None:
    runner = _load_runner()
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "agent_result": {
                    "n_input_tokens": 10,
                    "n_cache_tokens": 2,
                    "n_output_tokens": 4,
                    "cost_usd": 0.25,
                }
            }
        ),
        encoding="utf-8",
    )
    result = EvaluationResult(
        id="heldout",
        trials=[
            TrialResult(
                id="task-a__0",
                task_id="task-a",
                attempt=0,
                status="completed",
                metrics={"reward": MetricResult(name="reward", value=1.0)},
                resources={"result": ResourceRef(uri=result_path.as_uri())},
            ),
            TrialResult(
                id="task-b__0",
                task_id="task-b",
                attempt=0,
                status="failed",
                metrics={},
                error={"type": "RuntimeError", "message": "failed"},
            ),
        ],
    )

    summary = runner.summarize_evaluation(result, task_count=3, attempts=1)

    assert summary["expected_trials"] == 3
    assert summary["observed_trials"] == 2
    assert summary["missing_trials"] == 1
    assert summary["mean_reward_over_expected"] == pytest.approx(1 / 3)
    assert summary["harness_error_count"] == 2
    assert summary["tokens"] == {"input_tokens": 10, "cache_tokens": 2, "output_tokens": 4}
    assert summary["cost_usd"] == 0.25


def test_optimizer_job_summary_reports_full_trial_and_usage_totals(tmp_path: Path) -> None:
    runner = _load_runner()
    for name, trials, errors, tokens in (
        ("agent-0-train", 4, 1, 100),
        ("agent-1-validation", 2, 0, 50),
    ):
        job_dir = tmp_path / name
        job_dir.mkdir()
        (job_dir / "result.json").write_text(
            json.dumps(
                {
                    "n_total_trials": trials,
                    "stats": {
                        "n_completed_trials": trials,
                        "n_errored_trials": errors,
                        "n_input_tokens": tokens,
                        "n_cache_tokens": tokens // 2,
                        "n_output_tokens": tokens // 4,
                        "cost_usd": 0.1,
                        "evals": {"agent__dataset": {"metrics": [{"mean": 0.5}]}},
                    },
                }
            ),
            encoding="utf-8",
        )

    summary = runner.summarize_experimentalist_jobs(tmp_path)

    assert summary["jobs"] == 2
    assert summary["trials"] == 6
    assert summary["errored_trials"] == 1
    assert summary["input_tokens"] == 150
    assert summary["cost_usd"] == pytest.approx(0.2)
    assert len(summary["job_results"]) == 2
