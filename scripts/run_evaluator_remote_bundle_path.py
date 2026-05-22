# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Smoke-test evaluator plugin remote execution with bundled metrics."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass

import httpx
from nemo_evaluator.sdk._executor import _build_evaluate_spec
from nemo_evaluator.sdk.resources import Evaluator as PluginEvaluator
from nemo_evaluator.sdk.standalone_sdk.backend import NMPBackend
from nemo_evaluator_sdk import Evaluator as SDKEvaluator
from nemo_evaluator_sdk.execution.config import EvaluationRequest
from nemo_evaluator_sdk.metrics.bleu import BLEUMetric
from nemo_evaluator_sdk.metrics.cloudpickle import CloudpickleMetricBundler
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.f1 import F1Metric
from nemo_evaluator_sdk.metrics.number_check import NumberCheckMetric
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.metrics.rouge import ROUGEMetric
from nemo_evaluator_sdk.metrics.string_check import StringCheckMetric
from nemo_evaluator_sdk.metrics.tool_calling import ToolCallingMetric
from nemo_evaluator_sdk.values import RunConfig
from nemo_platform import NeMoPlatform

DatasetRow = dict[str, object]


@dataclass(frozen=True)
class MetricCase:
    name: str
    metric: Metric
    expected_aggregate_scores: tuple[str, ...]


class CustomContainsMetric:
    type = "custom-contains"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("contains")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        expected = str(input.row.data["expected"]).lower()
        candidate = str(input.row.data["model_output"]).lower()
        return MetricResult(outputs=[MetricOutput(name="contains", value=float(expected in candidate))])


def _base_url() -> str:
    return os.environ.get("NEMO_PLATFORM_BASE_URL", "http://127.0.0.1:8080")


def _workspace() -> str:
    return os.environ.get("NEMO_PLATFORM_WORKSPACE", "default")


def _poll_interval_seconds() -> float:
    return float(os.environ.get("NEMO_EVALUATOR_SMOKE_POLL_INTERVAL_SECONDS", "2"))


def _job_timeout_seconds() -> float:
    return float(os.environ.get("NEMO_EVALUATOR_SMOKE_JOB_TIMEOUT_SECONDS", "600"))


def _pending_timeout_seconds() -> float:
    return float(os.environ.get("NEMO_EVALUATOR_SMOKE_PENDING_TIMEOUT_SECONDS", "120"))


def _dataset() -> list[DatasetRow]:
    return [
        {
            "expected": "blue",
            "model_output": "Blue",
            "left_text": "prefix needle suffix",
            "right_text": "needle",
            "left_number": "42",
            "right_number": "42",
            "expected_tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "lookup_weather", "arguments": {"city": "Halifax"}},
                }
            ],
            "response": {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup_weather",
                                        "arguments": '{"city": "Halifax"}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        },
        {
            "expected": "Jupiter",
            "model_output": "Jupiter is the largest planet",
            "left_text": "another haystack with needle",
            "right_text": "needle",
            "left_number": "7.5",
            "right_number": "7.5",
            "expected_tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "lookup_planet", "arguments": {"name": "Jupiter"}},
                }
            ],
            "response": {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_2",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup_planet",
                                        "arguments": '{"name": "Jupiter"}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        },
    ]


