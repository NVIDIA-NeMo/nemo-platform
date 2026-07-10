<!--
SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# NeMo Guardrails × Relay — Plugin Design

_Status: design / PoC. Companion to [`AGENTIC-GUARDRAIL-SURFACES.md`](AGENTIC-GUARDRAIL-SURFACES.md)
(the surface catalog this doc builds on) and the PoC in this directory._

## 1. What we are building

A NeMo Relay **guardrail _and_ governance layer** that enforces policy **inside
the agent's execution loop**. It owns two pillars over the same managed
execution (see [`USE-CASES.md`](USE-CASES.md)):

- **Guardrails** — safety / policy / security enforcement: content rails,
  tool-policy rails, injection defense, cross-step exfiltration defense.
- **Governance** — reliability / cost enforcement: loop, step, and budget caps.

It grows into the **successor to Relay's built-in `nemo_guardrails` plugin** —
same config surface, but able to enforce on tool execution and cross-step
trajectory (which the built-in cannot do well), and with the governance pillar
the built-in never had. Pure eval/testing affordances (dry-run) are explicitly
out of scope; they use the same hooks for a non-enforcement purpose.

The single design decision everything else follows from:

> **Split policy by whether the check itself needs a model.**
> Deterministic checks run as plain in-process Python at Relay's hooks.
> Model-backed checks call a guardrails engine through one injected seam.

This maps directly onto the **Rail type** column in the surface catalog
(`Deterministic` / `Model-backed` / `Mixed`).

## 2. Two engines

### Deterministic engine (always in-process, no external call)

Allowlist, argument keyword/length rules, JSON-schema validation, tool-result
linkage, PII redaction, budgets, loop/taint bookkeeping. Pure functions, wired
straight into Relay's callback hooks.

This is the **shared deterministic core**: the *same* logic the shipped IGW
plugin runs. Today the IGW plugin wraps it in NeMo Guardrails custom actions +
Colang (because IGW's only hook is the LLM boundary); Relay exposes the tool
boundary natively, so the wrapping is dropped and the pure core is imported
directly. Target: one tested module, two thin adapters (IGW actions, Relay
hooks). See [reconciliation](#5-relationship-to-the-igw-plugin).

### Model-backed engine (pluggable, one seam)

Content safety, jailbreak/injection, topic control, self-check. These call an
LLM/classifier, so the plugin delegates them through a single injected check
function (today `build_llm_input_rail(cfg, check_fn)` in `policy.py`).

- **Now — `remote`:** `check_fn` POSTs to the NeMo Guardrails **service**
  (`/checks`). Light worker, centralized policy in the entity store.
- **Later — `local`:** swap in a `check_fn` backed by in-process `nemoguardrails`
  + the IGW plugin's `LLMRailsCache`. This is a latency/offline optimization, not
  a required mode. `remote` vs `local` is an implementation detail behind the
  seam — **not** something the rest of the plugin designs around.

## 3. How it integrates with Relay

The plugin is an **out-of-process gRPC worker** (`WorkerPlugin`). Relay's Rust
core spawns it and calls its registered hooks during managed execution. Each
surface from the catalog maps to a Relay registration:

| Surface (catalog #) | Relay hook | Engine | PoC status |
|---|---|---|---|
| LLM request (#1) | `register_llm_conditional_execution_guardrail` / `_request_intercept` | model-backed | ✅ input rail via `/checks` |
| LLM response (#2) | `register_llm_execution_intercept` (+ sanitize for obs) | model-backed + deterministic PII | planned |
| Proposed calls / tool args (#3, #4) | `register_tool_conditional_execution_guardrail` + `_request_intercept` | deterministic core (+ optional content) | ✅ allowlist block + arg redaction |
| Tool execution & result (#5) | `register_tool_execution_intercept` | deterministic (size/shape/PII) + content | planned |
| Tool-result integrity (#6) | `register_llm_request_intercept` (message-shape) | deterministic (linkage) | planned |
| Sub-agent boundaries (#9) | `register_subscriber` + scope-aware conditional | deterministic + content | future |
| Trajectory (#10) | `register_subscriber` + conditional | deterministic | future |

**The call area, per surface:** deterministic hooks make **no** external call —
they *are* the guardrail. Model-backed hooks call the engine through `check_fn`.
"IGW already owns content" is not a mode — it is simply leaving the `#1`/`#2`
content surfaces disabled; the tool/trajectory surfaces stay on regardless,
because IGW never sees tool execution.

## 4. How a user with an agent uses it

Relay hooks only fire on **managed execution**, so the user instruments their
agent once, then enables the plugin.

1. **Instrument the agent.** LangChain/LangGraph via `NemoRelayMiddleware`
   (routes model + tool calls through Relay); NAT and CLI paths as they mature.
   See `agent/demo_agent.py` for a runnable in-process example.
2. **Enable + configure the plugin.**
   `nemo-relay plugins add ./relay-plugin.toml` → `plugins enable <id>`, then a
   component config block (allowlist, redaction, `llm_input_rail`, …). Python
   workers install via `plugins add` (which provisions the venv); they cannot be
   referenced directly from `plugins.toml`.
3. **Run.** Tool guardrails fire wherever the agent's tools run through managed
   execution; the model-backed LLM rail fires on managed LLM calls (e.g. proxied
   through the `nemo-relay --bind` gateway).

**Form-factor caveat (today):** the `nemo-relay --bind` gateway drives only the
**LLM** chain, not `tool_call_execute`. So tool-surface enforcement needs the
agent's tools to run through managed execution **in-process** (the LangChain
middleware path). This is why the shippable form is the in-process
language-binding plugin (full coverage); the out-of-process worker covers the
LLM boundary only.

## 5. Relationship to the IGW plugin

The IGW plugin (`nemo_guardrails_plugin`) stays the right tool for the
**stateless inference boundary** and needs zero agent instrumentation. This
plugin is **additive** for instrumented agents (catalog §4 "net-new
capabilities"). They should share one deterministic core:

- **Shared (extract into a library-free module):** allowlist / arg-rule / schema
  / linkage predicates + PII redaction.
- **IGW-only glue (not ported):** `@action` signatures, `flows.co`, `register_action`.
- **Reused only in `local` mode:** `LLMRailsCache`.

## 6. Build order

1. **Extract the shared deterministic core** and rewire both IGW `actions.py`
   and the Relay worker onto it. _(Keystone — unblocks the rest.)_
2. **Add the tool `#5` and LLM `#2` surfaces** to the worker (execution
   intercepts; deterministic redaction + `check_fn` seam for content).
3. **Config/CLI parity** with the built-in `nemo_guardrails` (per-surface
   enables, priority, policy) so it is enable-able the same way.
4. **Trajectory / sub-agent surfaces** (`#9`, `#10`) via subscribers.
5. **First-party form factor** so it can supersede the built-in `kind`.

`local` mode and the retrieval/embedder surfaces (`#7`, `#8`) are explicitly
deferred.
