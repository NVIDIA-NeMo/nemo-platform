---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author
description: >-
  Work on the evaluation suites that live in a user's own repository: establish
  whether they run, explain why one fails, and report what it needs. Owns the
  standard every sub-flow follows, which is that a provider's own validators
  judge every recorded fact rather than the agent guessing from file layout. Use
  when the user asks about the evals in their repository without naming a step:
  "help me with my evals", "what's the state of the eval suite here?", "are these
  evals any good?", "I inherited this repo and there are Harbor tasks in it", or
  when you need to pick between the Eval Author sub-flows. Routes to a sub-flow;
  changes none of your source, and saves what it finds under `.eval-author/`.
triggers:
  - help me with the evals in this repo
  - what is the state of the eval suite here
  - I inherited a repo with Harbor tasks in it
  - work on my evaluation suite
  - which eval author step do I need
not-for:
  - eval-author-discover (use to run the discovery pass and get a runnable verdict)
  - eval-author-audit (use to generate and validate audit.md coverage denominators)
  - nemo-experimentalist (use to run insight-driven optimization end to end, which drives the Eval Author agent itself)
  - nemo-evaluator (use to run an existing benchmark rather than work on a repository's own suite)
compatibility: Reading only. Each sub-flow states its own runtime needs.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Read, Grep, Glob]
---

# Eval Author

Work on the evaluation suites that live in a user's own repository, so a later and
cheaper model can run them without working out how from scratch.

That last clause is the whole point, and it sets a standard the sub-flows have to
meet. A report that a downstream model trusts has to be right. A report that is
merely plausible is worse than no report, because it gets acted on.

## The standard

**Every fact you record is one a provider's validators confirmed, not one you
observed.**

The two are easy to confuse and not close to equivalent:

- **Observed.** A `harbor-job.yaml` exists, and a directory holds a `task.toml`.
  You read the filesystem and described it.
- **Proven.** Harbor parsed that config, resolved it into tasks, confirmed each
  task directory is valid, and named the host variables it needs.

Observation cannot substitute for proof. A config file that exists can still name
a dataset path that is absent, an agent that does not exist, or tasks the provider
silently drops. Each of those passes every structural check you could invent and
fails the moment the suite runs.

So no sub-flow reimplements a provider's rules. It asks the provider. Where a
sub-flow can only observe, it says so and marks the finding unproven.

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

## Sub-flows

Read the sub-flow's own `SKILL.md` and follow it. This file carries the standard
and the boundaries; the sub-flow carries the steps.

| Sub-flow | Use it to |
|---|---|
| `eval-author-discover` | Establish whether a repository's evaluations run, name the rung that fails, and get the exact command to run them |
| `eval-author-audit` | Generate and validate a finite `audit.md` coverage denominator, then measure one Harbor/ATIF trace against it |

Runnable tasks, verifier metrics, and coverage aggregation are not built yet.
`eval-author-audit` works one level above tasks: it generates and validates the
coverage denominator and can measure one Harbor/ATIF trace against it. When a
user asks for new runnable tasks, say so plainly rather than improvising a task
layout by hand. A task written against a guessed convention scores nothing and
costs a full evaluation run to discover.

## Boundaries

These hold for every sub-flow. They exist because the repository belongs to the
user, not to you.

- **Propose, never mutate.** Read the user's source and report on it. Do not edit,
  move, or reformat any of it, including its `.gitignore`. The only files you add
  belong under `.eval-author/`, which is theirs to commit or ignore.
  `eval-author-discover` scripts write nothing; `eval-author-audit` writes only
  the audit output path the user explicitly requested.
- **A missing tool is a finding, not a task.** When the provider is not installed,
  say so and stop short of proving anything. Report what you found regardless, and
  do not install the provider into the user's environment.
- **Do not run the suite.** Prove it can run and hand over the command. Starting a
  job spends the user's compute and credentials on a decision they did not make.
- **Trusted repositories only.** Validating a config can execute repository code,
  because an agent named by import path gets imported. If the repository is not
  trusted, say so and stop.
- **No platform services.** Eval Author sub-flows talk to no NeMo service, resolve
  no workspace, and upload nothing. Everything happens against the local checkout.

## Reporting

Lead with the verdict, then the evidence.

State whether the findings are proven, whether the suite is ready, and the names
of the checks that failed. Never describe a suite as ready while a required check
fails, and never present an observation as proof. When a sub-flow could not reach
its provider, the only honest headline is that nothing was proven.
