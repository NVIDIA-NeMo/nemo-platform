---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author
description: >-
  Work on evaluation suites in a user's repository or understand an agent run
  from NeMo Intake. Owns the evidence standard that every Eval Author sub-flow
  follows. Use when the user asks "help me with my evals",
  "what's the state of the eval suite here?", "what happened in this trace?", or
  when you need to pick between the Eval Author sub-flows. Routes to a sub-flow
  and changes none of the user's source. The selected sub-flow uses the
  provider's supported tools and saves its findings under `.eval-author/`.
triggers:
  - help me with the evals in this repo
  - what is the state of the eval suite here
  - I inherited a repo with Harbor tasks in it
  - work on my evaluation suite
  - what happened in this agent trace
  - which eval author step do I need
not-for:
  - eval-author-discover (use to run the discovery pass and get a runnable verdict)
  - eval-author-inspect-trace (use after this skill selects the trace sub-flow)
  - nemo-intake (use to instrument agents, ingest telemetry, or query Intake outside Eval Author)
  - nemo-experimentalist (use to run insight-driven optimization end to end)
  - nemo-evaluator (use to run an existing benchmark rather than work on a repository's own suite)
compatibility: >-
  Reading only. Discovery uses the local checkout. Trace inspection requires
  the nemo CLI, an explicit workspace, and read access to configured Intake.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Read, Grep, Glob]
---

# Eval Author

Work on repository-owned evaluation suites and understand agent traces. Route
each request to the narrow sub-flow that owns it.

A report that a downstream model trusts has to be right. A plausible report is
worse than no report when somebody acts on it.

## The standard

**Every fact you record comes from authoritative evidence, not a guess.**

The authority depends on the sub-flow:

- For suite discovery, Harbor's validators judge runnability. A file's presence
  doesn't prove that Harbor accepts it.
- For trace inspection, Intake establishes what happened. Local source code can
  explain behavior, but it can't replace recorded trace evidence.

No sub-flow reimplements a provider's rules. When evidence can't settle a claim,
the report marks the claim unproven or uncertain.

## Vocabulary

The sub-flows share this language, and reports use it verbatim.

| Term | Meaning |
|---|---|
| Check | One named result: `pass`, `warn`, or `fail`. Carries a message and, when it fails, a hint |
| Required | A failing required check blocks the suite. Report the suite as not ready |
| Advisory | A warning worth surfacing that blocks nothing |
| Rung | One step of a provider's validation ladder, ordered so a lower rung's failure often clears once a higher one is fixed |
| Proven | A provider judged this check. An unproven check is an observation and never evidence |
| Provider | The evaluation framework that owns the rules. Harbor today |
| Finding | One trace claim categorized as `behavior`, `issue`, `recovery`, or `uncertainty`, with evidence IDs |
| Outcome | The trace assessment: `success`, `failure`, or `unknown` |

## Sub-flows

Read the sub-flow's own `SKILL.md` and follow it. This file carries the standard
and the boundaries; the sub-flow carries the steps.

| Sub-flow | Use it to |
|---|---|
| `eval-author-discover` | Establish whether a repository's evaluations run, name the rung that fails, and get the exact command to run them |
| `eval-author-inspect-trace` | Understand one Intake trace without presuming that the trace contains a failure. Not user-invocable; this skill selects it |

Authoring new tasks and verifier metrics is not built yet. When a user asks for
that, say so plainly rather than improvising a task layout by hand. A task written
against a guessed convention scores nothing and costs a full evaluation run to
discover.

## Boundaries

These hold for every sub-flow. They exist because the repository belongs to the
user, not to you.

- **Propose, never mutate.** Read the user's source and report on it. Do not edit,
  move, or reformat any of it, including its `.gitignore`. The one thing you add is
  your own report under `.eval-author/`, which is theirs to commit or ignore. The
  bundled scripts write nothing at all; saving is your job, not theirs.
- **A missing tool is a finding, not a task.** When the provider is not installed,
  say so and stop short of proving anything. Report what you found regardless, and
  do not install the provider into the user's environment.
- **Do not run the suite.** Prove it can run and hand over the command. Starting a
  job spends the user's compute and credentials on a decision they did not make.
- **Trusted repositories only.** Validating a config can execute repository code,
  because an agent named by import path gets imported. If the repository is not
  trusted, say so and stop.
- **Intake reads are narrow.** Only `eval-author-inspect-trace` reads Intake. It
  uses read-only `nemo intake` commands against the configured instance and
  workspace. No sub-flow discovers accounts, ingests data, uploads files, or
  changes a remote resource.

## Reporting

Lead with the verdict or outcome, then the evidence.

State whether the findings are proven, whether the suite is ready, and the names
of the checks that failed. Never describe a suite as ready while a required check
fails, and never present an observation as proof. When a sub-flow could not reach
its provider, the only honest headline is that nothing was proven.

For a trace, use `success`, `failure`, or `unknown`. Tie key moments and findings
to span IDs, evaluator result IDs, or source symbols. A healthy trace doesn't
need an issue finding.
