# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trusted lifecycle extensions for ``agents.execute`` jobs."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any, Protocol

from nemo_agents_plugin.fabric.runtime import FabricRuntimeResult
from nemo_platform_plugin.job_context import JobContext

EXECUTE_AGENT_EXTENSION_ENTRY_POINT_GROUP = "nemo.agents.execute_extensions"
NOOP_EXECUTE_AGENT_EXTENSION_KIND = "noop"


class ExecuteAgentExtension(Protocol):
    """Plugin-owned deterministic work tied to the execute-agent lifecycle."""

    def after_invoke(self, context: ExecuteAgentAfterInvokeContext) -> None:
        """Run after a successful Fabric invocation."""


class NoopExecuteAgentExtension:
    """Default extension used when no plugin extension is configured."""

    def after_invoke(self, context: ExecuteAgentAfterInvokeContext) -> None:
        del context


@dataclass(frozen=True, slots=True)
class ExecuteAgentAfterInvokeContext:
    """Inputs available to a trusted execute-agent extension after Fabric succeeds."""

    ctx: JobContext
    config: dict[str, Any]
    agent_name: str
    fabric_result: FabricRuntimeResult


def resolve_execute_agent_extension(kind: str) -> type[ExecuteAgentExtension]:
    """Resolve an installed trusted execute-agent extension kind."""
    return _load_execute_agent_extension(kind)


def run_execute_agent_after_invoke_extension(kind: str, context: ExecuteAgentAfterInvokeContext) -> None:
    """Run the ``after_invoke`` lifecycle method for an installed extension kind."""
    extension_cls = _load_execute_agent_extension(kind)
    extension_cls().after_invoke(context)


def _load_execute_agent_extension(kind: str) -> type[ExecuteAgentExtension]:
    if kind == NOOP_EXECUTE_AGENT_EXTENSION_KIND:
        return NoopExecuteAgentExtension

    matches = [
        entry_point
        for entry_point in entry_points(group=EXECUTE_AGENT_EXTENSION_ENTRY_POINT_GROUP)
        if entry_point.name == kind
    ]
    if not matches:
        raise ValueError(f"Unknown agents.execute extension {kind!r}.")
    if len(matches) > 1:
        raise ValueError(f"Multiple agents.execute extensions are registered for {kind!r}.")
    return matches[0].load()
