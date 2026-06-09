# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cursor Agent backend — scaffold for phase 3."""

from __future__ import annotations

from collections.abc import Sequence

from nemo_evaluator_sdk.agent_eval.types import AgentEvalAttempt, AgentEvalRunConfig, AgentEvalTask

from runtimes.shared.config import CursorAgentRuntimeConfig


class CursorAgentAttemptRuntime:
    """Run agentic-use tasks via Cursor Agent CLI."""

    def __init__(self, config: CursorAgentRuntimeConfig) -> None:
        self.config = config

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalAttempt]:
        raise NotImplementedError("CursorAgentAttemptRuntime: implement in phase 3")
