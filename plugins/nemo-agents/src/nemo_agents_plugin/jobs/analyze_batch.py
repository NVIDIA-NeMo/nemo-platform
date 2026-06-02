# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""AnalyzeBatchJob — analyze a batch of eval-suite results.

Registered under ``nemo.jobs`` as ``agents.analyze``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import ClassVar, Literal

from nemo_platform_plugin.job import NemoJob
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AnalyzeBatchConfig(BaseModel):
    batch: str = Field(description="Path to a batch directory produced by evaluate-suite.")
    format: Literal["md", "json"] = Field(default="md", description="Output format: md or json.")
    mechanical_only: bool = Field(default=False, description="Skip the LLM analysis pass.")


class AnalyzeBatchJob(NemoJob):
    """Analyze a batch of eval-suite results — mechanical clustering + LLM hypotheses."""

    name: ClassVar[str] = "analyze"
    description: ClassVar[str] = "Analyze a batch of eval-suite results (clusters, regressions, hypotheses)."
    container: ClassVar[str] = "cpu-tasks"

    def run(self, config: dict) -> dict:
        from nemo_agents_plugin.improvement.analysis.llm import generate_gap_analysis
        from nemo_agents_plugin.improvement.analysis.mechanical import cluster_evals, mechanical_analysis
        from nemo_agents_plugin.improvement.baselines import load_baselines
        from nemo_agents_plugin.improvement.models import GapAnalysis, _serialize
        from nemo_agents_plugin.improvement.runners._harbor_results import parse_batch_results
        from nemo_agents_plugin.improvement.traces.base import TraceParser
        from nemo_agents_plugin.improvement.traces.claude_code_parser import ClaudeCodeTraceParser

        cfg = AnalyzeBatchConfig.model_validate(config)
        batch_dir = Path(cfg.batch).resolve()
        if not batch_dir.is_dir():
            raise RuntimeError(f"Batch directory not found: {batch_dir}")

        batch = parse_batch_results(batch_dir)
        baselines_path = batch_dir.parent.parent / "baselines.json"
        baselines = load_baselines(baselines_path) if baselines_path.exists() else {}

        # Pick the trace parser at the call site. Today the only
        # implementation is ClaudeCodeTraceParser (session.jsonl); when
        # other parsers exist (e.g. for NAT IntermediateStep records) this
        # becomes a config-driven choice. Batches whose traces aren't
        # claude-code-shaped run mechanical-only — the runner-agnostic
        # signals (failing/slowest/regressions/baselines) still populate.
        parser: TraceParser | None = ClaudeCodeTraceParser() if batch.agent == "claude-code" else None
        if parser is None:
            logger.warning("No trace parser for agent %r — trace-derived analysis skipped.", batch.agent)

        if cfg.mechanical_only:
            mech = mechanical_analysis(batch, parser, baselines)
            clusters = cluster_evals(mech, baselines=baselines, batch=batch)
            ga = GapAnalysis(batch_id=batch.batch_id, mechanical=mech, clusters=clusters, hypotheses=[])
        else:
            ga = asyncio.run(generate_gap_analysis(batch=batch, parser=parser, baselines=baselines))

        if cfg.format == "json":
            return _serialize(ga)  # type: ignore[return-value]

        # markdown
        from nemo_agents_plugin.improvement._analysis_reporting import generate_gap_report

        return {"format": "md", "report": generate_gap_report(ga)}
