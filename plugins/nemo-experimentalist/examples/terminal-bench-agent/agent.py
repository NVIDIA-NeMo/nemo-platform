# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A deliberately small LangChain coding agent for Terminal-Bench."""

import os
import signal
import subprocess
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

DEFAULT_API_BASE = "https://inference-api.nvidia.com/v1"
DEFAULT_MODEL = "aws/anthropic/claude-haiku-4-5-v1"
MAX_COMMAND_OUTPUT_CHARS = 40_000
SYSTEM_PROMPT = """\
You are solving a Terminal-Bench task inside its canonical Linux environment.
The task workspace is /app. Use the execute tool to inspect files, implement
the solution, and verify it. Do not modify files under /tests. Work directly in
/app and finish only after checking the result. Missing utilities or language
runtimes may be installed because network access is available.
"""


def _shell_path() -> str:
    bash = Path("/bin/bash")
    return str(bash) if bash.is_file() else "/bin/sh"


def _bounded_output(stdout: str, stderr: str, return_code: int) -> str:
    parts = [f"exit_code={return_code}"]
    if stdout:
        parts.append(f"stdout:\n{stdout}")
    if stderr:
        parts.append(f"stderr:\n{stderr}")
    rendered = "\n\n".join(parts)
    if len(rendered) <= MAX_COMMAND_OUTPUT_CHARS:
        return rendered
    omitted = len(rendered) - MAX_COMMAND_OUTPUT_CHARS
    return f"[... {omitted} earlier characters omitted ...]\n{rendered[-MAX_COMMAND_OUTPUT_CHARS:]}"


@tool
def execute(command: str, timeout_sec: int = 120) -> str:
    """Execute a shell command in /app and return its exit code, stdout, and stderr."""
    timeout_sec = max(1, min(timeout_sec, 840))
    process = subprocess.Popen(
        [_shell_path(), "-lc", command],
        cwd="/app",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        stderr = f"{stderr}\ncommand timed out after {timeout_sec} seconds".strip()
    return _bounded_output(stdout, stderr, process.returncode)


class UsageCallback(BaseCallbackHandler):
    """Accumulate model usage even when the graph reaches its recursion limit."""

    def __init__(self) -> None:
        self.totals = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0}
        self.last_content = ""

    def on_llm_end(self, response: LLMResult, **_kwargs: Any) -> None:
        for generation_group in response.generations:
            for generation in generation_group:
                message = getattr(generation, "message", None)
                if message is None:
                    continue
                content = getattr(message, "content", "")
                if isinstance(content, str) and content:
                    self.last_content = content
                self._add_usage(getattr(message, "usage_metadata", None))

    def _add_usage(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        self.totals["input_tokens"] += int(usage.get("input_tokens") or 0)
        self.totals["output_tokens"] += int(usage.get("output_tokens") or 0)
        details = usage.get("input_token_details")
        if isinstance(details, dict):
            self.totals["cache_read_tokens"] += int(details.get("cache_read") or 0)


async def solve(instruction: str) -> tuple[str, dict[str, int]]:
    """Run the LangChain tool-calling loop and return its final answer and usage."""
    api_key = os.environ["INFERENCE_API_KEY"]
    model = ChatOpenAI(
        model=os.environ.get("EXPERIMENTALIST_MODEL", DEFAULT_MODEL),
        base_url=os.environ.get("INFERENCE_API_BASE", DEFAULT_API_BASE),
        api_key=api_key,
    )
    coding_agent = create_agent(
        model=model,
        tools=[execute],
        system_prompt=SYSTEM_PROMPT,
    )
    usage = UsageCallback()
    try:
        result = await coding_agent.ainvoke(
            {"messages": [{"role": "user", "content": instruction}]},
            config={"callbacks": [usage], "recursion_limit": 30},
        )
    except GraphRecursionError:
        answer = usage.last_content or "Stopped after reaching the bounded agent step limit."
        return answer, usage.totals
    messages = result["messages"]
    content = messages[-1].content
    answer = content if isinstance(content, str) else str(content)
    return answer, usage.totals
