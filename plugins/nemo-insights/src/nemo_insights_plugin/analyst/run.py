# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reusable insights analyst run orchestration."""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from nemo_insights_plugin.analyst.agent import (
    KICKOFF,
    MAX_REQUESTS,
    build_analyst_agent,
)
from nemo_insights_plugin.analyst.analyst_backend import make_analyst_backend
from nemo_insights_plugin.analyst.deps import AnalystDeps
from nemo_insights_plugin.analyst.observability import (
    ANALYST_OBSERVABILITY_ENV,
    setup_analyst_observability,
)
from nemo_insights_plugin.analyst.result import AnalystResult
from nemo_insights_plugin.client import make_client
from pydantic_ai import Agent, UsageLimits
from pydantic_ai.messages import TextPart, ToolCallPart, ToolReturnPart

# Truncate long tool inputs/outputs when echoing the verbose trace so a single
# span dump doesn't flood the terminal.
_VERBOSE_TRUNCATE = 2000


async def run_analyst(
    *,
    agent: str,
    agent_spec: str | None,
    workspace: str,
    base_url: str | None,
    insights_output: str | Path | None = None,
    verbose: bool = False,
    since: datetime | None = None,
    evaluation_id: str | None = None,
) -> str:
    """Build and run the analyst agent against an agent's telemetry.

    The trace-volume floor for scheduled runs lives in the periodic controller,
    which decides whether a run is worth launching; this entry point just runs.

    Args:
        agent: Agent under test.
        agent_spec: Optional markdown spec content for the agent under test.
        workspace: Platform workspace.
        base_url: Platform base URL. ``None`` uses the active platform context.
        insights_output: Optional local YAML output path for Insight writes.
        verbose: Whether to stream model/tool events to stderr.
        since: Optional incremental lower bound enforced on trace/span reads.
        evaluation_id: Optional run scope; AND-pinned onto every span read.
    """
    client = make_client(base_url)
    observability = None
    insights_output_path = str(insights_output) if insights_output else None
    backend = make_analyst_backend(
        client=client,
        insights_output=insights_output_path,
    )
    try:
        deps = AnalystDeps(
            agent=agent,
            workspace=workspace,
            base_url=base_url,
            insights_output=insights_output_path,
            backend=backend,
            since=since,
            evaluation_id=evaluation_id,
        )
        if base_url and _analyst_observability_enabled():
            observability = setup_analyst_observability(
                base_url=base_url,
                workspace=workspace,
                target_agent=agent,
            )
        analyst = build_analyst_agent(
            agent=agent,
            agent_spec=agent_spec,
            observability=observability,
        )
        result = await _run_agent(analyst, deps, verbose=verbose)
        return await backend.persist_result(workspace=workspace, agent=agent, result=result)
    finally:
        if observability is not None:
            observability.shutdown()
        await client.close()


def _analyst_observability_enabled() -> bool:
    """True when dogfooding analyst self-observability is explicitly enabled."""
    value = os.environ.get(ANALYST_OBSERVABILITY_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


async def _run_agent(
    analyst: Agent[AnalystDeps, AnalystResult],
    deps: AnalystDeps,
    *,
    verbose: bool,
) -> AnalystResult:
    """Run *analyst*, optionally streaming its tool calls to stderr."""
    usage_limits = UsageLimits(request_limit=MAX_REQUESTS)
    if not verbose:
        result = await analyst.run(KICKOFF, deps=deps, usage_limits=usage_limits)
        return result.output

    async with analyst.iter(KICKOFF, deps=deps, usage_limits=usage_limits) as run:
        async for node in run:
            _echo_node(node)
    assert run.result is not None
    return run.result.output


def _echo_node(node: Any) -> None:
    """Print tool calls, model text, and tool returns for one graph node."""
    if Agent.is_call_tools_node(node):
        for part in node.model_response.parts:
            if isinstance(part, ToolCallPart):
                print(
                    f"[tool] {part.tool_name}({_truncate(str(part.args))})",
                    file=sys.stderr,
                )
            elif isinstance(part, TextPart) and part.content.strip():
                print(f"[thought] {part.content.strip()}", file=sys.stderr)
    elif Agent.is_model_request_node(node):
        for part in node.request.parts:
            if isinstance(part, ToolReturnPart):
                print(
                    f"[result] {part.tool_name} -> {_truncate(str(part.content))}",
                    file=sys.stderr,
                )


def _truncate(text: str, limit: int = _VERBOSE_TRUNCATE) -> str:
    return text if len(text) <= limit else f"{text[:limit]}... ({len(text)} chars)"
