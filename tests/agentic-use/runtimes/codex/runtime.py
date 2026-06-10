# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Codex backend wrapper for the SDK Codex AgentAttemptRuntime."""

from __future__ import annotations

from collections.abc import Sequence

from nemo_evaluator_sdk.agent_eval.runtimes.codex.runtime import (
    CodexCliAgentRuntime as SdkCodexCliAgentRuntime,
)
from nemo_evaluator_sdk.agent_eval.runtimes.codex.runtime import (
    CodexDockerCliAgentRuntime as SdkCodexDockerCliAgentRuntime,
)
from nemo_evaluator_sdk.agent_eval.types import AgentEvalAttempt, AgentEvalRunConfig, AgentEvalTask

from runtimes.shared.config import CodexRuntimeConfig


class CodexAgentAttemptRuntime:
    """Run agentic-use tasks via Codex CLI."""

    def __init__(self, config: CodexRuntimeConfig) -> None:
        self.config = config
        self._delegate = self._build_delegate()

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalAttempt]:
        return list(await self._delegate.run_tasks(tasks, config))

    def _build_delegate(self) -> SdkCodexCliAgentRuntime | SdkCodexDockerCliAgentRuntime:
        if self.config.codex_auth_json is not None:
            return SdkCodexDockerCliAgentRuntime(
                model=self.config.agent_model,
                auth_path=self.config.codex_auth_json,
            )
        return SdkCodexCliAgentRuntime(model=self.config.agent_model)
