# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Requirement-oriented snippets derived from ``examples.py``.

This file exists so external requirement tables can link to concrete evaluator
SDK code examples with stable GitHub line ranges.
"""

from __future__ import annotations

from nemo_evaluator_sdk.execution.evaluator import Evaluator
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.f1 import F1Metric
from nemo_evaluator_sdk.metrics.llm_judge import LLMJudgeMetric
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.metrics.string_check import StringCheckMetric
from nemo_evaluator_sdk.values import (
    InferenceParams,
    JSONScoreParser,
    Model,
    RangeScore,
    RunConfig,
    SecretRef,
)
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult

# Alias for BenchmarkEvaluationResult to align with the requirements
EvaluationSuiteResult = BenchmarkEvaluationResult

HELPFULNESS_PROMPT_V1 = (
    "You are an evaluator. Rate the response's helpfulness from 0-4. "
    'Return only a JSON object with this shape: {"helpfulness": <integer>}.'
)

OFFLINE_SUITE_DATASET = [
    {
        "prompt": "What is the capital of France?",
        "reference": "Paris",
        "actual": "Paris",
        "response": "Paris",
        "required_phrase": "Paris",
    },
    {
        "prompt": "What is the capital of England?",
        "reference": "London",
        "actual": "Berlin",
        "response": "Berlin",
        "required_phrase": "London",
    },
]

ONLINE_SUITE_DATASET = [
    {
        "prompt": "Return exactly this word with no punctuation: Paris",
        "reference": "Paris",
        "required_phrase": "Paris",
    },
    {
        "prompt": "Return exactly this word with no punctuation: Oslo",
        "reference": "London",
        "required_phrase": "London",
    },
]

ONLINE_CHAT_PROMPT_TEMPLATE = {"messages": [{"role": "user", "content": "{{item.prompt}}"}]}

MODEL = Model(
    url="https://integrate.api.nvidia.com/v1/chat/completions",
    name="nvidia/nemotron-3-nano-30b-a3b",
    api_key_secret=SecretRef(root="NVIDIA_API_KEY"),
)


def suite_metrics() -> list[Metric]:
    """Build the scorer set used by the suite snippets below."""
    exact_match = ExactMatchMetric(reference="{{item.reference}}", candidate="{{item.actual}}")
    contains_required_phrase = StringCheckMetric(
        operation="contains",
        left_template="{{item.actual}}",
        right_template="{{item.required_phrase}}",
    )
    return [exact_match, contains_required_phrase]


def create_reference_free_judge_metric(judge_model: Model) -> LLMJudgeMetric:
    """Build an LLM-as-judge scorer using the same metric contract."""
    return LLMJudgeMetric(
        model=judge_model,
        scores=[
            RangeScore(
                name="helpfulness",
                minimum=0,
                maximum=4,
                parser=JSONScoreParser(json_path="helpfulness"),
                description="How well does the response help the user?",
            )
        ],
        inference=InferenceParams(temperature=0.0, max_tokens=32768),
        prompt_template={
            "messages": [
                {"role": "system", "content": HELPFULNESS_PROMPT_V1},
                {
                    "role": "user",
                    "content": (
                        "User prompt: {{item.prompt}}\n\n"
                        "Assistant response: {{sample.output_text | default(item.response)}}\n\n"
                        "Rate this response."
                    ),
                },
            ],
        },
    )


class CustomPythonExactMatchMetric:
    """
    A pure-Python custom scorer that implements the same Metric protocol as LLMJudgeMetric.
    This is a deterministic code metric that can be used in the same way as other metrics.
    """

    type = "custom-python-exact-match"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score(self.type)]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        prediction = input.candidate.output_text
        reference = input.row.data.get("actual")
        if reference is None:
            reference = input.row.data.get("reference")
        score = 1.0 if prediction is not None and prediction == reference else 0.0
        return MetricResult(outputs=[MetricOutput(name=self.type, value=score)])


# 1a) Evaluation Suite: Dataset + Taskset
async def run_candidate_against_fixed_suite() -> EvaluationSuiteResult:
    """Run one fixed dataset and scorer set so candidate results are comparable."""
    metrics_suite = [
        ExactMatchMetric(reference="{{item.reference}}", candidate="{{item.actual}}"),
        StringCheckMetric(
            operation="contains",
            left_template="{{item.actual}}",
            right_template="{{item.required_phrase}}",
        ),
    ]

    return await Evaluator().run(
        metrics=metrics_suite,
        dataset=OFFLINE_SUITE_DATASET,
        config=RunConfig(parallelism=4),
    )


# 1b) Per-trial & Aggregate Results
async def collect_per_trial_and_aggregate_results() -> dict[str, object]:
    """Read per-row records and aggregate scores from the same completed result."""
    result = await run_candidate_against_fixed_suite()
    return {
        "per_trial": result.to_records(view="rows"),
        "aggregate": result.to_records(view="aggregate"),
        "exact_match_aggregate": result.metric_result("exact-match").aggregate_scores.scores,
    }


# 1c) Service Status
# Note: service related code snippets leverage the `nemo_evaluator.sdk` plugin SDK.
# The `nemo_evaluator.sdk` plugin SDK is a client that is used within the context of nemo-platform.
# The `nemo_evaluator_sdk` is standalone evaluator package that is used independently of nemo-platform.
# More details: https://jubilant-adventure-g4rv38m.pages.github.io/main/evaluator/#key-differences-from-standalone-library
async def submit_plugin_job_and_check_status() -> dict[str, object]:
    """Submit through the plugin SDK and inspect the returned job status."""
    from nemo_evaluator.sdk import AsyncEvaluator
    from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(base_url="http://localhost:8080", workspace="default")
    nemo_plugin_client: AsyncEvaluator = client.evaluator

    try:
        job = await nemo_plugin_client.submit(
            metric=ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}"),
            dataset=[
                {"expected": "blue", "model_output": "blue"},
                {"expected": "Jupiter", "model_output": "Saturn"},
            ],
            config=RunConfig(parallelism=2, limit_samples=2),
            metric_bundle_packager=CloudpickleMetricBundlePackager(),
        )
        submitted_status = await job.get_job_status()
        await job.wait_until_done(poll_interval_seconds=5)
        return {
            "job_name": job.name,
            "submitted_status": submitted_status,
            "terminal_status": await job.get_job_status(),
        }
    finally:
        client.close()


# 2a) Support for Local & Remote mode eval
async def run_local_and_submit_remote_with_plugin_sdk() -> dict[str, object]:
    """Use plugin SDK ``run`` locally and ``submit`` for service-backed execution."""
    from nemo_evaluator.sdk import AsyncEvaluator
    from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
    from nemo_platform import NeMoPlatform

    dataset = [
        {"expected": "blue", "model_output": "blue"},
        {"expected": "Jupiter", "model_output": "Saturn"},
    ]
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}")
    config = RunConfig(parallelism=2, limit_samples=2)

    client = NeMoPlatform(base_url="http://localhost:8080", workspace="default")
    nemo_plugin_client: AsyncEvaluator = client.evaluator

    try:
        local_result = nemo_plugin_client.run(metric=metric, dataset=dataset, config=config)
        remote_job = await nemo_plugin_client.submit(
            metric=metric,
            dataset=dataset,
            config=config,
            metric_bundle_packager=CloudpickleMetricBundlePackager(),
        )
        return {
            "local_result": local_result,
            "remote_job_name": remote_job.name,
            "remote_status": await remote_job.get_job_status(),
        }
    finally:
        client.close()


# 3a) Runner independent of scorer
# 3b) Change in scorer should not impact runner
async def run_supplied_scorers() -> None:
    """Keep runner execution independent from how each scorer is defined."""

    # Define the scorer
    exact_only = [ExactMatchMetric(reference="{{item.reference}}", candidate="{{item.actual}}")]

    # Run the scorer
    await Evaluator().run(
        metrics=exact_only,
        dataset=OFFLINE_SUITE_DATASET,
        config=RunConfig(parallelism=4),
    )


# 4a) Common interface for judge & python code based scorer
# 4b) Common schema for judge & python based scorer
def scorer_interface_examples() -> None:
    """Check that LLM-judge and Python scorers satisfy the Metric protocol."""
    judge_metric = create_reference_free_judge_metric(MODEL)
    if not isinstance(judge_metric, Metric):
        raise TypeError(f"{type(judge_metric).__name__} does not implement Metric")

    python_metric = CustomPythonExactMatchMetric()
    if not isinstance(python_metric, Metric):
        raise TypeError(f"{type(python_metric).__name__} does not implement Metric")


# 5a) Support variety types of scorers: reference-based (ground-truth) metrics,
# rubric-based reference-free LLM-as-judge, deterministic code metrics
# All available metrics: https://github.com/NVIDIA-NeMo/nemo-platform/tree/main/packages/nemo_evaluator_sdk/src/nemo_evaluator_sdk/metrics
def scorer_style_examples() -> dict[str, Metric]:
    """Inline concrete metric examples for different scorer styles."""
    return {
        "exact_match": ExactMatchMetric(reference="{{item.reference}}", candidate="{{item.actual}}"),
        "f1": F1Metric(reference="{{item.reference}}", candidate="{{item.actual}}"),
        "llm_judge": create_reference_free_judge_metric(MODEL),
        "custom_python": CustomPythonExactMatchMetric(),
    }


# 5b) Support variety types of scorers all scorer styles are expressible and runnable within one suite
async def run_mixed_scorer_suite() -> EvaluationSuiteResult:
    """Run the available scorer styles together in one evaluator suite."""
    return await Evaluator().run(
        metrics=list(scorer_style_examples().values()),
        dataset=OFFLINE_SUITE_DATASET,
        config=RunConfig(parallelism=4),
    )
