# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Examples demonstrating local evaluator workflows for the SDK."""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import shutil
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from nemo_evaluator_sdk.execution.evaluator import Evaluator
from nemo_evaluator_sdk.execution.values import EvaluationError
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.llm_judge import LLMJudgeMetric
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec
from nemo_evaluator_sdk.metrics.string_check import StringCheckMetric
from nemo_evaluator_sdk.values import (
    InferenceParams,
    JSONScoreParser,
    MetricResult,
    Model,
    RangeScore,
    RunConfig,
    RunConfigOnlineModel,
    SecretRef,
)

if TYPE_CHECKING:
    import numpy as np
    from nemo_platform import AsyncNeMoPlatform


# --- 1. Defining reusable metric configs and custom metrics ---
# Notice the public API is centered on Evaluator. Metrics stay focused on
# scoring logic and configuration rather than owning execution helpers.
HELPFULNESS_PROMPT_V1 = (
    "You are an evaluator. Rate the response's helpfulness from 0-4. "
    'Return only a JSON object with this shape: {"helpfulness": <integer>}.'
)
# Local evaluator and local plugin execution resolve this as an environment variable name.
DEFAULT_API_KEY_SECRET = os.getenv("NMP_EVALUATOR_DEFAULT_API_KEY_SECRET", "NVIDIA_API_KEY")
DEFAULT_WORKSPACE = os.getenv("NMP_EVALUATOR_DEFAULT_WORKSPACE", "default")
HELPSTEER2_VALIDATION_JSONL_URL = "https://huggingface.co/datasets/nvidia/HelpSteer2/resolve/main/validation.jsonl.gz"
_EXAMPLES_DIR = Path(__file__).resolve().parent


