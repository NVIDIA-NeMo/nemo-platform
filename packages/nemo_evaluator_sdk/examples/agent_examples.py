# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Examples demonstrating standalone agent evaluation workflows."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from nemo_evaluator_sdk.agent_eval import AgentEvalRunConfig, AgentEvaluator, load_profbench
from nemo_evaluator_sdk.values import InferenceParams, Model, RunConfigOnlineModel, SecretRef

DEFAULT_PROFBENCH_SOURCE = "https://huggingface.co/datasets/nvidia/ProfBench/resolve/main/test.jsonl"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "profbench-agent-eval-output"
DEFAULT_MODEL_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL_NAME = "nvidia/nemotron-3-nano-30b-a3b"
DEFAULT_API_KEY_SECRET = os.getenv("NMP_EVALUATOR_DEFAULT_API_KEY_SECRET", "NVIDIA_API_KEY")


def configure_example_logging() -> None:
    """Enable SDK progress logs when this example file is executed directly."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("nemo_evaluator_sdk.inference").setLevel(logging.WARNING)


def _print_example_separator(name: str) -> None:
    """Print a visible section header for an independently runnable example."""
    edge = "====="
    middle_line = f"{edge} {name} {edge}"
    rule = "=" * len(middle_line)
    print(f"\n{rule}\n{middle_line}\n{rule}\n")


def _profbench_source() -> str:
    """Return a local JSONL path or the default Hugging Face raw ProfBench URL."""
    return os.getenv("NEMO_EVALUATOR_PROFBENCH_SOURCE", DEFAULT_PROFBENCH_SOURCE)


def _profbench_limit_from_args(limit: int) -> int | None:
    """Convert a CLI limit value into the optional limit expected by load_profbench."""
    return None if limit == 0 else limit


def _profbench_output_dir(suffix: str) -> Path:
    """Return the output directory for example artifacts."""
    root = Path(os.getenv("NEMO_EVALUATOR_PROFBENCH_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
    return root / suffix


def _example_model() -> Model:
    """Build the model used by the optional live ProfBench example."""
    return Model(
        url=os.getenv("NEMO_EVALUATOR_PROFBENCH_MODEL_URL", DEFAULT_MODEL_URL),
        name=os.getenv("NEMO_EVALUATOR_PROFBENCH_MODEL", DEFAULT_MODEL_NAME),
        api_key_secret=SecretRef(root=DEFAULT_API_KEY_SECRET),
    )


async def run_profbench_baseline_example(*, limit: int | None) -> None:
    """Score the ProfBench baseline model responses bundled in the dataset.

    This path does not need a judge model: ProfBench includes per-rubric
    fulfilment labels for the baseline responses.
    """

    _print_example_separator(run_profbench_baseline_example.__name__)

    benchmark = load_profbench(_profbench_source(), limit=limit)
    result = await AgentEvaluator().run(
        tasks=benchmark.tasks,
        attempts=benchmark.attempts,
        config=AgentEvalRunConfig(
            output_dir=_profbench_output_dir("baseline"),
            benchmark=benchmark.metadata,
        ),
    )

    print(f"ProfBench tasks: {result.summary.task_count}")
    print(f"ProfBench attempts: {result.summary.attempt_count}")
    print(f"Overall score: {result.summary.overall_score:.3f}" if result.summary.overall_score is not None else "n/a")
    print(f"Model scores: {result.summary.model_scores}")
    print(f"Domain scores: {result.summary.domain_scores}")
    print(f"Dashboard: {result.dashboard_path}")


async def run_profbench_live_model_example(*, limit: int | None) -> None:
    """Generate fresh ProfBench responses from a model and score them with a judge.

    Pass ``--run-live`` when executing this module to run this example. The same
    model is used as generator and judge by default; override the endpoint/name
    with ``NEMO_EVALUATOR_PROFBENCH_MODEL_URL`` and
    ``NEMO_EVALUATOR_PROFBENCH_MODEL``.
    """

    _print_example_separator(run_profbench_live_model_example.__name__)

    benchmark = load_profbench(_profbench_source(), limit=limit)
    model = _example_model()

    result = await AgentEvaluator().run(
        tasks=benchmark.tasks,
        target=model,
        config=AgentEvalRunConfig(
            output_dir=_profbench_output_dir("live-model"),
            params=RunConfigOnlineModel(
                parallelism=2,
                inference=InferenceParams(temperature=0.0, max_tokens=4096),
            ),
            judge=model,
            benchmark=benchmark.metadata,
        ),
    )

    print(f"ProfBench tasks: {result.summary.task_count}")
    print(f"Live model score: {result.summary.model_scores}")
    print(f"Dashboard: {result.dashboard_path}")


async def run_examples(*, limit: int | None, run_live: bool) -> None:
    """Execute the agent-eval examples exposed by this module."""
    await run_profbench_baseline_example(limit=limit)

    if run_live:
        await run_profbench_live_model_example(limit=limit)
    else:
        print("Skipping live ProfBench model example. Pass --run-live to run it.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ProfBench agent-eval examples.")
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum number of ProfBench tasks to evaluate (0 = no limit). Default: 1.",
    )
    parser.add_argument(
        "--run-live",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run the live ProfBench model example after the baseline example.",
    )
    args = parser.parse_args()

    configure_example_logging()
    asyncio.run(
        run_examples(
            limit=_profbench_limit_from_args(args.limit),
            run_live=args.run_live,
        )
    )
