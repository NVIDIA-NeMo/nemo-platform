# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OptimizeSkillsJob — the optimize-skills loop.

Registered under ``nemo.jobs`` as ``agents.optimize-skills``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import ClassVar, Literal

from nemo_platform_plugin.job import NemoJob
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class OptimizeSkillsConfig(BaseModel):
    evals: str = Field(description="Path to the directory of eval tasks.")
    agent: str = Field(description="Agent root (where the loop runs from; skills live under it).")
    skills_path: str = Field(default=".agents/skills", description="Relative path inside agent where skills live.")
    filter_glob: str | None = Field(default=None, description="Glob filter on eval names (e.g. 'files-*').")
    iterations: int = Field(default=3, ge=1)
    concurrency: int = Field(default=2, ge=1)
    state: str | None = Field(default=None, description="Path to loop_state.json; default: <agent>/loop_state.json.")
    initial_batch: str | None = Field(default=None, description="Existing batch dir to seed from.")
    full_verification: bool = Field(default=False)
    open_pr: bool = Field(default=False)
    repeats: int = Field(default=1, ge=1)
    analyze_only: bool = Field(
        default=False,
        description=(
            "Analyze-only mode: consume an existing --initial-batch, generate suggestions, exit. "
            "Skips worktree, apply, verify, MR. Works with any AUT (Harbor or NAT)."
        ),
    )
    trace_parser: Literal["claude-code"] = Field(
        default="claude-code",
        description=(
            "Trace parser for the agent's traces. Today only 'claude-code' is registered "
            "(parses Claude Code session.jsonl). Future parsers — e.g. for NAT IntermediateStep "
            "records — extend this Literal."
        ),
    )


class OptimizeSkillsJob(NemoJob):
    """Run the optimize-skills loop end-to-end."""

    name: ClassVar[str] = "optimize-skills"
    description: ClassVar[str] = "Optimize an agent's skills against eval failures via a coding agent (Claude)."
    container: ClassVar[str] = "cpu-tasks"

    def run(self, config: dict) -> dict:
        from nemo_agents_plugin.improvement import preflight
        from nemo_agents_plugin.improvement.coding_agents.claude import ClaudeCodingAgent
        from nemo_agents_plugin.improvement.loop import run_analyze_only, run_loop
        from nemo_agents_plugin.improvement.models import _serialize

        cfg = OptimizeSkillsConfig.model_validate(config)
        agent_root = Path(cfg.agent).resolve()
        evals_dir = Path(cfg.evals).resolve()
        state_path = Path(cfg.state).resolve() if cfg.state else agent_root / "loop_state.json"
        initial = Path(cfg.initial_batch).resolve() if cfg.initial_batch else None

        if cfg.analyze_only:
            if initial is None:
                raise ValueError("analyze_only=True requires initial_batch to point at an existing batch directory.")
            # Skip Docker/Harbor/Claude/forge preflight — those gate apply, not analysis.
            preflight.check_evals_dir(evals_dir)
            preflight.check_anthropic_api()
            state = asyncio.run(
                run_analyze_only(
                    evals_dir=evals_dir,
                    initial_batch_dir=initial,
                    skills_path=cfg.skills_path,
                    trace_parser=cfg.trace_parser,
                )
            )
            return _serialize(state)  # type: ignore[return-value]

        # Preflight: fail fast before any slow work
        preflight.check_evals_dir(evals_dir)
        preflight.check_evals_inside_agent(agent_root, evals_dir)
        preflight.check_skills_path(agent_root, cfg.skills_path)
        preflight.check_docker()
        preflight.check_harbor()  # both runners need it for image inheritance
        # The loop accepts a Runner but rejects anything but harbor up-front
        # (see run_loop's runner-kind guard). It always invokes harbor with
        # skip_build=False, so the Dockerfile is always needed.
        preflight.check_dockerfile(agent_root)
        # Coding agent preflight (Claude CLI / OAuth for the apply step)
        ClaudeCodingAgent().preflight()
        # LLM analyzer preflight (Anthropic API for the gap-analysis step)
        preflight.check_anthropic_api()

        # MR/PR forge preflight — fail fast before slow eval work if the
        # branch won't be routable to a PR/MR at the end of the loop.
        if cfg.open_pr:
            preflight.check_forge_tooling()

        state = asyncio.run(
            run_loop(
                agent_root=agent_root,
                evals_dir=evals_dir,
                skills_path=cfg.skills_path,
                filter_glob=cfg.filter_glob,
                max_iterations=cfg.iterations,
                concurrency=cfg.concurrency,
                state_path=state_path,
                initial_batch_dir=initial,
                full_verification=cfg.full_verification,
                open_pr=cfg.open_pr,
                repeats=cfg.repeats,
                trace_parser=cfg.trace_parser,
            )
        )
        return _serialize(state)  # type: ignore[return-value]
