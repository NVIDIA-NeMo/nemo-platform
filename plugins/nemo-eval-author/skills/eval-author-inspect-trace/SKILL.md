---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-inspect-trace
description: >-
  Understand one agent trace from a NeMo Platform Intake instance without
  presuming that the trace failed. Reads the complete trace, evaluator results,
  and a deterministic overview. Then reports evidence-backed behavior, issues,
  recoveries, and uncertainties tied to span IDs. Use when the user asks "what
  happened in this trace?", "inspect this Intake trace", "explain this agent
  run", "did this trace succeed?", or "why did this production trace fail?".
  Optionally reads relevant local agent source, but changes none of it.
triggers:
  - inspect this Intake trace
  - what happened in this agent trace
  - explain this production agent run
  - did this trace succeed
  - why did this trace fail
not-for:
  - eval-author (use for the standard, the boundaries, and to pick a sub-flow)
  - eval-author-discover (use to establish whether a repository's Harbor suite is runnable)
  - nemo-experimentalist (use for an optimization experiment across many trials)
compatibility: >-
  Python 3.12 or later. Requires read access to Intake, NMP_BASE_URL, an explicit
  workspace, and NMP_ACCESS_TOKEN when the Platform requires authentication.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob]
---

# Eval Author: inspect a trace

Read one complete Intake trace, explain its trajectory, and save an
evidence-backed report. Read `eval-author` for the shared standard and boundaries.

The trace might show a use case, an issue, a recovery, or incomplete evidence.
Don't assume that every error span made the run fail. Don't assign one global
trace type because findings can use several categories.

## Before you start

Get the workspace and trace reference from the user or the preceding workflow.
The trace reference can be a bare ID, `intake://<id>`, or
`intake://traces/<id>`.

Set these environment variables in the shell that runs the script:

- `NMP_BASE_URL`: The Platform origin. Remote origins must use HTTPS. Loopback
  origins can use HTTP.
- `NMP_ACCESS_TOKEN`: A bearer token when the Platform requires authentication.

The script makes read-only `GET` requests. It follows no redirects, and it sends
credentials only to the validated origin.

## Step 1: build the analysis bundle

Run:

```bash
python3 <skill_dir>/scripts/inspect_trace.py \
  --workspace "<workspace>" \
  --trace "<trace-reference>"
```

The script calls shared modules under `eval-author/scripts/intake/`:

- `scripts/intake/_http.py` validates and reads the Intake API.
- `scripts/intake/traces.py` queries spans and trace summaries.
- `scripts/intake/reader.py` loads detailed spans and evaluator results.
- `scripts/intake/overview.py` derives factual structure.

The command prints one JSON object and writes no files. An exit code of `1`
means that the object contains `error` and `hint` fields. Resolve that error
before interpreting the trace.

Preserve the complete JSON object. Span payloads and evaluator comments are
evidence, and dropping them can change the assessment.

## Step 2: review the overview

Read the deterministic `overview` before the payloads. It reports structure,
not an outcome:

- Root and span statuses
- Timing and span kinds
- Tools, models, providers, agents, sessions, and projects
- Error, canceled, and incomplete spans
- A `root_succeeded_with_errors` recovery signal
- Evaluator results

Treat `root_succeeded_with_errors` as a signal, not proof of correct behavior.
A successful root status can still conflict with the requested result or an
evaluator score.

## Step 3: analyze the trajectory

Read `trace.spans` in chronological order. For each important transition:

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
local agent source if it is available. Intake remains authoritative about what
happened.

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
The script derives its bounded filename from the Platform origin, workspace, and
trace ID with SHA-256. Don't build a path from the raw trace ID. Create the
`traces` directory when it doesn't exist. Replace a preceding report for the
same trace instead of merging assessments.

Start the file with JSON-compatible YAML front matter that preserves the complete
input bundle:

```markdown
---
{
  "input_bundle": {
    "...": "paste the complete script output here"
  }
}
---
```

Then use this report shape:

```markdown
# Intake trace <trace-id>

## Outcome
<success, failure, or unknown, followed by the decisive evidence>

## Summary
<what the trace did and why the outcome follows>

## Key moments
- `<span-id>` — <observed transition and its significance>

## Findings
- **<behavior, issue, recovery, or uncertainty>** — <claim and evidence IDs>

## Source evidence
- `<path>:<symbol>` — <source-backed explanation>
```

Omit **Source evidence** when you didn't inspect source. Keep uncertainties in
the findings instead of resolving them through speculation.

## Step 7: verify the report

Before reporting completion, confirm:

1. The front matter contains the unmodified input bundle.
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
| `scripts/inspect_trace.py` | Entry point. Reads the trace, builds the overview, and prints the JSON bundle |
