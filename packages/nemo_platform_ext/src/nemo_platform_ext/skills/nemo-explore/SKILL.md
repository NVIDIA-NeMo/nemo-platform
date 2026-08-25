---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: nemo-explore
description: Captures what a NeMo Platform agent should do before any code or YAML. Explores the user's codebase and docs first, fills in every Ethos field it can infer, then asks the user only for the gaps — including the intent it cannot read from source, such as constraints, trade-offs, and principles. Output feeds nemo-ethos. Use over generic brainstorming for any NeMo Platform agent design conversation.
triggers:
  - design my agent
  - what should my agent do
  - help me think through the agent
  - I want to build an agent
  - agent design
  - explore the agent
  - figure out what my agent needs
  - bootstrap AGENT_DESCRIPTION
  - onboard my existing agent
not-for:
  - nemo-skill-selection (use to dispatch when intent is unclear)
  - nemo-ethos (use to write the Ethos file once explore is done)
  - nemo-build-agent (use after the Ethos exists)
  - nemo-model-selection (use for the model question in step 5; explore delegates to it)
  - superpowers:brainstorming (use for design work unrelated to NeMo Platform)
preconditions:
  - nemo_cli_available
compatibility: nemo-platform >= 0.1.0; dialogue-driven with read-only pre-flight (`ls`, `find`, `Read`); safe under any sandbox; works offline; output is a structured conversation handed to nemo-ethos.
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Read, Glob, Grep, Bash]
---

# NeMo Platform agent explore

Capture what the agent should do before any code or YAML. Product mission and
user goals matter more than implementation inventory. The output of this skill
is the data that `nemo-ethos` writes into `agents/<name>-ethos/ETHOS.md` —
the durable contract that downstream optimization agents read as their primary
context. Underspecified input here directly degrades the quality of generated
Insights and PRs downstream.

This skill is **explore-first, gap-fill second**. You do not interview the
user from scratch. You scan the codebase and docs, infer what you can against
the Ethos schema below, present what you found, and ask the user only for the
fields you could not fill.

The division of labor is: **infer implementation, ask for intent.** Almost
everything about what the agent *is* can be read from source. Nothing about what
the developer *wants* can be. Constraints, trade-offs, and principles are never in
the code, so they are the questions worth spending the user's attention on.

## The schema you are filling

The Ethos has five front-matter fields and fifteen body sections, tiered by how
badly a consumer needs them. One section is a hard requirement: handoff to
`nemo-ethos` is blocked until `Role` is concrete.

**Front matter**

| Field | Required | Guidance |
| :---- | :---- | :---- |
| `schema_version` | yes | Always `2` for new files. `nemo-ethos` fills this at write time. |
| `name` | yes | Canonical agent name. Use the directory or workflow name if obvious; ask if not. |
| `created_timestamp` | yes | ISO 8601 timestamp for when the Ethos is created. `nemo-ethos` fills this at write time. |
| `author` | yes | Human or agent that created the Ethos. `nemo-ethos` fills this from the current author context when known; ask only if ambiguous. |
| `owner` | optional | Accountable human or team for the approvals named in `Constraints` or `Change Scope`. Ask only if those sections name an approval. |

**Body sections** (in canonical order)

Tier legend: **core** fails to parse when missing, **intent** warns and blocks
strict optimizer runs, **optional** can be omitted silently.

