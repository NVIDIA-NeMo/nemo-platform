---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-inspect-trace
description: >-
  Understand one agent trace from a supported trace source without presuming
  that the trace failed. Reports evidence-backed behavior, issues, recoveries,
  and uncertainties tied to span IDs. Use when the user asks "what happened in
  this trace?", "inspect this trace", "explain this agent run", "did this trace
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
  Python 3.9 or later, with no third-party packages. Each trace source states its
  own access, authentication, and runtime requirements.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob]
---

# Eval Author: inspect a trace

Read one complete trace, explain its trajectory, and save an evidence-backed
report. Read `eval-author` for the shared standard and boundaries.

The trace might show a use case, an issue, a recovery, or incomplete evidence.
Don't assume that every error span made the run fail. Don't assign one global
trace type because findings can use several categories.

## Before you start

Get a source-qualified trace reference from the user or the preceding workflow.
A source-qualified reference starts with a URI scheme. Reject a bare trace ID
because it doesn't identify its source.

Select the matching source guide:

| Trace reference | Source guide |
|---|---|
| `intake://...` | `references/intake.md` |

If no guide matches, stop and report the unsupported scheme. Don't reinterpret
the reference as one of the supported sources.

When nobody named a trace, don't guess an ID. Run the `list` verb for the source
the user names. It returns candidates, each with a reference the read verbs accept
verbatim. Report the candidates, then inspect the one the user picks, or the most
recent one when the user asks for whatever is there.

## Step 1: read the trace structure

Read the selected source guide and run its `overview` command exactly. The
`scripts/inspect_trace.py` entry point validates the URI scheme, invokes the
matching source adapter, and applies the source-neutral overview.

Every command prints one JSON object and writes no files. An exit code of `1`
means that the object contains `error` and `hint` fields. Resolve that error
before interpreting the trace.

The `overview` verb reads every span in a compact form, so it stays affordable on
a trace of any size. It returns `source` identity and context, a `report_path`,
the deterministic `overview`, and a per-span `timeline`. It carries no span
payloads, which is what makes it cheap. Step 3 fetches those for the spans you
choose.

## Step 2: review the overview

Read the deterministic `overview` before any payload. It reports structure,
not an outcome:

- Root and span statuses
- Root duration and span kinds
- Tools, models, providers, agents, sessions, and projects
- Error, canceled, and incomplete spans
- A `root_succeeded_with_errors` recovery signal
- Evaluator results

Treat `root_succeeded_with_errors` as a signal, not proof of correct behavior.
A successful root status can still conflict with the requested result or an
evaluator score.

An `error_spans` message keeps only its first characters, and
`error_message_truncated` marks the cut. When the exact wording decides
something, read the full text with the `spans` verb in step 3.

Then read the `timeline`. It orders every span with `offset_ms` from the first
start and its own `duration_ms`, which is the only place either appears: span
payloads carry timestamps but no duration. Use it to find where the time went
and which spans ran as siblings.

## Step 3: read the spans that matter

The overview and timeline name every span, so you now choose which ones to read
in full. Run the source guide's `spans` command, selecting by status, kind, or
span ID. Read the error spans and the transitions the timeline makes look
decisive, rather than every span in the trace.

Payloads arrive shortened by default, and a shortened field records its full
length beside it. Ask for a field in full only when the exact text decides the
assessment. Span payloads and evaluator comments are evidence, so quote them
rather than paraphrasing.

For each important transition:

1. Identify the span ID.
2. State what the span received or attempted.
3. State what the span produced.
4. Connect it to the preceding and following spans.
5. Distinguish observed facts from your interpretation.

Choose only moments that explain the path through the trace. Include handled
errors, retries, tool choices, evaluator targets, and the final response when
they affect the outcome.

## Step 4: inspect source only when it helps

After the trace identifies a behavior that source can explain, read the relevant
local agent source if it is available. The selected trace source remains
authoritative about what happened.

For every source-based claim:

- Name the repository-relative path and symbol.
- Explain how that code can produce the observed behavior.
- Mark the statement as source evidence.

Don't infer runtime behavior from source alone. If the source and trace differ,
report the difference as an `uncertainty`. If no source is available, omit source
claims.

## Step 5: assess the evidence

Assign one outcome:

- `success`: The trace has direct evidence that the requested work completed.
- `failure`: The trace has direct evidence that the requested work didn't
  complete or produced an incorrect result.
- `unknown`: Evidence is missing, incomplete, or contradictory.

Create findings from these categories:

- `behavior`: What the agent did, without judging it as defective.
- `issue`: A behavior or result that directly harmed correctness, safety, cost,
  or latency.
- `recovery`: A later action that handled an earlier problem.
- `uncertainty`: A question that the available evidence can't settle.

A finding starts with one of those exact lowercase labels.
A successful use case can contain only `behavior` findings. Don't invent an
`issue` to fill a category. Tie each finding to one or more span IDs, evaluator
result IDs, or source symbols.

## Step 6: save the report

Write the report to the exact top-level `report_path` from the analysis bundle.
The script derives that bounded filename from the source identity. Don't build a
path from the raw trace reference. Create the `traces` directory when it doesn't
exist. Replace a preceding report for the same trace instead of merging
assessments.

Start the file with JSON-compatible YAML front matter that carries the source
identity, the deterministic overview, and the command that rebuilds the evidence:

```markdown
---
{
  "source": "copy the source object from the script output",
  "overview": "copy the overview object from the script output",
  "command": "the exact command you ran to build the bundle"
}
---
```

Copy those two objects verbatim, writing them with a tool instead of retyping
them. Don't paste the `timeline` or any span payload into the front matter. A
long timeline rivals the report in size, retyping either invites corruption, and
the recorded command rebuilds both exactly when a later reader needs them.

Then use this report shape:

```markdown
# Trace <TRACE_REFERENCE>

## Source
<SOURCE_KIND_REFERENCE_AND_CONTEXT>

## Outcome
<OUTCOME_AND_DECISIVE_EVIDENCE>

## Summary
<TRACE_SUMMARY>

## Key moments
- `<SPAN_ID>`: <TRANSITION_AND_SIGNIFICANCE>

## Findings
- **<FINDING_CATEGORY>**: <CLAIM_AND_EVIDENCE_IDS>

## Source evidence
- `<PATH>:<SYMBOL>`: <SOURCE_BACKED_EXPLANATION>
```

Omit **Source evidence** when you didn't inspect source. Keep uncertainties in
the findings instead of resolving them through speculation.

## Step 7: verify the report

Before reporting completion, confirm:

1. The front matter carries the unmodified `source` and `overview` objects and the command.
2. Every key moment names a span ID.
3. Every finding uses one allowed category and names its evidence.
4. The outcome is `success`, `failure`, or `unknown`.
5. Every source claim names a path and symbol.
6. The output path matches `report_path` and stays under `.eval-author/traces/`.
7. The report changes no other file.

Leave the report in the working tree and state its path. Committing it is the
user's decision.

## Files in this skill

| Path | Purpose |
|---|---|
| `scripts/inspect_trace.py` | Runs the `list`, `overview`, and `spans` verbs against the source a reference names |
| `scripts/overview.py` | Derives factual trace structure and the span timeline without assigning an outcome |
| `references/intake.md` | Provides Intake requirements, invocation, and adapter details |
