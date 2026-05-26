# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Smoke-test evaluator plugin local execution with runtime metrics."""

from __future__ import annotations

import httpx
from nemo_evaluator.sdk.resources import Evaluator as PluginEvaluator
from nemo_evaluator.sdk.standalone_sdk.backend import NMPBackend
from nemo_evaluator_sdk import Evaluator as SDKEvaluator
from nemo_evaluator_sdk.metrics.bundles import MetricBundle, MetricBundler
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values import RunConfig
from nemo_platform import NeMoPlatform


class CustomContainsMetric:
    type = "custom-contains"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("contains")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        expected = str(input.row.data["expected"]).lower()
        candidate = str(input.row.data["model_output"]).lower()
        return MetricResult(outputs=[MetricOutput(name="contains", value=float(expected in candidate))])


class _FailIfBundled(MetricBundler):
    def bundle(self, metric: Metric) -> MetricBundle:
        raise AssertionError("local evaluator execution should not bundle metrics")

    def unbundle(self, metric: MetricBundle) -> Metric:
        raise AssertionError("local evaluator execution should not unbundle metrics")


def main() -> int:
    with httpx.Client() as http_client:
        platform = NeMoPlatform(
            base_url="http://localhost:8000",
            workspace="default",
            http_client=http_client,
        )
        plugin_resource = PluginEvaluator(platform)
        backend = NMPBackend(
            plugin_resource,
            execution_mode="local",
            metric_bundler=_FailIfBundled(),
        )
        evaluator = SDKEvaluator(client=backend)
        dataset = [
            {"expected": "blue", "model_output": "Blue"},
            {"expected": "Jupiter", "model_output": "Jupiter is the largest planet"},
        ]

        exact_result = evaluator.run_sync(
            metrics=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}"),
            dataset=dataset,
            config=RunConfig(parallelism=2),
        )
        exact_score = exact_result.aggregate_scores.scores[0]
        custom_result = evaluator.run_sync(
            metrics=CustomContainsMetric(),
            dataset=dataset,
            config=RunConfig(parallelism=2),
        )
        custom_score = custom_result.aggregate_scores.scores[0]
        multi_result = evaluator.run_sync(
            metrics=[
                ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}"),
                CustomContainsMetric(),
            ],
            dataset=dataset,
            config=RunConfig(parallelism=2),
        )

        print(f"exact_rows={len(exact_result.row_scores)}")
        print(f"exact_score_name={exact_score.name}")
        print(f"exact_mean={exact_score.mean}")
        print(f"custom_rows={len(custom_result.row_scores)}")
        print(f"custom_score_name={custom_score.name}")
        print(f"custom_mean={custom_score.mean}")
        print(f"multi_rows={len(multi_result.row_scores)}")
        print(f"multi_scores={[score.name for score in multi_result.aggregate_scores.scores]}")
        print(f"multi_means={[score.mean for score in multi_result.aggregate_scores.scores]}")

        assert len(exact_result.row_scores) == 2
        assert exact_score.name == "exact-match.exact-match"
        assert exact_score.mean == 0.5
        assert len(custom_result.row_scores) == 2
        assert custom_score.name == "custom-contains.contains"
        assert custom_score.mean == 1.0
        assert len(multi_result.row_scores) == 2
        assert [score.name for score in multi_result.aggregate_scores.scores] == [
            "exact-match.exact-match",
            "custom-contains.contains",
        ]
        assert [score.mean for score in multi_result.aggregate_scores.scores] == [0.5, 1.0]
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
