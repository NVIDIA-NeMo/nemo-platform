# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Command-line runner for the ProfBench agent-eval example."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    raise SystemExit(
        "Run ProfBench as a module from the repository root:\n"
        "  python -m packages.nemo_evaluator_sdk.examples.profbench.runner"
    )

from nemo_evaluator_sdk.agent_eval import AgentEvalRunConfig, AgentEvaluator
from nemo_evaluator_sdk.values import InferenceParams, Model, RunConfigOnlineModel, SecretRef

from .dashboard import write_example_dashboards
from .profbench import PROFBENCH_DATASET_URL, ProfBenchModelJudge, load_profbench

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "profbench-agent-eval-output"
DEFAULT_EVALUATED_MODEL_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_EVALUATED_MODEL_NAME = "nvidia/nemotron-3-nano-30b-a3b"
DEFAULT_JUDGE_MODEL_URL = DEFAULT_EVALUATED_MODEL_URL
DEFAULT_JUDGE_MODEL_NAME = DEFAULT_EVALUATED_MODEL_NAME
DEFAULT_API_KEY_SECRET = os.getenv("NMP_EVALUATOR_DEFAULT_API_KEY_SECRET", "NVIDIA_API_KEY")


def configure_example_logging() -> None:
    """Enable SDK progress logs when this example file is executed directly."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("nemo_evaluator_sdk.inference").setLevel(logging.WARNING)


async def run_profbench_baseline_example(
    *,
    limit: int | None,
    output_root: str | Path | None = None,
    run_instance_id: str | None = None,
) -> None:
    """Score the ProfBench baseline model responses bundled in the dataset."""
    _print_example_separator(run_profbench_baseline_example.__name__)

    output_root = _resolve_profbench_output_root(output_root)
    run_instance_id = run_instance_id or _new_profbench_run_instance_id()
    output_dir = _profbench_output_dir(output_root, run_instance_id, "baseline")
    benchmark = load_profbench(_profbench_source(), limit=limit, evidence_dir=output_dir / "evidence")
    result = await AgentEvaluator().run(
        tasks=benchmark.tasks,
        attempts=benchmark.attempts,
        config=AgentEvalRunConfig(
            output_dir=output_dir,
            run_id=f"{run_instance_id}-baseline",
            benchmark=benchmark.metadata,
            write_dashboard=False,
        ),
    )
    sdk_dashboard_path, dashboard_path = write_example_dashboards(result, output_dir)

    print(f"ProfBench tasks: {result.summary.task_count}")
    print(f"ProfBench attempts: {result.summary.attempt_count}")
    print(f"Overall score: {result.summary.overall_score:.3f}" if result.summary.overall_score is not None else "n/a")
    print(f"Metric scores: {result.summary.metric_scores}")
    print(f"SDK dashboard: {sdk_dashboard_path}")
    print(f"Dashboard: {dashboard_path}")


async def run_profbench_live_judge_example(
    *,
    limit: int | None,
    output_root: str | Path | None = None,
    run_instance_id: str | None = None,
) -> None:
    """Score the recorded ProfBench responses with a live LLM judge."""
    _print_example_separator(run_profbench_live_judge_example.__name__)

    judge_model = _judge_model()
    output_root = _resolve_profbench_output_root(output_root)
    run_instance_id = run_instance_id or _new_profbench_run_instance_id()
    output_dir = _profbench_output_dir(output_root, run_instance_id, "live-judge")
    benchmark = load_profbench(
        _profbench_source(),
        limit=limit,
        judge=ProfBenchModelJudge(model=judge_model),
        evidence_dir=output_dir / "evidence",
        include_cached_fulfilments=False,
    )

    result = await AgentEvaluator().run(
        tasks=benchmark.tasks,
        attempts=benchmark.attempts,
        config=AgentEvalRunConfig(
            output_dir=output_dir,
            run_id=f"{run_instance_id}-live-judge",
            benchmark={**benchmark.metadata, "score_source": "live_judge"},
            write_dashboard=False,
        ),
    )
    sdk_dashboard_path, dashboard_path = write_example_dashboards(result, output_dir)

    print(f"ProfBench tasks: {result.summary.task_count}")
    print(f"Recorded attempts judged: {result.summary.attempt_count}")
    print(f"Live judge score: {result.summary.metric_scores}")
    print(f"SDK dashboard: {sdk_dashboard_path}")
    print(f"Dashboard: {dashboard_path}")


async def run_profbench_live_candidate_example(
    *,
    limit: int | None,
    output_root: str | Path | None = None,
    run_instance_id: str | None = None,
) -> None:
    """Generate fresh ProfBench responses from a model and score them with a judge."""
    _print_example_separator(run_profbench_live_candidate_example.__name__)

    evaluated_model = _evaluated_model()
    judge_model = _judge_model()
    output_root = _resolve_profbench_output_root(output_root)
    run_instance_id = run_instance_id or _new_profbench_run_instance_id()
    output_dir = _profbench_output_dir(output_root, run_instance_id, "live-candidate")
    params = RunConfigOnlineModel(
        parallelism=2,
        inference=InferenceParams(temperature=0.0, max_tokens=4096),
    )
    benchmark = load_profbench(
        _profbench_source(),
        limit=limit,
        judge=ProfBenchModelJudge(model=judge_model),
        evidence_dir=output_dir / "evidence",
        include_cached_fulfilments=False,
    )

    result = await AgentEvaluator().run(
        tasks=benchmark.tasks,
        target=evaluated_model,
        config=AgentEvalRunConfig(
            output_dir=output_dir,
            run_id=f"{run_instance_id}-live-candidate",
            params=params,
            benchmark={**benchmark.metadata, "score_source": "fresh_candidate_and_live_judge"},
            write_dashboard=False,
        ),
    )
    sdk_dashboard_path, dashboard_path = write_example_dashboards(result, output_dir)

    print(f"ProfBench tasks: {result.summary.task_count}")
    print(f"Live model score: {result.summary.metric_scores}")
    print(f"SDK dashboard: {sdk_dashboard_path}")
    print(f"Dashboard: {dashboard_path}")


async def run_examples(
    *,
    limit: int | None,
    run_live_judge: bool,
    run_live_candidate: bool,
    output_root: str | Path | None = None,
    run_instance_id: str | None = None,
) -> None:
    """Execute the ProfBench agent-eval examples."""
    output_root = _resolve_profbench_output_root(output_root)
    run_instance_id = run_instance_id or _new_profbench_run_instance_id()
    run_output_dir = Path(output_root) / run_instance_id
    run_output_dir.mkdir(parents=True, exist_ok=True)

    print(f"ProfBench output root: {output_root}")
    print(f"ProfBench run instance: {run_instance_id}")

    await run_profbench_baseline_example(
        limit=limit,
        output_root=output_root,
        run_instance_id=run_instance_id,
    )

    if run_live_judge:
        await run_profbench_live_judge_example(
            limit=limit,
            output_root=output_root,
            run_instance_id=run_instance_id,
        )
    else:
        print("Skipping live ProfBench judge example. Pass --run-live-judge to run it.")

    if run_live_candidate:
        await run_profbench_live_candidate_example(
            limit=limit,
            output_root=output_root,
            run_instance_id=run_instance_id,
        )
    else:
        print("Skipping live ProfBench candidate example. Pass --run-live-candidate to run it.")


def _profbench_source() -> str:
    return os.getenv("NEMO_EVALUATOR_PROFBENCH_SOURCE", PROFBENCH_DATASET_URL)


def _profbench_limit_from_args(limit: int) -> int | None:
    return None if limit == 0 else limit


def _resolve_profbench_output_root(output_dir: str | Path | None = None) -> Path:
    if output_dir is not None:
        return Path(output_dir).expanduser()
    env_output_dir = os.getenv("NEMO_EVALUATOR_PROFBENCH_OUTPUT_DIR")
    if env_output_dir:
        return Path(env_output_dir).expanduser()
    return DEFAULT_OUTPUT_DIR


def _new_profbench_run_instance_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-1]
    return f"{timestamp}_{uuid.uuid4().hex[:6]}"


def _profbench_output_dir(output_root: str | Path, run_instance_id: str, mode: str) -> Path:
    return Path(output_root).expanduser() / run_instance_id / mode


def _evaluated_model() -> Model:
    return Model(
        url=_model_env(
            "NEMO_EVALUATOR_PROFBENCH_EVALUATED_MODEL_URL",
            DEFAULT_EVALUATED_MODEL_URL,
            legacy_key="NEMO_EVALUATOR_PROFBENCH_MODEL_URL",
        ),
        name=_model_env(
            "NEMO_EVALUATOR_PROFBENCH_EVALUATED_MODEL",
            DEFAULT_EVALUATED_MODEL_NAME,
            legacy_key="NEMO_EVALUATOR_PROFBENCH_MODEL",
        ),
        api_key_secret=SecretRef(root=DEFAULT_API_KEY_SECRET),
    )


def _judge_model() -> Model:
    return Model(
        url=_model_env(
            "NEMO_EVALUATOR_PROFBENCH_JUDGE_MODEL_URL",
            DEFAULT_JUDGE_MODEL_URL,
            legacy_key="NEMO_EVALUATOR_PROFBENCH_MODEL_URL",
        ),
        name=_model_env(
            "NEMO_EVALUATOR_PROFBENCH_JUDGE_MODEL",
            DEFAULT_JUDGE_MODEL_NAME,
            legacy_key="NEMO_EVALUATOR_PROFBENCH_MODEL",
        ),
        api_key_secret=SecretRef(root=DEFAULT_API_KEY_SECRET),
    )


def _model_env(key: str, default: str, *, legacy_key: str) -> str:
    return os.getenv(key) or os.getenv(legacy_key) or default


def _print_example_separator(name: str) -> None:
    edge = "====="
    middle_line = f"{edge} {name} {edge}"
    rule = "=" * len(middle_line)
    print(f"\n{rule}\n{middle_line}\n{rule}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ProfBench agent-eval examples.")
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum number of ProfBench tasks to evaluate (0 = no limit). Default: 1.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Root directory for ProfBench outputs. "
            "Defaults to NEMO_EVALUATOR_PROFBENCH_OUTPUT_DIR or the example output directory."
        ),
    )
    parser.add_argument(
        "--run-live-judge",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Score the recorded ProfBench responses with a live LLM judge after the baseline example.",
    )
    parser.add_argument(
        "--run-live-candidate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate fresh candidate responses from the configured model, then score them with a live LLM judge.",
    )
    args = parser.parse_args()
    configure_example_logging()

    asyncio.run(
        run_examples(
            limit=_profbench_limit_from_args(args.limit),
            run_live_judge=bool(args.run_live_judge),
            run_live_candidate=bool(args.run_live_candidate),
            output_root=args.output_dir,
        )
    )
