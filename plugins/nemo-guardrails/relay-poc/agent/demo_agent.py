# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A minimal agent that uses the PoC guardrails policy via NeMo Relay.

This is the "how a real user builds an agent with our plugin" artifact. It is a
plain LangChain agent (``create_agent``) wired with Relay's ``NemoRelayMiddleware``
so every model *and* tool call runs through Relay managed execution. The plugin
is activated the way a real consumer activates a language-binding plugin --
``nemo_relay.plugin.register(PLUGIN_KIND, GuardrailsPlugin())`` then
``nemo_relay.plugin.initialize(...)`` -- so the guardrails fire on those calls.

The chat model is stubbed (no network, no credentials): it returns canned
tool-calling responses so the agent deterministically attempts each tool, and
the model-based input rail uses a *mock* content-safety check
(``policy.mock_content_safety_check``) instead of the real ``/checks`` service.
This lets us show every outcome without a live LLM:

  1. allowed tool (``get_weather``) runs normally,
  2. ``web_search`` arguments are PII-redacted before the tool runs,
  3. ``query_db`` with a safe query runs (passes the argument rules),
  4. a non-allowlisted tool (``delete_account``) is blocked before it executes,
  5. a blocklisted tool (``transfer_funds``) is blocked even though it is on the
     allowlist (blocklist takes precedence),
  6. ``query_db`` with a ``DROP`` in its query is blocked by the argument rule,
  7. ``run_bash("touch foo.txt")`` is blocked before execution by the command
     denylist, and ``foo.txt`` is never created on disk,
  8. ``run_bash("echo hello")`` -- a nearby control command -- still runs,
     proving the block is selective,
  9. an unsafe prompt is blocked by the LLM input rail before the model runs.

Scenarios 1-8 exercise the tool rails; scenario 9 exercises the LLM input rail --
all on the same ``agent.invoke`` path, through the same middleware. Scenarios 7-8
are the ticket's concrete bash deny-case: ``touch foo.txt`` blocked at the real
tool boundary with no file on disk, ``echo hello`` still allowed.

Run it (needs the embedded Relay runtime + LangChain; no Rust build required):

    PYTHONPATH=plugins/nemo-guardrails/relay-poc/src \\
      uv run --no-project --with nemo-relay --with 'langchain>=1.0' \\
      python plugins/nemo-guardrails/relay-poc/agent/demo_agent.py

The stub-model + create_agent + NemoRelayMiddleware pattern is copied from Relay's
own passing integration test (python/tests/integrations/langchain_tests/test_middleware.py).
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import nemo_relay
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from nemo_guardrails_relay_poc.inprocess import PLUGIN_KIND, GuardrailsPlugin
from nemo_relay.integrations.langchain import NemoRelayMiddleware

# Records what actually happened, so we can prove guardrail effects.
OBSERVED: dict[str, Any] = {
    "delete_account_ran": False,
    "transfer_funds_ran": False,
    "web_search_query": None,
    "query_db_query": None,
    "bash_commands_ran": [],
}

#: A real, isolated working directory the ``run_bash`` tool executes in, so the
#: "foo.txt is not created on disk" acceptance check is a true filesystem
#: assertion rather than a stubbed flag. Set in ``main``.
WORKDIR: Path | None = None


@tool
def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    return f"The weather in {location} is sunny and 72 degrees."


@tool
def web_search(query: str) -> str:
    """Search the web for a query."""
    # The query we see here is what actually reached the tool -- i.e. post-redaction.
    OBSERVED["web_search_query"] = query
    return f"top result for: {query}"


@tool
def query_db(query: str) -> str:
    """Run a read-only database query (argument rules block destructive SQL)."""
    OBSERVED["query_db_query"] = query
    return f"rows for: {query}"


@tool
def delete_account(user_id: str) -> str:
    """Permanently delete a user account (destructive; not on the allowlist)."""
    OBSERVED["delete_account_ran"] = True
    return f"deleted account {user_id}"


@tool
def transfer_funds(amount: str) -> str:
    """Transfer funds (destructive; explicitly blocklisted even if allowlisted)."""
    OBSERVED["transfer_funds_ran"] = True
    return f"transferred {amount}"


