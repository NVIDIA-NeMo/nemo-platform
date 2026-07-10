<!--
SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# NeMo Guardrails × NeMo Relay — Plugin PoC

A proof-of-concept that enforces NeMo Guardrails policy **inside the agent's
execution loop** using NeMo Relay. It ships as an **in-process Relay
[language-binding plugin](https://docs.nvidia.com/nemo/relay/build-plugins/language-binding/about)**
(`GuardrailsPlugin`): your agent registers it with the embedded `nemo-relay`
runtime, and its guardrails fire on the model calls *and* the tool calls that
Relay manages.

This is the form factor that covers every surface we've built. (An
out-of-process gRPC worker form also exists — see [Secondary: gRPC worker
form](#secondary-grpc-worker-form-llm-boundary-only) — but it only covers the
LLM boundary.)

## Surfaces it enforces

| Surface | Config key | Relay hook | Effect |
|---|---|---|---|
| Tool allowlist | `tool_policy.allowed_tools` | `register_tool_conditional_execution_guardrail` | When non-empty, blocks any tool not listed before it executes |
| Tool blocklist | `tool_policy.blocked_tools` | `register_tool_conditional_execution_guardrail` | Explicit deny; blocks a listed tool even if it is allowlisted |
| Tool argument rules | `tool_policy.arguments` | `register_tool_conditional_execution_guardrail` | Blocks a call whose args hit a blocked keyword or exceed `max_length` |
| Tool argument redaction | `tool_policy.redact_args` | `register_tool_request_intercept` | PII-redacts named args before the tool runs |
| LLM input content-safety | `llm_input_rail` | `register_llm_conditional_execution_guardrail` | Blocks an unsafe prompt before the model runs |

The tool-policy checks (allowlist, blocklist, argument rules) and redaction are
deterministic (pure Python, no model). The input rail is model-based; in this
PoC it uses a **mock** content-safety check (no network) so the demo is
hermetic. Swapping in the real Guardrails `/checks` service is a drop-in change
(see [Configuration](#configuration)).

The tool-policy checks decide on the tool name and arguments alone — all that
Relay's tool guardrail hook provides today. Two further checks from the IGW tool
rails, **JSON-schema validation** and **tool-result linkage**, are deferred
because they need the declared tool schema / message history, which the tool
hook does not yet carry (see [Known gaps](#known-gaps-poc-caveats)).

## Install

Not published yet; install from source. This pulls `nemo-relay` from PyPI.

```bash
# from the repo root
uv pip install -e plugins/nemo-guardrails/relay-poc          # the plugin
uv pip install -e 'plugins/nemo-guardrails/relay-poc[langchain]'  # + LangChain, to run the demo
```

## Quickstart: activate the plugin in your agent

A consumer activates the plugin with the standard language-binding lifecycle,
then adds `NemoRelayMiddleware` to their agent so model and tool calls run
through Relay managed execution:

```python
import asyncio

import nemo_relay
from langchain.agents import create_agent
from nemo_relay.integrations.langchain import NemoRelayMiddleware

from nemo_guardrails_relay_poc.inprocess import PLUGIN_KIND, GuardrailsPlugin

# 1. Describe the policy as JSON config.
config = nemo_relay.plugin.PluginConfig(
    components=[
        nemo_relay.plugin.ComponentSpec(
            kind=PLUGIN_KIND,
            config={
                "tool_policy": {
                    "allowed_tools": ["get_weather", "web_search"],
                    "redact_args": {"web_search": ["query"]},
                },
                "llm_input_rail": {"enabled": True, "model": "mock-content-safety"},
            },
        )
    ]
)

# 2. Register + validate + initialize the plugin into this process's runtime.
nemo_relay.plugin.register(PLUGIN_KIND, GuardrailsPlugin())
report = nemo_relay.plugin.validate(config)
if any(d["level"] == "error" for d in report["diagnostics"]):
    raise RuntimeError(report["diagnostics"])
asyncio.run(nemo_relay.plugin.initialize(config))

# 3. Build your agent with the middleware. Guardrails now fire on its calls.
agent = create_agent(model=my_model, tools=[...], middleware=[NemoRelayMiddleware()])
agent.invoke({"messages": [{"role": "user", "content": "..."}]})

# 4. On shutdown:
nemo_relay.plugin.clear()
```

The plugin runs **in your agent's process**. That's what lets the tool
guardrails fire: `NemoRelayMiddleware` routes both model and tool calls through
Relay managed execution in-process, and the plugin registered its guardrails on
that same runtime.

## Configuration

Component `config` is JSON (`snake_case`):

```json
{
  "tool_policy": {
    "allowed_tools": ["get_weather", "web_search", "query_db"],
    "blocked_tools": ["transfer_funds"],
    "arguments": {
      "query_db": { "query": { "blocked_keywords": ["DROP", "DELETE"], "max_length": 200 } }
    },
    "redact_args": { "web_search": ["query"] }
  },
  "llm_input_rail": {
    "enabled": true,
    "model": "mock-content-safety"
  }
}
```

- `tool_policy.allowed_tools` — tools permitted to execute. Empty/absent allows all.
- `tool_policy.blocked_tools` — tools explicitly denied. Takes precedence over the allowlist.
- `tool_policy.arguments` — `tool_name -> arg_name -> {blocked_keywords, max_length}`. `blocked_keywords` is a case-insensitive substring match; `max_length` caps the argument's string length. Unlisted tools/args are unconstrained; if a listed tool's arguments are not a JSON object, the call fails closed (blocked).
- `tool_policy.redact_args` — `tool_name -> [arg_names]` whose string values are PII-redacted before the tool runs.
- `llm_input_rail.enabled` — turns the model-based input rail on.
- `llm_input_rail.model` — required when enabled (recorded on the check; validated by the plugin).

**Real content-safety backend (not wired in this PoC).** The plugin currently
backs the input rail with a mock check. `policy.py` already contains a
`GuardrailsServiceClient` and the async rail that call the Guardrails `/checks`
endpoint; those honor additional keys (`base_url`, `workspace`, `config_id`,
`fail_closed`, `timeout_s`, `checks_path`). Switching the plugin from the mock
to the real client is a one-line change in `GuardrailsPlugin.register`.

## Run the demo

`agent/demo_agent.py` is a runnable example of the quickstart above. It uses a
**stubbed** chat model (no network, no credentials) and the mock input-rail
check, and asserts seven outcomes:

1. `get_weather` (allowed) runs normally.
2. `web_search` arguments are PII-redacted before the tool runs.
3. `query_db` with a safe query passes the argument rules and runs.
4. `delete_account` (not on the allowlist) is blocked before it executes.
5. `transfer_funds` (blocklisted, though also allowlisted) is blocked.
6. `query_db` with a `DROP` in its query is blocked by the argument rule.
7. An unsafe prompt is blocked by the input rail before the model runs.

```bash
PYTHONPATH=plugins/nemo-guardrails/relay-poc/src \
  uv run --no-project --with nemo-relay --with 'langchain>=1.0' \
  python plugins/nemo-guardrails/relay-poc/agent/demo_agent.py
```

(`--no-project` keeps `uv` from trying to build the surrounding `nemo-platform`
workspace; the demo only needs `nemo-relay` + `langchain`.)

Expected output ends with:

```
    [PASS] safe query ran: 'SELECT name FROM users'
    [PASS] delete_account was blocked; its function never ran
    [PASS] transfer_funds was blocked by the blocklist; its function never ran
    [PASS] destructive query was blocked by the argument rule; the tool never ran
    [PASS] unsafe prompt blocked by input rail; the model never ran

All guardrail surfaces behaved correctly through the agent + Relay.
```

## Run the unit tests

```bash
PYTHONPATH=plugins/nemo-guardrails/relay-poc/src \
  uv run --no-project --with nemo-relay --with pytest \
  python -m pytest plugins/nemo-guardrails/relay-poc/tests -q
```

`tests/test_policy.py` covers the host-agnostic guardrail logic; `tests/test_plugin.py`
covers the plugin contract (`validate` diagnostics and what `register` installs).

## Run against a local Relay checkout

To test against your own NeMo-Relay branch (rather than the published wheel),
build `nemo_relay` from source. It is a maturin-built Rust extension, so this
needs a Rust toolchain and runs outside any sandbox:

```bash
cd /path/to/NeMo-Relay
uv sync --extra langchain      # compiles nemo_relay._native from your checkout
uv pip install httpx           # policy.py's runtime dep

POC=/path/to/nemo-platform/plugins/nemo-guardrails/relay-poc
PYTHONPATH="$POC/src" uv run python "$POC/agent/demo_agent.py"

# confirm you're on the local build, not PyPI:
uv run python -c "import nemo_relay; print(nemo_relay.__file__)"
```

## Layout

```
relay-poc/
  pyproject.toml          # package + deps (core: nemo-relay, httpx; extras: worker, langchain)
  src/nemo_guardrails_relay_poc/
    policy.py             # host-agnostic guardrail logic (no Relay import) — unit-testable
    inprocess.py          # GuardrailsPlugin: the in-process language-binding plugin (SHIPPABLE)
    worker.py             # WorkerPlugin: the out-of-process gRPC worker form (secondary, LLM-only)
    _predicates.py        # vendored dependency-free tool-policy predicates (allow/block/arg rules)
  relay-plugin.toml       # manifest for the gRPC worker form
  tests/
    test_policy.py        # unit tests for the policy logic
    test_plugin.py        # unit tests for the GuardrailsPlugin contract
  agent/demo_agent.py     # runnable LangChain example that activates the plugin
```

`policy.py` never imports Relay, so the guardrail logic is testable on its own.
`inprocess.py` and `worker.py` are two thin adapters that wire that logic onto
Relay's two plugin types.

## Secondary: gRPC worker form (LLM boundary only)

`worker.py` + `relay-plugin.toml` package the same policy as an out-of-process
[gRPC worker plugin](https://docs.nvidia.com/nemo/relay/build-plugins/dynamic-plugins/grpc-worker/python/about),
loaded by the CLI gateway via `nemo-relay plugins add`. Install its extra deps
with `pip install -e '.[worker]'`.

**Important limitation:** the CLI gateway only drives *LLM* calls through managed
execution — it does not drive tool execution, and the embedded runtime does not
load worker plugins. So the worker form can enforce the **input rail** but
**not** the tool guardrails. Use the language-binding plugin above for full
coverage; the worker form is for framework-agnostic, LLM-boundary-only
deployments where the agent proxies its LLM traffic through the gateway.

## Known gaps (PoC caveats)

- **Mock content-safety backend.** The input rail uses a mock check, not the real
  Guardrails `/checks` service. The real client exists in `policy.py` but isn't
  wired into `GuardrailsPlugin` yet.
- **LangChain only.** Tool guardrails require `NemoRelayMiddleware`, which is a
  LangChain middleware today. Other frameworks (e.g. NAT) would need an
  equivalent seam to route managed tool execution through Relay in-process.
- **Tool-policy checks are name/args only.** Allowlist, blocklist, and argument
  keyword/length rules run today because they need only the tool name and args.
  **JSON-schema validation** and **tool-result linkage** (both in the IGW tool
  rails) are deferred: they need the declared tool schema / message history,
  which Relay's tool guardrail hook does not currently carry. Building them means
  threading that context to the tool hook (e.g. via a subscriber that captures
  the LLM request's declared tools) — a scoped Relay change, not a redesign.
- **Shared predicate packaging.** The tool-policy predicates are *vendored* in
  `_predicates.py` (mirroring the IGW plugin's `tool_rails`) to keep the package
  dependency-light and let this branch ship as a self-contained PR independent of
  the unmerged IGW tool-rails work. Follow-up: extract the pure predicates into a
  small standalone package shared with the IGW plugin.
- **Package name.** Still `nemo-guardrails-relay-poc`; drop the `-poc` suffix
  before a real release.