def configure_example_logging() -> None:
    """Enable SDK progress logs when this example file is executed directly."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


OFFLINE_EXACT_MATCH_DATASET = [
    {"reference": "Paris", "actual": "Paris"},
    {"reference": "London", "actual": "Berlin"},
]
ONLINE_EXACT_MATCH_DATASET = [
    {
        "prompt": "What is the capital of France? Reply in single word.",
        "reference": "Paris",
    },
    {
        "prompt": "How do I make scrambled eggs? Reply in single word.",
        "reference": "Eggs",
    },
]

OFFLINE_JUDGE_DATASET = [
    {
        "prompt": "What is the capital of France?",
        "response": "Paris",
    },
    {
        "prompt": "How do I make scrambled eggs?",
        "response": "Eggs.",
    },
]

OFFLINE_BENCHMARK_DATASET = [
    {
        "reference": "Paris",
        "actual": "Paris",
        "required_phrase": "Paris",
    },
    {
        "reference": "London",
        "actual": "Berlin",
        "required_phrase": "London",
    },
]

ONLINE_BENCHMARK_DATASET = [
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

ONLINE_JUDGE_DATASET = [
    {
        "prompt": "What is the capital of France?",
    },
    {
        "prompt": "How do I make scrambled eggs?",
    },
]

OFFLINE_HELPFULNESS_DATASET = [
    {
        "prompt": "What is the capital of France?",
        "response": "Paris is the capital of France.",
        "helpfulness": 4,
    },
    {
        "prompt": "How do I make scrambled eggs?",
        "response": "Eggs.",
        "helpfulness": 1,
    },
]


def get_helpsteer2_dataset() -> Path:
    """Return a local HelpSteer2 validation JSONL path, downloading it when absent."""

    dataset_dir = _EXAMPLES_DIR / "temp" / "helpsteer2-eval"
    validation_jsonl = dataset_dir / "validation.jsonl"
    if validation_jsonl.exists():
        return validation_jsonl

    dataset_dir.mkdir(parents=True, exist_ok=True)
    validation_jsonl_gz = dataset_dir / "validation.jsonl.gz"
    try:
        with (
            urllib.request.urlopen(HELPSTEER2_VALIDATION_JSONL_URL, timeout=60) as response,
            validation_jsonl_gz.open("wb") as gz_file,
        ):
            shutil.copyfileobj(response, gz_file)
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Failed to download HelpSteer2 validation dataset from {HELPSTEER2_VALIDATION_JSONL_URL}: {e}"
        ) from e
    with gzip.open(validation_jsonl_gz, "rb") as compressed_file, validation_jsonl.open("wb") as output_file:
        shutil.copyfileobj(compressed_file, output_file)  # pyright: ignore[reportArgumentType]
    return validation_jsonl


ONLINE_CHAT_PROMPT_TEMPLATE = {"messages": [{"role": "user", "content": "{{item.prompt}}"}]}


model = Model(
    url="https://integrate.api.nvidia.com/v1/chat/completions",
    name=os.getenv("NEMO_DEFAULT_MODEL", "nvidia/nemotron-3-nano-30b-a3b"),
    # looks up NVIDIA_API_KEY by default - override via NMP_EVALUATOR_DEFAULT_API_KEY_SECRET
    api_key_secret=SecretRef(root=DEFAULT_API_KEY_SECRET),
)

model_with_custom_headers = model.with_default_headers({"X-My-Header": "value"})


async def ensure_remote_evaluator_api_key_secret(workspace: str, client: AsyncNeMoPlatform) -> str:
    """Resolve API key secret name from env and ensure the secret exists on the platform."""
    from nemo_platform import ConflictError, NotFoundError

    # API service expects lowercase secret name; if we keep it uppercase, the request will fail.
    secret_name = DEFAULT_API_KEY_SECRET.lower()
    try:
        await client.secrets.retrieve(secret_name, workspace=workspace)
    except NotFoundError:
        api_key = os.getenv(DEFAULT_API_KEY_SECRET) or os.getenv("NVIDIA_API_KEY") or os.getenv("NVIDIA_BUILD_API_KEY")
        if api_key is None:
            raise RuntimeError(
                f"Remote online evaluation needs a platform secret named '{secret_name}' in workspace "
                f"'{workspace}'. Set NVIDIA_BUILD_API_KEY or NVIDIA_API_KEY to let this "
                "example create it, or create it manually with: "
                f"nemo secrets create {secret_name} --data '<api-key>' --workspace {workspace}"
            ) from None
        try:
            await client.secrets.create(workspace=workspace, name=secret_name, value=api_key)
            print(f"Secret {workspace}/{secret_name} created")
        except ConflictError:
            pass
    return secret_name


async def model_with_valid_secret(
    *,
    execution_mode: Literal["local", "remote"],
    workspace: str,
    client: AsyncNeMoPlatform,
) -> Model:
    """Return a model configured for local or remote NeMo Platform example execution."""
    if execution_mode == "remote":
        secret_name = await ensure_remote_evaluator_api_key_secret(workspace, client)
        return model.model_copy(update={"api_key_secret": SecretRef(root=secret_name)})
    return model


def create_helpfulness_metric(judge_model: Model) -> LLMJudgeMetric:
    """Build a reusable LLM judge metric for helpfulness scoring."""
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
        inference=InferenceParams(
            temperature=0.0,
            max_tokens=32768,
        ),
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


def _print_example_separator(name: str, **params: Any) -> None:
    """Print a visible section header for an independently runnable example."""
    edge = "====="
    inner = name
    if params:
        inner += "(" + ", ".join(f"{k}={v!r}" for k, v in params.items()) + ")"
    middle_line = f"{edge} {inner} {edge}"
    rule = "=" * len(middle_line)
    print(f"\n{rule}\n{middle_line}\n{rule}\n")


def extract_helpfulness_scores(
    row_scores: Sequence[Any],
    *,
    dimension: str = "helpfulness",
    metric_ref: str | None = None,
    judge_response_index: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract aligned judge and human score arrays from metric-job rows.

    Args:
        row_scores: Row-level metric-job results returned by ``Evaluator.run``
            or ``client.evaluation.metric_jobs.results.row_scores.download``.
        dimension: Dataset field and judge JSON key to compare.
        metric_ref: Optional metric key for benchmark rows where scores are
            already materialized in ``row.metrics``.
        judge_response_index: Request-log index containing the judge response.

    Returns:
        A pair of NumPy arrays: ``(judge_scores, human_scores)``.
    """
    import numpy as np

    judge_scores = []
    human_scores = []
    failed_requests = 0

    for row in row_scores:
        try:
            human_score = float(row.item[dimension])

            if metric_ref is None:
                if not row.requests:
                    raise ValueError("Missing judge request payload")
                judge_response = row.requests[judge_response_index]["response"]["choices"][0]["message"]["content"]
                judge_data = json.loads(judge_response)
                judge_score = float(judge_data[dimension])
            else:
                judge_score = float(row.metrics[metric_ref][0].value)

            human_scores.append(human_score)
            judge_scores.append(judge_score)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            failed_requests += 1
            continue

    print(f"Total errors: {failed_requests}")
    return np.array(judge_scores), np.array(human_scores)


