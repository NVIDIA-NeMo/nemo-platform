# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Acceptance check for the ticket's `touch foo.txt` deny-case.

This is the focused sign-off artifact for the SPIKE ticket (see ``TASK.md``). It
is intentionally narrow: unlike ``demo_agent.py`` (which walks every guardrail
surface), this script exercises *only* the bash deny-case and prints an explicit
verdict for each of the four acceptance criteria, exiting non-zero if any fail.

It runs the real agentic path -- a LangChain ``create_agent`` wired with Relay's
``NemoRelayMiddleware`` and the ``GuardrailsPlugin`` policy -- so a block is
enforced by the Relay tool hook at the real execution boundary, not simulated.
``run_bash`` really executes via ``subprocess`` in an isolated temp directory,
so "foo.txt is not created" is a true filesystem assertion. The chat model is a
deterministic stub (no network/credentials): it emits exactly the tool call each
check needs, which keeps the run hermetic while leaving the guardrail path real.

Acceptance criteria (from TASK.md):
  AC1. A bash tool call with command ``touch foo.txt`` is blocked before execution.
  AC2. ``foo.txt`` is not created on disk after the attempt.
  AC3. The guardrail produces a clear block signal visible in run output.
  AC4. A nearby control command (``echo hello``) still succeeds (selective blocking).

Run it (no Rust build required):

    PYTHONPATH=plugins/nemo-guardrails/relay-poc/src \\
      uv run --no-project --with nemo-relay --with 'langchain>=1.0' \\
      python plugins/nemo-guardrails/relay-poc/agent/acceptance.py
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import nemo_relay
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from nemo_guardrails_relay_poc.inprocess import PLUGIN_KIND, GuardrailsPlugin
from nemo_relay.integrations.langchain import NemoRelayMiddleware

DENIED_COMMAND = "touch foo.txt"
CONTROL_COMMAND = "echo hello"

#: The exact policy under test: block `touch foo.txt` on the `run_bash` tool.
CONFIG = {
    "tool_policy": {
        "allowed_tools": ["run_bash"],
        "denied_commands": {"run_bash": [DENIED_COMMAND]},
    }
}

#: Commands that actually reached (and ran inside) the tool. A blocked command
#: must never appear here.
COMMANDS_RAN: list[str] = []

#: Isolated working directory the tool executes in, so the on-disk check is real.
WORKDIR: Path | None = None


