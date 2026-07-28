# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
from datetime import timedelta

from mcp_timeout import create_tool
from nooa import Agent, CodeActStrategy, strategy
from nooa.config import CodeActConfig
from nooa.tools import ShellTools
from nooa.tracing import enable_tracing, exporters
from nooa.unifiedllm import CompletionClient

enable_tracing(
    exporters=[
        exporters.jsonl(trace_dir="/app/traces/"),
    ]
)

# Generous because send_message_to_user blocks on the sidecar's user-simulator LLM.
MCP_TOOL_TIMEOUT_SECONDS = float(os.environ.get("TAU3_MCP_TOOL_TIMEOUT_SECONDS", "300"))

# harbor_wrapper hands OPENAI_API_KEY/OPENAI_BASE_URL to this process, matching the
# names the tau3 task environment uses. INFERENCE_* is the fallback for running the
# agent outside the wrapper.
llm = CompletionClient(
    model=os.environ.get("NEMO_AGENT_MODEL", "openai/azure/anthropic/claude-haiku-4-5"),
    api_key=os.environ.get("OPENAI_API_KEY") or os.environ.get("INFERENCE_API_KEY"),
    api_base=os.environ.get("OPENAI_BASE_URL")
    or os.environ.get("INFERENCE_API_BASE", "https://inference-api.nvidia.com/v1"),
)


class Codeact(Agent, llm=llm):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.shell = ShellTools()
        self.tau3_runtime = create_tool(
            "tau3-runtime",
            url=os.environ.get("TAU3_RUNTIME_URL", "http://tau3-runtime:8000/mcp"),
            tool_call_timeout=timedelta(seconds=MCP_TOOL_TIMEOUT_SECONDS),
        )

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=60)))
    async def solve(self, instruction: str) -> None:
        """Solve the task given the instruction.

        Start by calling ``await self.tau3_runtime.start_conversation()``. Use
        the returned state and subsequent tau3-runtime tools to complete the
        conversation before returning.
        """
        self.context["instruction"] = instruction
        self.context["mcp_usage"] = (
            "Use await self.tau3_runtime.<tool_name>(...) to call the "
            "tau3-runtime MCP tools. Start with "
            "await self.tau3_runtime.start_conversation()."
        )
        ...
