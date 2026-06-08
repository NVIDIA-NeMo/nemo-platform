#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run one agentic-use task through AgentEvaluator + a backend runtime."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

AGENTIC_USE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENTIC_USE_DIR))
sys.path.insert(0, str(AGENTIC_USE_DIR / "shared"))

from runtimes import AgenticEvalOrchestrator, AgenticOrchestratorConfig, runtime_for_backend
from runtimes.shared.config import AgenticSharedConfig


async def _main() -> int:
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
    parser.add_argument("--aut-agent-name", default=os.environ.get("AUT_AGENT_NAME", ""))
    parser.add_argument("--aut-agent-config", type=Path, default=None)
    args = parser.parse_args()

    shared = AgenticSharedConfig(
        nmp_base_url=args.nmp_base_url,
        nvidia_api_key=os.environ.get("NVIDIA_API_KEY"),
    )
    backend_kwargs: dict[str, object] = {"agent_model": args.agent_model}
    if args.backend == "aut":
        backend_kwargs["aut_agent_name"] = args.aut_agent_name
        backend_kwargs["aut_agent_config"] = args.aut_agent_config

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
        print(f"agent_ok: {attempt.metadata.get('agent_ok')}")
        print(f"run_dir: {attempt.metadata.get('run_dir')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