class CustomExactMatchMetric:
    """A user-defined metric that depends on runtime-injected state."""

    type = "custom-exact-match"

    def __init__(self, db_connection_string: str):
        """Store runtime state needed by the custom metric.

        Args:
            db_connection_string: Example dependency injected into the metric.
        """
        self.db_connection_string = db_connection_string

    def output_spec(self) -> list[MetricOutputSpec]:
        """Return the outputs produced by the metric."""
        return [MetricOutputSpec.continuous_score(self.type)]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        """Convert the custom score into the SDK metric result shape.

        Args:
            input: Original dataset row and evaluated candidate output.

        Returns:
            A metric result containing one exact-match score.
        """
        prediction = input.candidate.output_text
        reference = input.row.data.get("actual")
        if reference is None:
            reference = input.row.data.get("reference")
        if prediction is None or reference is None:
            return MetricResult(outputs=[MetricOutput(name=self.type, value=0.0)])
        score = 1.0 if prediction == reference else 0.0
        return MetricResult(outputs=[MetricOutput(name=self.type, value=score)])


class CustomFailingMetric:
    """A user-defined metric that raises to demonstrate metric failure handling."""

    type = "custom-metric-with-failure"

    def __init__(self, message: str):
        """Store the error message emitted by this example metric.

        Args:
            message: Text used for the raised runtime error.
        """
        self.message = message

    def output_spec(self) -> list[MetricOutputSpec]:
        """Return the outputs produced by the metric."""
        return [MetricOutputSpec.continuous_score(self.type)]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        """Convert the intentionally raised error into normal metric execution.

        Args:
            input: Original dataset row and evaluated candidate output.

        Raises:
            RuntimeError: Always raised to exercise benchmark failure handling.
        """
        del input
        # This example metric is intentionally failing to demonstrate structured
        # benchmark error handling in local evaluator workflows.
        raise RuntimeError(self.message)


# --- 2. Local evaluator workflows ---
async def run_offline_local_exact_match_example() -> None:
    """Run one offline exact-match evaluation example.

    Returns:
        None.
    """

    _print_example_separator(run_offline_local_exact_match_example.__name__)

    evaluator = Evaluator()
    # TODO: fix error message in another branch
    exact_match = ExactMatchMetric(reference="{{item.reference}}", candidate="{{item.actual}}")

    print("Running offline exact match...")

    exact_match_result = await evaluator.run(
        metrics=exact_match,
        dataset=OFFLINE_EXACT_MATCH_DATASET,
        config=RunConfig(parallelism=4),
    )
    exact_match_result.print_summary()


async def run_online_local_exact_match_example() -> None:
    """Run one local online exact-match evaluation example.

    Returns:
        None.
    """

    _print_example_separator(run_online_local_exact_match_example.__name__)

    evaluator = Evaluator()
    exact_match = ExactMatchMetric(reference="{{item.reference}}")

    print("Running local online exact match...")

    exact_match_result = await evaluator.run(
        metrics=exact_match,
        target=model,
        dataset=ONLINE_EXACT_MATCH_DATASET,
        config=RunConfig(parallelism=4),
    )
    exact_match_result.print_summary()


