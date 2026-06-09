# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Runnable ProfBench adapter examples.

Run from the repository root with:
    uv run --frozen python -m packages.nemo_evaluator_sdk.examples.profbench.examples offline
"""

from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from nemo_evaluator_sdk.agent_eval import (
    AgentEvalBenchmarkEvaluationKind,
    AgentEvalBenchmarkLoadConfig,
    AgentEvalBenchmarkReports,
    AgentEvalRunResult,
    benchmark_report_paths,
    benchmark_report_writer,
    run_benchmark_bundle,
)
from nemo_evaluator_sdk.agent_eval.runtimes.codex.runtime import RuntimeChoice, resolve_codex_target
from nemo_evaluator_sdk.values import Model, SecretRef

from .profbench import ProfBenchAgentEvalBenchmark, ProfBenchModelJudge

DEFAULT_OUTPUT_ROOT = Path("env/profbench-results")
DEFAULT_JUDGE_MODEL_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_JUDGE_MODEL_NAME = "nvidia/nemotron-3-nano-30b-a3b"
DEFAULT_JUDGE_API_KEY_ENV = "NVIDIA_API_KEY"
DEFAULT_DOCKER_SANDBOX_MODEL = "gpt-5.4"


async def run_offline_profbench_adapter_smoke(
    *,
    output_dir: str | Path | None = None,
    run_id: str | None = None,
    source: str | Path | None = None,
    limit: int | None = 1,
) -> tuple[AgentEvalRunResult, AgentEvalBenchmarkReports]:
    """Score ProfBench's bundled recorded attempts without live model credentials."""
    output_dir, resolved_run_id = _resolve_example_run(output_dir, run_id)
    benchmark = ProfBenchAgentEvalBenchmark()
    bundle = benchmark.load(
        AgentEvalBenchmarkLoadConfig(
            evaluation_kind=AgentEvalBenchmarkEvaluationKind.STORED_ATTEMPTS,
            source=source,
            limit=limit,
            evidence_dir=output_dir / "evidence",
        )
    )
    result, reports = await run_benchmark_bundle(
        bundle=bundle,
        output_dir=output_dir,
        run_id=resolved_run_id,
        report_writer=benchmark_report_writer(benchmark),
    )
    _print_example_summary("Offline ProfBench adapter smoke", result, reports)
    return result, reports


async def run_docker_sandbox_profbench_live_candidate_smoke(
    *,
    output_dir: str | Path | None = None,
    run_id: str | None = None,
    source: str | Path | None = None,
    limit: int | None = 1,
    agent_model: str | None = None,
    judge_model_url: str = DEFAULT_JUDGE_MODEL_URL,
    judge_model_name: str = DEFAULT_JUDGE_MODEL_NAME,
    judge_api_key_env: str = DEFAULT_JUDGE_API_KEY_ENV,
) -> tuple[AgentEvalRunResult, AgentEvalBenchmarkReports]:
    """Generate ProfBench attempts through a Docker-backed Codex runtime and score them with a live judge."""
    output_dir, resolved_run_id = _resolve_example_run(output_dir, run_id)
    target, score_source, effective_runtime = resolve_codex_target(
        runtime=RuntimeChoice.DOCKER,
        model=agent_model or DEFAULT_DOCKER_SANDBOX_MODEL,
        output_dir=output_dir,
    )
    print(f"Codex runtime: {effective_runtime}")

    benchmark = _live_judge_benchmark(
        score_source=score_source,
        judge_model_url=judge_model_url,
        judge_model_name=judge_model_name,
        judge_api_key_env=judge_api_key_env,
    )
    bundle = benchmark.load(
        AgentEvalBenchmarkLoadConfig(
            evaluation_kind=AgentEvalBenchmarkEvaluationKind.LIVE_TARGET,
            source=source,
            limit=limit,
            evidence_dir=output_dir / "evidence",
        )
    )
    result, reports = await run_benchmark_bundle(
        bundle=bundle,
        output_dir=output_dir,
        run_id=resolved_run_id,
        target=target,
        report_writer=benchmark_report_writer(benchmark),
    )
    _print_example_summary("Docker sandbox ProfBench live candidate smoke", result, reports)
    return result, reports


