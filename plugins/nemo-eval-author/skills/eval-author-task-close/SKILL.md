---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-task-close
description: >-
  Close one generated Eval Author Harbor task draft by repairing only the draft,
  proving task/verifier quality with Harbor Oracle, running the real agent when
  authorized, measuring the resulting ATIF traces, and reporting whether the
  selected audit coverage gap closed. Use when the user asks to finish, verify,
  close, or prove a generated task draft. Writes only under `.eval-author/`.
triggers:
  - close a generated Harbor task
  - verify a generated eval task closes coverage
  - finish the Eval Author task draft
  - prove the generated task works
  - turn the generated task into coverage closure
not-for:
  - eval-author (use for the shared standard and routing)
  - eval-author-audit (use to create the denominator and coverage report)
  - eval-author-task-create (use to select a gap and scaffold the initial draft)
  - eval-author-discover (use to prove an existing suite is runnable)
  - nemo-evaluator (use to run an existing benchmark without authoring tasks)
compatibility: >-
  Python 3.11 or later for the helper script. Harbor is required for Oracle and
  real-agent trials. Docker is required for Docker-backed tasks. Real-agent runs
  may require provider credentials and explicit user approval.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob]
---

# Eval Author: close task

Read `eval-author` for the shared evidence standard and boundaries. Read
`eval-author-task-create` for the draft's selected target and canonical paths.
Read `eval-author-audit` before measuring any new trajectory.

This sub-flow owns the evidence loop after `eval-author-task-create` has already
created a candidate under `.eval-author/task-drafts/<task-slug>`:

```text
generated Harbor draft
  -> runnable task with a meaningful verifier
  -> Oracle reward 1
  -> real-agent ATIF repeats
  -> measured coverage closure or precise failure
```

Do not optimize for a green real-agent score. A real-agent verifier failure can
be a successful eval-authoring result when the task is runnable, the verifier is
meaningful, and the measured trace closes the target tool gap.

## Script

`scripts/task_close.py` provides deterministic checks and reports:

| Command | Verdict |
|---|---|
| `preflight` | Checks whether the local Harbor CLI is compatible and, when requested, Docker is reachable |
| `inspect` | Checks the draft layout, obvious placeholders, verifier reward writer, failure path, task metadata, and optional before-report target |
| `report` | Combines the before report, after coverage reports, Oracle reward, and real-agent rewards into one fine-grained closure verdict |

The script prints one JSON object. For `report`, exit code 0 means coverage
closure was accepted, not that the real agent necessarily passed the task.

## Status Updates

Give the user short status updates before each material step:

- draft inspection
- verifier/environment repair attempt
- Harbor Oracle run
- real-agent run request
- ATIF measurement
- closure classification

When stopping, name the specific status and human next step. Failure is a valid
outcome; asking for human task design, credentials, environment help, or verifier
review is expected when evidence is insufficient.

## Inputs

Start from the generated draft and the coverage artifacts that motivated it:

```text
.eval-author/audit.md
.eval-author/audit-coverage-report.json
.eval-author/task-drafts/<task-slug>/
target tool name
```

Use the existing Harbor config or agent invocation only when it is already proven
for this repository or the user supplies it. Real-agent runs spend credentials,
so ask before starting them unless the user already approved the run.

## Step 1: preflight local executors

```bash
uv run <skill_dir>/scripts/task_close.py preflight --require-docker \
  --out .eval-author/task-closures/<task-slug>/preflight.json
```

If this returns `blocked_no_harbor`, `blocked_incompatible_harbor`, or
`blocked_no_docker`, stop and report the status unless the user wants to change
the local environment. Do not skip Oracle proof and call the task accepted.

## Step 2: inspect the draft

```bash
uv run <skill_dir>/scripts/task_close.py inspect \
  --draft .eval-author/task-drafts/<task-slug> \
  --target <tool-name> \
  --before .eval-author/audit-coverage-report.json \
  --out .eval-author/task-closures/<task-slug>/inspection.json
```

Repair required failures before Oracle. Edit only files inside
`.eval-author/task-drafts/<task-slug>/`. Do not edit customer source, existing
evals, or frozen input traces.

## Step 3: repair for runnability and verifier sanity

Use at most three repair attempts for each category before asking for human help:

