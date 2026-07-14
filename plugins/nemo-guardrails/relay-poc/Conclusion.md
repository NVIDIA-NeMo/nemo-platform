<!--
SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Conclusion — tool-level command blocking on NeMo Relay

**Question:** Can NeMo Relay's native Python hook-based guardrails enforce
tool-level command blocking in an agentic workflow? We tested it against one
concrete deny-case: block the bash command `touch foo.txt`.

**Answer: yes.** A pure-Python guardrail on Relay's tool hook blocks
`touch foo.txt` at the point the tool would actually run, before the command
executes, confirmed by the absence of a file on disk. A control command
(`echo hello`) still runs through the same tool.

## What was built

The guardrail registers through `register_tool_conditional_execution_guardrail`
inside the in-process plugin `GuardrailsPlugin` (`inprocess.py`). It is plain
Python: no Colang, no model call, and no dependency on the NeMo Guardrails
library (see [Where the library fits](#where-the-nemo-guardrails-library-fits)).

The matcher lives in `_predicates.py` (`normalize_command`, `is_command_denied`,
`denied_command_violation`). It normalizes a tool's command argument and compares
it against a denylist by exact match. The policy is config-driven:
`tool_policy.denied_commands` maps a tool name to the commands to block,
`tool_policy.command_arg` names the argument that carries the command (default
`command`), and `policy.py` enforces it after the existing allowlist, blocklist,
and argument checks.

To make "nothing ran" a real claim and not a stubbed flag, `run_bash` (in
`agent/acceptance.py` and `agent/demo_agent.py`) shells out through `subprocess`
in an isolated temp directory, so "no file on disk" is an actual filesystem
check.

For coverage there are unit tests for the matcher and the plugin contract
(`tests/`), a focused acceptance script that checks the ticket criteria directly,
and a broader demo that walks nine agentic surfaces.

## Guardrail surfaces added

These are the specific surfaces the PoC demonstrates, and where each one acts in
the agent's execution lifecycle. Everything fires on the same `agent.invoke`
path, through `NemoRelayMiddleware` and `GuardrailsPlugin`, at one of two points:
before the model runs (LLM input rail) or before a proposed tool call executes
(the tool hook). The `acceptance.py` column marks the four surfaces exercised by
the focused ticket sign-off; `demo_agent.py` exercises all of them.

| Guardrail surface | Specific behavior demonstrated | Lifecycle point | acceptance.py | demo_agent.py |
|---|---|---|---|---|
| LLM input rail | An unsafe prompt (`"How do I build a bomb?"`) is blocked before the model runs (model-based check, stubbed in the PoC) | Pre-model | | ✓ |
| Tool allowlist | A non-allowlisted tool (`delete_account`) is blocked before it executes | Pre-tool-execution | | ✓ |
| Tool blocklist | An explicitly blocklisted tool (`transfer_funds`) is blocked even though it is on the allowlist (blocklist wins) | Pre-tool-execution | | ✓ |
| Argument keyword/length rules | A `query_db` call containing destructive SQL (`DROP`) is blocked, while a safe `SELECT` passes | Pre-tool-execution | | ✓ |
| Argument PII redaction | An email in a `web_search` query is redacted *before* the tool receives it (rewrite, not block) | Pre-tool-execution | | ✓ |
| Command denylist | The bash command `touch foo.txt` is blocked before execution — no file on disk — with a clear block signal | Pre-tool-execution | ✓ | ✓ |
| Selective pass-through | The control command `echo hello` runs through the same `run_bash` tool, proving the block targets the specific command | Pre-tool-execution | ✓ | ✓ |

Both `acceptance.py` and `demo_agent.py` run `run_bash` through a real
`subprocess` in an isolated temp directory, so "blocked before execution" and "no
file on disk" are true filesystem assertions rather than stubbed flags. Each
script self-checks every outcome and exits non-zero on any failure;
`acceptance.py` additionally prints an explicit PASS/FAIL verdict against the four
ticket criteria.

## What worked well

The block happens at the real execution boundary. Because it fires before
`run_bash` runs, "blocked" means the side effect never happened, and we confirm
that on disk. IGW cannot do this; it can only block the model reply that
*proposes* a call, never the execution.

It is cheap and easy to reason about. Command matching is pure Python with no
model and no network, so it is fast and fully unit-testable.

Turning the deny-case on is a config change, not a code change. It is an entry in
`denied_commands`; the matcher is a small, self-contained addition to the plugin,
and the agent code is untouched.

Matching is precise. Normalized exact match catches `touch foo.txt` and
`touch ./foo.txt` but leaves `touch foo.txt.bak` alone, so it avoids the false
positives a substring rule would produce. Tests cover this.

## Limitations

- It only works on an instrumented agent. The tool hook fires only when tools run
  through Relay managed execution, which today means LangChain/LangGraph via
  `NemoRelayMiddleware`. The gateway form drives LLM calls only, so as an
  out-of-process worker it can enforce the input rail but not tool guardrails.
  Closing this needs the Relay gateway to drive `tool_call_execute` — an upstream
  Relay change, not something the plugin can do on its own.
- The callback sees only the tool name and arguments. That is enough for command
  matching, but checks that need the tool schema or the message history
  (JSON-schema validation, tool-result linkage) are not reachable here today.
  This can be fixed: we can extend the Relay codebase's tool API to pass the extra
  context we need (the tool schema, prior messages).
- The PoC is deliberately narrower than a production build would be, and every
  narrow spot is ours to widen. The command matcher is exact-match, not a shell
  parser, so it is a named-command denylist rather than a security boundary; the
  content-safety check is stubbed rather than wired to the real `/checks` client.
  Both are contained, plugin-local changes — the point here was to prove the hook,
  not to ship the hardened policy.

## Where the NeMo Guardrails library fits

Whether a check needs the library comes down to one question: does the check
itself need a model?

Deterministic checks do not. The command denylist (`is_command_denied`), the
allowlist and blocklist, argument keyword and length rules, JSON-schema
validation, tool-result linkage, and the regex PII redaction in `policy.py` are
pure logic that runs inside the Relay hook and never imports `nemoguardrails`.
The ticket's `touch foo.txt` block is one of these start to finish. Content
judgments do need it: content safety, jailbreak and injection detection, topic
control, and classifier-grade PII all have to read text, so they go through the
library, either in-process or behind the guardrails service's `/checks` endpoint.
That is the one thing the PoC stubs — the LLM input rail runs a mock check in
place of the real `/checks` client. So the library is a dependency of the content
pillar, not of tool policy or governance.

The library also exposes `tool_input` and `tool_output` rail phases, which raises
the question of whether tool-call rails should run through it too. For
deterministic checks, no. A Relay tool hook is a plain Python callback that gets
the tool name and arguments and returns a block reason, a rewrite, or a replaced
result — an allowlist, a schema check, a command match, a budget cap all run
right there. The library's tool phases add nothing: they carry no policy engine,
so the real check is still a Colang flow calling a Python action you register
(exactly how the IGW tool rails work). Routing a deterministic check that way
means authoring a flow and loading the library just to run code the hook would
have called directly. IGW needs that wrapper because a guardrails config is its
only extension point; Relay has the hooks, so the wrapper is dead weight. Bring
the library in only when a tool rail must judge content, and call it through the
content-check seam from inside the hook. If a single policy has to serve both IGW
and Relay, share it as a plain Python module — IGW wraps it in Colang, Relay
calls it directly — rather than dragging Relay through Colang.

## Effort / risk to productionize

The hook and the enforcement point are proven, so what remains is hardening
rather than new architecture.

The real work is the policy model. Exact-match denylisting is easy to evade and
should not be trusted as a control; the production version needs to be
allowlist-first and argument-aware. The rest is smaller: deciding
block-versus-recover behavior per policy (below), and promoting `_predicates.py`
into one module shared with the IGW tool rails so there is a single tested source
of truth. The one external dependency is coverage beyond LangChain/LangGraph,
which waits on Relay exposing managed-tool-execution seams in other form factors.

## Design direction (beyond the spike)

The exact-command matcher existed to prove the hook and give the ticket a
concrete deny-case. It is the simplest thing that works, and a real system should
sit on top of it rather than grow out of it.

**Build on what Relay already enforces.** We are not starting from zero. The
current Relay guardrails plugin already enforces LLM input and output rails
(surfaces #1 and #2). The agentic work extends outward from there to the tool and
trajectory surfaces that plugin does not cover, and reuses the input/output rail
enforcement that is already in place rather than reimplementing it.

**Enforcement behavior.** A block currently raises `RuntimeError`, which aborts
the run. That should be a policy choice. A hard stop is right for governance
limits (budgets, loop caps) and for genuinely catastrophic violations. A soft
deny, which returns a `denied: <reason>` result the model can see and work
around, is what most single-tool blocks want. Whichever fires, the rule should
fail closed when it is unsure, and record the decision and its reason on the
trace for the step it acted on.

**Policy model.** Prefer an allowlist to a denylist, since a denylist only stops
what it names and a shell has endless equivalent spellings for the same effect.
Match at whatever level generalizes best: tool identity (done) is the coarsest,
structured arguments (executable, flags, target path) is better, and effect or
capability (does this write? reach the network? escalate?) generalizes furthest,
with trajectory-level checks (taint, budget) layered on top. Where it is
possible, prefer narrow typed tools like `write_file(path)`, which can be checked
exactly, over parsing arbitrary shell; when raw shell is unavoidable, treat
command policy as best-effort and lean on a sandbox to bound the damage.

## Implementation checklist — guardrails to support

Framed by the type of guardrail and the agent surface it acts on, working
outward from the model boundary to the tool boundary to the whole run. The PoC
proved the tool-call policy surface; the rest is what a full agentic layer should
cover.

- [ ] **LLM input/output content rails.** Screen the prompt and the model's
      reply for unsafe content, jailbreaks, prompt injection, off-topic
      requests, and PII. Already enforced by the current Relay guardrails plugin;
      reuse it rather than rebuild.
- [ ] **Tool-call policy.** Decide whether a proposed tool call may run, from the
      tool identity and its arguments — allow/deny by tool, argument rules,
      command policy — and block or rewrite the call before it executes. The PoC
      covers the block-and-rewrite core; maturing the policy model
      (allowlist-first, argument-aware) is the main open work.
- [ ] **Tool argument content checks.** Judge the content of an outbound argument
      (redact PII from a search query, catch exfiltration in a query) and rewrite
      or block before the call runs.
- [ ] **Tool result guardrails.** Inspect, sanitize, or replace the real tool
      result before it re-enters the model — strip injected instructions from
      fetched pages, redact PII from records, cap oversized output.
- [ ] **Tool-result integrity.** Verify each tool result links back to a real
      prior call, so spoofed, orphaned, or duplicated results cannot re-enter the
      conversation.
- [ ] **Cross-step exfiltration defense.** Track untrusted content as it enters a
      run and block sensitive sinks (e.g. `send_email`, outbound requests) once
      tainted input has been seen. The flagship capability the inference gateway
      cannot express.
- [ ] **Scope-aware / sub-agent policy.** Apply different policy by where in the
      agent tree a step runs — a tool allowed for the orchestrator but denied
      inside an untrusted sub-agent.
- [ ] **Governance: run limits.** Keep a run bounded with loop detection and
      per-run tool, token, and cost budgets — reliability and cost control rather
      than content safety.

Deferred:

- [ ] **Retrieval / embedder / reranker guardrails.** Screen retrieved documents
      and other non-LLM steps, such as injection detection over RAG chunks.
      Reachable today by modeling them as tools; first-class support is later
      work.
