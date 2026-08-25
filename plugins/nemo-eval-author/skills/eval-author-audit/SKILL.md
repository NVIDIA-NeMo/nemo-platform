---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-audit
description: >-
  Validate an existing audit-spec coverage denominator for Eval Author. Use when
  the user already has an audit.md file and needs schema enforcement for declared
  tools, capabilities, failure cases, evidence, and references. Does not generate
  or draft audit.md.
triggers:
  - validate audit.md coverage schema
  - check audit.md coverage denominator
  - audit.md schema validation
  - is this audit spec valid
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
sub-flow validates an existing finite coverage denominator. It assumes
`.eval-author/audit.md` already exists. It does not draft or update audit specs,
generate tasks, or measure traces yet.

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

Do not edit the customer's source, existing evals, source-of-truth documents, or
`.eval-author/audit.md` while validating.

## Scripts

Audit-spec mechanics live under `scripts/audit_spec/`:

| Script | Use it to |
|---|---|
| `scripts/audit_spec/validate.py` | Validate the marked audit-spec block in `audit.md` |

Shared helpers are private modules in the same tree:
`scripts/audit_spec/_schema.py` and `scripts/audit_spec/_markdown.py`.

## Input

Expect `.eval-author/audit.md` to exist before this skill runs. If it is missing,
stop and say audit generation is future work for a separate sub-flow. A
hand-author can copy `templates/audit.md` as a starting format, but this
validation skill should not populate missing items. `ETHOS.md` is the expected
first source for generated audit specs when present, but the audit schema does
not require Ethos.

Use `templates/audit.md` and `schemas/audit.schema.json` only as format
references when explaining validation failures. The marked YAML block is the
machine-readable part; prose outside the markers is for reviewers and may be
edited freely. When an audit spec was generated from `ETHOS.md`, it should
include the optional `sources` entry for Ethos with a digest computed as:

```bash
shasum -a 256 ETHOS.md | awk '{print "sha256:" $1}'
```

`schemas/audit.schema.json` is the canonical structural schema. The Python
validator applies that schema first, then checks any source digests that are
provided and cross-item references such as `required_tools` and `applies_to`.
`source_refs` are advisory provenance notes in v1; the validator preserves them
but does not resolve them against `sources` until a future generator or grammar
defines that reference format.

Capabilities that do not need tools, such as policy refusals or out-of-scope
handling, should use `required_tools: []`. Failure cases attach to capability
names through `applies_to`; tool-level failure expectations stay on the tool item
as `expected_failure_behavior`.

## Validate

Run validation on the existing audit file:

```bash
python <skill_dir>/scripts/audit_spec/validate.py --audit .eval-author/audit.md
```

Validation proves only structure and references, not that the denominator is
complete or correct. Treat generator, measurement, and coverage-report scripts
as future work until those scripts exist in this skill.
