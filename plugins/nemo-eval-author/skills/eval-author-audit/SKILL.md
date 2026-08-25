---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-audit
description: >-
  Define and validate an audit-spec coverage denominator for Eval Author. Use
  when the user wants a hand-editable audit.md format derived from Ethos, needs
  schema enforcement for declared tools, capabilities, and failure cases, or
  wants to review the finite set of things future evals should cover.
  Changes none of the user's source, and saves audit artifacts under
  `.eval-author/`.
triggers:
  - define audit.md from ETHOS.md
  - validate audit.md coverage schema
  - what should my evals cover from the agent ethos
  - review the audit coverage denominator
not-for:
  - eval-author (use for the standard, the boundaries, and to pick a sub-flow)
  - eval-author-discover (use to prove whether a Harbor suite is runnable)
  - nemo-experimentalist (use to optimize an agent from Insights or explicit datasets)
compatibility: >-
  Python 3.11 or later. PyYAML must be importable by the interpreter that runs
  the bundled scripts. Validation reads local audit files only; it does not
  start Harbor jobs or call platform services.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob]
---

# Eval Author: audit

Read `eval-author` for the shared standard, vocabulary, and boundaries. This
sub-flow defines and validates a finite coverage denominator from `ETHOS.md`.
It does not generate tasks or measure traces yet.

The audit-spec approach has three item kinds in v1:

| Kind | Meaning |
|---|---|
| `tool` | A canonical tool name the agent may call |
| `capability` | A high-level behavior the agent should exercise |
| `failure_case` | Expected safe behavior when a capability cannot proceed normally |

Write audit artifacts under `.eval-author/`. Do not edit the customer's source,
existing evals, or `ETHOS.md`.

## Scripts

Audit-spec mechanics live under `scripts/audit_spec/`:

| Script | Use it to |
|---|---|
| `scripts/audit_spec/validate.py` | Validate the marked audit-spec block in `audit.md` |

Shared helpers are private modules in the same tree:
`scripts/audit_spec/_schema.py` and `scripts/audit_spec/_markdown.py`.

## Step 1: Draft Or Update The Audit Spec

Read `ETHOS.md` and draft audit items at the level between Ethos and runnable
tasks: canonical tools, high-level capabilities, and material failure cases. Keep
the list finite. Do not create separate items for prompt paraphrases, fixture
variants, or ordinary happy-path permutations.

Use `templates/audit.md` as the starting format for `.eval-author/audit.md`.
The marked YAML block is the machine-readable part; prose outside the markers is
for reviewers and may be edited freely.

## Step 2: Validate

Run validation after every hand-edited audit file:

```bash
python <skill_dir>/scripts/audit_spec/validate.py --audit .eval-author/audit.md
```

Validation proves only structure and references, not that the denominator is
complete or correct. Treat generator, measurement, and coverage-report scripts
as future work until those scripts exist in this skill.
