---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-task-create
description: >-
  Create one Harbor task from one actionable uncovered tool in an Eval Author
  audit coverage report. Use when the user asks to fill an eval gap, turn audit
  uncovered_items into a Harbor task draft, or add missing tool coverage. Hand
  the generated draft to `eval-author-task-close` for Oracle proof, real-agent
  runs, measured ATIF, and closure classification. Writes drafts and proposals
  only under `.eval-author/`.
triggers:
  - create a Harbor task from an audit gap
  - fill an uncovered eval tool
  - generate missing eval tasks
  - close audit coverage gaps
  - turn uncovered_items into Harbor tasks
not-for:
  - eval-author (use for the shared standard and routing)
  - eval-author-audit (use to create the denominator and coverage report)
  - eval-author-task-close (use to prove or reject an existing generated task draft)
  - eval-author-discover (use to prove an existing suite is runnable)
  - nemo-evaluator (use to run an existing benchmark without authoring tasks)
compatibility: >-
  Python 3.11 or later for the copied helper scripts and a Harbor CLI compatible
  with `harbor task init`. Closing the generated draft requires
  `eval-author-task-close`, Harbor, and often Docker plus provider credentials.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob]
---

# Eval Author: create task

Read `eval-author` for the shared evidence standard and boundaries. Read
`eval-author-audit` for the coverage report that provides actionable gaps. This
sub-flow owns only:

```text
actionable uncovered tool
  → Harbor-native draft
```

Work on one tool gap at a time. Keep every generated artifact under
`.eval-author/`; do not edit existing tasks or customer source.

## Script

`scripts/task_pipeline.py` has three deterministic commands:

| Command | Verdict |
|---|---|
| `select` | Lists only tool items with `reason: not_covered_by_any_input_report` and emits a deterministic `task_slug` plus artifact paths |
| `scaffold` | Calls Harbor's own `harbor task init`, requires matching draft/proposal names for that slug, and installs the supplied instruction |
| `verify` | Deterministic primitive used by task-close-style workflows; exits 0 only when the selected tool was uncovered before and covered in two distinct repeated after-reports with distinct ATIF `subject.run_id` values |

The script prints one JSON object. Exit code 0 is success; do not replace its
verdict with model judgment.

## Step 1: select one actionable gap

```bash
uv run <skill_dir>/scripts/task_pipeline.py select \
  --report .eval-author/audit-coverage-report.json
```

Choose one item from `actionable_tools`. Stop when the list is empty. Capability
or failure-case items with `reason: not_measured_by_any_method` are not task
generation inputs in v1.

Each actionable tool includes a deterministic `task_slug` of the form
`cover-<tool-name>` and a `paths` object for the proposal, draft, and
measurement directories. Use those paths verbatim for the rest of this flow.
Do not invent alternate slugs or filenames.

## Step 2: design the smallest objective task

Read the selected item's `description`, `focus`, `needed_tools`, and
`evidence_required`. Read one nearby task for domain conventions only. Do not
copy its directory: a sibling can carry an obsolete Harbor schema, placeholder
verifier, or unrelated solution.

Write the instruction only to `paths.proposal` from Step 1. State the observable
goal, paths, and constraints without naming the target tool or leaking verifier
logic. The task should naturally require the selected tool and no unrelated
capability.

Decide the verifier before scaffolding. Prefer deterministic shell or pytest.
The verifier must grade the task outcome, not the tool call; ATIF measurement
proves tool coverage separately.

## Step 3: scaffold with Harbor

```bash
uv run <skill_dir>/scripts/task_pipeline.py scaffold \
  --report .eval-author/audit-coverage-report.json \
  --target <tool-name> \
  --out .eval-author/task-drafts/<task-slug> \
  --task-name <org>/<task-slug> \
  --description "<one-line description>" \
  --author "<author>" \
  --instruction-file .eval-author/proposals/<task-slug>-instruction.md
```

Use the Step 1 `task_slug` for `<task-slug>` in every path above. `scaffold`
rejects mismatched draft, task-name, or proposal filenames.

Then complete Harbor's generated files:

- `environment/Dockerfile`: task prerequisites, never the solution.
- `tests/test.sh`: deterministic reward writer using absolute paths.
- `solution/solve.sh`: executable Oracle solution.
- `task.toml`: nonempty keywords, metadata, realistic timeouts and resources.
- `README.md`: purpose, environment, verifier, layout, and run commands.

Do not leave generated placeholders, `pass`, unconditional reward 1, or empty
keywords.

## Step 4: hand off to task-close

After the draft exists and the generated files are filled in, use
`eval-author-task-close` to repair it, prove it with Oracle, run the real agent
when authorized, measure new ATIF, and classify closure.

The legacy `verify` command remains available as a deterministic coverage-only
primitive:

```bash
uv run <skill_dir>/scripts/task_pipeline.py verify \
  --before .eval-author/audit-coverage-report.json \
  --after .eval-author/task-measurements/<task-slug>/repeat-1-report.json \
  --after .eval-author/task-measurements/<task-slug>/repeat-2-report.json \
  --target <tool-name>
```