async def run_local_codex_profbench_live_candidate_smoke(
    *,
    output_dir: str | Path | None = None,
    run_id: str | None = None,
    source: str | Path | None = None,
    limit: int | None = 1,
    agent_model: str | None = None,
    judge_model_url: str = DEFAULT_JUDGE_MODEL_URL,
    judge_model_name: str = DEFAULT_JUDGE_MODEL_NAME,
    judge_api_key_env: str = DEFAULT_JUDGE_API_KEY_ENV,
) -> tuple[AgentEvalRunResult, AgentEvalBenchmarkReports]:
    """Generate ProfBench attempts through host `codex exec` local runtime and score them with a live judge."""
    output_dir, resolved_run_id = _resolve_example_run(output_dir, run_id)
    target, score_source, effective_runtime = resolve_codex_target(
        runtime=RuntimeChoice.LOCAL,
        model=agent_model,
        output_dir=output_dir,
    )
    print(f"Codex runtime: {effective_runtime}")

    benchmark = _live_judge_benchmark(
        score_source=score_source,
        judge_model_url=judge_model_url,
        judge_model_name=judge_model_name,
        judge_api_key_env=judge_api_key_env,
    )
    bundle = benchmark.load(
        AgentEvalBenchmarkLoadConfig(
            evaluation_kind=AgentEvalBenchmarkEvaluationKind.LIVE_TARGET,
            source=source,
            limit=limit,
            evidence_dir=output_dir / "evidence",
        )
    )
    result, reports = await run_benchmark_bundle(
        bundle=bundle,
        output_dir=output_dir,
        run_id=resolved_run_id,
        target=target,
        report_writer=benchmark_report_writer(benchmark),
    )
    _print_example_summary("Local Codex ProfBench live candidate smoke", result, reports)
    return result, reports


def main(argv: Sequence[str] | None = None) -> None:
    """Run one ProfBench example from the command line."""
    args = _parse_args(argv)
    asyncio.run(_run_selected_example(args))


async def _run_selected_example(args: argparse.Namespace) -> None:
    if args.example == "offline":
        await run_offline_profbench_adapter_smoke(
            output_dir=args.output_dir,
            run_id=args.run_id,
            source=args.source,
            limit=args.limit,
        )
    elif args.example == "docker":
        await run_docker_sandbox_profbench_live_candidate_smoke(
            output_dir=args.output_dir,
            run_id=args.run_id,
            source=args.source,
            limit=args.limit,
            agent_model=args.agent_model,
            judge_model_url=args.judge_model_url,
            judge_model_name=args.judge_model_name,
            judge_api_key_env=args.judge_api_key_env,
        )
    elif args.example == "local":
        await run_local_codex_profbench_live_candidate_smoke(
            output_dir=args.output_dir,
            run_id=args.run_id,
            source=args.source,
            limit=args.limit,
            agent_model=args.agent_model,
            judge_model_url=args.judge_model_url,
            judge_model_name=args.judge_model_name,
            judge_api_key_env=args.judge_api_key_env,
        )
    else:
        raise ValueError(f"unsupported ProfBench example {args.example!r}")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ProfBench agent-eval examples.")
    parser.add_argument("example", choices=["offline", "docker", "local"])
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--source", default=None, help="ProfBench JSONL path or URL.")
    parser.add_argument("--limit", type=_limit_from_arg, default=1, help="Task limit. Use 0 for no limit.")
    parser.add_argument("--agent-model", default=None, help="Evaluated agent model for live ProfBench examples.")
    parser.add_argument("--judge-model-url", default=DEFAULT_JUDGE_MODEL_URL)
    parser.add_argument("--judge-model-name", default=DEFAULT_JUDGE_MODEL_NAME)
    parser.add_argument("--judge-api-key-env", default=DEFAULT_JUDGE_API_KEY_ENV)
    return parser.parse_args(argv)


def _limit_from_arg(value: str) -> int | None:
    limit = int(value)
    return None if limit == 0 else limit


def _resolve_example_run(output_root: str | Path | None, run_id: str | None) -> tuple[Path, str]:
    run_instance_id = _new_profbench_run_instance_id()
    return _example_output_dir(output_root, run_instance_id), run_id or run_instance_id


def _example_output_dir(output_root: str | Path | None, run_instance_id: str) -> Path:
    root = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    return root / run_instance_id


def _new_profbench_run_instance_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pid = os.getpid() % 100000
    return f"{timestamp}_{pid:05d}_{uuid.uuid4().hex[:6]}"


def _live_judge_benchmark(
    *,
    score_source: str,
    judge_model_url: str,
    judge_model_name: str,
    judge_api_key_env: str,
) -> ProfBenchAgentEvalBenchmark:
    judge_model = Model(
        url=judge_model_url,
        name=judge_model_name,
        api_key_secret=SecretRef(root=judge_api_key_env),
    )
    return ProfBenchAgentEvalBenchmark(
        judge_factory=lambda: ProfBenchModelJudge(model=judge_model),
        score_source=score_source,
    )


def _print_example_summary(
    label: str,
    result: AgentEvalRunResult,
    reports: AgentEvalBenchmarkReports,
) -> None:
    sdk_dashboard_path, dashboard_path = benchmark_report_paths(reports)
    print(label)
    print(f"tasks: {result.summary.task_count}")
    print(f"attempts: {result.summary.attempt_count}")
    print(f"overall_score: {result.summary.overall_score}")
    print(f"metric_scores: {result.summary.metric_scores}")
    print(f"SDK dashboard: {sdk_dashboard_path}")
    print(f"Dashboard: {dashboard_path}")


if __name__ == "__main__":
    main()
