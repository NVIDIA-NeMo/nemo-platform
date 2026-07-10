<!--
SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# NeMo Guardrails × NeMo Relay — Plugin PoC

A proof-of-concept that enforces NeMo Guardrails policy **inside the agent's
execution loop** using NeMo Relay. It ships as an in-process Relay
[language-binding plugin](https://docs.nvidia.com/nemo/relay/build-plugins/language-binding/about)
(`GuardrailsPlugin`): your agent registers it with the embedded `nemo-relay`
runtime and adds `NemoRelayMiddleware`, and the plugin's guardrails then fire on
the model calls *and* the tool calls Relay manages.

> **Just here to verify the ticket?** Go straight to
> [PoC Acceptance Criteria](#poc-acceptance-criteria).

## How it works

- The plugin runs **in your agent's process** as a language-binding plugin.
- `NemoRelayMiddleware` routes the agent's model and tool calls through Relay's
  *managed execution*.
- The plugin registers guardrail callbacks on that runtime using Relay's native
  hooks. Because it sees the **real tool-execution boundary**, it can block a
  tool before it runs, rewrite its arguments, or block an unsafe prompt before
  the model runs. Tool-policy checks are deterministic (pure Python, no model);
  the content-safety input rail is model-based (mock in this PoC, no network).

Activation is the standard language-binding lifecycle; config is JSON keyed by
the [surfaces](#surfaces-it-enforces) below (see `agent/demo_agent.py` for a full
worked example):

```python
import asyncio, nemo_relay
from langchain.agents import create_agent
from nemo_relay.integrations.langchain import NemoRelayMiddleware
from nemo_guardrails_relay_poc.inprocess import PLUGIN_KIND, GuardrailsPlugin

config = nemo_relay.plugin.PluginConfig(components=[
    nemo_relay.plugin.ComponentSpec(kind=PLUGIN_KIND, config={
        "tool_policy": {
            "allowed_tools": ["run_bash"],
            "denied_commands": {"run_bash": ["touch foo.txt"]},
        },
    })
])

nemo_relay.plugin.register(PLUGIN_KIND, GuardrailsPlugin())
asyncio.run(nemo_relay.plugin.initialize(config))

agent = create_agent(model=my_model, tools=[...], middleware=[NemoRelayMiddleware()])
agent.invoke({"messages": [{"role": "user", "content": "..."}]})  # guardrails fire here

nemo_relay.plugin.clear()
```

## Surfaces it enforces

| Surface | Config key | Relay hook | Effect |
|---|---|---|---|
| Tool allowlist | `tool_policy.allowed_tools` | `register_tool_conditional_execution_guardrail` | When non-empty, blocks any tool not listed before it executes |
| Tool blocklist | `tool_policy.blocked_tools` | `register_tool_conditional_execution_guardrail` | Explicit deny; blocks a listed tool even if it is allowlisted |
| Tool argument rules | `tool_policy.arguments` | `register_tool_conditional_execution_guardrail` | Blocks a call whose args hit a blocked keyword or exceed `max_length` |
| Tool command denylist | `tool_policy.denied_commands` | `register_tool_conditional_execution_guardrail` | Blocks a shell/bash tool whose command argument matches a denied command (normalized exact match, e.g. `touch foo.txt`) before it executes |
| Tool argument redaction | `tool_policy.redact_args` | `register_tool_request_intercept` | PII-redacts named args before the tool runs |
| LLM input content-safety | `llm_input_rail` | `register_llm_conditional_execution_guardrail` | Blocks an unsafe prompt before the model runs |

## PoC Acceptance Criteria

The spike requires blocking the bash command `touch foo.txt` at the tool
boundary, with a benign control command still running. `agent/acceptance.py` is
the focused sign-off artifact: it runs the real
agentic path (`create_agent` + `NemoRelayMiddleware` + `GuardrailsPlugin`), checks
each acceptance criterion, and prints an explicit PASS/FAIL, **exiting non-zero if
any fail**. `run_bash` really executes via `subprocess` in an isolated temp
directory, so "`foo.txt` not created" is a true on-disk check.

**Prerequisites:** [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
installed and network access to PyPI. No NeMo Relay checkout or separate install
step is needed. **Run the command from the repo root** (the paths are
repo-root-relative).

```bash
# from the repo root
PYTHONPATH=plugins/nemo-guardrails/relay-poc/src \
  uv run --no-project --with nemo-relay --with 'langchain>=1.0' \
  python plugins/nemo-guardrails/relay-poc/agent/acceptance.py
```

Expected output (a harmless `PyTorch was not found` warning may print first; it
is unrelated):

```
=== Acceptance criteria ===
  [PASS] AC1 touch foo.txt is blocked before execution
           -> guardrail raised and the command never reached the shell
  [PASS] AC2 foo.txt is not created on disk
           -> .../foo.txt does not exist
  [PASS] AC3 clear block signal visible in run output
           -> signal: "guardrail rejected: blocked: tool 'run_bash' command 'touch foo.txt' is denied"
  [PASS] AC4 control command 'echo hello' still succeeds
           -> ran and returned 'hello'

ALL ACCEPTANCE CRITERIA MET.
```

The process exits `0` when all criteria pass and non-zero otherwise, so it
doubles as a check (`... acceptance.py; echo "exit=$?"`). Each line maps to the
ticket:

| Ticket acceptance criterion | How the script verifies it |
|---|---|
| A bash `touch foo.txt` call is blocked before execution | the guardrail raises a block **and** the command never reaches the shell (it is absent from the list of commands the tool actually ran) |
| `foo.txt` is not created on disk | asserts the tool's isolated temp working directory contains no `foo.txt` |
| A clear block signal is visible in run output | asserts and prints the block-reason string surfaced from the guardrail |
| A control command still succeeds | `echo hello` runs through the *same* `run_bash` tool and returns real stdout |

For the full write-up (what worked, limitations, effort/risk to productionize,
and design direction), see [Conclusion.md](Conclusion.md).

## Run the broader demo (optional)

`agent/demo_agent.py` walks **every** guardrail surface across nine scenarios
(allowlist, blocklist, argument rules, command denylist, PII redaction, input
rail), with verbose per-scenario logging of the prompt, the model's plan, and the
resulting conversation. The `touch foo.txt` deny-case is scenarios 7–8.

```bash
# from the repo root
PYTHONPATH=plugins/nemo-guardrails/relay-poc/src \
  uv run --no-project --with nemo-relay --with 'langchain>=1.0' \
  python plugins/nemo-guardrails/relay-poc/agent/demo_agent.py
```

## Run the unit tests (optional)

```bash
# from the repo root
PYTHONPATH=plugins/nemo-guardrails/relay-poc/src \
  uv run --no-project --with nemo-relay --with pytest \
  python -m pytest plugins/nemo-guardrails/relay-poc/tests -q
```

`tests/test_policy.py` covers the host-agnostic guardrail logic (including the
command matcher); `tests/test_plugin.py` covers the plugin contract.

> The `uv run --no-project --with ...` form is fully self-contained: it pulls
> `nemo-relay` and `langchain` from PyPI into an ephemeral environment, so no
> checkout or install is required. `--no-project` stops `uv` from building the
> surrounding `nemo-platform` workspace; `--with` then re-supplies the deps that
> ephemeral env drops.

## Layout

```
relay-poc/
  src/nemo_guardrails_relay_poc/
    policy.py        # host-agnostic guardrail logic (no Relay import) — unit-testable
    _predicates.py   # dependency-free tool-policy predicates (allow/block/arg/command rules)
    inprocess.py     # GuardrailsPlugin: the in-process language-binding plugin (SHIPPABLE)
    worker.py        # WorkerPlugin: out-of-process gRPC worker form (secondary, LLM-only)
  agent/
    acceptance.py    # focused sign-off: explicit PASS/FAIL per ticket acceptance criterion
    demo_agent.py    # runnable LangChain example that walks every guardrail surface
  tests/             # unit tests for the policy logic and the plugin contract
```

`policy.py` never imports Relay, so the guardrail logic is testable on its own;
`inprocess.py` and `worker.py` are thin adapters onto Relay's two plugin types.

## Known gaps (PoC caveats)

- **Command denylist is not a shell parser.** `denied_commands` normalizes
  whitespace and a leading `./`, then matches exactly. It does not interpret
  quoting, env vars, globbing, or chaining (`;`, `&&`, `|`), so it is a
  named-command denylist, **not a security boundary**. Robust shell-command
  policy needs a real parse — see [Conclusion.md](Conclusion.md).
- **Mock content-safety backend.** The input rail uses a mock check, not the real
  Guardrails `/checks` service. The real client exists in `policy.py` but isn't
  wired into `GuardrailsPlugin` yet.
- **LangChain only.** Tool guardrails require `NemoRelayMiddleware`, a LangChain
  middleware today; other frameworks (e.g. NAT) need an equivalent seam.
- **Tool-policy checks are name/args only.** JSON-schema validation and
  tool-result linkage (both in the IGW tool rails) are deferred: they need the
  declared tool schema / message history, which Relay's tool hook does not carry.

## Secondary: gRPC worker form (LLM boundary only)

`worker.py` + `relay-plugin.toml` package the same policy as an out-of-process
[gRPC worker plugin](https://docs.nvidia.com/nemo/relay/build-plugins/dynamic-plugins/grpc-worker/python/about)
loaded by the CLI gateway. The gateway only drives *LLM* calls through managed
execution, so the worker form enforces the **input rail** but **not** the tool
guardrails. Use the in-process language-binding plugin above for full coverage.
