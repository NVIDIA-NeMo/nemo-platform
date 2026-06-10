#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run one agentic-use task through AgentEvaluator + a backend runtime."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

AGENTIC_USE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENTIC_USE_DIR))
sys.path.insert(0, str(AGENTIC_USE_DIR / "shared"))

from nemo_evaluator_sdk.agent_eval import AgentEvalTarget, benchmark_report_paths  # noqa: E402
from nemo_evaluator_sdk.values import InferenceParams, Model, RunConfigOnlineModel, SecretRef  # noqa: E402

from runtimes import AgenticEvalOrchestrator, AgenticOrchestratorConfig, runtime_for_backend  # noqa: E402
from runtimes.profbench import (  # noqa: E402
    DEFAULT_JUDGE_API_KEY_ENV,
    DEFAULT_JUDGE_MODEL_NAME,
    DEFAULT_JUDGE_MODEL_URL,
    PROFBENCH_TASK_NAME,
    ProfBenchRuntimeConfig,
    run_profbench_agent_eval,
)
from runtimes.shared.config import AgenticSharedConfig  # noqa: E402

DEFAULT_PROFBENCH_CANDIDATE_MAX_TOKENS = 2048


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run agentic-use task via AgentAttemptRuntime.")
    parser.add_argument("--task", required=True, help="Task directory name under tests/agentic-use/")
    parser.add_argument(
        "--backend",
        default="workflow",
        choices=["workflow", "aut", "claude-code", "codex", "cursor-agent"],
    )
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--nmp-base-url", default=os.environ.get("NMP_BASE_URL", "http://localhost:8080"))
    parser.add_argument("--agent-model", default=os.environ.get("NAT_AGENT_MODEL"))
    parser.add_argument("--model", dest="agent_model", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    parser.add_argument("--aut-agent-name", default=os.environ.get("AUT_AGENT_NAME", ""))
    parser.add_argument("--aut-agent-config", type=Path, default=None)
    parser.add_argument("--codex-auth-json", type=Path, default=None)
    parser.add_argument("--allow-dirty", action="store_true", help="Accepted for parity with nat_runner.py.")
    parser.add_argument(
        "--rescore-dir",
        type=Path,
        action="append",
        default=None,
        help="Score existing result.json run dir(s) offline instead of running the agent (repeatable).",
    )
    parser.add_argument("--source", default=None, help="ProfBench JSONL path or URL; only used with --task profbench.")
    parser.add_argument(
        "--limit",
        type=_limit_from_arg,
        default=1,
        help="ProfBench task limit; use 0 for no limit. Only used with --task profbench.",
    )
    parser.add_argument("--judge-model-url", default=DEFAULT_JUDGE_MODEL_URL)
    parser.add_argument("--judge-model-name", default=DEFAULT_JUDGE_MODEL_NAME)
    parser.add_argument("--judge-api-key-env", default=DEFAULT_JUDGE_API_KEY_ENV)
    return parser.parse_args(argv)


def _limit_from_arg(value: str) -> int | None:
    limit = int(value)
    if limit < 0:
        raise argparse.ArgumentTypeError("limit must be non-negative")
    return None if limit == 0 else limit


async def _main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    shared = AgenticSharedConfig(
        nmp_base_url=args.nmp_base_url,
        nvidia_api_key=os.environ.get("NVIDIA_API_KEY"),
    )
    backend_kwargs: dict[str, object] = {"agent_model": args.agent_model}
    if args.backend == "aut":
        backend_kwargs["aut_agent_name"] = args.aut_agent_name
        backend_kwargs["aut_agent_config"] = args.aut_agent_config
    if args.backend == "codex":
        backend_kwargs["codex_auth_json"] = args.codex_auth_json

    reports = None
    if args.task == PROFBENCH_TASK_NAME:
        if args.rescore_dir:
            raise ValueError("--rescore-dir is not supported with --task profbench")
        target, params = _profbench_target(args, shared, backend_kwargs)
        result, reports = await run_profbench_agent_eval(
            target=target,
            output_dir=args.output_dir,
            config=ProfBenchRuntimeConfig(
                source=args.source,
                limit=args.limit,
                judge_model_url=args.judge_model_url,
                judge_model_name=args.judge_model_name,
                judge_api_key_env=args.judge_api_key_env,
                skip_build=args.skip_build,
            ),
            params=params,
        )
    elif args.rescore_dir:
        runtime = runtime_for_backend(args.backend, shared_kwargs=shared.__dict__, backend_kwargs=backend_kwargs)
        orchestrator = AgenticEvalOrchestrator(
            runtime,
            config=AgenticOrchestratorConfig(skip_build=args.skip_build),
        )
        result = await orchestrator.score_captured_attempts(
            args.task,
            result_dirs=args.rescore_dir,
            output_dir=args.output_dir,
        )
    else:
        runtime = runtime_for_backend(args.backend, shared_kwargs=shared.__dict__, backend_kwargs=backend_kwargs)
        orchestrator = AgenticEvalOrchestrator(
            runtime,
            config=AgenticOrchestratorConfig(skip_build=args.skip_build),
        )
        result = await orchestrator.run_agent_eval(args.task, output_dir=args.output_dir)

    print(f"run_id: {result.run_id}")
    print(f"attempts: {len(result.attempts)}")
    print(f"overall_score: {result.summary.overall_score}")
    print(f"metric_scores: {result.summary.metric_scores}")
    if result.attempts:
        attempt = result.attempts[0]
        if "agent_ok" in attempt.metadata:
            print(f"agent_ok: {attempt.metadata['agent_ok']}")
        if "run_dir" in attempt.metadata:
            print(f"run_dir: {attempt.metadata['run_dir']}")
    if reports is not None:
        sdk_dashboard_path, dashboard_path = benchmark_report_paths(reports)
        print(f"SDK dashboard: {sdk_dashboard_path}")
        print(f"Dashboard: {dashboard_path}")
    return 0


def _profbench_target(
    args: argparse.Namespace,
    shared: AgenticSharedConfig,
    backend_kwargs: dict[str, object],
) -> tuple[AgentEvalTarget, RunConfigOnlineModel | None]:
    if args.backend != "workflow":
        return runtime_for_backend(args.backend, shared_kwargs=shared.__dict__, backend_kwargs=backend_kwargs), None

    return (
        Model(
            url=DEFAULT_JUDGE_MODEL_URL,
            name=args.agent_model or DEFAULT_JUDGE_MODEL_NAME,
            api_key_secret=SecretRef(root=args.judge_api_key_env),
        ),
        RunConfigOnlineModel(
            inference=InferenceParams(max_tokens=DEFAULT_PROFBENCH_CANDIDATE_MAX_TOKENS),
        ),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    raise SystemExit(asyncio.run(_main()))
