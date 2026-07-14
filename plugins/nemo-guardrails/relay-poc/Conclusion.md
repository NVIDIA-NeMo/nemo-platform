<!--
SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Conclusion — tool-level command blocking on NeMo Relay

**Question:** Can NeMo Relay's native Python hook-based guardrails enforce
tool-level command blocking in an agentic workflow? The ticket set one concrete
deny-case as the bar: block the bash command `touch foo.txt`.

**Answer: yes.** We built an end-to-end guardrails plugin for NeMo Relay that
enforces policy on an agent's tool calls at the point they run. It clears the
ticket's bar — blocking `touch foo.txt` before it executes while a control
command still runs — and, on the same agent, also covers a few surrounding
guardrail surfaces: tool allow/deny policy, argument-level rules and PII
redaction, and a model-based LLM input rail.

## What was built

A guardrails plugin for NeMo Relay that enforces policy on an agent's tool calls
at the moment each call would run. For the ticket's deny-case, it blocks the bash
command `touch foo.txt` before the command executes — the block is enforced by
the agent's runtime, not simulated — while a control command (`echo hello`) still
runs. The check is pure logic: no model call, no network, and no dependency on
the NeMo Guardrails library.

The policy is configuration, not code. Which commands are blocked, and the
allowlist, blocklist, and argument rules alongside them, is a config entry; the
agent itself is untouched, so changing what is enforced never means changing the
agent.

We validated it two ways: a focused sign-off that checks the ticket's four
acceptance criteria directly, and a broader demo that exercises seven guardrail
behaviors across the agent's model and tool boundaries in a single real agent
run. In both, the tool actually executes shell commands in an isolated directory,
so "blocked before execution" and "no file created" are verified against the
filesystem rather than asserted with a flag. Unit tests cover the matching logic
and the plugin's behavior.

## Why this matters?

Agents run tools, so the main risks live in what an agent does, not just what it
says: a destructive tool firing, data exfiltration, runaway loops or cost. These
happen inside the agent's execution loop. The inference gateway sees only the
model conversation and handles each call in isolation, so it cannot reach tool
execution or reason across steps. Relay enforces inside the loop, at the real tool
boundary — which is what this PoC demonstrates.

## Next Steps: Open Decisions

- **Where it lives.** Given the IGW/Relay runtime merge, do agentic guardrails
  live in the Relay guardrails plugin, with the inference gateway as a thin router
  into it? That keeps a single enforcement plane and one shared policy module
  rather than two that can drift. (Recommended.)
- **Implementation planning and resourcing.** Which of the guardrail surfaces below do
  we commit to, and in what order?

## Guardrail surfaces added

These are the specific surfaces the PoC demonstrates, and where each one acts in
the agent's execution lifecycle. Every check fires on the same agent run, at one
of two points: before the model runs (the LLM input rail) or before a proposed
tool call executes (the tool boundary). The **Simple demo** column marks the
surfaces exercised by the focused acceptance check; the **Full demo** exercises
all of them.

| Guardrail surface | Specific behavior demonstrated | Lifecycle point | Simple demo | Full demo |
|---|---|---|---|---|
| LLM input rail | An unsafe prompt (`"How do I build a bomb?"`) is blocked before the model runs (model-based check, stubbed in the PoC) | Pre-model | | ✓ |
| Tool allowlist | A non-allowlisted tool (`delete_account`) is blocked before it executes | Pre-tool-execution | | ✓ |
| Tool blocklist | An explicitly blocklisted tool (`transfer_funds`) is blocked even though it is on the allowlist (blocklist wins) | Pre-tool-execution | | ✓ |
| Argument keyword/length rules | A database query containing destructive SQL (`DROP`) is blocked, while a safe `SELECT` passes | Pre-tool-execution | | ✓ |
| Argument PII redaction | An email in a web-search query is redacted *before* the tool receives it (rewrite, not block) | Pre-tool-execution | | ✓ |
| Command denylist | The bash command `touch foo.txt` is blocked before execution — no file on disk — with a clear block signal | Pre-tool-execution | ✓ | ✓ |
| Selective pass-through | The control command `echo hello` runs through the same tool, proving the block targets the specific command | Pre-tool-execution | ✓ | ✓ |

Both verification scripts run the tool through a real subprocess in an isolated
temp directory, so "blocked before execution" and "no file on disk" are true
filesystem assertions rather than stubbed flags. Each script self-checks every
outcome and fails loudly on any deviation; the acceptance check additionally
prints an explicit PASS/FAIL verdict against the four ticket criteria.

## What worked well

- **The block happens at the real execution boundary.** Because the guardrail
  fires before the tool runs, "blocked" means the side effect never happened —
  confirmed on disk. The inference gateway cannot do this; it can only block the
  model reply that *proposes* a call, never the execution itself.
- **It is cheap and predictable.** The command check is pure logic with no model
  call and no network, so it is fast, deterministic, and fully testable.
- **Enforcement is configuration, not code.** Turning the rule on is a policy
  entry; the matching logic is a small, self-contained addition, and the agent
  code is untouched.
