---
name: <canonical-agent-name>
created_timestamp: <ISO 8601 creation timestamp, e.g. 2026-06-02T20:00:00Z>
author: <human or agent that created this spec>
---

# Agent Spec: <name>

> This file is the agent's AGENTSpec.md — the durable contract that
> describes the intended behavior, capabilities, validation setup, and change
> boundaries for the agent under test (AUT). The analyst and experimentalist
> agents in the NeMo optimization loop read this file as their primary
> context. Keep it accurate; stale entries here directly degrade the quality
> of generated Insights and PRs.
>
> The layout below is lightly parseable by `nemo-spec`: front matter and the
> required `##` section headers are machine-checked, while section bodies stay
> markdown for humans and agents to read directly.
>
> Section rules:
>
> - **Bullet sections** (`Open Questions`): list items only. If the list
>   is empty, write `_(none)_` instead of leaving the section blank.
> - **Labeled-bullet sections** (`Scope`, `Model`, `Framework`, `Harness`, `Change Scope`):
>   `- Label: value` lines only. No prose, no blank-line-separated paragraphs.
>   For list-valued labels inside `Scope`, separate items with semicolons, or
>   write `_(none)_`.
> - **Free-form sections** (`Role`, `Purpose`, `Tools`, `Behavior`,
>   `Success Criteria`, `Evaluation Setup`, `Signals`): any markdown. `Tools`
>   accepts a markdown table or the literal string `Prompt-only.`

## Role

<one concrete sentence describing the role this agent plays for its users; this
is the fast, human-readable one-liner another agent should remember>

## Purpose

<one or two short paragraphs explaining why the agent exists, what user value
it provides, and the decision, workflow, or business context it supports>

## Scope

- Audience: <who talks to it — internal employees, external customers, developers, etc.>
- Categories: <3-6 task buckets, separated by semicolons; e.g. VPN; password reset; software access>
- In scope: <capabilities, user intents, or situations the agent is expected to handle; semicolon-separated or `_(none)_`>
- Out of scope: <capabilities, user intents, or situations the agent should not handle; semicolon-separated or `_(none)_`>

## Tools

<tools, APIs, and knowledge sources the agent can use, or the literal string
`Prompt-only.` if none. For each tool/source, capture purpose, credentials or
scopes, side effects, data freshness, expected failures, and anything an
analyst should know when deciding whether a trace shows bad agent behavior or
a normal tool/source limitation.>

| Tool or source | Purpose | Credentials/scopes | Side effects | Freshness / expected failures |
|---|---|---|---|---|
| current_datetime | clock for time-sensitive answers | none | none | current at call time |

## Model

- Mode: <cloud | local-nim>
- Family: <model family or size, e.g. `Nemotron Super 49B`>

## Framework

- Resolution: <langgraph-nat | needs-wrapper>
- Source framework: <only when resolution is `needs-wrapper`; e.g. `crewai`, `autogen`, `langchain`, `pydantic-ai`, `custom service`; omit if not needed>
- Notes: <temporary NeMo Platform compatibility note, such as wrapper plan, version constraints, migration path, or `_(none)_`>

## Harness

- Description: <the extra-model layer that makes the model behave as an agent: loop, tools, context, state, constraints, observation, and validation>
- Agent loop: <how model calls, tool calls, observations, retries, and stop conditions are orchestrated; omit if unknown>
- Tool dispatch: <how tool calls are validated, routed, executed, and returned to the model; omit if unknown>
- Context management: <how prompts, history, retrieval, compaction, and context windows are managed; omit if unknown>
- State management: <how session state, memory, artifacts, or durable workspace state are stored and reused; omit if unknown>
- Guardrails: <permission, safety, policy, sandboxing, or middleware controls around agent actions; omit if unknown>
- Observability: <tracing, logging, metrics, replay, or audit data emitted by the harness; omit if unknown>
- Verification: <checks, validators, tests, self-verification, or recovery loops run before work is accepted; omit if unknown>
- Runtime: <execution environment, e.g. NAT workflow, FastAPI service, hosted vendor agent, CLI command, notebook; omit if unknown>
- Notes: <caveats, recovery behavior, budget controls, or other harness details; use `_(none)_` if there are none>

Use `_(none)_` for this whole section if the harness details are unknown.

## Behavior

<behavioral rules and boundaries: constraints, refusal and escalation policy,
tone, safety/compliance requirements, accepted limitations, and known non-goals.
Use this to tell analyst agents what counts as divergence and what should not
be filed as a failure.>

## Success Criteria

<what good production behavior looks like for this agent, independent of the
current eval suite. Capture desired user outcomes, quality standards,
escalation quality, accuracy expectations, latency or cost expectations where
relevant, and representative examples of successful behavior.>

## Evaluation Setup

<the current validation setup. Include how to run it, what datasets or checks it
uses, what scorers or metrics measure, pass/fail thresholds, and known coverage
gaps relative to the success criteria. If no eval suite is wired yet, say that
explicitly and describe any partial/manual validation that exists.>

## Change Scope

- System prompt: yes
- Tools: yes
- Middleware: yes
- Inference params: yes
- Model swap (within mode): yes
- Skills: yes
- Fine-tuning: no
- Notes: <vetoes, exceptions, required human approvals, or other scope clarifications; use `_(none)_` if there are none>

## Signals

<how observers and analyst agents should interpret telemetry, user feedback,
eval outcomes, and trace patterns. Include high-priority signals, noisy signals
to ignore, traffic or cohort caveats, and agent identity details if needed. Use
`defaults` if nothing specific.>

## Open Questions

- <optional unresolved fact that affects safe use, evaluation, or modification of the agent; remove once answered>