- environment/Dockerfile or task metadata repair
- verifier repair
- Oracle solution repair

The verifier grades the task outcome, not tool calls. ATIF measurement proves
tool coverage separately. Do not weaken the verifier merely to get reward 1.

Before Oracle, reason through these controls and implement them when practical:

- empty or missing answer fails
- wrong answer fails
- canonical solution passes
- verifier does not inspect trajectory/tool-call logs
- verifier does not award unconditional reward 1

If a generated verifier cannot be made meaningful, stop with
`needs_human_verifier_review`.

## Step 4: prove with Oracle

Run Harbor's Oracle before spending model credentials:

```bash
harbor trial start \
  --path .eval-author/task-drafts/<task-slug> \
  --agent oracle \
  --trial-name oracle \
  --trials-dir .eval-author/task-runs/<task-slug>/oracle
```

Continue only when Harbor reports no exception and reward 1.0. If Oracle fails,
repair the task, solution, or verifier without weakening the verifier. Stop with
`oracle_failed` after the repair budget is exhausted.

## Step 5: run the real agent without aiming for green

Run two real-agent repeats only after approval:

```bash
harbor trial start \
  --path .eval-author/task-drafts/<task-slug> \
  --agent <agent-name> \
  --trial-name repeat-1 \
  --trials-dir .eval-author/task-runs/<task-slug>/repeat-1
```

Repeat for `repeat-2`. Record each reward and trial directory. A reward 0 can be
a valid result if the task is sane and the target tool is covered.

Require each trial to emit an `agent/trajectory.json` that
`eval-author-audit` can parse. A missing or invalid ATIF file is
`trajectory_invalid`, not coverage evidence.

## Step 6: measure each new trajectory

Measure repeats separately so one successful run cannot hide another:

```bash
uv run --with-requirements <audit_skill_dir>/requirements.txt \
  <audit_skill_dir>/scripts/audit_spec/measure.py \
  --audit .eval-author/audit.md \
  --trial-dir .eval-author/task-runs/<task-slug>/repeat-1 \
  --task-id <task-slug> \
  --run-id repeat-1 \
  --out-dir .eval-author/task-measurements/<task-slug>/repeat-1

uv run --with-requirements <audit_skill_dir>/requirements.txt \
  <audit_skill_dir>/scripts/audit_spec/report.py \
  --audit .eval-author/audit.md \
  --coverage-dir .eval-author/task-measurements/<task-slug>/repeat-1 \
  --out .eval-author/task-measurements/<task-slug>/repeat-1-report.json
```

Repeat for `repeat-2`.

## Step 7: classify closure

```bash
uv run <skill_dir>/scripts/task_close.py report \
  --before .eval-author/audit-coverage-report.json \
  --after .eval-author/task-measurements/<task-slug>/repeat-1-report.json \
  --after .eval-author/task-measurements/<task-slug>/repeat-2-report.json \
  --target <tool-name> \
  --draft .eval-author/task-drafts/<task-slug> \
  --oracle-reward <oracle-reward> \
  --agent-reward <repeat-1-reward> \
  --agent-reward <repeat-2-reward> \
  --out .eval-author/task-closures/<task-slug>/closure-report.json
```

The classifier uses `--draft` to verify each after-report belongs to
`<task-slug>`. If you classify without `--draft`, pass `--task-id <task-slug>`.

Report the JSON verdict. Treat these distinctions carefully:

- `closed`: Oracle passed and both measured real-agent repeats covered the target tool.
- `agent_solved_without_target_tool`: the real agent got reward but coverage did not close.
- `coverage_unproven`: fewer than two distinct measured real-agent repeats were supplied.
- `coverage_not_closed`: the target tool was not covered in every repeat.
- `trajectory_invalid`: a new run did not produce measurable ATIF.
- `oracle_failed`: Harbor did not prove the task/verifier/solution combination.
- `task_draft_needs_repair`: static draft inspection found required gaps.
- `oracle_unproven`: Oracle was not run or the reward was not supplied.
- `blocked_no_docker`: local Docker is unavailable for Docker-backed proof.

When `status: closed` and `real_agent.passed_task: false`, the generated eval is
valid and found an agent failure. Promotion into the repository's canonical eval
suite is a separate explicit step after the user accepts the draft.
