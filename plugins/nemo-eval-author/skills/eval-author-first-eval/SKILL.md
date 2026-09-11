---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-first-eval
description: >-
  Help a user with no evals establish a required Ethos, plan evaluation cases,
  and set up a small working Harbor suite while explaining its parts. No prior
  traces or coverage reports are required. Missing Harbor blocks scaffolding
  and execution, not planning.
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
to enter `eval-author-task-create`. The first milestone is a small working suite
the user understands and can rerun. Modest coverage is acceptable: do not require
comprehensive coverage, difficult tasks, repeated agent success, or trace-driven
optimization before delivering it. Explain what the starter checks measure and
where they are weak. A working suite and strong evaluation quality are separate
claims.

## 1. Establish Ethos and check the environment

### Ground the user before asking for intent

Before the first intent question, explain the outcome in ordinary language:
we will build a few repeatable checks of the agent's behavior, so the user can
see what works and rerun the checks after changes. Briefly inspect the agent's
README and entry point to make this explanation concrete. Lead with that value,
not an installation inventory, missing-file report, or skill requirement.

Explain **ETHOS.md** on first mention: it records what the agent is supposed
to do, its boundaries, and what success looks like, giving the checks a target.
If it exists, summarize the relevant intent instead of asking the user to
recreate it. If missing, explain that we will capture that intent first. Before
handing off to `nemo-explore`, give it this user-facing context and preserve its
required interview and review steps. Keep questions concrete and rooted in the
agent's actual workflows; avoid abstract choices such as “demo versus production
accountability” unless the user's goal requires that distinction.

For an airline demo with no Ethos, an opening could be:

> We'll build a few repeatable checks for this airline agent, so you can see
> whether it handles common requests correctly and rerun those checks after changes.
>
> First, we'll capture what the agent is supposed to do in **ETHOS.md**—a short
> description of its purpose, boundaries, and what success looks like. That gives
> us something to test against.
>
> For this demo, should we focus on answering baggage questions, changing seats,
> and helping with disrupted flights?

Adapt the examples to repository evidence. These are proposed areas of intent,
not authored evaluation cases; case design still waits for Ethos. If the user
already supplied the intended scope, acknowledge it and ask only the next
question required by the Ethos flow. Avoid repeating this introduction on resume.

Explain the practical reason for a question rather than using a quotation from
a skill as the explanation. If the assistant must disclose a skill-imposed
pause or permission requirement, keep that disclosure brief and separate from
the user-facing grounding; it does not replace the explanation above.

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

Run this prerequisite check without making its version or importability the
opening message. Introduce **Harbor** when explaining execution or a setup
blocker: it runs the checks from a fresh starting environment and records each
result. If available, say there is nothing to set up for Harbor at this step.
Keep version and interpreter details in the saved report unless troubleshooting
requires the user to act on them.

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
the actual agent runs. Aim for two or three simple representative cases from Ethos,
adjusting to the user's scope and available resources rather than enforcing a quota:
the user request, initial fixture, expected observable outcome, a meaningful
failure example, and the Ethos requirement each case tests. Ask only for intent
or invocation details not already established. Do not make the user supply
Harbor YAML or choose a framework.

Save `.eval-author/first-eval.md` with the Ethos path and requirement references,
cases, agent invocation, planned verifiers, prerequisites,
and unresolved questions. Preserve existing artifacts on resumption. This is an
**evaluation plan**, not a coverage report or runnable evals.

Start with a reproducible happy path, then a useful variation or expected failure
when supported by Ethos. Grade an observable result rather than a specific tool
call or exact prose. Simple assertions are acceptable if their limits are clear.
Do not replace subjective quality with brittle string
matching or mock away the behavior under test. If the requested case cannot be
tested with available resources, explain the limitation and select a supported
case with the user.

If Harbor is missing, deliver the plan and installation next step here. Resume
at step 3 after verifying Harbor; do not restart the Ethos interview.

## 3. Build the starter tasks and explain their parts

Require a working Harbor CLI and Python environment. Read its
`harbor task init --help` and `harbor run --help` before using options. Use an
unused descriptive slug for each selected case under `.eval-author/task-drafts/`.
Build one task end to end before adding the others. For each task:

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

