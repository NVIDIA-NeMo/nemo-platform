# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for compile_metric_job function."""

from typing import Any, cast

import pytest
from nmp.common.files.storage_config import HuggingfaceStorageConfig
from nmp.evaluator.app.jobs.metrics import compile_metric_job
from nmp.evaluator.app.values import Fileset, MetricOfflineJob, MetricOnlineJob


def _hf_storage_config() -> HuggingfaceStorageConfig:
    """Create a Hugging Face storage config for inline Fileset tests."""
    return HuggingfaceStorageConfig(repo_id="test-org/test-dataset", repo_type="dataset")


class TestCompileMetricJob:
    """Tests for compile_metric_job function."""

    @pytest.mark.asyncio
    async def test_compile_custom_metric_uses_python_entrypoint(self):
        """Evaluator-owned custom metric step should run task directly, not via /bin/sh."""
        job = MetricOnlineJob.model_validate(
            {
                "model": {"url": "http://nim.test/v1/chat/completions", "name": "my/model"},
                "dataset": {"rows": [{"input": "hello", "expected": "hello"}]},
                "prompt_template": {"messages": [{"role": "user", "content": "{{input}}"}]},
                "metric": {"type": "exact-match", "reference": "{{item.expected}}"},
            }
        )

        result = await compile_metric_job(job)
        steps = list(result["steps"])

        assert len(steps) == 1
        assert steps[0]["name"] == "evaluation"
        assert _get_container(steps[0]).get("entrypoint") == [
            "python",
            "-m",
            "nmp.evaluator.tasks.evaluate_metric",
        ]

    @pytest.mark.asyncio
    async def test_compile_custom_metric_inline_fileset_adds_download_step(self):
        """Custom metric jobs should download inline Fileset datasets before evaluation."""
        job = MetricOfflineJob.model_validate(
            {
                "metric": {
                    "type": "exact-match",
                    "reference": "{{item.expected}}",
                    "candidate": "{{item.output}}",
                },
                "dataset": Fileset(storage=_hf_storage_config(), path="data/validation.jsonl"),
            }
        )

        result = await compile_metric_job(job)
        steps = list(result["steps"])

        assert [step["name"] for step in steps] == ["dataset-download", "evaluation"]
        assert _get_container(steps[1]).get("entrypoint") == [
            "python",
            "-m",
            "nmp.evaluator.tasks.evaluate_metric",
        ]


def _get_container(step: object) -> dict[str, Any]:
    step_dict = cast(dict[str, Any], step)
    return cast(dict[str, Any], step_dict["executor"]["container"])
