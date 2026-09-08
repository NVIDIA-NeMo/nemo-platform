# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Worker-side guardrail judge — the per-tool policy chain.

Runs inside the ``nemoguardrails`` worker that Relay's built-in ``nemo_guardrails``
plugin spawns. NeMo Guardrails does the heavy lifting: ``render_task_prompt`` fills
in the prompt and ``llm_call`` makes the judge LLM call (model/keys from
``config.yml``). This action adds only the one thing the library has no built-in
rail for — for the tool being called, run EVERY authored check and block if any
refuses (block-if-any, mirroring NAT's per-tool ``pre_tool_verifier`` chain).

The policy lives entirely in ``prompts.yml`` (tasks ``guardrail__<tool>__<check>``);
adding a check is a prompt task, not code.

Payload at the ``tool_input`` boundary is JSON ``{"tool_name", "arguments"}``. The
context workaround injects the user turn into ``arguments[RELAY_CONTEXT_KEY]``;
this action reads it back out and strips it before judging. (We inject this context
because Relay only makes the tool call name and arguments available at the tool call boundary).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from nemoguardrails.actions import action
from nemoguardrails.actions.llm.utils import llm_call

# Must match relay_guardrails.context.RELAY_CONTEXT_KEY (workaround coupling).
RELAY_CONTEXT_KEY = "__relay_guardrail_context__"
_PROMPTS_PATH = Path(__file__).resolve().parent / "prompts.yml"
_VERDICT = (
    "\n\nApply the policy above to the content provided. Respond with EXACTLY one "
    "token on the final line: ALLOW or BLOCK."
)


def _debug(msg: str) -> None:
    """Append a diagnostics line to $IRON_SWARM_DEBUG, if set (used by the verify step)."""
    path = os.environ.get("IRON_SWARM_DEBUG")
    if path:
        try:
            with open(path, "a") as fh:
                fh.write(msg + "\n")
        except OSError:
            pass


@lru_cache(maxsize=1)
def _prompts() -> dict[str, str]:
    """Task name -> prompt content, from prompts.yml."""
    doc = yaml.safe_load(_PROMPTS_PATH.read_text()) or {}
    return {
        e["task"]: str(e.get("content", ""))
        for e in doc.get("prompts", [])
        if isinstance(e, dict) and e.get("task")
    }


def _render(task: str, ctx: dict[str, str], ltm: Any) -> str:
    """Prefer the library's Jinja render; fall back to plain substitution if unavailable."""
    if ltm is not None:
        try:
            rendered = ltm.render_task_prompt(task=task, context=ctx)
            if rendered:
                return str(rendered)
        except Exception:  # noqa: BLE001
            pass
    content = _prompts().get(task, "")
    for key, value in ctx.items():
        content = content.replace("{{ " + key + " }}", value).replace("{{" + key + "}}", value)
    return content


def _blocked(text: str) -> bool:
    """Read ALLOW/BLOCK off the verdict, tolerant of trailing markdown/punctuation."""
    upper = (text or "").upper()

    for line in reversed(upper.splitlines()):
        token = line.strip().strip(".!:*`\"' ")
        if token.endswith("BLOCK"):
            return True
        if token.endswith("ALLOW"):
            return False

    return "BLOCK" in upper


@action(name="tool_call_judge")
async def tool_call_judge(
    context: dict | None = None,
    llm: Any = None,
    llm_task_manager: Any = None,
) -> str:
    """Return "allow" or "block" for the current tool call (block if any check refuses)."""
    try:
        payload = json.loads((context or {}).get("user_message") or "{}")
    except (ValueError, TypeError):
        payload = {}
    tool_name = payload.get("tool_name")
    checks = sorted(t for t in _prompts() if t.startswith(f"guardrail__{tool_name}__"))
    if not tool_name or llm is None or not checks:
        return "allow"

    arguments = dict(payload.get("arguments") or {})
    injected = arguments.pop(RELAY_CONTEXT_KEY, {}) or {}
    ctx = {
        "user_turn": injected.get("user_turn", ""),
        "tool_call": json.dumps({"tool_name": tool_name, "arguments": arguments}),
    }
    _debug(f"JUDGE tool={tool_name!r} context_present={bool(injected)} user_turn={ctx['user_turn']!r}")

    for task in checks:
        verdict = await llm_call(llm, f"{_render(task, ctx, llm_task_manager)}{_VERDICT}")
        blocked = _blocked(getattr(verdict, "content", None) or str(verdict))
        _debug(f"  CHECK {task} -> {'BLOCK' if blocked else 'allow'}")
        if blocked:
            return "block"

    return "allow"
