# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Claude Code backend — scaffold for phase 3."""

from __future__ import annotations

from collections.abc import Sequence

from nemo_evaluator_sdk.agent_eval.types import AgentEvalAttempt, AgentEvalRunConfig, AgentEvalTask

from runtimes.shared.config import ClaudeCodeRuntimeConfig


class ClaudeCodeAgentAttemptRuntime:
    """Run agentic-use tasks via Claude Code CLI."""

    def __init__(self, config: ClaudeCodeRuntimeConfig) -> None:
        self.config = config

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalAttempt]:
        raise NotImplementedError("ClaudeCodeAgentAttemptRuntime: implement in phase 3")
