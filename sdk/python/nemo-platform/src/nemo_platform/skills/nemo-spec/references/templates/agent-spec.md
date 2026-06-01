---
name: <canonical-agent-name>
eval_command: <CLI command to run evaluations against this agent; omit the key entirely if no eval suite is wired yet>
---

# Agent Spec: <name>

> This file is the agent's AGENTSpec.md — the durable contract that
> describes the intended behavior of the agent under test (AUT). The analyst
> and experimentalist agents in the NeMo optimization loop read this file as
> their primary context. Keep it accurate; stale entries here directly
> degrade the quality of generated Insights and PRs.
>
> The structured layout below is parseable by `AgentSpec` (Pydantic model in
> `nemo_agents_plugin.spec`). If you hand-edit this file, preserve the section
> headers and labeled-bullet format exactly — `nemo-spec` will refuse to load
> a malformed spec.
>
> Section rules:
>
> - **Bullet sections** (`Constraints`, `Open Questions`): list items only.
>   If the list is empty, write `_(none)_` instead of leaving the section blank.
> - **Labeled-bullet sections** (`Model`, `Framework`, `Allowed Changes`):
>   `- Label: value` lines only. No prose, no blank-line-separated paragraphs.
> - **Free-form sections** (`Job`, `Audience`, `Tools`, `Feedback Signals`,
>   `Eval Command`): any markdown. `Tools` accepts a markdown table or the
>   literal string `Prompt-only.`

## Job

<one concrete sentence describing what the agent does>

## Audience

<who talks to it — internal employees, external customers, developers, etc.>

## Categories

- <category 1>
- <category 2>
- <category 3>

## Tools

<table of tools the agent calls beyond the model itself, or the literal
string `Prompt-only.` if none>

| Tool | Purpose | Credentials needed |
|---|---|---|
| current_datetime | clock for time-sensitive answers | none |

## Model

- Mode: <cloud | local-nim>
- Family: <model family or size, e.g. `Nemotron Super 49B`>

## Framework

- Resolution: <langgraph-nat | needs-wrapper>
- Source framework: <only when resolution is `needs-wrapper`; e.g. `crewai`, `autogen`, `langchain`, `pydantic-ai`>
- Notes: <optional free-form note>

## Constraints

- <negative requirement, e.g. "never give medical advice">

## Success Criteria

- <concrete check question with what a pass looks like, OR named metric threshold like `tool_call_accuracy >= 0.85`>

## Allowed Changes

- System prompt: yes
- Tools: yes
- Middleware: yes
- Inference params: yes
- Model swap (within mode): yes
- Skills: yes
- Fine-tuning: no
- Notes: <optional free-form note>

## Feedback Signals

<how the analyst should prioritize issues for this agent — e.g. "highest
priority: thumbs-down on escalation flows; ignore: internal QA traffic". Use
`defaults` if nothing specific.>

## Eval Command

<free-form notes on eval state when the suite is not well-defined yet
(coverage gaps, why). The runnable command lives in the `eval_command` front
matter. Use `_(none)_` if there is nothing to note.>

## Open Questions

- <anything unresolved for the build step>