| # | Section | Tier | What "good" looks like |
| :---- | :---- | :---- | :---- |
| 1 | Role | **core** | One concrete sentence describing the role this agent plays. Example: "answer IT helpdesk questions about VPN, password reset, and software access." Vague answers ("help with stuff") are useless downstream. |
| 2 | Purpose & Outcomes | core | Two labeled parts. **Mission:** why the agent exists, what user value it provides, and the product or workflow context it serves — not a restatement of implementation mechanics. **Outcome:** the external result it is accountable for, with the measurable target and who owns that number. A mission with no outcome cannot be optimized; an outcome with no mission gets optimized in the wrong direction. Say so plainly when the agent is internal tooling with no business metric. |
| 3 | Scope | core | Audience, 3-6 task categories, expected in-scope work, and explicit out-of-scope work/non-goals. |
| 4 | Tools | core | Tools, APIs, and knowledge sources the agent can use, or "Prompt-only." Group related helpers by capability or source. Capture only behaviorally important purpose, credentials/scopes, side effects, freshness, and expected failures. |
| 5 | Harness | optional | Describe the selected or likely harness, the source framework where one exists, and the behavior the harness owns: loop, tool dispatch, context/state, guardrails, observability, verification, and runtime. Record a framework as an observation, not as proof of lifecycle compatibility. Use `_(none)_` if selection should wait until config authoring. |
| 6 | Behavior | core | Behavioral rules and boundaries: refusal/escalation policy, tone, safety/compliance requirements, accepted limitations, and known non-goals. Hard external limits belong in `Constraints`. |
| 7 | Principles | intent | How the agent should decide when no rule in `Behavior` covers the case: which way to err on an ambiguous request, what it protects even at some cost to the answer, and whose interest wins when the user and the business disagree. Two or three concrete judgment calls. "Helpful, harmless, and honest" is not an answer — it is true of every agent. |
| 8 | Success Criteria | core | What good production behavior looks like, independent of current evals: mission-level outcomes, quality standards, escalation quality, accuracy expectations, and examples of success. Rank them when some matter more. |
| 9 | Trade-offs | intent | How to choose when two improvements conflict. Needs three things: hard gates never traded away, a priority order over the rest (quality, latency, cost, reliability), and regressions that are unacceptable even alongside a headline win. "Balance quality and cost" is not an answer. |
| 10 | Constraints | intent | Hard external bounds no change may cross: approved providers/models/regions, data residency and handling, compliance obligations, production cost ceilings and latency SLOs, and changes that need human sign-off. Give the current measured figure next to a ceiling when you know it. Usually organizational, which is why the code cannot supply them. |
| 11 | Evaluation Setup | intent | Current validation setup: how to run it, what datasets/checks it uses, what scorers/metrics measure, pass/fail thresholds, and known coverage gaps relative to the success criteria. If no eval suite exists, say so explicitly. |
| 12 | Metric Semantics | optional | What ambiguous or load-bearing metric and telemetry field names actually mean, and which claims they do not support. Only worth filling when a name could be misread. |
| 13 | Change Scope | core | A permissions list — what the optimization loop may modify. Each lever takes `yes`, `no`, or `with-approval`. Defaults: system prompt, tools, middleware, inference params, model swap within mode, skills. Fine-tuning is never on by default. The loop never edits the Ethos itself. |
| 14 | Vision | optional | Where the agent is headed: an intention beyond today's job, plus one or two concrete use cases it should grow into but does not serve yet. That last part marks what `Scope` excludes *for now* rather than on principle. Omit rather than pasting a dated backlog. |
| 15 | Open Questions | optional | Open facts that affect safe use, evaluation, or modification of the agent. Remove once answered. |

Known issues / failure patterns are tracked as first-class Insight entities by
the insights plugin — do not duplicate them into the Ethos.

## Pre-flight

Check whether an Ethos already exists for this agent. If `agents/<name>-ethos/ETHOS.md`
is present, ask the user whether they want to edit the existing Ethos or start
over. If they want to edit, route to `nemo-ethos` directly.

```bash
ls agents/*-ethos/ETHOS.md 2>/dev/null || echo "no ethos yet"
```

If you find a legacy `agents/*-spec/AGENT-SPEC.md` instead, the agent predates
the rename. Tell the user to run `nemo agents ethos migrate`, then continue from
the migrated file rather than starting over.

```bash
ls agents/*-spec/AGENT-SPEC.md 2>/dev/null && echo "legacy contract — run: nemo agents ethos migrate"
```

## Step 1 — Explore the codebase

Time-box this to ~5 minutes of tool use. Read first, ask second. Greenfield
projects will turn up nothing here, which is fine — move to step 2 and ask
the user the full set of unfilled fields.

1. **Find agent definitions and entry points.** Look for Platform
   `agent.yaml`, NAT workflow YAMLs, supported harness configuration, Python
   agent builders, system prompts, skills, and tool definitions:

   ```bash
   find . -maxdepth 5 -type f -name "agent.yaml" 2>/dev/null
   find . -maxdepth 4 -type f \( -name "*.workflow.yaml" -o -name "*.workflow.yml" \) 2>/dev/null
   find . -maxdepth 4 -type d -name "agents" 2>/dev/null
   ```

   Then use `Glob` / `Grep` to find `nemo-agents-spec-v1`,
   `default_harness`, `codex`, `hermes`, `deepagents`, `claude`, `langgraph`,
   `StateGraph`, `create_react_agent`, `system_prompt`, skills, MCP servers,
   and tool definitions.

