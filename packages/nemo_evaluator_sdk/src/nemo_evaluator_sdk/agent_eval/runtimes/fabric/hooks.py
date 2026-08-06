# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Per-task lifecycle hooks for :class:`FabricAgentRuntime`.

Fabric already accepts a complete typed config per ``Fabric.run``. These hooks
exist so callers (e.g. optimize trials) can wrap each task with agent-specific
ephemeral state — run-scoped MCP bindings, credential handoffs — without
baking that logic into the runtime or into Fabric itself.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask


@dataclass
class FabricTaskRunSession:
    """Mutable bag owned by a hook for one task invocation."""

    state: dict[str, Any] = field(default_factory=dict)


class FabricTaskRunHook(Protocol):
    """Optional prepare / after-success / cleanup around one Fabric task run."""

    def prepare(
        self,
        config: Any,
        task: AgentEvalTask,
        evidence_dir: Path,
        workspace_dir: Path,
        session: FabricTaskRunSession,
    ) -> Any:
        """Return the config that should be passed to ``Fabric.run`` for this task.

        ``config`` is a composed ``nemo_fabric.FabricConfig`` (typed when Fabric is installed).
        """

    def after_success(
        self,
        task: AgentEvalTask,
        result: Any,
        session: FabricTaskRunSession,
    ) -> dict[str, Any] | None:
        """Optional extras merged into trial ``output.metadata`` / ``metadata`` on success.

        ``result`` is a Fabric ``RunResult``. Raise to fail the trial (e.g. analyzer audit failed).
        """

    def cleanup(self, session: FabricTaskRunSession) -> None:
        """Always invoked in ``finally`` after the task attempt (success or failure)."""