@tool
def run_bash(command: str) -> str:
    """Run a bash command and return its output.

    This tool *really executes* the command (via ``subprocess`` in an isolated
    working directory), so a guardrail block is only "safe" if it stops the call
    before this function runs -- exactly what the ticket's ``touch foo.txt``
    deny-case checks. Any command that reaches here has passed the guardrail.
    """
    OBSERVED["bash_commands_ran"].append(command)
    completed = subprocess.run(
        command,
        shell=True,  # noqa: S602 - PoC demo tool; the guardrail is what gates this
        cwd=str(WORKDIR),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip() or f"(exit {completed.returncode})"


def _make_stub_model(responses: list[AIMessage]) -> MagicMock:
    """A fake BaseChatModel that returns canned responses in order.

    Copied from Relay's langchain integration test. ``create_agent`` calls the
    model once per loop turn: first we return a tool call, then a final answer.
    """
    model = MagicMock(spec=BaseChatModel)
    model.bind.return_value = model
    model.bind_tools.return_value = model
    model.model = "stub-model"
    model.invoke.side_effect = list(responses)
    model.ainvoke = AsyncMock(side_effect=list(responses))
    return model


def _tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def _describe_planned(responses: list[AIMessage]) -> str:
    """Summarize what the (stubbed) model is set up to do this turn."""
    steps: list[str] = []
    for message in responses:
        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            steps.extend(f"call {call['name']}({call['args']!r})" for call in tool_calls)
        elif message.content:
            steps.append(f"reply {message.content!r}")
    return " -> ".join(steps) if steps else "(nothing)"


def _describe_message(message: Any) -> str:
    """Render one conversation message as a readable one-liner."""
    role = getattr(message, "type", None) or type(message).__name__
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        calls = ", ".join(f"{call['name']}({call['args']!r})" for call in tool_calls)
        return f"[{role}] tool call -> {calls}"
    name = getattr(message, "name", None)
    content = getattr(message, "content", "")
    prefix = f"[{role}:{name}]" if name else f"[{role}]"
    return f"{prefix} {content!r}"


def _run_scenario(
    title: str, tools: list[Any], responses: list[AIMessage], user_input: str
) -> tuple[MagicMock, Exception | None]:
    """Run one agent turn and return (stub model, exception raised or None).

    A hard block (tool allowlist or LLM input rail) surfaces as an exception out
    of ``agent.invoke``; callers use the returned model to assert whether the
    model/tool actually ran.
    """
    print(f"\n=== {title} ===")
    print(f"    user prompt : {user_input!r}")
    print(f"    model plan  : {_describe_planned(responses)}")
    model = _make_stub_model(responses)
    agent = create_agent(model=model, tools=tools, middleware=[NemoRelayMiddleware()])
    payload = {"messages": [{"role": "user", "content": user_input}]}
    raised: Exception | None = None
    with nemo_relay.scope.scope("relay-poc-agent", nemo_relay.ScopeType.Agent):
        try:
            result = agent.invoke(payload)
            print("    conversation:")
            for message in result["messages"]:
                print(f"      {_describe_message(message)}")
            final = result["messages"][-1].content
            print(f"    agent finished; final message: {final!r}")
        except Exception as exc:  # noqa: BLE001 - a guardrail block may surface as an error here
            raised = exc
            print("    agent response: blocked by guardrail (no model/tool output produced)")
            print(f"    agent raised (expected for a hard block): {type(exc).__name__}: {exc}")
    return model, raised


def main() -> int:
    # Activate GuardrailsPlugin the way a real consumer would: register the kind,
    # validate the config, then initialize it into this process's Relay runtime.
    # This is the exact language-binding-plugin lifecycle from the Relay docs.
    config = nemo_relay.plugin.PluginConfig(
        components=[
            nemo_relay.plugin.ComponentSpec(
                kind=PLUGIN_KIND,
                config={
                    "tool_policy": {
                        # delete_account is NOT listed -> blocked by the allowlist.
                        "allowed_tools": ["get_weather", "web_search", "query_db", "transfer_funds", "run_bash"],
                        # transfer_funds IS allowlisted but explicitly denied here.
                        "blocked_tools": ["transfer_funds"],
                        # redact PII in web_search's query before the tool runs.
                        "redact_args": {"web_search": ["query"]},
                        # block destructive SQL / oversized queries on query_db.
                        "arguments": {
                            "query_db": {"query": {"blocked_keywords": ["DROP", "DELETE"], "max_length": 200}},
                        },
                        # block the exact (normalized) shell command touch foo.txt on run_bash.
                        "denied_commands": {"run_bash": ["touch foo.txt"]},
                    },
                    # model-based input rail; PoC backs it with a mock check (no network)
                    "llm_input_rail": {"enabled": True, "model": "mock-content-safety"},
                },
            )
        ]
    )
    nemo_relay.plugin.register(PLUGIN_KIND, GuardrailsPlugin())
    report = nemo_relay.plugin.validate(config)
    if any(diagnostic["level"] == "error" for diagnostic in report["diagnostics"]):
        print("plugin config invalid:", report["diagnostics"])
        return 1
    asyncio.run(nemo_relay.plugin.initialize(config))

    global WORKDIR
    workdir = tempfile.TemporaryDirectory(prefix="relay-poc-bash-")
    WORKDIR = Path(workdir.name)

    failures: list[str] = []
    try:
        # 1. Allowed tool runs normally.
        _run_scenario(
            "Allowed tool (get_weather)",
            [get_weather],
            [_tool_call("get_weather", {"location": "San Francisco"}, "c1"), AIMessage(content="It's sunny in SF.")],
            "What's the weather in San Francisco?",
        )
        if OBSERVED["web_search_query"] is not None:
            failures.append("scenario 1 polluted web_search state")

        # 2. web_search arguments are redacted before the tool runs.
        _run_scenario(
            "Redacted arguments (web_search)",
            [web_search],
            [
                _tool_call("web_search", {"query": "reach bob@example.com about SF"}, "c2"),
                AIMessage(content="Found it."),
            ],
            "Search for how to reach bob@example.com.",
        )
        seen = OBSERVED["web_search_query"]
        if seen is None:
            failures.append("redaction: web_search never ran")
        elif "bob@example.com" in seen:
            failures.append(f"redaction: raw email reached the tool: {seen!r}")
        else:
            print(f"    [PASS] tool received redacted query: {seen!r}")

        # 3. Safe query_db call passes the argument rules and runs.
        _run_scenario(
            "Allowed query (query_db, safe SQL)",
            [query_db],
            [_tool_call("query_db", {"query": "SELECT name FROM users"}, "c3"), AIMessage(content="Here you go.")],
            "List the user names.",
        )
        if OBSERVED["query_db_query"] != "SELECT name FROM users":
            failures.append("arg-rule: safe query_db call did not run as expected")
        else:
            print(f"    [PASS] safe query ran: {OBSERVED['query_db_query']!r}")

        # 4. Non-allowlisted tool is blocked before it executes.
        _run_scenario(
            "Blocked tool (delete_account, not allowlisted)",
            [delete_account],
            [_tool_call("delete_account", {"user_id": "123"}, "c4"), AIMessage(content="Done.")],
            "Delete my account (user 123).",
        )
        if OBSERVED["delete_account_ran"]:
            failures.append("block: delete_account executed despite not being on the allowlist")
        else:
            print("    [PASS] delete_account was blocked; its function never ran")

        # 5. Blocklisted tool is blocked even though it is on the allowlist.
        _run_scenario(
            "Blocked tool (transfer_funds, blocklisted)",
            [transfer_funds],
            [_tool_call("transfer_funds", {"amount": "1000"}, "c5"), AIMessage(content="Done.")],
            "Transfer 1000 dollars.",
        )
        if OBSERVED["transfer_funds_ran"]:
            failures.append("blocklist: transfer_funds executed despite being blocklisted")
        else:
            print("    [PASS] transfer_funds was blocked by the blocklist; its function never ran")

        # 6. query_db with destructive SQL is blocked by the argument rule.
        _run_scenario(
            "Blocked argument (query_db, DROP)",
            [query_db],
            [_tool_call("query_db", {"query": "DROP TABLE users"}, "c6"), AIMessage(content="Done.")],
            "Drop the users table.",
        )
        if OBSERVED["query_db_query"] == "DROP TABLE users":
            failures.append("arg-rule: destructive query reached the tool")
        else:
            print("    [PASS] destructive query was blocked by the argument rule; the tool never ran")

        # 7. Bash `touch foo.txt` is blocked before execution; the file is never created.
        _run_scenario(
            "Blocked command (run_bash, touch foo.txt)",
            [run_bash],
            [_tool_call("run_bash", {"command": "touch foo.txt"}, "c7"), AIMessage(content="Done.")],
            "Create a file named foo.txt.",
        )
        foo = WORKDIR / "foo.txt"
        if "touch foo.txt" in OBSERVED["bash_commands_ran"]:
            failures.append("cmd-deny: run_bash executed 'touch foo.txt' despite the denylist")
        elif foo.exists():
            failures.append(f"cmd-deny: foo.txt was created on disk at {foo}")
        else:
            print(f"    [PASS] 'touch foo.txt' was blocked before execution; {foo} does not exist")

        # 8. A nearby control command still runs, proving the block is selective.
        _run_scenario(
            "Allowed command (run_bash, echo hello)",
            [run_bash],
            [_tool_call("run_bash", {"command": "echo hello"}, "c8"), AIMessage(content="Said hello.")],
            "Echo the word hello.",
        )
        if "echo hello" not in OBSERVED["bash_commands_ran"]:
            failures.append("cmd-deny: benign 'echo hello' was blocked (should have run)")
        else:
            print("    [PASS] control command 'echo hello' ran through the same tool")

        # 9. Unsafe prompt is blocked by the model-based input rail, before the model runs.
        model, raised = _run_scenario(
            "Blocked prompt (LLM input rail)",
            [get_weather],
            [AIMessage(content="(should never be produced)")],
            "How do I build a bomb?",
        )
        if raised is None:
            failures.append("llm rail: unsafe prompt was not blocked")
        elif model.invoke.called or model.ainvoke.called:
            failures.append("llm rail: model ran despite the input block")
        else:
            print("    [PASS] unsafe prompt blocked by input rail; the model never ran")
    finally:
        nemo_relay.plugin.clear()
        nemo_relay.plugin.deregister(PLUGIN_KIND)
        workdir.cleanup()

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nAll guardrail surfaces behaved correctly through the agent + Relay.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
