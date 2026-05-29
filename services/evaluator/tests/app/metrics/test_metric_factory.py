# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest
from nemo_evaluator_sdk.metrics.llm_judge import (
    JSONScoreParser,
    LLMJudgeMetric,
    Model,
    ModelFormat,
    RangeScore,
    SupportedJobTypes,
    default_judge_prompt_template_chat,
)
from nmp.evaluator.app.metrics.metric import metric_runtime_kwargs, new_metric
from pytest_mock import MockerFixture


def _judge_metric_config() -> LLMJudgeMetric:
    return LLMJudgeMetric(
        model=Model(url="https://judge.example.test/v1/chat/completions", name="judge", format=ModelFormat.OPEN_AI),
        scores=[RangeScore(name="quality", minimum=1, maximum=5, parser=JSONScoreParser(json_path="quality"))],
    )


class TestMetricRuntimeKwargs:
    def test_llm_judge_omits_unset_prompt_template(self):
        params = _judge_metric_config()

        kwargs = metric_runtime_kwargs(params, LLMJudgeMetric)

        assert "prompt_template" not in kwargs

    def test_llm_judge_preserves_explicit_default_shaped_prompt_template(self):
        params = LLMJudgeMetric(
            model=Model(url="https://judge.example.test/v1/chat/completions", name="judge", format=ModelFormat.OPEN_AI),
            scores=[RangeScore(name="quality", minimum=1, maximum=5, parser=JSONScoreParser(json_path="quality"))],
            prompt_template=default_judge_prompt_template_chat(),
        )

        kwargs = metric_runtime_kwargs(params, LLMJudgeMetric)

        assert kwargs["prompt_template"] == default_judge_prompt_template_chat()


class TestNewMetric:
    @pytest.mark.asyncio
    async def test_raises_for_unknown_metric_type(self):
        with pytest.raises(ValueError, match="Unknown metric type"):
            await new_metric(SimpleNamespace(type="unknown"))

    @pytest.mark.asyncio
    async def test_passes_job_type_to_direct_runtime_metrics(self):
        params = _judge_metric_config()
        metric = await new_metric(params, job_type=SupportedJobTypes.OFFLINE)

        assert metric.model == params.model
        assert metric.scores == params.scores
        assert metric.job_type == SupportedJobTypes.OFFLINE

    @pytest.mark.asyncio
    async def test_sets_inference_fn_when_metric_supports_inference(self):
        async def fake_inference(*_args, **_kwargs):
            raise AssertionError("This test should only verify dependency injection")

        metric = await new_metric(_judge_metric_config(), inference_fn=fake_inference)
        assert metric.inference_fn is fake_inference

    @pytest.mark.asyncio
    async def test_attaches_platform_headers_to_llm_judge_model(self, mocker: MockerFixture):
        mocker.patch(
            "nmp.evaluator.app.metrics.metric.app_inference.get_platform_headers",
            return_value={"X-NMP-Principal-Id": "service:evaluator"},
        )

        metric = await new_metric(_judge_metric_config())

        assert metric.model.default_headers == {"X-NMP-Principal-Id": "service:evaluator"}

    @pytest.mark.asyncio
    async def test_runs_preflight_when_requested(self, mocker: MockerFixture):
        preflight = mocker.patch.object(LLMJudgeMetric, "preflight", new_callable=mocker.AsyncMock)

        await new_metric(_judge_metric_config(), run_preflight=True)

        preflight.assert_awaited_once()