async def run_offline_local_multi_metric_example() -> None:
    """Run one local multi-metric evaluation example.

    Returns:
        None.
    """

    _print_example_separator(run_offline_local_multi_metric_example.__name__)

    evaluator = Evaluator()
    custom_metric = CustomExactMatchMetric(db_connection_string="postgresql://localhost@localhost:5432/mydatabase")
    exact_match = ExactMatchMetric(reference="{{item.reference}}", candidate="{{item.actual}}")

    print("\nRunning local multi-metric evaluation...")

    combined_result = await evaluator.run(
        metrics=[exact_match, custom_metric],
        dataset=OFFLINE_EXACT_MATCH_DATASET,
        config=RunConfig(parallelism=4),
    )
    combined_result.print_summary()
    print(f"Per-metric keys: {list(combined_result.per_metric)}")
    print(f"Exact match aggregate scores: {combined_result.metric_result('exact-match').aggregate_scores.scores}")


async def run_offline_local_benchmark_example() -> None:
    """Run one local benchmark example with multiple metrics.

    Returns:
        None.
    """

    _print_example_separator(run_offline_local_benchmark_example.__name__)

    evaluator = Evaluator()
    exact_match = ExactMatchMetric(reference="{{item.reference}}", candidate="{{item.actual}}")
    contains_required_phrase = StringCheckMetric(
        operation="contains",
        left_template="{{item.actual}}",
        right_template="{{item.required_phrase}}",
    )

    print("\nRunning local benchmark evaluation...")

    benchmark_result = await evaluator.run(
        metrics=[exact_match, contains_required_phrase],
        dataset=OFFLINE_BENCHMARK_DATASET,
        config=RunConfig(parallelism=4),
    )
    benchmark_result.print_summary()
    print(f"Benchmark metric keys: {list(benchmark_result.per_metric)}")
    print(f"Exact match scores: {benchmark_result.metric_result('exact-match').aggregate_scores.scores}")
    print(f"String check scores: {benchmark_result.metric_result('string-check').aggregate_scores.scores}")


async def run_online_local_benchmark_example() -> None:
    """Run one local online benchmark example with multiple metrics.

    Returns:
        None.
    """

    _print_example_separator(run_online_local_benchmark_example.__name__)

    evaluator = Evaluator()
    exact_match = ExactMatchMetric(reference="{{item.reference}}")
    contains_required_phrase = StringCheckMetric(
        operation="contains",
        left_template="{{sample.output_text}}",
        right_template="{{item.required_phrase}}",
    )

    print("\nRunning local online benchmark evaluation...")

    benchmark_result = await evaluator.run(
        metrics=[exact_match, contains_required_phrase],
        target=model,
        dataset=ONLINE_BENCHMARK_DATASET,
        prompt_template=ONLINE_CHAT_PROMPT_TEMPLATE,
        config=RunConfig(parallelism=4),
    )
    benchmark_result.print_summary()
    print(f"Online benchmark metric keys: {list(benchmark_result.per_metric)}")
    print(f"Exact match scores: {benchmark_result.metric_result('exact-match').aggregate_scores.scores}")
    print(f"String check scores: {benchmark_result.metric_result('string-check').aggregate_scores.scores}")


async def run_local_benchmark_with_metric_failure_example() -> None:
    """Run one benchmark where a sibling metric survives another metric failure."""

    _print_example_separator(run_local_benchmark_with_metric_failure_example.__name__)

    evaluator = Evaluator()
    exact_match = ExactMatchMetric(reference="{{item.reference}}", candidate="{{item.actual}}")
    failing_metric = CustomFailingMetric(message="intentional benchmark metric failure")

    print("\nRunning local benchmark evaluation with one failing metric...")

    try:
        await evaluator.run(
            metrics=[exact_match, failing_metric],
            dataset=OFFLINE_BENCHMARK_DATASET,
            config=RunConfig(parallelism=4),
        )
    except EvaluationError as error:
        print("Benchmark evaluation failed with structured context:")
        print(f"  error: {error}")
        print(f"  row index: {error.index}")
        print(f"  phase: {error.phase.value}")
        print(f"  metric key: {error.metric_key}")
        print(f"  message: {error.message}")