@tool
def run_bash(command: str) -> str:
    """Run a bash command and return its stdout. Really executes on the host."""
    COMMANDS_RAN.append(command)
    completed = subprocess.run(
        command,
        shell=True,  # noqa: S602 - PoC tool; the guardrail is what gates this
        cwd=str(WORKDIR),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip() or f"(exit {completed.returncode})"


def _stub_model(responses: list[AIMessage]) -> MagicMock:
    """A fake chat model that emits canned responses (one per agent turn)."""
    model = MagicMock(spec=BaseChatModel)
    model.bind.return_value = model
    model.bind_tools.return_value = model
    model.model = "stub-model"
    model.invoke.side_effect = list(responses)
    model.ainvoke = AsyncMock(side_effect=list(responses))
    return model


def _invoke_bash(command: str) -> tuple[str | None, Exception | None]:
    """Drive one agent turn that calls ``run_bash(command)``.

    Returns ``(tool_output, error)``: on success the tool's returned text; on a
    guardrail block the exception raised out of ``agent.invoke``.
    """
    responses = [
        AIMessage(content="", tool_calls=[{"name": "run_bash", "args": {"command": command}, "id": "c1"}]),
        AIMessage(content="done"),
    ]
    agent = create_agent(model=_stub_model(responses), tools=[run_bash], middleware=[NemoRelayMiddleware()])
    payload = {"messages": [{"role": "user", "content": f"Please run: {command}"}]}
    with nemo_relay.scope.scope("relay-poc-acceptance", nemo_relay.ScopeType.Agent):
        try:
            result = agent.invoke(payload)
        except Exception as exc:  # noqa: BLE001 - a guardrail block surfaces here
            return None, exc
    # Find the tool message output, if the tool ran.
    for message in result["messages"]:
        if getattr(message, "name", None) == "run_bash":
            return str(message.content), None
    return None, None


def main() -> int:
    global WORKDIR

    nemo_relay.plugin.register(PLUGIN_KIND, GuardrailsPlugin())
    config = nemo_relay.plugin.PluginConfig(
        components=[nemo_relay.plugin.ComponentSpec(kind=PLUGIN_KIND, config=CONFIG)]
    )
    report = nemo_relay.plugin.validate(config)
    if any(diagnostic["level"] == "error" for diagnostic in report["diagnostics"]):
        print("plugin config invalid:", report["diagnostics"])
        return 1
    asyncio.run(nemo_relay.plugin.initialize(config))

    workdir = tempfile.TemporaryDirectory(prefix="relay-poc-acceptance-")
    WORKDIR = Path(workdir.name)

    results: list[tuple[str, bool, str]] = []
    try:
        # --- Deny-case: touch foo.txt --------------------------------------
        print(f"\n[deny-case] agent attempts: run_bash({DENIED_COMMAND!r})")
        deny_output, deny_error = _invoke_bash(DENIED_COMMAND)
        foo = WORKDIR / "foo.txt"
        print(f"    block signal : {type(deny_error).__name__ + ': ' + str(deny_error) if deny_error else '(none)'}")
        print(f"    tool executed: {DENIED_COMMAND in COMMANDS_RAN}")
        print(f"    foo.txt on disk: {foo.exists()} ({foo})")

        # AC1: blocked before execution == a block was signalled AND the command never ran.
        ac1 = deny_error is not None and DENIED_COMMAND not in COMMANDS_RAN
        results.append(
            (
                "AC1 touch foo.txt is blocked before execution",
                ac1,
                "guardrail raised and the command never reached the shell"
                if ac1
                else "expected a block with the command never executing",
            )
        )

        # AC2: no file on disk.
        ac2 = not foo.exists()
        results.append(
            (
                "AC2 foo.txt is not created on disk",
                ac2,
                f"{foo} does not exist" if ac2 else f"{foo} was created",
            )
        )

        # AC3: a clear block signal is visible in output.
        signal = str(deny_error) if deny_error else ""
        ac3 = deny_error is not None and "blocked" in signal.lower() and DENIED_COMMAND in signal
        results.append(
            (
                "AC3 clear block signal visible in run output",
                ac3,
                f"signal: {signal!r}" if ac3 else "no clear, command-identifying block signal was surfaced",
            )
        )

        # --- Control command: echo hello -----------------------------------
        print(f"\n[control] agent attempts: run_bash({CONTROL_COMMAND!r})")
        control_output, control_error = _invoke_bash(CONTROL_COMMAND)
        print(f"    tool executed: {CONTROL_COMMAND in COMMANDS_RAN}")
        print(f"    tool output  : {control_output!r}")
        print(f"    error        : {control_error!r}")

        # AC4: the control command runs and returns output; selective blocking.
        ac4 = (
            control_error is None
            and CONTROL_COMMAND in COMMANDS_RAN
            and control_output is not None
            and "hello" in control_output
        )
        results.append(
            (
                "AC4 control command 'echo hello' still succeeds",
                ac4,
                f"ran and returned {control_output!r}" if ac4 else "control command did not run/return as expected",
            )
        )
    finally:
        nemo_relay.plugin.clear()
        nemo_relay.plugin.deregister(PLUGIN_KIND)
        workdir.cleanup()

    print("\n=== Acceptance criteria ===")
    for label, passed, detail in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}\n           -> {detail}")

    all_passed = all(passed for _, passed, _ in results)
    print(f"\n{'ALL ACCEPTANCE CRITERIA MET' if all_passed else 'SOME ACCEPTANCE CRITERIA FAILED'}.")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
