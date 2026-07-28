# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os

import requests  # noqa: F401
from nooa import Agent, CodeActStrategy, strategy
from nooa.config import CodeActConfig
from nooa.mcp import MCPManager
from nooa.tools import ShellTools
from nooa.tracing import enable_tracing, exporters
from nooa.unifiedllm import CompletionClient

enable_tracing(
    exporters=[
        exporters.jsonl(trace_dir="/app/traces/"),
    ]
)

llm = CompletionClient(
    model=os.environ.get("NEMO_AGENT_MODEL", "openai/azure/anthropic/claude-haiku-4-5"),
    api_key=os.environ.get("INFERENCE_API_KEY"),
    api_base=os.environ.get("INFERENCE_BASE_URL", "https://inference-api.nvidia.com/v1"),
)


class Codeact(Agent, llm=llm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shell = ShellTools()
        self.tau3_runtime = MCPManager.create_from_server(
            "tau3-runtime",
            url=os.environ.get("TAU3_RUNTIME_URL", "http://tau3-runtime:8000/mcp"),
            transport="streamable-http",
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
