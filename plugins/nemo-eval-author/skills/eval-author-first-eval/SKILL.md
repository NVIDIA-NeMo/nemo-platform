---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-first-eval
description: >-
  Help a user with no evals establish a required Ethos, plan evaluation cases,
  and build and prove a first Harbor task. No prior traces or coverage reports
  are required. Missing Harbor blocks scaffolding and execution, not planning.
triggers:
  - help me build my first evals
  - my agent has no evals yet
  - create an evaluation suite from scratch
not-for:
  - eval-author (use for the shared standard and routing)
  - eval-author-task-create (use for measured audit coverage gaps)
  - eval-author-discover (use to check an existing suite)
compatibility: >-
  Ethos is required before evaluation design. Ethos generation needs usable
  nemo-explore and nemo-ethos skills and their prerequisites. Planning needs
  no Harbor installation. Scaffolding requires an existing Harbor CLI;
  validation requires its Python environment. Execution may require Docker,
  an agent adapter, and provider credentials.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob]
---

# Eval Author: first eval

Read `eval-author` for the shared standard and boundaries. No evals is a normal
starting state. Do not require a previous run or manufacture a coverage report
to enter `eval-author-task-create`. Work toward one repeatable test of the user's
actual agent, beginning with its intended behavior.

## 1. Establish Ethos and check the environment

**ETHOS.md is required before designing evaluation cases.** Use a user-supplied
path first; otherwise look for root `ETHOS.md`, then
`agents/<name>-ethos/ETHOS.md`. Read the file and confirm that it describes the
intended agent. If multiple candidates are ambiguous, ask which agent to evaluate.
An empty file, placeholder, or unrelated Ethos does not satisfy this prerequisite.