- **Matching is precise.** It blocks `touch foo.txt` and `touch ./foo.txt` but
  leaves `touch foo.txt.bak` alone, avoiding the false positives a naive
  substring rule would produce.

## Limitations

- It only works on an instrumented agent. Tool guardrails fire only when the
  agent's tool calls run through Relay's managed execution, which today means
  LangChain/LangGraph agents. Enforcing tool policy purely at the gateway (with no
  agent instrumentation) is an upstream Relay change, not something the plugin can
  do on its own.
- Today the guardrail sees only the tool name and its arguments — enough for
  command matching, but not the tool's full schema or the surrounding
  conversation, which some checks (schema validation, tool-result linkage) need.
  Passing that extra context is a contained change to Relay's tool API.
- The PoC is intentionally narrower than a production build. The command matcher
  is exact-match rather than a full shell parser, and the content-safety check is
  stubbed rather than wired to the real `/checks` client. Both are small,
  plugin-local changes — the goal was to prove the hook, not harden the policy.

## IGW vs. Relay: surface coverage

The two execution environments reach different parts of the agent. The inference
gateway (IGW) is a proxy in front of the model endpoints: it sees every LLM call,
handles each one independently with no memory across calls, and its only lever is
to block or rewrite the whole turn. Relay runs inside the agent's execution loop:
when the agent's model and tool calls go through Relay's managed execution, it
wraps each step, remembers earlier steps, and can block, rewrite, or replace an
individual step. The consequence is that everything at or past the tool-execution
boundary is reachable by Relay and invisible to IGW, because the agent's tools
never pass through the gateway.

| Agent surface | IGW | Relay |
|---|---|---|
| LLM request (the prompt) | ✅ inspect / rewrite / block | ✅ inspect / rewrite / block |
| LLM response (the reply) | ✅ inspect / rewrite / block | ✅ inspect / rewrite / block |
| Proposed tool calls | ⏳ block the whole turn | ✅ at the real execution boundary |
| Tool arguments (before the call runs) | ⏳ block the whole turn | ✅ block **or** rewrite the actual call |
| Tool execution & result | ❌ runs out of band | ✅ block / replace / inspect the real result |
| Tool-result integrity (linkage) | ⏳ validate linkage + block | ✅ via the real result |
| Retrieved documents (RAG) | ❌ | ◐ model the retriever as a tool |
| Embedder / reranker | ❌ | ◐ observe-only |
| Sub-agent boundaries | ❌ | ✅ scope-aware policy |
| Cross-step / trajectory (loops, budgets, taint) | ❌ no memory across calls | ✅ stateful policy |

Legend: ✅ supported · ◐ possible but not first-class · ❌ not possible · ⏳ IGW
branch, in review.

IGW covers the two LLM surfaces fully and the proposed-call / argument / linkage
surfaces partially — always block-the-turn, never at the real boundary.
Everything from tool execution onward (execution and result, sub-agent scope,
cross-step trajectory) is Relay-only, because those steps happen inside the loop
IGW cannot see. That boundary is the whole reason the agentic work lives in the
Relay execution path.

## Effort / risk to productionize

The hook and the enforcement point are proven, so what remains is hardening
rather than new architecture.

The real work is the policy model. Exact-match denylisting is easy to evade and
should not be trusted as a control; the production version needs to be
allowlist-first and argument-aware. The rest is smaller: deciding
block-versus-recover behavior per policy, and promoting the shared matching logic
into a single module that both the gateway and Relay paths use, so there is one
tested source of truth. The one external dependency is coverage
beyond LangChain/LangGraph, which waits on Relay exposing managed tool execution
in other agent form factors.

## Where the NeMo Guardrails library fits

Whether a check needs the library comes down to one question: does the check
itself need a model?

Deterministic checks do not. The command denylist, the allowlist and blocklist,
argument keyword and length rules, JSON-schema validation, tool-result linkage,
and regex PII redaction are all pure logic that runs inside the Relay hook and
never touches the `nemoguardrails` library.
The ticket's `touch foo.txt` block is one of these start to finish. Content
judgments do need it: content safety, jailbreak and injection detection, topic
control, and classifier-grade PII all have to read text, so they go through the
library, either in-process or behind the guardrails service's `/checks` endpoint.
That is the one thing the PoC stubs — the LLM input rail runs a mock check in
place of the real `/checks` client. So the library is a dependency of the content
pillar, not of tool policy or governance.

The library also exposes tool-rail phases, so should tool-call rails run through
it? For deterministic checks, no. A Relay tool hook is a plain callback — an
allowlist, a schema check, a command match, a budget cap all run right there. The
library's tool phases carry no policy engine of their own, so using them means
wrapping that same logic in a Colang flow just to run code the hook could call
directly. Bring the library in only when a tool rail must judge content; and if a
single policy must serve both IGW and Relay, share it as a plain Python module
rather than routing Relay through Colang.

## Proposed guardrails to support

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