2. **Find design context.** Look for `README.md`, `AGENTS.md`,
   product/design/planning docs, launch notes, and anything in `docs/`. Read
   docs that describe goals and user value before implementation details when
   they look agent-relevant.

3. **Map findings to schema fields.** As you scan, hold a running mental
   table of what you can fill from the code/docs. Be honest about confidence:
   "inferred from system prompt" is different from "confirmed by the user."

4. **Choose the model.** Hand off to `nemo-model-selection` after the
   code/docs scan. That skill profiles the agent on tool density, primary
   capability, and deployment, then recommends a specific NIM model with a
   plain-English explanation grounded in what the model is actually good at.
   Return here with the chosen model string, which `nemo-build-agent` writes
   into `agent.yaml`. The Ethos has no `Model` section — record the *permitted*
   providers and model families in `Constraints` instead, since the config
   already carries the model in use and it changes without touching the Ethos.
   If the user wants to skip the conversation, the default is cloud,
   `nvidia/llama-3.3-nemotron-super-49b-v1` — announce that and move on.
   Local NIMs require host-gpu mode.

   Typical inferences per field:

   - **name** — directory name, workflow name, or top-level package name.
   - **Role** — first paragraph of README, system prompt preamble, or
     top-level docstring. Often partial; usually needs user confirmation.
   - **Purpose & Outcomes** — mission from product docs, README motivation,
     system prompt preamble, or workflow context; prefer explicit goal context
     over implementation-only inference. The outcome is rarely in code, so look
     for OKR or launch notes, dashboards, and README motivation that name a
     metric, and ask when the scan turns up nothing.
   - **Scope** — audience from docs or prompts; categories from enumerated
     capabilities or named tool clusters; in/out boundaries from prompt rules.
   - **Tools** — from `@tool` decorators, NAT tool registry,
     `create_react_agent(tools=[...])`, retrieval/corpus config, or API clients.
     Group low-level helpers when they share credentials, side effects,
     freshness, and failure modes.
   - **Harness** — infer from `default_harness` and `harnesses` in
     `agent.yaml`, adapter configuration, NAT workflow YAML, service
     entrypoints, CLI commands, Dockerfiles, notebooks, or deployment configs.
     Capture behaviorally relevant capabilities, not low-level settings. If
     there is no selection yet, leave it unresolved for `nemo-agent-config`.
   - **Behavior** — system prompt rules ("never give medical advice"),
     refusal/escalation policy, tone, accepted limitations, and non-goals.
   - **Success Criteria** — desired production outcomes, product goals,
     quality standards, escalation quality, accuracy expectations, and examples
     of successful behavior.
   - **Trade-offs** — not in the code; ask the user in step 1.5.
   - **Constraints** — mostly not in the code, but scan for partial evidence
     worth confirming: a pinned gateway base URL or provider allowlist, region
     settings, redaction or PII middleware, timeout and token ceilings, and
     compliance notes in docs. Treat findings as a starting draft to confirm,
     never as the complete list.
   - **Evaluation Setup** — Makefile targets, scripts, CI config, eval YAMLs,
     metric definitions, thresholds, and coverage notes.
   - **Metric Semantics** — from scorer definitions, metric names in eval
     configs, and telemetry field names. Fill only the entries whose meaning is
     genuinely ambiguous from the name.
   - **Change Scope** — not in the code; ask the user.
   - **Principles** — not in the code; ask the user in step 1.5. A prompt may
     hint at one, but a prompt is the implementation, not the intent behind it.
   - **Vision** — not in the code. Roadmap docs, design notes, or a README's
     future-work section sometimes carry it. Omit rather than guessing.
   - **Open Questions** — TODOs / FIXMEs in agent-adjacent code that
     affect safe use, evaluation, or modification.

## Step 1.5 — The intent round

The code told you what the agent is. It cannot tell you what the developer
wants, and the intent-tier sections exist precisely to capture what no scan can
recover. This is the one place where asking is mandatory rather than a fallback.

