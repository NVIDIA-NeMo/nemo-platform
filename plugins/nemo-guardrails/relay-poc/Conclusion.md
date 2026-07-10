<!--
SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Conclusion — tool-level command blocking on NeMo Relay

**Question:** Can NeMo Relay's native Python hook-based guardrails enforce
tool-level command blocking in an agentic workflow, using the deny-case of
blocking the bash command `touch foo.txt`?

**Answer: yes.** A pure-Python guardrail registered on Relay's native tool hook
blocks `touch foo.txt` at the real tool-execution boundary — before the command
runs, verified by no file on disk — while a control command (`echo hello`) still
executes through the same tool.

## What was built

- **A deterministic tool guardrail on Relay's native hook**
  (`register_tool_conditional_execution_guardrail`) inside the in-process
  language-binding plugin `GuardrailsPlugin` (`inprocess.py`). No Colang, no model
  call.
- **A command-denylist matcher** (`normalize_command` / `is_command_denied` /
  `denied_command_violation` in `_predicates.py`): normalized exact match on a
  tool's command argument. Configured via `tool_policy.denied_commands`
  (`tool_name -> [commands]`) and `tool_policy.command_arg` (default `command`),
  parsed and enforced in `policy.py` after the allowlist/blocklist/argument checks.
- **A real `run_bash` tool** (in `agent/acceptance.py` and `agent/demo_agent.py`)
  that executes via `subprocess` in an isolated temp directory, so "no file on
  disk" is a true filesystem check rather than a stubbed flag.
- **Tests and runnable proof:** unit tests for the matcher and the plugin
  contract (`tests/`), a focused acceptance script, and a broader nine-surface
  demo.

## Acceptance criteria — met

`agent/acceptance.py` checks each criterion and prints PASS/FAIL, exiting
non-zero on any failure (reproduce via the README's
[PoC Acceptance Criteria](README.md#poc-acceptance-criteria)).

| Ticket criterion | How it is verified in code |
|---|---|
| `touch foo.txt` blocked before execution | the guardrail returns a block reason **and** the command is never appended to the tool's executed-commands list |
| `foo.txt` not created on disk | asserts the tool's isolated temp working directory has no `foo.txt` |
| Clear block signal in run output | surfaces `guardrail rejected: blocked: tool 'run_bash' command 'touch foo.txt' is denied` |
| Control command still succeeds | `echo hello` runs through the same `run_bash` tool and returns `'hello'` |

## What worked well

- **Enforcement at the real boundary.** The block fires before `run_bash` runs,
  so "blocked" means the side effect never happened — confirmed on disk. IGW
  cannot reach this: it can only block the reply that *proposes* a call, not the
  tool execution itself.
- **Deterministic and cheap.** Command matching is pure Python — no model, no
  network — so it is fast and easy to test and reason about.
- **Policy-as-config for the agent owner.** Enabling the deny-case is a config
  entry (`denied_commands`); the matcher itself is a small, self-contained
  addition to the plugin, not a change to agent code.
- **Selective and precise.** Normalized exact match blocks `touch foo.txt` (and
  `touch ./foo.txt`) but not `touch foo.txt.bak`, avoiding the over-matching a
  substring rule would cause — covered by unit tests.

## Limitations

- **Requires an instrumented agent.** The tool hook only fires when tools run
  through Relay managed execution — today LangChain/LangGraph via
  `NemoRelayMiddleware`. The CLI gateway drives only LLM calls, so the
  out-of-process worker form enforces the input rail but **not** tool guardrails.
- **Name/args-only context.** The tool guardrail callback receives only the tool
  name and arguments. That suffices for command matching, but checks needing the
  tool schema or message history (JSON-schema validation, tool-result linkage)
  are not reachable at this hook without threading extra context to it.
- **The matcher is not a shell parser.** Normalization only collapses whitespace
  and strips a leading `./` per token; it does not interpret quoting, env vars,
  globbing, or chaining (`;`, `&&`, `|`). So `touch foo.txt; rm -rf .` or
  `t"o"uch foo.txt` would not match. It is a named-command denylist, **not a
  security boundary**.
- **Mock content-safety backend.** The LLM input rail (a separate surface) uses a
  mock check; the real `/checks` client exists in `policy.py` but is not wired
  into the plugin.

## Effort / risk to productionize

Low-to-moderate: the hook path and enforcement point are proven; the rest is
hardening, not new architecture.

- **Command policy robustness (moderate — the main risk).** Move from exact match
  to a parsed, argument-aware, allowlist-first model. An exact-match denylist is
  trivially evadable and must not be relied on as a security control.
- **Enforcement behavior (low).** Decide block-vs-recover per policy (below).
- **Shared predicates (low).** Promote the vendored `_predicates.py` into one
  package shared with the IGW tool rails, for a single tested source of truth.
- **Framework coverage (moderate, external).** Coverage beyond LangChain/LangGraph
  depends on Relay adding managed-tool-execution seams; Relay roadmap.

## Design direction (beyond the spike)

The exact-command matcher was scoped to prove the hook and give the ticket a
concrete deny-case. It is deliberately the weakest useful mechanism; a fuller
system should layer on top of it, not generalize from it.

**Enforcement behavior**

- **Block granularity should be a policy choice, not an accident.** Today a block
  raises a `RuntimeError` that aborts the whole run. Two modes matter: *hard stop*
  (right for governance — budgets, loop caps — and catastrophic violations) and
  *soft deny* (return a `denied: <reason>` observation to the model so the agent
  can recover). Most single-tool policy blocks want soft deny.
- **Invariants:** fail closed on ambiguity; record every decision and its reason
  on the acted-on step's trace.

**Policy model**

- **Allowlist-first, not denylist** — a denylist only stops what it enumerates,
  and a shell has infinite equivalent spellings of the same effect.
- **Match at the right altitude:** tool identity (built) → structured arguments
  (executable + flags + target path) → effect/capability (writes? network?
  escalation?) → trajectory (taint, budget). Effect-level policy generalizes far
  better than string match.
- **Prefer typed tools + a sandbox over parsing arbitrary shell.** Narrow typed
  tools (`write_file(path)`) can be checked precisely; when raw shell is
  unavoidable, treat command policy as best-effort and bound consequences with an
  execution sandbox.

## Stretch goal (not done)

IGW parity — wiring an equivalent policy and confirming the same block for
`touch foo.txt` — was out of scope. The guarantee differs: IGW would block the
model turn that *proposes* the command, but since tools run outside IGW that does
not guarantee the command never executes. Guaranteeing non-execution is exactly
what Relay's tool hook provides, and what this spike validated.
