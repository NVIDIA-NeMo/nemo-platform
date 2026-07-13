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

## Acceptance criteria — met

`agent/acceptance.py` checks each criterion, prints PASS/FAIL, and exits non-zero
on any failure.

| Ticket criterion | How it is verified in code |
|---|---|
| `touch foo.txt` blocked before execution | the guardrail returns a block reason and the command is never appended to the tool's executed-commands list |
| `foo.txt` not created on disk | asserts the tool's isolated temp working directory has no `foo.txt` |
| Clear block signal in run output | surfaces `guardrail rejected: blocked: tool 'run_bash' command 'touch foo.txt' is denied` |
| Control command still succeeds | `echo hello` runs through the same `run_bash` tool and returns `'hello'` |

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
  This is addressable: we can extend the Relay tool hook to pass the extra
  context we need (the tool schema, prior messages). It is an upstream change to
  Relay's tool API rather than plugin-only work, but the hook machinery is
  generic and the change is contained.
- The matcher is not a shell parser. Normalization collapses whitespace and
  strips a leading `./` per token, and nothing more. It does not understand
  quoting, environment variables, globbing, or chaining, so `touch foo.txt; rm
  -rf .` and `t"o"uch foo.txt` slip past. This is a named-command denylist, not a
  security boundary. This one is ours to fix, and the fix is the policy-model work
  below (allowlist-first, argument-aware), not more elaborate string matching.
- The content-safety surface is stubbed. The LLM input rail uses a mock check;
  the real `/checks` client is present in `policy.py` but is not wired into the
  plugin yet. Wiring it is plugin-only work — the client already exists.

## Where the NeMo Guardrails library fits

Whether a check needs the library comes down to one question: does the check
itself need a model?

The deterministic Python checks do not. The command denylist (`is_command_denied` in `_predicates.py`), the
allowlist and blocklist, the argument keyword and length rules, JSON-schema
validation, tool-result linkage, and the regex PII redaction in `policy.py` are
all pure logic. They run as ordinary Python inside the Relay hook and never
import `nemoguardrails`. Everything the ticket asked for lands here: the
`touch foo.txt` block is a deterministic tool check start to finish, with no
library in the picture.

The rest do. Content safety, jailbreak and injection detection, topic control,
self-check, and classifier-grade PII all judge text, which takes a model or
classifier. These go through the NeMo Guardrails library, either in-process or
behind the guardrails service's `/checks` endpoint, which wraps it. In the PoC
that is the LLM input rail, and it is the one thing we stub: `GuardrailsPlugin`
registers `mock_content_safety_check` in place of the real `/checks` client,
which already exists in `policy.py` but is not wired in.

So the library is a dependency of the content pillar, not of tool policy or
governance. The tool-execution guarantee, the point of the spike, is the hook
plus our own logic and owes the library nothing. The library earns its place only
when something has to judge text, wherever that text sits: a prompt, a tool
argument, or a tool result.

The library also has `tool_input` and `tool_output` rail phases, so it is worth
asking whether tool-call rails should run through it as well. For deterministic
checks, no. Relay's tool hooks are plain Python callbacks: they receive the tool
name and arguments and return a block reason, a rewrite, or a replaced result.
An allowlist, an argument-schema check, a command match, result linkage, a
budget cap are ordinary logic, and they run right there in the callback. The
library adds nothing to them. Its tool rail phases have no policy engine of their
own; the real check is still a Colang flow the developer writes that calls a
Python action they register, which is exactly how the IGW tool rails are built.
Using that path for a deterministic check means writing a flow, registering an
action, and loading the library just to run code the hook could have called
directly. IGW has to work that way because a guardrails config is its only
extension point. Relay has the hooks, so the Colang wrapper is dead weight.

The same split applies at the tool boundary. Keep deterministic tool policy in
Python at the hook, and bring in the library only when a tool rail has to judge
content, such as whether an argument or a result is unsafe, an injection, or
PII. Call it through the content-check seam from inside the hook, not through the
library's tool rail phases. The one case for the Colang path is authoring a
single policy that both IGW and Relay enforce, and even then the cleaner way to
share is a plain Python module: IGW wraps it in Colang, Relay calls it directly,
and the logic stays in one place without dragging Relay through Colang.

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
