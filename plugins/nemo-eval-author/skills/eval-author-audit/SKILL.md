---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-audit
description: >-
  Generate and validate an audit-spec coverage denominator for Eval Author. Use
  when the user wants a hand-editable audit.md file derived from Ethos, needs
  schema enforcement for declared tools, capabilities, failure cases, evidence,
  and references, or wants to review the finite set of things future evals
  should cover. Changes none of the user's source, and saves audit artifacts
  under `.eval-author/`.
triggers:
  - generate audit.md from ETHOS.md
  - validate audit.md coverage schema
  - check audit.md coverage denominator
  - what should my evals cover from the agent ethos
  - review the audit coverage denominator
not-for:
  - eval-author (use for the standard, the boundaries, and to pick a sub-flow)
  - eval-author-discover (use to prove whether a Harbor suite is runnable)
  - nemo-experimentalist (use to optimize an agent from Insights or explicit datasets)
compatibility: >-
  Python 3.11 or later. PyYAML and jsonschema must be importable by the
  interpreter that runs the bundled scripts. Generation and validation read
  local files only; they do not start Harbor jobs or call platform services.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Grep, Glob]
---

# Eval Author: audit

Read `eval-author` for the shared standard, vocabulary, and boundaries. This
sub-flow generates and validates a finite coverage denominator from `ETHOS.md`
and reviewed audit items. It does not generate tasks or measure traces yet.

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
existing evals, source-of-truth documents, or `ETHOS.md`.

## Scripts

Audit-spec mechanics live under `scripts/audit_spec/`:

| Script | Use it to |
|---|---|
| `scripts/audit_spec/generate.py` | Create, reconcile, replace, or preview `.eval-author/audit.md` from `ETHOS.md` and reviewed item proposals |
| `scripts/audit_spec/validate.py` | Validate the marked audit-spec block in `audit.md` |

Shared helpers are private modules in the same tree:
`scripts/audit_spec/_schema.py` and `scripts/audit_spec/_markdown.py`.

## Step 1: Draft Or Update Audit Items

Before drafting or updating `.eval-author/audit-items.yaml`, read
`templates/audit.md` and `schemas/audit.schema.json`. Use the template as the
worked example and the JSON Schema descriptions as the field definitions. Do not
use validation as the primary way to discover the format; validation is the
enforcement and repair step after drafting.

Read `ETHOS.md` and draft audit items at the level between Ethos and runnable
tasks: canonical tools, high-level capabilities, and material failure cases. Keep
the list finite. Do not create separate items for prompt paraphrases, fixture
variants, or ordinary happy-path permutations.

Save the reviewed item proposals as `.eval-author/audit-items.yaml`. The items
file may be either a mapping with an `items` key or the item list itself. It
should use the same item shape shown in `templates/audit.md` and enforced by
`schemas/audit.schema.json`.

For an initial audit, this file should contain the full proposed denominator.
For an update, it may contain only the proposed additions or edits. Existing
reviewed `audit.md` items remain the source of truth in reconcile mode.

Capabilities that do not need tools, such as policy refusals or out-of-scope
handling, should use `required_tools: []`. Failure cases attach to capability
names through `applies_to`; tool-level failure expectations stay on the tool item
as `expected_failure_behavior`.

## Step 2: Generate Or Reconcile Audit.md

Create or update `.eval-author/audit.md` from `ETHOS.md` and the reviewed item
proposals:

```bash
python <skill_dir>/scripts/audit_spec/generate.py \
  --ethos ETHOS.md \
  --items .eval-author/audit-items.yaml \
  --out .eval-author/audit.md
```

The default mode is `reconcile`. If `.eval-author/audit.md` does not exist, it
creates the file. If it already exists, the generator parses the existing marked
block, updates source metadata such as the Ethos digest, preserves existing item
bodies by stable `name`, appends new proposed items, and reports proposed edits
or possibly stale items without silently rewriting them. Hand-authored prose
outside the marked block is preserved.

Use the explicit modes when the default is not what the user wants:

```bash
python <skill_dir>/scripts/audit_spec/generate.py \
  --ethos ETHOS.md \
  --items .eval-author/audit-items.yaml \
  --out .eval-author/audit.md \
  --mode suggest

python <skill_dir>/scripts/audit_spec/generate.py \
  --ethos ETHOS.md \
  --items .eval-author/audit-items.yaml \
  --out .eval-author/audit.md \
  --mode reconcile

python <skill_dir>/scripts/audit_spec/generate.py \
  --ethos ETHOS.md \
  --items .eval-author/audit-items.yaml \
  --out .eval-author/audit.md \
  --mode replace
```

`suggest` performs the same comparison as `reconcile` but writes nothing.
`replace` rewrites the whole output from the item proposal file and should be
used only when the user wants to discard the existing generated audit file.

The generator prints a JSON summary containing `written`, `added_items`,
`changed_items`, and `possibly_stale_items`. Treat `changed_items` as items where
the proposal differs from the reviewed audit item; reconcile mode preserves the
reviewed item and leaves the change for the user to accept manually or through a
future editor.

The generator adds an optional `sources` entry for Ethos with `name: ethos`, a
path relative to `audit.md`, and a real `sha256` digest. It uses the frontmatter
`name` from `ETHOS.md` when `--agent` is omitted. `source_refs` are advisory
provenance notes in v1; the validator preserves them but does not resolve them
against `sources` until a future generator or grammar defines that reference
format.

## Step 3: Validate

Run validation after every generated or hand-edited audit file:

```bash
python <skill_dir>/scripts/audit_spec/validate.py --audit .eval-author/audit.md
```

`schemas/audit.schema.json` is the canonical structural schema. The Python
validator applies that schema first, then checks any source digests that are
provided and cross-item references such as `required_tools` and `applies_to`.

Validation proves only structure and references, not that the denominator is
complete or correct. Treat measurement and coverage-report scripts as future
work until those scripts exist in this skill.
