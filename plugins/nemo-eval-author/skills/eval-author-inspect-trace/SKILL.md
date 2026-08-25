---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-inspect-trace
description: >-
  Understand one agent trace from NeMo Intake without presuming that the trace
  failed. Reports evidence-backed behavior, issues, recoveries, and
  uncertainties tied to span IDs. Use when the user asks "what happened in this
  trace?", "inspect this trace", "explain this agent run", "did this trace
  succeed?", or "why did this production trace fail?". Optionally reads relevant
  local agent source, but changes none of it.
triggers:
  - inspect this agent trace
  - what happened in this agent trace
  - explain this production agent run
  - did this trace succeed
  - why did this trace fail
not-for:
  - eval-author (use for the standard, the boundaries, and to pick a sub-flow)
  - eval-author-discover (use to establish whether a repository's Harbor suite is runnable)
  - nemo-experimentalist (use for an optimization experiment across many trials)
compatibility: >-
  An installed nemo CLI, an explicit workspace, and read access to Intake on a
  configured local or remote NeMo Platform instance.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob]
---

# Eval Author: inspect an Intake trace

Read one Intake trace, explain its trajectory, and save an evidence-backed
report. Read `eval-author` for the shared standard and boundaries.

## Requirements

Use the installed `nemo` CLI with an explicit workspace and read access to
Intake. The configured NeMo Platform instance can be local or remote. Use the
active context, a caller-supplied context, or `NMP_BASE_URL` and
`NMP_ACCESS_TOKEN`.

Don't install the CLI, authenticate, change contexts, start services, or repair
the platform. Don't print, copy, or save credentials. The first Intake read
validates access. If it exits nonzero, quote the CLI error and stop.

## Select the trace

Accept a bare Intake trace ID or `intake://traces/TRACE_ID`. Reject every other
URI scheme. If no trace is named, list recent candidates:

```bash
nemo intake traces list --output-format=json --workspace="WORKSPACE" --mode=preview --sort=-started_at --page-size=20
```

If the request names an agent, list recent traces that contain its spans:

```bash
nemo intake spans groups list --output-format=json --workspace="WORKSPACE" --by=trace_id --filter.agent-name="AGENT_NAME" --sort=-started_at --page-size=20
```

For a time-bounded agent search, add the command's JSON `--filter` value with
`started_at.gte` and `started_at.lte`. Don't encode the filter. If the command
returns no candidates, report the empty result and stop. Don't widen the search
without user direction.

## Read the trace structure

Read the server-computed trace rollups:

```bash
nemo intake traces get --output-format=json --workspace="WORKSPACE" --mode=detailed "TRACE_ID"
```

Then read every span without payloads:

```bash
nemo intake spans list --output-format=json --workspace="WORKSPACE" --filter.trace-id="TRACE_ID" --mode=summary --sort=started_at --all-pages
```

Use Intake's root status, duration, token, cost, span-count, error-count, model,
and provider rollups. Use span timestamps and parent IDs when order matters.
Don't recreate a timeline object or assume that an error span made the trace
fail.

## Read selective detail

Read bounded previews for a server-side selection:

```bash
nemo intake spans list --output-format=json --workspace="WORKSPACE" --filter.trace-id="TRACE_ID" --filter.status=error --mode=preview --sort=started_at --page-size=20
```

Use `--filter.kind` or `--filter.parent-span-id` for equivalent selections. Read
an exact payload only when its text affects the assessment:

```bash
nemo intake spans get --output-format=json --workspace="WORKSPACE" "SPAN_ID"
```

Require the returned `trace_id` to equal the selected trace ID. Otherwise,
discard the span and report the mismatch. Don't recreate payload-length flags.

## Read evaluator evidence

Collect unique session IDs from the summary spans. Query each relevant session:

```bash
nemo intake evaluator-results list --output-format=json --workspace="WORKSPACE" --filter.session-id="SESSION_ID" --sort=created_at --all-pages
```

Keep only results whose `span_id` belongs to the selected trace. Quote evaluator
comments when they affect the outcome.

## Assess the evidence

Use exact payload text only when it changes the assessment. For every important
moment, name the span ID, input or attempt, output, and relationship to nearby
spans. Separate observations from interpretations.

Assign one outcome:

- `success`: Direct evidence shows that the requested work completed.
- `failure`: Direct evidence shows that the work didn't complete or was wrong.
- `unknown`: Evidence is missing, incomplete, or contradictory.

Start every finding with one category:

- `behavior`: What the agent did without judging it as defective.
- `issue`: A result that harmed correctness, safety, cost, or latency.
- `recovery`: A later action that handled an earlier problem.
- `uncertainty`: A question that the evidence can't settle.

Don't invent an `issue` for a successful trace. Tie every important claim to a
span ID, evaluator result ID, or source symbol.

Inspect local source only after trace evidence identifies behavior that source
can explain. Name the repository-relative path and symbol. Source can't override
recorded trace evidence. Report conflicts as `uncertainty`.

## Save the report

Use the trace ID returned by Intake. Replace characters outside letters,
numbers, `.`, `_`, and `-` with `_`. Save the report as
`.eval-author/traces/intake-TRACE_ID.md`, replacing any report for the same trace.

Put only source metadata and exact read commands in JSON-compatible YAML front
matter. Record the workspace and a named CLI context when used. Never record a
token. Then include outcome, summary, important moments, findings, and optional
source evidence:

```markdown
---
{"source":{"kind":"intake","trace_id":"TRACE_ID","workspace":"WORKSPACE","context":"CONTEXT_OR_NULL"},"commands":["EXACT_READ_COMMAND"]}
---
# Trace TRACE_ID
## Source
<SOURCE_METADATA>
## Outcome
<OUTCOME_AND_DECISIVE_EVIDENCE>
## Summary
<TRACE_SUMMARY>
## Important moments
- `<SPAN_ID>`: <TRANSITION_AND_SIGNIFICANCE>
## Findings
- **<FINDING_CATEGORY>**: <CLAIM_AND_EVIDENCE_IDS>
## Source evidence
- `<PATH>:<SYMBOL>`: <SOURCE_BACKED_EXPLANATION>
```

Omit **Source evidence** when you didn't inspect source. Before completion,
verify every important moment and finding names evidence, the outcome uses an
allowed value, and only the report changed. Leave the report uncommitted and
state its path.
