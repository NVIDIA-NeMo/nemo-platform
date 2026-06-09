---
name: nemo-explore
description: Captures what a NeMo Platform agent should do before any code or YAML. Explores the user's codebase and docs first, fills in every spec field it can infer, then asks the user only for the gaps. Output feeds nemo-spec. Use over generic brainstorming for any NeMo Platform agent design conversation.
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
  - nemo-spec (use to write the spec file once explore is done)
  - nemo-build-agent (use after spec exists)
  - nemo-model-selection (use for the model question in step 5; explore delegates to it)
  - superpowers:brainstorming (use for design work unrelated to NeMo Platform)
compatibility: nemo-platform >= 0.1.0; dialogue-driven with read-only pre-flight (`ls`, `find`, `Read`); safe under any sandbox; works offline; output is a structured conversation handed to nemo-spec.
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Read, Glob, Grep, Bash]
---

# NeMo Platform agent explore

Capture what the agent should do before any code or YAML. Product mission and
user goals matter more than implementation inventory. The output of this skill
is the data that `nemo-spec` writes into `agents/<name>-spec/AGENT-SPEC.md` —
the durable contract that downstream optimization agents read as their primary
context. Underspecified input here directly degrades the quality of generated
Insights and PRs downstream.

This skill is **explore-first, gap-fill second**. You do not interview the
user from scratch. You scan the codebase and docs, infer what you can against
the spec schema below, present what you found, and ask the user only for the
fields you could not fill.

## The schema you are filling

The spec has three front-matter fields and thirteen body sections. Two are hard
requirements: handoff to `nemo-spec` is blocked until both are resolved.

**Front matter**

| Field | Required | Guidance |
| :---- | :---- | :---- |
| `name` | yes | Canonical agent name. Use the directory or workflow name if obvious; ask if not. |
| `created_timestamp` | yes | ISO 8601 timestamp for when the spec is created. `nemo-spec` fills this at write time. |
| `author` | yes | Human or agent that created the spec. `nemo-spec` fills this from the current author context when known; ask only if ambiguous. |

**Body sections** (in order)

| # | Section | Required | What "good" looks like |
| :---- | :---- | :---- | :---- |
| 1 | Role | **yes** | One concrete sentence describing the role this agent plays. Example: "answer IT helpdesk questions about VPN, password reset, and software access." Vague answers ("help with stuff") are rejected. |
| 2 | Purpose | yes | One or two short paragraphs explaining the mission: why the agent exists, what user value it provides, which goal it advances, and the decision, workflow, or business context it supports. Do not merely restate implementation mechanics. |
| 3 | Scope | yes | Audience, 3-6 task categories, expected in-scope work, and explicit out-of-scope work/non-goals. |
| 4 | Tools | yes | Tools, APIs, and knowledge sources the agent can use, or "Prompt-only." Group related helpers by capability or source. Capture only behaviorally important purpose, credentials/scopes, side effects, freshness, and expected failures. |
| 5 | Model | yes | Mode (cloud vs local NIM) + model family/size. Example: "cloud, Nemotron Super 49B." `nemo-build-agent` resolves to a specific model entity ID later. |
| 6 | Framework | **yes** | Temporary NeMo Platform compatibility field. Keep it binary: `langgraph-nat` or `needs-wrapper`; include source-framework context only when a wrapper is needed. |
| 7 | Harness | optional | Modern harness description: the extra-model layer around the agent — loop, tool dispatch, context/state, guardrails, observability, verification, and runtime. Summarize at useful granularity; omit low-level settings unless they affect behavior. Use `_(none)_` if unknown. |
| 8 | Behavior | yes | Behavioral rules and boundaries: constraints, refusal/escalation policy, tone, safety/compliance requirements, accepted limitations, and known non-goals. |
| 9 | Success Criteria | yes | What good production behavior looks like, independent of current evals: mission-level outcomes, quality standards, escalation quality, accuracy expectations, latency/cost expectations if relevant, and examples of success. |
| 10 | Evaluation Setup | yes | Current validation setup: how to run it, what datasets/checks it uses, what scorers/metrics measure, pass/fail thresholds, and known coverage gaps relative to the success criteria. If no eval suite exists, say so explicitly. |
| 11 | Change Scope | yes | A permissions list — what the optimization loop is allowed to modify. Defaults: system prompt, tools, middleware, inference params, model swap within mode, skills. Fine-tuning is never on by default. The loop never edits the spec itself. |
| 12 | Signals | optional | How analysts should interpret telemetry, user feedback, eval outcomes, and trace patterns. Include high-priority signals and anything to explicitly ignore (e.g., QA traffic). If user has nothing specific, write "defaults" and move on. |
| 13 | Open Questions | optional | Open facts that affect safe use, evaluation, or modification of the agent. Remove once answered. |

