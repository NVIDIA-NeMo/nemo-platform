# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reusable insights analyst run orchestration."""

import importlib
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Protocol, cast

from nemo_insights_plugin.analyst.agent import (
    KICKOFF,
    Analyst,
    build_analyst_agent,
)
from nemo_insights_plugin.analyst.analyst_backend import make_analyst_backend
from nemo_insights_plugin.analyst.deps import AnalystDeps
from nemo_insights_plugin.analyst.observability import (
    ANALYST_OBSERVABILITY_ENV,
    setup_analyst_observability,
)
from nemo_insights_plugin.analyst.result import AnalystResult
from nemo_platform import AsyncNeMoPlatform
from nooa.context_blocks import EventBase
from nooa.events import LLMComplete, PythonOutput

# Truncate long tool inputs/outputs when echoing the verbose trace so a single
# span dump doesn't flood the terminal.
_VERBOSE_TRUNCATE = 2000


class _LiteLLMModule(Protocol):
    drop_params: bool


class ClientConstructionError(Exception):
    """The analyst's NeMo Platform client could not be constructed."""


async def run_analyst(
    *,
    agent: str,
    agent_spec: str | None,
    workspace: str,
    base_url: str | None,
    client: AsyncNeMoPlatform,
    insights_output: str | Path | None = None,
    local_only: bool = False,
    verbose: bool = False,
    since: datetime | None = None,
    evaluation_id: str | None = None,
    seeded_findings: str | None = None,
) -> str:
    """Build and run the analyst agent against an agent's telemetry.

    The trace-volume floor for scheduled runs lives in the periodic controller,
    which decides whether a run is worth launching; this entry point just runs.

    Args:
        agent: Agent under test.
        agent_spec: Optional markdown spec content for the agent under test.
        workspace: Platform workspace.
        base_url: Platform base URL. ``None`` uses the active platform context.
        client: Platform client to use. This function closes it before returning.
        insights_output: Optional local YAML path. Receives a mirror of the
            insights the platform stored, or the only copy under *local_only*.
        local_only: Skip the platform and persist insights to *insights_output*
            alone. Reserved for the insights testbed — no CLI flag sets it.
            Requires *insights_output*.
        verbose: Whether to stream model/tool events to stderr.
        since: Optional incremental lower bound enforced on trace/span reads.
        evaluation_id: Optional run scope; AND-pinned onto every span read.
        seeded_findings: Optional markdown findings from a prior analysis,
            used to focus this run. Leads to re-verify, not a contract.
    """
    observability = None
    insights_output_path = str(insights_output) if insights_output else None
    try:
        _enable_litellm_drop_params()
        backend = make_analyst_backend(
            client=client,
            insights_output=insights_output_path,
            local_only=local_only,
        )
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
            deps=deps,
            agent=agent,
            agent_spec=agent_spec,
            seeded_findings=seeded_findings,
        )
        result = await _run_agent(analyst, verbose=verbose)
        return await backend.persist_result(workspace=workspace, agent=agent, result=result)
    finally:
        try:
            if observability is not None:
                observability.shutdown()
        finally:
            await client.close()


def _analyst_observability_enabled() -> bool:
    """True when dogfooding analyst self-observability is explicitly enabled."""
    value = os.environ.get(ANALYST_OBSERVABILITY_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _enable_litellm_drop_params() -> None:
    """Let LiteLLM omit parameters unsupported by the configured model."""
    litellm = cast(_LiteLLMModule, importlib.import_module("litellm"))
    litellm.drop_params = True


async def _run_agent(
    analyst: Analyst,
    *,
    verbose: bool,
) -> AnalystResult:
    """Run *analyst*, optionally streaming Nooa reasoning and execution events."""
    if not verbose:
        return await analyst.analyze(KICKOFF)

    unsubscribers = [
        analyst.event_manager.on("LLMComplete", _echo_event),
        analyst.event_manager.on("PythonOutput", _echo_event),
    ]
    try:
        return await analyst.analyze(KICKOFF)
    finally:
        for unsubscribe in unsubscribers:
            unsubscribe()


def _echo_event(event: EventBase) -> None:
    """Print one useful Nooa event in the legacy verbose CLI format."""
    if isinstance(event, LLMComplete):
        if event.reasoning_content.strip():
            print(f"[thought] {_truncate(event.reasoning_content.strip())}", file=sys.stderr)
        for tool_call in event.tool_calls:
            name = str(tool_call.get("function_name", "tool"))
            arguments = tool_call.get("arguments", "")
            print(f"[tool] {name}({_truncate(str(arguments))})", file=sys.stderr)
        return

    if isinstance(event, PythonOutput):
        parts = [part.rstrip() for part in (event.stdout, event.stderr, event.error) if part.rstrip()]
        if event.value is not None:
            parts.append(repr(event.value))
        detail = "\n".join(parts) or event.execution_status.value
        print(f"[result] execute_python -> {_truncate(detail)}", file=sys.stderr)


def _truncate(text: str, limit: int = _VERBOSE_TRUNCATE) -> str:
    return text if len(text) <= limit else f"{text[:limit]}... ({len(text)} chars)"
