# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker-backed parity coverage for the two Harbor evaluator paths."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from harbor_job_dir import assert_comparable_trials_dump
from nemo_experimentalist_plugin.entities import DatasetRef, EvaluationResult
from nemo_experimentalist_plugin.experimentalist.components.evaluator.factory import (
    DatasetFactory,
    EvaluatorFactory,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration,
    pytest.mark.timeout(300),
    pytest.mark.xdist_group("harbor-evaluator-parity"),
]

_FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "harbor_evaluator_parity"


def _require_docker() -> None:
    """Skip locally, but fail CI, when the real Harbor runtime is unavailable."""
    try:
        completed = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        reason = f"Docker is unavailable for the real Harbor evaluator parity test: {exc}"
    else:
        if completed.returncode == 0:
            return
        reason = "Docker is unavailable for the real Harbor evaluator parity test"
        if completed.stderr.strip():
            reason = f"{reason}: {completed.stderr.strip()}"

    if os.environ.get("CI"):
        pytest.fail(reason)
    pytest.skip(reason)


def _assert_golden_outcomes(result: EvaluationResult) -> None:
    """Pin the independently hand-derived optimizer-facing outcome."""
    assert result.aggregate_metrics == {"format_ok": 1.0, "reward": 0.5}
    expected_tokens = {"n_input_tokens": 7, "n_output_tokens": 3, "n_cache_tokens": 1}

    trials = {trial.task_id: trial for trial in result.trials}
    assert len(result.trials) == len(trials)
    assert set(trials) == {
        "completed-correct-answer",
        "completed-incorrect-answer",
        "debug-agent-runtime-error",
    }
    assert {task_id: trial.metadata for task_id, trial in trials.items()} == {
        task_id: expected_tokens for task_id in trials
    }

    completed_correct = trials["completed-correct-answer"]
    assert completed_correct.status == "completed"
    assert completed_correct.error is None
    assert {name: metric.value for name, metric in completed_correct.metrics.items()} == {
        "format_ok": 1,
        "reward": 1,
    }
    assert completed_correct.trace is not None

    completed_incorrect = trials["completed-incorrect-answer"]
    assert completed_incorrect.status == "completed"
    assert completed_incorrect.error is None
    assert {name: metric.value for name, metric in completed_incorrect.metrics.items()} == {
        "format_ok": 1,
        "reward": 0,
    }
    assert completed_incorrect.trace is not None

    runtime_error = trials["debug-agent-runtime-error"]
    assert runtime_error.status == "failed"
    assert runtime_error.metrics == {}
    assert runtime_error.trace is None
    assert runtime_error.error is not None
    assert runtime_error.error["type"] == "RuntimeError"
    message = runtime_error.error["message"]
    assert isinstance(message, str)
    assert "exit code 127:" in message


async def test_native_and_sdk_harbor_evaluators_have_identical_real_runtime_outcomes(
    tmp_path: Path,
    comparable_trials: Callable[[Sequence[Any]], list[dict[str, Any]]],
) -> None:
    """Both factory paths must expose equivalent trial semantics from real Harbor jobs."""
    _require_docker()

    dataset_ref = DatasetRef(uri=str(_FIXTURE_ROOT / "dataset" / "validation"))
    dataset = DatasetFactory().build_dataset("harbor-native", dataset_ref)
    evaluator_factory = EvaluatorFactory()

    native_result = await evaluator_factory.build_evaluator(
        "harbor-native",
        {"jobs_dir": Path("jobs"), "n_concurrent_trials": 1, "quiet": True},
        experiment_dir=tmp_path / "native-experiment",
    ).run(_FIXTURE_ROOT / "agent", dataset)
    sdk_result = await evaluator_factory.build_evaluator(
        "harbor-runner",
        {"jobs_dir": Path("jobs"), "n_concurrent_trials": 1, "quiet": True},
        experiment_dir=tmp_path / "sdk-experiment",
    ).run(_FIXTURE_ROOT / "agent", dataset)

    assert comparable_trials(native_result.trials) == comparable_trials(sdk_result.trials)
    assert native_result.aggregate_metrics == sdk_result.aggregate_metrics
    _assert_golden_outcomes(native_result)
    _assert_golden_outcomes(sdk_result)
    assert_comparable_trials_dump(native_result.trials, sdk_result.trials)