Known issues / failure patterns are tracked as first-class Insight entities by
the insights plugin — do not duplicate them into the spec.

## Pre-flight

Check whether a spec already exists for this agent. If `agents/<name>-spec/AGENT-SPEC.md`
is present, ask the user whether they want to edit the existing spec or start
over. If they want to edit, route to `nemo-spec` directly.

```bash
ls agents/*-spec/AGENT-SPEC.md 2>/dev/null || echo "no specs yet"
```

## Step 1 — Explore the codebase

Time-box this to ~5 minutes of tool use. Read first, ask second. Greenfield
projects will turn up nothing here, which is fine — move to step 2 and ask
the user the full set of unfilled fields.

1. **Find agent entry points.** Look for NAT workflow YAMLs, LangGraph
   builders, system prompts, tool definitions:

   ```bash
   find . -maxdepth 4 -type f \( -name "*.workflow.yaml" -o -name "*.workflow.yml" \) 2>/dev/null
   find . -maxdepth 4 -type d -name "agents" 2>/dev/null
   ```

   Then use `Glob` / `Grep` to find `langgraph`, `StateGraph`,
   `create_react_agent`, `system_prompt`, and tool definitions.

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
   Return here with the chosen model string captured for the spec. If the
   user wants to skip the conversation, the default is cloud,
   `nvidia/llama-3.3-nemotron-super-49b-v1` — announce that and move on.
   Local NIMs require host-gpu mode.

   Typical inferences per field:

   - **name** — directory name, workflow name, or top-level package name.
   - **Role** — first paragraph of README, system prompt preamble, or
     top-level docstring. Often partial; usually needs user confirmation.
   - **Purpose** — product docs, README motivation, system prompt preamble,
     or workflow context. Prefer explicit goal context over implementation-only
     inference.
   - **Scope** — audience from docs or prompts; categories from enumerated
     capabilities or named tool clusters; in/out boundaries from prompt rules.
   - **Tools** — from `@tool` decorators, NAT tool registry,
     `create_react_agent(tools=[...])`, retrieval/corpus config, or API clients.
     Group low-level helpers when they share credentials, side effects,
     freshness, and failure modes.
   - **Model** — model id strings in workflow YAML, env vars, config files.
   - **Framework** — `langgraph` import + NAT workflow YAML → "LangGraph +
     NAT." `crewai` / `autogen` / `pydantic_ai` imports → `needs-wrapper`
     with source-framework context. Plain `langchain` without `langgraph` →
     `needs-wrapper`. Do not turn this into a detailed implementation audit.
   - **Harness** — `langgraph` imports, NAT workflow YAML, `crewai` /
     `autogen` / `pydantic_ai` imports, service entrypoints, CLI commands,
     Dockerfiles, notebooks, or deployment configs. Capture what exists
     descriptively; platform-specific wrapper needs can go in notes.
   - **Behavior** — system prompt rules ("never give medical advice"),
     refusal/escalation policy, tone, accepted limitations, and non-goals.
   - **Success Criteria** — desired production outcomes, product goals,
     quality standards, escalation quality, accuracy expectations, and examples
     of successful behavior.
   - **Evaluation Setup** — Makefile targets, scripts, CI config, eval YAMLs,
     metric definitions, thresholds, and coverage notes.
   - **Change Scope** — not in the code; ask the user.
   - **Signals** — usually not in the code; ask the user.
   - **Open Questions** — TODOs / FIXMEs in agent-adjacent code that
     affect safe use, evaluation, or modification.

## Step 1.5 — Mission and outside-context check

After the code/docs scan, check whether `Purpose`, `Scope`, and `Success
Criteria` are grounded in product/design context or merely inferred from
implementation details. Code can tell you what exists; it often cannot tell
you the mission, customer goal, launch criteria, or success bar.

If the mission is missing or weakly inferred, ask one context-forward question
before handoff:

> "I can draft this from the code, but the mission/goals are only inferred from
> implementation. Is there any context outside the codebase that explains the
> goals, users, success bar, or business/workflow motivation I should
> incorporate? Paste/link it now, or say there isn't any and I'll proceed with
> the implementation-grounded draft."

