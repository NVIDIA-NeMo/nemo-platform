# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The contract that lets a method-level model choice use the ordinary config path.

Three `@strategy` methods pick a non-default tier. They used to do it with a proxy that
read the environment at first use, because a decorator argument is evaluated at import
time when no instance exists to read config from.

nooa PR #81 removes that constraint: `@strategy(llm=...)` accepts a callable taking the
agent, resolved on each generation call, so a method-level tier reads off the instance
like everything else. The same change also strips `llm` before argument binding, which
makes the per-call precedence `actor.py` documents actually reachable — it never was.

These tests pin both, because the proxy's removal depends entirely on the first and a
regression in the second would be silent.

Scripted fakes throughout; no network calls.
"""

import json
from typing import Any

import pytest
from nooa import Agent, CodeActStrategy, strategy
from nooa.config import CodeActConfig
from nooa.unifiedllm import FakeLLMClient, LLMResponse, ToolCall


def _returns(value: str) -> FakeLLMClient:
    """A fake whose single scripted turn makes the method return *value*."""
    response = LLMResponse(
        raw_response=None,
        content="",
        finish_reason="tool_calls",
        assistant_message={"role": "assistant", "content": ""},
        tool_calls=[
            ToolCall(
                id="call_exec",
                name="execute_python",
                arguments=json.dumps({"code": f"return_result(result={value!r})"}),
            )
        ],
    )
    return FakeLLMClient(scripted_responses=[response])


class _TieredAgent(Agent):
    """One generation method with no decorator override, one with."""

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=5)))
    async def plain(self) -> str:  # pyright: ignore[reportReturnType]
        """Return a string."""
        ...


@pytest.mark.asyncio
async def test_a_method_falls_back_to_the_agents_own_client() -> None:
    """The baseline: no decorator override, no call override."""
    agent = _TieredAgent(llm=_returns("from-agent"))

    assert await agent.plain() == "from-agent"


@pytest.mark.asyncio
async def test_a_decorator_override_beats_the_agents_own_client() -> None:
    """What *is* available: a value fixed at decoration time, before any instance exists.

    This is the constraint that forced a deferred proxy: a plain client fixed here is
    shared by every instance, and there is no instance yet to read config from.
    """

    class _WithDecoratorOverride(Agent):
        @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=5)), llm=_returns("from-decorator"))
        async def pick(self) -> str:  # pyright: ignore[reportReturnType]
            """Return a string."""
            ...

    agent = _WithDecoratorOverride(llm=_returns("from-agent"))

    assert await agent.pick() == "from-decorator"


@pytest.mark.asyncio
async def test_a_callable_override_resolves_from_the_instance() -> None:
    """What replaced the proxy: the tier is read off the instance, per call.

    This is the ordinary config path — whatever the runner injected at construction — with
    no import-time resolution, no environment variable, and nothing ambient. Two instances
    of the same class can run against different models, which the baked-on client could
    never express.
    """

    class _PerInstance(Agent):
        def __init__(self, *, mid: Any, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.mid = mid

        @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=5)), llm=lambda self: self.mid)
        async def pick(self) -> str:  # pyright: ignore[reportReturnType]
            """Return a string."""
            ...

    first = _PerInstance(llm=_returns("agent-a"), mid=_returns("mid-of-a"))
    second = _PerInstance(llm=_returns("agent-b"), mid=_returns("mid-of-b"))

    assert await first.pick() == "mid-of-a"
    assert await second.pick() == "mid-of-b"


@pytest.mark.asyncio
async def test_a_call_level_llm_now_reaches_the_resolver() -> None:
    """The adjacent fix in the same change: `llm=` is stripped before arity binding.

    Not what the tier choice will use, but it is the behaviour `actor.py` always claimed
    and never delivered, so pin it — a regression here would be silent.
    """
    agent = _TieredAgent(llm=_returns("from-agent"))

    assert await agent.plain(llm=_returns("from-call")) == "from-call"  # ty: ignore[unknown-argument]