Ask these four questions in **a single message**, and say up front why you are
asking: an optimizer that does not know the constraints will spend real money
proposing changes the user cannot ship.

> "The code told me what your agent does. Four things it can't tell me, and
> they're what stop an optimizer from proposing changes you can't ship:
>
> 1. **Outside context** — is there anything explaining the goals, users,
>    success bar, or business motivation that isn't in the repo? Paste or link
>    it, or tell me there isn't any.
> 2. **Hard constraints** — anything that's off the table no matter how well it
>    performs? Approved model providers or regions, data that can't leave a
>    boundary, compliance rules, a cost-per-run or latency ceiling in
>    production, changes that need sign-off.
> 3. **Trade-offs** — when two improvements conflict, how should I choose? What
>    can never be traded away, and how would you rank quality, latency, and cost
>    after that?
> 4. **Principles** — when a request doesn't fit any rule you've written, which
>    way should the agent err? Ask, assume, or refuse? And is there anything it
>    should protect even when that makes the answer worse?"

Rules for this round:

- **One message, four questions.** Do not serialize them into an interview.
- **Accept "I don't know" and move on.** Write the honest gap into `Open
  Questions` rather than inventing a plausible constraint. A fabricated
  constraint is worse than a missing one: it silently removes good candidates.
- **Reject generic virtues for `Principles`.** "Helpful, harmless, and honest"
  is true of every agent and gives a downstream reader nothing. Ask for the
  judgment call instead: what does this agent do that a careless version of it
  would not? If nothing comes back, leave the section out.
- **Do not collect run limits.** A per-experiment spend cap or wall-clock limit
  configures one optimization run and belongs to the tool running it, not to a
  durable contract. If the user volunteers one, keep the standing policy behind
  it — a production cost ceiling goes in `Constraints`, an approver goes in
  `Constraints` or `Change Scope` — and drop the number.
