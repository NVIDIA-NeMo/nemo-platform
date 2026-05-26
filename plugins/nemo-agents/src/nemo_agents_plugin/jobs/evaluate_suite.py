# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""EvaluateSuiteJob — run a directory of containerized eval tasks against an agent.

Registered under ``nemo.jobs`` as ``agents.evaluate-suite``. Invoke as

Two invocation paths share the same ``run(config)`` body:

* ``nemo agents evaluate-suite run --spec '{...}'`` — local, in-process, no
  platform job row (good for offline iteration / no platform required).
* ``nemo agents evaluate-suite submit --spec '{...}'`` — POSTs to the
  platform; the jobs controller dispatches a subprocess on the same host that
  runs the platform (today: the user's laptop) and the result lands in
  ``nemo jobs list`` / Studio's Jobs view.

or, preferred for repeatable runs, with a YAML spec file:

    nemo agents evaluate-suite run --spec-file .agent-improver.yml
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar, Literal

from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EvaluateSuiteConfig(BaseModel):
    evals: str = Field(description="Path to the directory of eval tasks.")
    agent: str | None = Field(default=None, description="Agent root (defaults to repo root).")
    runner: Literal["auto", "harbor", "nat"] = Field(default="auto", description="Eval runner.")
    prefer: Literal["harbor", "nat"] = Field(default="nat", description="Tiebreaker when both markers present.")
    concurrency: int = Field(default=4, ge=1, description="Parallel eval concurrency.")
    skip_build: bool = Field(default=False, description="Skip docker build (Harbor only).")
    output: str | None = Field(default=None, description="Output dir for batch artifacts.")
    filter_glob: str | None = Field(default=None, description="Glob filter on eval names.")
    repeats: int = Field(default=1, ge=1, description="Trials per eval (median aggregation when >1).")


class EvaluateSuiteJob(NemoJob):
    """Run a suite of containerized eval tasks against an agent."""

    name: ClassVar[str] = "evaluate-suite"
    description: ClassVar[str] = "Run a directory of containerized eval tasks (Harbor or NAT) against an agent."
    container: ClassVar[str] = "cpu-tasks"
    spec_schema: ClassVar[type[BaseModel]] = EvaluateSuiteConfig

    @classmethod
    async def compile(  # type: ignore[override]
        cls,
        *,
        workspace: str,
        spec: EvaluateSuiteConfig,
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        """Single-step PlatformJobSpec running ``nemo_agents_plugin.tasks.evaluate_suite``.

        Dispatched by the platform's host-subprocess executor — same machine as the
        platform (and the user's docker daemon).  No dedicated container image.
        """
        from nemo_platform_plugin.jobs.api_factory import (
            PlatformJobStep,
            SubprocessExecutionProviderSpec,
        )

        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="evaluate-suite",
                    executor=SubprocessExecutionProviderSpec(
                        provider="subprocess",
                        command=["python", "-m", "nemo_agents_plugin.tasks.evaluate_suite"],
                    ),
                    config=spec.model_dump(mode="json"),
                ),
            ],
        )

    def run(self, config: dict) -> dict:
        from nemo_agents_plugin.improvement import preflight
        from nemo_agents_plugin.improvement.runners.detect import detect_runner, get_runner

        cfg = EvaluateSuiteConfig.model_validate(config)
        evals_dir = Path(cfg.evals).resolve()
        agent_root = Path(cfg.agent).resolve() if cfg.agent else Path.cwd()
        output = (
            Path(cfg.output).resolve()
            if cfg.output
            else (Path.cwd() / "runs" / f"batch-{datetime.now(timezone.utc).strftime('%Y-%m-%d__%H-%M-%S')}")
        )

        # Preflight: fail fast before any slow work
        preflight.check_evals_dir(evals_dir)
        preflight.check_docker()

        runner = detect_runner(evals_dir, prefer=cfg.prefer) if cfg.runner == "auto" else get_runner(cfg.runner)
        logger.info("Using runner: %s (evals=%s)", runner.name, evals_dir)

        # Per-runner preflights
        if runner.name == "harbor":
            preflight.check_harbor()
            if not cfg.skip_build:
                preflight.check_dockerfile(agent_root)
        elif runner.name == "nat":
            preflight.check_nat_runner(agent_root)

        evals = runner.discover(evals_dir)
        if cfg.filter_glob:
            from fnmatch import fnmatch as _fn

            evals = [e for e in evals if _fn(e.name, cfg.filter_glob)]
        if not evals:
            return {"status": "no-evals-found", "runner": runner.name, "evals_dir": str(evals_dir)}

        batch = asyncio.run(
            runner.run_batch(
                evals=evals,
                batch_dir=output,
                concurrency=cfg.concurrency,
                skip_build=cfg.skip_build,
                project_root=agent_root,
                repeats=cfg.repeats,
            )
        )
        return {
            "status": "completed",
            "runner": runner.name,
            "batch_id": batch.batch_id,
            "batch_dir": str(output),
            "passed": batch.pass_count,
            "failed": batch.fail_count,
            "errors": batch.error_count,
            "total": len(batch.results),
        }
