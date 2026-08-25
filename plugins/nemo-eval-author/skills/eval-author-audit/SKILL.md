---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-audit
description: >-
  Define and validate an audit-spec coverage denominator for Eval Author. Use
  when the user wants a hand-editable audit.md format, needs
  schema enforcement for declared tools, capabilities, and failure cases, or
  wants to review the finite set of things future evals should cover. Ethos is
  the preferred first source when present, but is not required by the format.
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
  Python 3.11 or later. PyYAML and jsonschema must be importable by the
  interpreter that runs the bundled scripts. Validation reads local audit files
  only; it does not start Harbor jobs or call platform services.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob]
---

# Eval Author: audit

Read `eval-author` for the shared standard, vocabulary, and boundaries. This
sub-flow defines and validates a finite coverage denominator. It is expected and
strongly encouraged to start from `ETHOS.md` when one exists, but `audit.md` is a
standalone contract and can also be authored from other source-of-truth
documents. It does not generate tasks or measure traces yet.

The audit-spec approach has three item kinds in v1:

| Kind | Meaning |
|---|---|
| `tool` | A canonical tool name the agent may call |
| `capability` | A high-level behavior the agent should exercise |
| `failure_case` | Expected safe behavior when a capability cannot proceed normally |

Every item uses `name` as its stable coverage key. Names must be unique across
the whole file; do not add sequential numeric IDs. Tool references in
`required_tools`, `expected_tools`, and `evidence_required[].tool` must match the
`name` of a declared `tool` item. `prohibited_tools` may name any syntactically
valid tool name, including tools the agent must never call and therefore should
not declare as allowed tools.

Write audit artifacts under `.eval-author/`. Do not edit the customer's source,
existing evals, or source-of-truth documents such as `ETHOS.md`.

## Scripts

Audit-spec mechanics live under `scripts/audit_spec/`:

| Script | Use it to |
|---|---|
| `scripts/audit_spec/validate.py` | Validate the marked audit-spec block in `audit.md` |

Shared helpers are private modules in the same tree:
`scripts/audit_spec/_schema.py` and `scripts/audit_spec/_markdown.py`.

## Step 1: Draft Or Update The Audit Spec

Prefer `ETHOS.md` as the first source when it exists, then draft audit items at
the level between source-of-truth material and runnable tasks: canonical tools,
high-level capabilities, and material failure cases. If there is no Ethos file,
use the available product, agent, policy, or requirements document instead. Keep
the list finite. Do not create separate items for prompt paraphrases, fixture
variants, or ordinary happy-path permutations.

Use `templates/audit.md` as the starting format for `.eval-author/audit.md`.
The marked YAML block is the machine-readable part; prose outside the markers is
for reviewers and may be edited freely. When generating from `ETHOS.md`, include
the optional `sources` entry for Ethos and replace the digest placeholder with:

```bash
shasum -a 256 ETHOS.md | awk '{print "sha256:" $1}'
```

`schemas/audit.schema.json` is the canonical structural schema. The Python
validator applies that schema first, then checks any source digests that are
provided and cross-item references such as `required_tools` and `applies_to`.

Capabilities that do not need tools, such as policy refusals or out-of-scope
handling, should use `required_tools: []`. Failure cases attach to capability
names through `applies_to`; tool-level failure expectations stay on the tool item
as `expected_failure_behavior`.

## Step 2: Validate

Run validation after every hand-edited audit file:

```bash
python <skill_dir>/scripts/audit_spec/validate.py --audit .eval-author/audit.md
```

Validation proves only structure and references, not that the denominator is
complete or correct. Treat generator, measurement, and coverage-report scripts
as future work until those scripts exist in this skill.
