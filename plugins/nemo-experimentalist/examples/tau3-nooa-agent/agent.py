# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import cast

from nooa import Agent, CodeActStrategy, strategy
from nooa.config import CodeActConfig
from nooa.mcp import MCPManager
from nooa.tools import ShellTools
from nooa.tracing import enable_tracing, exporters
from nooa.unifiedllm import CompletionClient

enable_tracing(
    exporters=[
        exporters.jsonl(trace_dir=os.environ.get("NEMO_AGENT_TRACE_DIR", "/app/traces/")),
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


class ConversationEnded(BaseException):
    """Stop the agent cleanly after the Tau3 user simulator emits its stop token."""


class StopAwareMCPManager:
    """End the current CodeAct block when Tau3 signals that the user is done."""

    def __init__(self, manager: object) -> None:
        self._manager = manager

    def __dir__(self) -> list[str]:
        return dir(self._manager)

    def __getattr__(self, name: str) -> object:
        attribute = getattr(self._manager, name)
        if not callable(attribute):
            return attribute

        tool = cast(Callable[..., Awaitable[object]], attribute)

        async def call_and_stop(*args: object, **kwargs: object) -> object:
            try:
                result = await tool(*args, **kwargs)
            except Exception as exc:
                if "Conversation has already ended" in str(exc):
                    raise ConversationEnded from None
                raise
            rendered = str(result)
            if "###STOP###" in rendered or "Conversation has already ended" in rendered:
                raise ConversationEnded
            return result

        call_and_stop.__name__ = getattr(attribute, "__name__", name)
        call_and_stop.__qualname__ = getattr(attribute, "__qualname__", name)
        call_and_stop.__doc__ = getattr(attribute, "__doc__", None)
        setattr(call_and_stop, "__wrapped__", attribute)
        return call_and_stop


class Codeact(Agent, llm=llm):
    def __init__(self) -> None:
        super().__init__()
        self.shell = ShellTools()
        self.tau3_runtime = StopAwareMCPManager(
            MCPManager.create_from_server(
                "tau3-runtime",
                url=os.environ.get("TAU3_RUNTIME_URL", "http://tau3-runtime:8000/mcp"),
                transport="streamable-http",
                tool_call_timeout=timedelta(seconds=MCP_TOOL_TIMEOUT_SECONDS),
            )
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
            "await self.tau3_runtime.start_conversation(). Discover the domain "
            "tools with dir(self.tau3_runtime), then use inspect.signature(...) "
            "and inspect.getdoc(...) before calling them. Use the relevant domain "
            "tools to perform the requested operation; do not replace them with a "
            "conversation-only loop. The process exits automatically when the "
            "user simulator emits ###STOP###."
        )
        ...