async def run_local_metric_with_template_failure_example() -> None:
    """Run metric evaluations that expose Jinja template failures clearly.

    Returns:
        None.
    """

    _print_example_separator(run_local_metric_with_template_failure_example.__name__)

    evaluator = Evaluator()
    invalid_metric = ExactMatchMetric(
        reference="{{item.missing_reference}}",
        candidate="{{item.actual}}",
    )
    dataset = OFFLINE_EXACT_MATCH_DATASET[:1]

    print("\nRunning local metric evaluation with an invalid metric template...")
    try:
        await evaluator.run(
            metrics=invalid_metric,
            dataset=dataset,
            config=RunConfig(parallelism=1),
        )
    except EvaluationError as error:
        print("Metric evaluation failed with structured context:")
        print(f"  error: {error}")
        print(f"  row index: {error.index}")
        print(f"  phase: {error.phase.value}")
        print(f"  metric key: {error.metric_key}")
        print(f"  message: {error.message}")
        if error.__cause__ is not None:
            print(f"  cause: {type(error.__cause__).__name__}: {error.__cause__}")


async def run_offline_local_llm_judge_example() -> None:
    """Run one local LLM-judge evaluation example with run overrides.

    Returns:
        None.
    """

    _print_example_separator(run_offline_local_llm_judge_example.__name__)

    evaluator = Evaluator()
    llm_judge_metric = create_helpfulness_metric(model_with_custom_headers)

    print("\nRunning local LLM judge evaluation...")

    llm_judge_result = await evaluator.run(
        metrics=llm_judge_metric,
        dataset=OFFLINE_JUDGE_DATASET,
        config=RunConfig(parallelism=2),
    )
    llm_judge_result.print_summary()


async def run_online_local_llm_judge_example() -> None:
    """Run one local online LLM-judge evaluation example with run overrides.

    Returns:
        None.
    """

    _print_example_separator(run_online_local_llm_judge_example.__name__)

    evaluator = Evaluator()
    llm_judge_metric = create_helpfulness_metric(model_with_custom_headers)

    print("\nRunning local online LLM judge evaluation...")

    llm_judge_result = await evaluator.run(
        metrics=llm_judge_metric,
        target=model_with_custom_headers,
        dataset=ONLINE_JUDGE_DATASET,
        config=RunConfig(parallelism=2),
    )
    llm_judge_result.print_summary()


def run_sync_example() -> None:
    """Run a minimal synchronous evaluator workflow.

    Returns:
        None.
    """

    evaluator = Evaluator()
    result = evaluator.run_sync(
        metrics=ExactMatchMetric(reference="{{item.reference}}"),
        dataset=OFFLINE_EXACT_MATCH_DATASET[:1],  # Only run the first sample
        config=RunConfig(parallelism=1),
    )
    print("\nRunning sync exact match...")
    result.print_summary()


# --- 3. NeMo Platform evaluator plugin workflows ---
async def run_nmp_online_metric_example() -> None:
    """Run one online metric job locally through the evaluator plugin resource."""

    _print_example_separator(run_nmp_online_metric_example.__name__)

    from nemo_evaluator.sdk.standalone_sdk.backend import AsyncNMPBackend
    from nemo_platform import AsyncNeMoPlatform

    client = AsyncNeMoPlatform(workspace=DEFAULT_WORKSPACE, timeout=30000.0)
    try:
        evaluator = Evaluator(client=AsyncNMPBackend(client.evaluator))
        result = await evaluator.run(
            metrics=ExactMatchMetric(reference="{{item.reference}}"),
            target=model,
            dataset=ONLINE_EXACT_MATCH_DATASET,
            prompt_template=ONLINE_CHAT_PROMPT_TEMPLATE,
            config=RunConfigOnlineModel(parallelism=4),
        )
    finally:
        await client.close()

    print("\nCompleted NeMo Platform online evaluator plugin job locally...")
    result.print_summary()


