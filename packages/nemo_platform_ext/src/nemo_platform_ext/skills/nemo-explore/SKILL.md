---
name: nemo-explore
description: Captures what a new NeMo Platform agent should do before any code or YAML. Walks the user through job, audience, categories, tools, model, and constraints, then hands the answers to nemo-spec. Use over generic brainstorming for any NeMo Platform agent design conversation.
triggers:
  - design my agent
  - what should my agent do
  - help me think through the agent
  - I want to build an agent
  - agent design
  - explore the agent
  - figure out what my agent needs
not-for:
  - nemo-skill-selection (use to dispatch when intent is unclear)
  - nemo-spec (use to write the spec file once explore is done)
  - nemo-build-agent (use after spec exists)
  - nemo-model-selection (use for the model question in step 5; explore delegates to it)
  - superpowers:brainstorming (use for design work unrelated to NeMo Platform)
compatibility: nemo-platform >= 0.1.0; dialogue-driven with one read-only pre-flight (`ls agents/*.spec.md`); safe under any sandbox; works offline; output is a structured conversation handed to nemo-spec.
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Read, Bash]
---

# NeMo Platform agent explore

Capture what the agent should do before any code or YAML. This skill is the questions; nothing else. Output goes to `nemo-spec`.

## Pre-flight

Check whether a spec already exists for this agent. If `agents/<name>.spec.md` is present, ask the user whether they want to edit the existing spec or start over. If they want to edit, route to `nemo-spec` directly.

```bash
ls agents/*.spec.md 2>/dev/null || echo "no specs yet"
```

## What you do

Ask in this order, one at a time. Wait for each answer.

1. **The job.** "What should this agent do? One sentence." Push back on vague answers ("help with stuff"). A real one-liner: "answer IT helpdesk questions about VPN, password reset, and software access."

2. **The user.** "Who talks to it: internal employees, external customers, developers?" Shapes tone and what is safe to say.

3. **The categories.** "What buckets of questions should it handle?" Aim for 3 to 6.

4. **The tools.** "Does it need to call anything (search, database, HTTP API), or can it answer from prompt and model alone?" Default: prompt-only with `current_datetime` as the only tool. Tools beyond that need a follow-up about credentials.

5. **The model.** Hand off to `nemo-model-selection` for this question. That skill profiles the agent on tool density, primary capability, and deployment, then recommends a specific NIM model with a plain-English explanation grounded in what the model is actually good at. Return here with the chosen model string captured for the spec. If the user wants to skip the conversation, the default is cloud, `nvidia/llama-3.3-nemotron-super-49b-v1` — announce that and move on. Local NIMs require host-gpu mode.

6. **Constraints.** "Anything off-limits? e.g., cannot mention competitors, must redirect medical questions, response length cap?"

7. **Framework honesty.** If the user has not said yet: ask whether they have an existing agent or want to build from scratch. If existing: confirm it is LangGraph wrapped in NVIDIA NeMo Agent Toolkit (NAT). If the agent is CrewAI, AutoGen, plain LangChain, or Pydantic AI, tell them the build path requires a NAT wrapper first.

Hand the answers to `nemo-spec` for the artifact.

## Verification

This skill produces no system change, so verification is conversational: at the end, summarize what the user said in 7 bullets (one per question above) and ask "Did I get this right?" Do not hand off to `nemo-spec` until the user confirms.

## If verification fails

If the user says the summary is wrong, ask which bullet is wrong and re-ask only that question. Do not restart the full sequence. If the user keeps changing their mind on the job statement: stop and tell them the agent will not be useful until they can write one concrete sentence; offer to come back later.

## Gotchas

- **"You decide" means commit to the default and announce it.** Example: "I'll go with cloud and `nvidia/llama-3.3-nemotron-super-49b-v1`. Tell me to change if not." Never silently fill in. Prefer routing through `nemo-model-selection` so the user gets a plain-English reason, not just a name.
- **Tool over-spec is the most common error.** Users ask for a search tool when prompt-only would work. Probe: "Do you have evidence the model alone fails on these?" If no, drop the tool.
- **"No constraints" usually means "I haven't thought about it."** Probe once: "Anything that should never appear: names, phone numbers, competitor mentions?" One probe, then move on.
- **Do not propose a design before the user has answered.** Skipping ahead skips the value of the questions.
- **NeMo Platform optimizes LangGraph agents wrapped in NAT today.** Other frameworks need a user-written wrapper. Surface that constraint in question 7, not at the build step.