Do this as one lightweight checkpoint, not a per-field interview. If the user
provides outside context, read it and update the inferred spec before the
review pass. If they say none, proceed and make the implementation-grounded
assumption explicit in `Open Questions` only if it materially affects safe use,
evaluation, or modification.

## Step 2 — One review pass, not a Q&A loop

Keep onboarding lightweight. The codebase scan and mission/context checkpoint
should have filled most fields already. Your goal here is **one review
round-trip with the user**, not a per-field interview.

Present the entire spec at once — every field, with inferred values shown
inline and any required-but-missing fields called out. Pick a sensible
default for every optional field rather than asking. Then ask the user a
single question:

> "Here's the full spec I'd write. Tell me what to change — especially if
> there's outside context I missed — and I need the two missing required fields
> below before I can hand off to `nemo-spec`."

Show the rendered spec inline in markdown (one `##` section per field, same
shape as the on-disk file). For fields you defaulted, note the default in
parentheses so the user knows they can override:

- `Tools: Prompt-only.` *(default — say so if the agent needs tools)*
- `Purpose` / `Success Criteria` inferred from implementation *(say so if
  there is outside context to incorporate)*
- `Change Scope:` all defaults on, fine-tuning off *(default — call out
  anything you want to lock down)*
- `Signals: defaults` *(default — replace if you have specific
  priority/ignore rules)*

**Do not** walk the schema field by field. **Do not** ask for confirmation on
high-confidence inferences. **Do not** ask one question at a time. The whole
point of this skill is that the codebase scan paid for the right to skip the
interrogation.

Do not use public-facing shorthand like `AUT` or "agent under test" in the
rendered spec. Use "this agent" for the agent being specified. Use "target
agent" only where the agent's purpose is explicitly to inspect or modify
another agent, and name optimizer helper agents only when they are part of the
actual product workflow.

Allowed exceptions where a follow-up question is justified:

1. A **hard-required field** (`Role`, `Framework`) is missing — list those
   explicitly and ask for them in the same single round-trip.
2. The user's reply to the review block surfaces a contradiction that needs
   one targeted clarification (e.g. they say "drop the search tool" but the
   codebase shows the agent depends on it).

## Step 3 — Hand off

After the user's reply, apply the corrections and check the two hard
preconditions:

1. **Role** is a concrete one-sentence answer (not "help with stuff").
2. **Framework** is resolved (`langgraph-nat` or `needs-wrapper` with a
   source-framework name).

If either is still unresolved, ask for it in one final message and stop until
the user provides it. Do not hand off with a hard requirement blank —
`nemo-spec` will reject the write.

If both are satisfied, announce the handoff in one line ("Handing off to
`nemo-spec` to write `agents/<name>-spec/AGENT-SPEC.md` and upload the canonical copy
to Filesets") and trigger it.

## If the user pushes back

- **They want to change one or two fields.** Apply the edits, re-show the
  changed sections only, ask "good now?", proceed.
- **They want to redo the whole thing.** That usually means the codebase
  scan got something fundamentally wrong. Re-scan with their correction in
  mind, then re-present once.
- **They keep changing their mind on Role.** Stop. Tell them the agent will
  not be useful until they can write one concrete sentence and offer to
  come back later. Do not loop on rewording.

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
- **Mission before mechanics.** A spec that only says how the current code is
  wired is not good enough. If goal context cannot be found in the codebase or
  docs, say the mission is inferred from implementation and give the user one
  chance to supply the missing outside context.
- **"No behavior constraints" usually means "I haven't thought about it."** Probe
  once: "Anything that should never appear — names, phone numbers, competitor
  mentions?" One probe, then move on.
- **Do not skip the codebase scan even when the user seems eager to dive
  into questions.** Spending the first five minutes reading earns the right
  to ask shorter, sharper questions. Asking something the codebase already
  answers loses trust immediately.
- **NeMo Platform optimizes LangGraph agents wrapped in NAT today.** Other
  frameworks may still be valid AGENTSpec harnesses, but need a user-written
  wrapper for the current NeMo build path. Record that as Harness notes; do
  not make the standard schema a NeMo-specific capability gate.
- **Change Scope is a permissions list, not a wishlist.** It controls
  what the experimentalist agent will edit. Walk the defaults explicitly so
  the user knows what they're consenting to.
- **Do not invent Known Issues fields.** Known issues / recurring failure
  patterns live in the Insights plugin as first-class entities, not in the
  spec.
