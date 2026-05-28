# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for compile_benchmark_job function."""

from typing import Any, cast

import pytest
from nemo_evaluator_sdk.enums import MetricType
from nmp.evaluator.app.jobs.benchmarks import compile_benchmark_job
from nmp.evaluator.app.values import BenchmarkOfflineJob, BenchmarkOnlineJob


@pytest.fixture
def custom_offline_benchmark_job() -> BenchmarkOfflineJob:
    return BenchmarkOfflineJob.model_validate(
        {
            "benchmark": {
                "name": "bench",
                "dataset": "ws/dataset",
                "metrics": [
                    {
                        "metric_ref": "ws/m1",
                        "metric": {
                            "type": "exact-match",
                            "reference": "{{item.reference}}",
                        },
                    }
                ],
            }
        }
    )


def _get_container(step: object) -> dict[str, Any]:
    step_dict = cast(dict[str, Any], step)
    return cast(dict[str, Any], step_dict["executor"]["container"])


@pytest.mark.asyncio
async def test_compile_offline_benchmark_passes_inner_metric_to_new_metric(
    monkeypatch: pytest.MonkeyPatch, custom_offline_benchmark_job: BenchmarkOfflineJob
):
    seen_metric_types: list[MetricType] = []

    class _Metric:
        def secrets(self) -> dict[str, object]:
            return {}

    async def _fake_new_metric(metric_config, *_args, **_kwargs):
        assert hasattr(metric_config, "type"), "Expected inner metric config, got benchmark wrapper"
        seen_metric_types.append(metric_config.type)
        return _Metric()

    monkeypatch.setattr("nmp.evaluator.app.jobs.benchmarks.new_metric", _fake_new_metric)

    await compile_benchmark_job(custom_offline_benchmark_job)
    assert seen_metric_types == [MetricType.EXACT_MATCH]


@pytest.mark.asyncio
async def test_compile_online_benchmark_passes_inner_metric_to_new_metric(monkeypatch: pytest.MonkeyPatch):
    seen_metric_types: list[MetricType] = []

    class _Metric:
        def secrets(self) -> dict[str, object]:
            return {}

    async def _fake_new_metric(metric_config, *_args, **_kwargs):
        assert hasattr(metric_config, "type"), "Expected inner metric config, got benchmark wrapper"
        seen_metric_types.append(metric_config.type)
        return _Metric()

    monkeypatch.setattr("nmp.evaluator.app.jobs.benchmarks.new_metric", _fake_new_metric)

    job = BenchmarkOnlineJob.model_validate(
        {
            "benchmark": {
                "name": "bench",
                "dataset": "ws/dataset",
                "metrics": [
                    {
                        "metric_ref": "ws/m1",
                        "metric": {
                            "type": "exact-match",
                            "reference": "{{item.reference}}",
                        },
                    }
                ],
            },
            "model": {"url": "http://nim.test/v1", "name": "my/model"},
            "prompt_template": "{{item.input}}",
        }
    )

    await compile_benchmark_job(job)
    assert seen_metric_types == [MetricType.EXACT_MATCH]


@pytest.mark.asyncio
async def test_compile_custom_benchmark_uses_python_entrypoint(custom_offline_benchmark_job: BenchmarkOfflineJob):
    """Evaluator-owned custom benchmark step should run task directly, not via /bin/sh."""

    result = await compile_benchmark_job(custom_offline_benchmark_job)
    steps = list(result["steps"])

    assert len(steps) == 2
    assert steps[1]["name"] == "evaluation"
    assert _get_container(steps[1]).get("entrypoint") == [
        "python",
        "-m",
        "nmp.evaluator.tasks.evaluate_benchmark",
    ]