Teach each concept when it becomes concrete, using the files being created:

- The instruction is the request the agent receives.
- Fixtures and the environment provide a repeatable starting state.
- The verifier checks the output and writes the reward. Explain the actual
  assertion and an example it cannot distinguish yet.
- The Oracle is a reference solution used to check the task, not the user's agent.
- The suite config selects tasks and an agent; job results show what happened.

Keep explanations short and practical. Do not require a separate tutorial or
turn initial task design into an exhaustive evaluation methodology exercise.

For Docker-backed execution, check `docker info` first. Retain all jobs under
`.eval-author/jobs/`, with new names on reruns:

```bash
harbor run -p .eval-author/task-drafts/<slug> -a nop \
  --jobs-dir .eval-author/jobs --job-name <slug>-nop-1
harbor run -p .eval-author/task-drafts/<slug> -a oracle \
  --jobs-dir .eval-author/jobs --job-name <slug>-oracle-1
```

For each task, inspect Harbor trial results and recorded rewards. Require NOP
reward 0 and Oracle reward 1 without exceptions: doing nothing should fail, and
the reference solution should pass. These are basic wiring and verifier sanity
checks, not evidence of broad coverage or a robust benchmark. Do not add repeated
proof runs or a separate negative-control campaign as an onboarding gate.
Investigate obvious unconditional rewards or leaked answers. Fix broken tasks
and rerun affected checks; do not weaken the intended assertion to force a pass.
Report blocked tasks separately and deliver the working subset without silently
dropping planned cases or claiming the whole suite passed.

## 4. Evaluate the user's agent and deliver

Establish a supported Harbor integration for the actual agent from its entry
point, installed adapter code, registry, and CLI help. Do not substitute another
agent or rewrite the application. If the adapter is missing, deliver the starter
tasks and their sanity-check results
and the specific integration requirement; agent performance remains unmeasured.

When supported, write `.eval-author/first-eval.yaml` using the installed Harbor
JobConfig schema: explicitly select the working starter tasks, the actual agent
and model settings, one attempt per task, and jobs under `.eval-author/jobs/`.
Do not include unrelated drafts merely because they share a parent directory.
Resolve paths from the repository
root and reference credential environment variables rather than embedding secrets.
Follow `eval-author-discover` to validate this config and report its per-config
verdict if other configs exist. Do not claim it is runnable from YAML presence.

Confirm that the resolved task set matches the selected starter tasks. Explain
the selected task count and where rewards and errors will appear.
Once validated, show the tasks, agent, model, and one-attempt-per-task command.
Run it only when the user asked for execution or approved model spend; preserve
existing authorization. From the repository root:

```bash
harbor job start -c .eval-author/first-eval.yaml
```

Inspect results for every selected task and update the plan with exact commands,
artifact paths, sanity-check results, per-task agent rewards and exceptions, and
remaining blockers. Show the user how to rerun the suite, inspect one result, and
add or modify a task. Distinguish a plan, tasks whose sanity checks passed, a
validated runnable config, and a completed agent run. If execution is blocked or
not authorized, say which milestone was reached instead of claiming the suite
ran. An agent failing a functioning task is a useful baseline, not a reason to
weaken the test or start repeated unrequested runs.

Deliver when the selected starter tasks execute and record rewards through a
validated config, even if the agent scores poorly or the checks are basic.
Document limitations such as narrow fixtures or assertions that only check part
of an outcome. Do not present successful setup as high-quality evaluation.

Treat traces and improvement as the next stage, not a prerequisite for setup.
Explain that traces reveal the agent's steps and tool calls, helping identify
failure patterns, missing coverage, and weak checks. Point to actual trace
artifacts when emitted; if absent, explain the adapter or instrumentation work
needed without blocking the working starter suite.
For coverage accounting, follow `eval-author-audit` with the established Ethos
and actual ATIF from completed runs, then `eval-author-task-create` for measured
actionable gaps. Do not fabricate traces or measurement reports when the agent
does not emit ATIF.
