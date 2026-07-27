# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The context workaround, as GLOBAL Relay intercepts (Fabric-compatible).

Relay does not carry conversation context across the tool boundary, so the
built-in ``nemo_guardrails`` plugin's worker can't see the user turn when it
judges a tool call. This module supplies it with three global intercepts that
fire during any managed run -- including Fabric's deepagents harness, whose
middleware routes model calls through ``nemo_relay.llm.execute`` and tool calls
through ``nemo_relay.typed.tool_execute`` (both run the global intercept
pipeline). No middleware subclassing, no Fabric fork.

  1. capture (LLM request intercept)   -- read the user turn off each model call.
  2. inject  (tool request intercept)  -- put it into the tool args, so the
                                          plugin serializes it into the worker
                                          payload and the judge can read it.
  3. strip   (tool execution intercept) -- remove it before the real tool runs.

Ordering is deterministic: within one agent turn the model call (capture) runs
before the tool call (inject/strip), and Relay's tool pipeline runs request
intercepts (inject) before execution intercepts, with the high-priority strip
nested inside the plugin's own tool intercept (which judges first).

This whole module is the throwaway workaround: it disappears when Relay carries
context across the tool boundary natively (the feature request).
"""

from __future__ import annotations

from typing import Any

import nemo_relay

# Key under which the user turn is smuggled through the tool args. The worker
# judge (guardrails_config/actions.py) reads it; the strip removes it.
RELAY_CONTEXT_KEY = "__relay_guardrail_context__"

# Last user turn seen on a model call. Module-level is sufficient for the
# reference (a single agent, sequential turns); a scope-keyed store would be the
# production-safe form under concurrency.
_state: dict[str, str] = {"user_turn": ""}

_CAPTURE_NAME = "iron_swarm_capture"
_INJECT_NAME = "iron_swarm_inject"
_STRIP_NAME = "iron_swarm_context_strip"


def _capture_llm(name: str, request: Any, annotated: Any) -> tuple[Any, Any]:
    """Record the latest user turn from a managed model call."""
    try:
        if annotated is not None:
            getter = getattr(annotated, "last_user_message", None)
            text = getter() if callable(getter) else None
            if text:
                _state["user_turn"] = text
    except Exception:  # noqa: BLE001 - capture must never break the model call
        pass
    return request, annotated


def _inject_tool(tool_name: str, args: Any) -> Any:
    """Attach the captured user turn to the tool args before the plugin judges."""
    if isinstance(args, dict):
        return {**args, RELAY_CONTEXT_KEY: {"user_turn": _state["user_turn"]}}
    return args


async def _strip_tool(tool_name: str, args: Any, next_call: Any) -> Any:
    """Remove the smuggled context before the real tool runs."""
    if isinstance(args, dict) and RELAY_CONTEXT_KEY in args:
        args = {key: value for key, value in args.items() if key != RELAY_CONTEXT_KEY}
    return await next_call(args)


def register_context_workaround(*, strip_priority: int = 1_000_000) -> None:
    """Register capture + inject + strip. Use for the real agent (Fabric)."""
    nemo_relay.intercepts.register_llm_request(_CAPTURE_NAME, 10, False, _capture_llm)
    nemo_relay.intercepts.register_tool_request(_INJECT_NAME, 10, False, _inject_tool)
    nemo_relay.intercepts.register_tool_execution(_STRIP_NAME, strip_priority, _strip_tool)


def register_context_strip(*, priority: int = 1_000_000) -> None:
    """Register only the strip. Use when context is injected manually (run_spike)."""
    nemo_relay.intercepts.register_tool_execution(_STRIP_NAME, priority, _strip_tool)