def _metric_cases() -> list[MetricCase]:
    return [
        MetricCase(
            name="exact_match",
            metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}"),
            expected_aggregate_scores=("exact-match.exact-match",),
        ),
        MetricCase(
            name="f1",
            metric=F1Metric(reference="{{item.expected}}", candidate="{{item.model_output}}"),
            expected_aggregate_scores=("f1.f1",),
        ),
        MetricCase(
            name="bleu",
            metric=BLEUMetric(references=["{{item.expected}}"], candidate="{{item.model_output}}"),
            expected_aggregate_scores=("bleu.sentence", "bleu.corpus"),
        ),
        MetricCase(
            name="rouge",
            metric=ROUGEMetric(reference="{{item.expected}}", candidate="{{item.model_output}}"),
            expected_aggregate_scores=(
                "rouge.rouge_1_score",
                "rouge.rouge_2_score",
                "rouge.rouge_3_score",
                "rouge.rouge_L_score",
            ),
        ),
        MetricCase(
            name="string_check",
            metric=StringCheckMetric(
                operation="contains",
                left_template="{{item.left_text}}",
                right_template="{{item.right_text}}",
            ),
            expected_aggregate_scores=("string-check.string-check",),
        ),
        MetricCase(
            name="number_check",
            metric=NumberCheckMetric(
                operation="equals",
                left_template="{{item.left_number}}",
                right_template="{{item.right_number}}",
            ),
            expected_aggregate_scores=("number-check.number-check",),
        ),
        MetricCase(
            name="tool_calling",
            metric=ToolCallingMetric(reference="{{item.expected_tool_calls}}"),
            expected_aggregate_scores=(
                "tool-calling.function_name_accuracy",
                "tool-calling.function_name_and_args_accuracy",
            ),
        ),
        MetricCase(
            name="custom_protocol",
            metric=CustomContainsMetric(),
            expected_aggregate_scores=("custom-contains.contains",),
        ),
    ]


def _aggregate_score_names(result) -> list[str]:
    return [score.name for score in result.aggregate_scores.scores]


def _assert_scores_present(actual: Sequence[str], expected: Sequence[str]) -> None:
    missing = [score_name for score_name in expected if score_name not in actual]
    if missing:
        raise AssertionError(f"missing aggregate scores {missing}; actual scores: {list(actual)}")


def main() -> int:
    dataset = _dataset()
    config = RunConfig(parallelism=2)
    bundler = CloudpickleMetricBundler()
    metric_cases = _metric_cases()

    with httpx.Client(timeout=httpx.Timeout(30.0)) as http_client:
        platform = NeMoPlatform(
            base_url=_base_url(),
            workspace=_workspace(),
            http_client=http_client,
        )
        plugin_resource = PluginEvaluator(platform)
        backend = NMPBackend(
            plugin_resource,
            execution_mode="remote",
            metric_bundler=bundler,
        )
        evaluator = SDKEvaluator(client=backend)

        exact_result = evaluator.run_sync(
            metrics=metric_cases[0].metric,
            dataset=dataset,
            config=config,
        )
        exact_score = exact_result.aggregate_scores.scores[0]
        custom_result = evaluator.run_sync(
            metrics=CustomContainsMetric(),
            dataset=dataset,
            config=config,
        )
        custom_score = custom_result.aggregate_scores.scores[0]

        multi_spec = _build_evaluate_spec(
            metrics=[metric_case.metric for metric_case in metric_cases],
            request=EvaluationRequest(dataset=dataset, params=config),
            metric_bundler=bundler,
        )
        multi_job = plugin_resource._executor.create(spec=multi_spec, workspace=_workspace())
        multi_job.wait_until_done(
            poll_interval_seconds=_poll_interval_seconds(),
            job_timeout_seconds=_job_timeout_seconds(),
            pending_timeout_seconds=_pending_timeout_seconds(),
        )
        multi_result = multi_job.get_result()

        print(f"exact_rows={len(exact_result.row_scores)}")
        print(f"exact_score_name={exact_score.name}")
        print(f"exact_mean={exact_score.mean}")
        print(f"custom_rows={len(custom_result.row_scores)}")
        print(f"custom_score_name={custom_score.name}")
        print(f"custom_mean={custom_score.mean}")
        print(f"multi_job={multi_job.name}")
        print(f"multi_rows={len(multi_result.row_scores)}")
        print(f"multi_scores={_aggregate_score_names(multi_result)}")
        print(f"multi_means={[score.mean for score in multi_result.aggregate_scores.scores]}")

        assert len(exact_result.row_scores) == 2
        assert exact_score.name == "exact-match.exact-match"
        assert exact_score.mean == 0.5
        assert len(custom_result.row_scores) == 2
        assert custom_score.name == "custom-contains.contains"
        assert custom_score.mean == 1.0
        assert len(multi_result.row_scores) == 2
        multi_score_names = _aggregate_score_names(multi_result)
        for metric_case in metric_cases:
            _assert_scores_present(multi_score_names, metric_case.expected_aggregate_scores)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