- **Push once on a non-answer for trade-offs.** "Balance quality and cost" is
  not decidable. One concrete follow-up ("if a change cut cost 30% but lost 2
  points of accuracy, would you take it?") usually produces a usable ranking.
  If it does not, record the ambiguity and move on.
- **Confirm, do not assume, anything you inferred for `Constraints`.** If the
  scan found a pinned gateway or a redaction middleware, show it and ask whether
  it is a real boundary or an implementation detail.

If the user provides outside context, read it and update the inferred draft
before the review pass.

## Step 2 — One review pass, not a Q&A loop

Keep onboarding lightweight. The codebase scan and the intent round should have
filled most fields already. Your goal here is **one review round-trip with the
user**, not a per-field interview.

Present the entire Ethos at once — every field, with inferred values shown
inline and any required-but-missing fields called out. Pick a sensible
default for every optional field rather than asking. Then ask the user a
single question:

> "Here's the full Ethos I'd write. Tell me what to change — especially if
> there's outside context I missed — and I need the two missing required fields
> below before I can hand off to `nemo-ethos`."

Show the rendered Ethos inline in markdown (one `##` section per field, same
shape as the on-disk file). For fields you defaulted, note the default in
parentheses so the user knows they can override:

- `Tools: Prompt-only.` *(default — say so if the agent needs tools)*
- `Purpose & Outcomes` / `Success Criteria` inferred from implementation *(say
  so if there is outside context to incorporate)*
- `Change Scope:` all defaults on, fine-tuning off *(default — call out
  anything you want to lock down, or mark it `with-approval`)*

Mark any intent-tier section the user could not answer as an explicit gap, not a
default. Say "`Constraints`: none given — the optimizer will treat every provider
and cost as fair game" so the consequence is visible while it is still cheap to
fix.

**Do not** walk the schema field by field. **Do not** ask for confirmation on
high-confidence inferences. **Do not** ask one question at a time. The whole
point of this skill is that the codebase scan paid for the right to skip the
interrogation.

Do not use public-facing shorthand like `AUT` or "agent under test" in the
rendered Ethos. Use "this agent" for the agent being specified. Use "target
agent" only where the agent's purpose is explicitly to inspect or modify
another agent, and name optimizer helper agents only when they are part of the
actual product workflow.

Allowed exceptions where a follow-up question is justified:

1. The **hard-required** `Role` is missing or vague — ask for it in the same
   single round-trip.
2. The user's reply to the review block surfaces a contradiction that needs
   one targeted clarification (e.g. they say "drop the search tool" but the
   codebase shows the agent depends on it).

## Step 3 — Hand off

After the user's reply, apply the corrections and check the one hard
precondition:

1. **Role** is a concrete one-sentence answer (not "help with stuff").

If it is still unresolved, ask for it in one final message and stop until the
user provides it. Do not hand off with `Role` blank — the artifact is useless
downstream even though the parser accepts it.

Intent-tier gaps do **not** block handoff. Carry them through as gaps so
`nemo-ethos` can surface the parser warnings, and note them in `Open Questions`
when they affect safe optimization.

If both hard requirements are satisfied, announce the handoff in one line
("Handing off to `nemo-ethos` to write `agents/<name>-ethos/ETHOS.md` and upload
the canonical copy to Filesets") and trigger it.

## If the user pushes back

- **They want to change one or two fields.** Apply the edits, re-show the
  changed sections only, ask "good now?", proceed.
- **They want to redo the whole thing.** That usually means the codebase
  scan got something fundamentally wrong. Re-scan with their correction in
  mind, then re-present once.
- **They keep changing their mind on Role.** Stop. Tell them the agent will
  not be useful until they can write one concrete sentence and offer to
  come back later. Do not loop on rewording.
- **They skip the intent round entirely.** Proceed, but say once what it costs:
  the optimizer will treat any provider, any cost, and any latency as
  acceptable, so its suggestions may be unshippable. Then write the Ethos with
  the gaps recorded and move on. Do not re-ask.

## Gotchas

- **"You decide" means commit to the default and announce it.** Example:
  "I'll go with cloud and `nvidia/llama-3.3-nemotron-super-49b-v1`. Tell me
  to change if not." Never silently fill in. Prefer routing through
  `nemo-model-selection` so the user gets a plain-English reason, not just a
  name.
- **Tool over-spec is the most common error.** Users ask for a search tool
  when prompt-only would work. Probe: "Do you have evidence the model alone
  fails on these?" If no, drop the tool.
- **Tool and harness inventory should be compressed.** Do not create one row
  per helper method when several helpers share the same source, credential,
  side effect, freshness, and failure mode. Group them and call out only the
  differences an optimizer or evaluator needs to know.
- **Mission before mechanics.** An Ethos that only says how the current code is
  wired is not good enough. If goal context cannot be found in the codebase or
  docs, say the mission is inferred from implementation and give the user one
  chance to supply the missing outside context.
- **Never infer a constraint you cannot verify.** A guessed provider allowlist
  or cost ceiling silently deletes good candidates and looks authoritative doing
  it. Ask, or leave the section empty and record the gap.
- **Trade-offs are the highest-leverage question you will ask.** Without a
  priority order, every candidate that improves one metric and regresses another
  is undecidable, and the optimizer either stalls or picks arbitrarily.
- **"No behavior constraints" usually means "I haven't thought about it."** Probe
  once: "Anything that should never appear — names, phone numbers, competitor
  mentions?" One probe, then move on.
- **Do not skip the codebase scan even when the user seems eager to dive
  into questions.** Spending the first five minutes reading earns the right
  to ask shorter, sharper questions. Asking something the codebase already
  answers loses trust immediately.
- **A framework import does not prove harness compatibility.** Record the source
  framework in `Harness` as an observation, not as a promise that a supported
  harness can own the lifecycle. Imports such as `langchain`, `langgraph`,
  `crewai`, `autogen`, or `pydantic_ai` say nothing about that.
- **Keep Platform terminology at the design boundary.** Record the desired
  harness behavior and artifacts without exposing Fabric SDK types or asking
  the user to design a raw runtime config. `nemo-agent-config` owns the
  machine-readable Platform YAML after the Ethos is approved.
- **Change Scope is a permissions list, not a wishlist.** It controls
  what the experimentalist agent will edit. Walk the defaults explicitly so
  the user knows what they're consenting to. Offer `with-approval` for levers
  the user wants available but not automatic.
- **Do not invent Known Issues fields.** Known issues / recurring failure
  patterns live in the Insights plugin as first-class entities, not in the
  Ethos.