async def run_nmp_llm_judge_example(
    is_online: bool = False,
    limit_samples: int = 2,
    execution_mode: Literal["local", "remote"] = "local",
) -> None:
    """Run a helpfulness judge job locally through the evaluator plugin resource."""

    _print_example_separator(
        run_nmp_llm_judge_example.__name__,
        is_online=is_online,
        limit_samples=limit_samples,
        execution_mode=execution_mode,
    )

    from nemo_evaluator.sdk.standalone_sdk.backend import AsyncNMPBackend
    from nemo_platform import AsyncNeMoPlatform

    nemo_client = AsyncNeMoPlatform(workspace=DEFAULT_WORKSPACE, timeout=30000.0)
    evaluator_plugin_client = nemo_client.evaluator
    try:
        run_kwargs: dict[str, Any] = {}
        model = await model_with_valid_secret(
            execution_mode=execution_mode,
            workspace=DEFAULT_WORKSPACE,
            client=nemo_client,
        )
        evaluator = Evaluator(client=AsyncNMPBackend(evaluator_plugin_client, execution_mode=execution_mode))
        params: RunConfig | RunConfigOnlineModel = RunConfig(limit_samples=limit_samples)

        if is_online:
            params = RunConfigOnlineModel(parallelism=4, limit_samples=limit_samples)
            run_kwargs["target"] = model
            run_kwargs["prompt_template"] = ONLINE_CHAT_PROMPT_TEMPLATE

        result = await evaluator.run(
            metrics=create_helpfulness_metric(model),
            dataset=get_helpsteer2_dataset(),
            config=params,
            **run_kwargs,
        )
        result.print_summary()
    finally:
        await nemo_client.close()

    judge_scores, human_scores = extract_helpfulness_scores(
        result.row_scores,
        judge_response_index=1 if is_online else 0,
    )
    print(f"\nEvaluated: {len(judge_scores)} samples")
    if len(judge_scores):
        print(f"judge avg: {judge_scores.mean()}")
        print(f"human avg: {human_scores.mean()}")


async def run_nmp_benchmark_example() -> None:
    """Run one NeMo Platform online benchmark example with multiple metrics locally."""

    _print_example_separator(run_nmp_benchmark_example.__name__)

    from nemo_evaluator.sdk.standalone_sdk.backend import AsyncNMPBackend
    from nemo_platform import AsyncNeMoPlatform

    client = AsyncNeMoPlatform(workspace=DEFAULT_WORKSPACE, timeout=30000.0)
    try:
        evaluator = Evaluator(client=AsyncNMPBackend(client.evaluator))
        exact_match = ExactMatchMetric(reference="{{item.reference}}")
        contains_required_phrase = StringCheckMetric(
            operation="contains",
            left_template="{{sample.output_text}}",
            right_template="{{item.required_phrase}}",
        )

        print("\nRunning local NeMo Platform online benchmark evaluation...")

        benchmark_result = await evaluator.run(
            metrics=[exact_match, contains_required_phrase],
            target=model,
            dataset=ONLINE_BENCHMARK_DATASET,
            prompt_template=ONLINE_CHAT_PROMPT_TEMPLATE,
            config=RunConfigOnlineModel(parallelism=4),
        )
    finally:
        await client.close()
    benchmark_result.print_summary()
    print(f"Online benchmark metric keys: {list(benchmark_result.per_metric)}")
    print(f"Exact match scores: {benchmark_result.metric_result('exact-match').aggregate_scores.scores}")
    print(f"String check scores: {benchmark_result.metric_result('string-check').aggregate_scores.scores}")


async def run_examples() -> None:
    """Execute the example workflows exposed by this module.

    Returns:
        None.
    """
    #### Local backend examples ####
    await run_offline_local_exact_match_example()
    await run_online_local_exact_match_example()
    await run_offline_local_llm_judge_example()
    await run_online_local_llm_judge_example()
    await run_offline_local_benchmark_example()
    await run_online_local_benchmark_example()
    await run_local_benchmark_with_metric_failure_example()
    await run_local_metric_with_template_failure_example()

    ##### NeMo Platform backend examples #####
    ### !!! `uv sync --group enabled-plugins` before `nemo run services` to enable evaluator plugin !!!
    await run_nmp_online_metric_example()
    await run_nmp_llm_judge_example(is_online=True, execution_mode="remote")
    await run_nmp_benchmark_example()


if __name__ == "__main__":
    configure_example_logging()
    asyncio.run(run_examples())
