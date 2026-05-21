# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
from unittest.mock import patch

import pytest
from nemo_evaluator_sdk.enums import MetricType, ModelFormat
from nemo_evaluator_sdk.metrics.bleu import BLEUMetric
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.f1 import F1Metric
from nemo_evaluator_sdk.metrics.llm_judge import LLMJudgeMetric
from nemo_evaluator_sdk.metrics.number_check import NumberCheckMetric
from nemo_evaluator_sdk.metrics.protocol import Metric
from nemo_evaluator_sdk.metrics.rouge import ROUGEMetric
from nemo_evaluator_sdk.metrics.string_check import StringCheckMetric
from nemo_evaluator_sdk.metrics.tool_calling import ToolCallingMetric
from nemo_evaluator_sdk.values import (
    JSONScoreParser,
    Model,
    RemoteScore,
    Rubric,
    RubricScore,
    SecretRef,
)
from nmp.evaluator.app.metrics.metric import _METRIC_CLASSES
from nmp.evaluator.app.metrics.remote import NemoAgentToolkitRemoteMetric, RemoteMetric


class TestProtocolConformance:
    def test_metric_typing_bleu(self):
        metric = BLEUMetric(references=["Hello, world!"], candidate="Hello, world!")
        assert isinstance(metric, Metric)

    def test_metric_typing_exact_match(self):
        metric = ExactMatchMetric(reference="Hello, world!", candidate="Hello, world!")
        assert isinstance(metric, Metric)

    def test_metric_typing_f1(self):
        metric = F1Metric(reference="Hello, world!")
        assert isinstance(metric, Metric)

    @patch.dict(os.environ, {"secret_name": "secret_***"})
    def test_metric_typing_llm_judge(self):
        score = RubricScore(
            name="name",
            rubric=[
                Rubric(label="label", description="description", value=1),
                Rubric(label="label", description="description", value=1),
            ],
        )
        score.parser = JSONScoreParser(json_path="json_path")
        metric = LLMJudgeMetric(
            model=Model(
                url="https://api.openai.com/v1",
                name="gpt-4o",
                api_key_secret=SecretRef(root="secret_name"),
                format=ModelFormat.OPEN_AI,
            ),
            prompt_template="prompt_template",
            scores=[score],
        )
        assert isinstance(metric, Metric)

    def test_metric_typing_number_check(self):
        metric = NumberCheckMetric(
            operation="equals",
            left_template="left_template",
            right_template="right_template",
        )
        assert isinstance(metric, Metric)

    def test_metric_typing_remote(self):
        metric = RemoteMetric(
            url="url",
            body={"input_args": "input_args"},
            scores=[RemoteScore(name="score", parser=JSONScoreParser(json_path="$.result.score"))],
        )
        assert isinstance(metric, Metric)

    def test_metric_typing_nemo_agent_toolkit_remote(self):
        metric = NemoAgentToolkitRemoteMetric(
            url="url",
            evaluator_name="tool_accuracy",
        )
        assert isinstance(metric, Metric)

    def test_metric_typing_rouge(self):
        metric = ROUGEMetric(reference="Hello, world!")
        assert isinstance(metric, Metric)

    def test_metric_typing_string_check(self):
        metric = StringCheckMetric(
            operation="equals",
            left_template="left_template",
            right_template="right_template",
        )
        assert isinstance(metric, Metric)

    def test_metric_typing_tool_calling(self):
        metric = ToolCallingMetric(reference="Hello, world!")
        assert isinstance(metric, Metric)

    @pytest.mark.parametrize(
        ("metric_type", "metric_cls"),
        [
            (MetricType.BLEU, BLEUMetric),
            (MetricType.EXACT_MATCH, ExactMatchMetric),
            (MetricType.F1, F1Metric),
            (MetricType.LLM_JUDGE, LLMJudgeMetric),
            (MetricType.NUMBER_CHECK, NumberCheckMetric),
            (MetricType.REMOTE, RemoteMetric),
            (MetricType.NEMO_AGENT_TOOLKIT_REMOTE, NemoAgentToolkitRemoteMetric),
            (MetricType.ROUGE, ROUGEMetric),
            (MetricType.STRING_CHECK, StringCheckMetric),
            (MetricType.TOOL_CALLING, ToolCallingMetric),
        ],
    )
    def test_metric_registry_uses_direct_runtime_classes(self, metric_type: MetricType, metric_cls: type[Metric]):
        assert _METRIC_CLASSES[metric_type] is metric_cls