If missing, explain that Ethos records the agent's purpose, intended behavior,
constraints, success and failure criteria, and what may change. It is the source
of truth for what the evals should test; code only shows current implementation.
Share the [Ethos documentation](https://docs.nvidia.com/nemo-platform/documentation/agents/optimize-agents/ethos).

- When both `nemo-explore` and `nemo-ethos` are available and usable in this
  assistant environment, read their skills and use them in that order to create
  Ethos. Explain the handoff and follow their required intent interview, review,
  validation, and permission steps. Do not add a separate choice about whether
  to use the skills when the user already asked to build evals.
- When either skill is absent or its prerequisites cannot be met, explain the
  specific limitation. Tell the user to create an Ethos using the documentation
  and provide its path. Do not claim generation is available merely because a
  skill name appears in documentation.

Return here after the Ethos exists and has passed the generating skill's checks.
For a supplied file, check it against the documented Ethos structure and resolve
missing intent before continuing. Do not substitute README files, code, traces,
or a draft evaluation plan for Ethos. Eval Author does not write a placeholder.
The Ethos skills own their output paths and any required platform operations;
this handoff does not authorize unrelated deployment or source edits.

Check Harbor early using the interpreter probe in
[`eval-author-discover`](../eval-author-discover/SKILL.md#before-you-start) and
`harbor --help`. Distinguish a missing installation from the wrong Python
environment; a CLI on PATH alone does not prove that discovery can import Harbor.
Do not run suite discovery just to report a missing config in an empty repository.

If Harbor is unavailable, explain: “Harbor is the framework Eval Author uses to
build and run repeatable evaluation tasks. We can establish Ethos and plan your
eval cases now; building and running them needs Harbor in your execution
environment.” Share [Harbor Getting Started](https://www.harborframework.com/docs/getting-started).
Provide `uv tool install harbor` as a command for the user to run, not an action
to execute automatically. Respect a repository's documented compatible version.
After installation, verify `harbor --help` and locate its Python environment
with the discovery probe before using its validators. A uv tool installation
is isolated from the project's Python environment; do not repeatedly probe only
the project interpreter or install a second copy to work around that distinction.

Missing Harbor does not block Ethos creation or step 2. Missing Ethos does block
step 2, even when Harbor is installed. Check Docker only for a task whose chosen
backend requires it; it is not a prerequisite for the design conversation.

## 2. Plan the first cases from Ethos

Read the agent entry point, tool definitions, and usage docs to understand how
the actual agent runs. Derive a small set of representative cases from Ethos:
the user request, initial fixture, expected observable outcome, a meaningful
failure example, and the Ethos requirement each case tests. Ask only for intent
or invocation details not already established. Do not make the user supply
Harbor YAML or choose a framework.

Save `.eval-author/first-eval.md` with the Ethos path and requirement references,
cases, selected first case, agent invocation, planned verifier, prerequisites,
and unresolved questions. Preserve existing artifacts on resumption. This is an
**evaluation plan**, not a coverage report or runnable evals.

Choose one reproducible case with an objective outcome. Grade the result rather
than a specific tool call or exact prose. Define a known incorrect result before
writing the solution. Do not replace subjective quality with brittle string
matching or mock away the behavior under test. If the requested case cannot be
tested with available resources, explain the limitation and select a supported
case with the user.

If Harbor is missing, deliver the plan and installation next step here. Resume
at step 3 after verifying Harbor; do not restart the Ethos interview.

## 3. Build and prove one task

Require a working Harbor CLI and Python environment. Read its
`harbor task init --help` and `harbor run --help` before using options. Use an
unused descriptive slug under `.eval-author/task-drafts/`:

```bash
harbor task init <org>/<slug> --tasks-dir .eval-author/task-drafts \
  --description "<behavior being tested>" --author "<actual author>"
```

Verify that the expected directory was created. Complete Harbor's generated
`instruction.md`, `task.toml`, `environment/`, `tests/test.sh`, and
`solution/solve.sh` using its installed schema. Keep solutions and verifier-only
fixtures out of the agent's initial environment. Set executable permissions,
realistic timeouts, and deterministic rewards; leave no scaffold placeholders.
Add a README with the Ethos requirement, fixtures, verifier, and run commands.

For Docker-backed execution, check `docker info` first. Retain all jobs under
`.eval-author/jobs/`, with new names on reruns:

```bash
harbor run -p .eval-author/task-drafts/<slug> -a nop \
  --jobs-dir .eval-author/jobs --job-name <slug>-nop-1
harbor run -p .eval-author/task-drafts/<slug> -a oracle \
  --jobs-dir .eval-author/jobs --job-name <slug>-oracle-1
```

Inspect Harbor trial results. Require NOP reward 0 and Oracle reward 1 without
exceptions. Also exercise the planned incorrect result against the verifier in
an isolated draft environment and retain its rejection evidence. An execution
error is not a successful negative control. Fix task defects without weakening
the intended assertion, then repeat proof after changes. Report missing backend
or failed proof honestly; a draft is not a proven test.

## 4. Evaluate the user's agent and deliver

Establish a supported Harbor integration for the actual agent from its entry
point, installed adapter code, registry, and CLI help. Do not substitute another
agent or rewrite the application. If the adapter is missing, deliver task proof
and the specific integration requirement; agent performance remains unmeasured.

When supported, write `.eval-author/first-eval.yaml` using the installed Harbor
JobConfig schema: one draft task, the actual agent and model settings, one
attempt, and jobs under `.eval-author/jobs/`. Resolve paths from the repository
root and reference credential environment variables rather than embedding secrets.
Follow `eval-author-discover` to validate this config and report its per-config
verdict if other configs exist. Do not claim it is runnable from YAML presence.

Once validated, show the actual task, agent, model, and one-attempt command.
Run it only when the user asked for execution or approved model spend; preserve
existing authorization. From the repository root:

```bash
harbor job start -c .eval-author/first-eval.yaml
```

Inspect results and update the plan with exact commands, artifact paths, proof
evidence, actual agent reward and exceptions, and remaining blockers. Distinguish
an evaluation plan, a proven task, a validated runnable config, and an evaluated
agent. An agent failing a proven task is a useful baseline, not a reason to
weaken the test or start repeated unrequested runs. One case does not prove
suite coverage or reliability.

To expand, add a representative behavior or failure case grounded in Ethos.
For coverage accounting, follow `eval-author-audit` with the established Ethos
and actual ATIF from completed runs, then `eval-author-task-create` for measured
actionable gaps. Do not fabricate traces or measurement reports when the agent
does not emit ATIF.
