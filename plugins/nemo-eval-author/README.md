<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Eval Author

Skills that an agent reads to work on evaluation suites in a user's own
repository, close generated eval gaps, and understand traces from NeMo Intake.
This directory provides no installed public package or service, so a customer
points their agent at `skills/` and nothing gets installed.

The audit sub-flow also ships a bundled validator CLI at
[`skills/eval-author-audit/scripts/audit_spec/validate.py`](skills/eval-author-audit/scripts/audit_spec/validate.py)
and private helper modules under `scripts/audit_spec/`. They are invoked from the
copied skill tree, not published as a package API.

## Prerequisites

Discovery imports nothing beyond the standard library and Harbor itself, so it
runs on whatever Python the customer already has. Audit validation needs PyYAML
to read the marked YAML block and jsonschema to enforce
`schemas/audit.schema.json`. Trace inspection requires the supported `nemo` CLI,
an explicit workspace, and read access to a configured local or remote NeMo
Platform instance. Closing a generated task draft requires Harbor and may
require Docker plus model provider credentials.

`tests/test_skill_contract.py` holds to the same boundary and imports nothing
from the platform, so `pytest`, `pyyaml`, and `jsonschema` are enough to run it.
The five tests that make Harbor judge a fixture suite skip when Harbor is absent,
which is why this directory declares no dependencies and appears in no dependency
group.

| Skill | Role |
| --- | --- |
| [`eval-author`](skills/eval-author/SKILL.md) | Core. Owns the standard every sub-flow follows and routes to one. |
| [`eval-author-discover`](skills/eval-author-discover/SKILL.md) | Sub-flow. Records whether a repository's Harbor evals are ready to run. |
| [`eval-author-audit`](skills/eval-author-audit/SKILL.md) | Sub-flow. Generates, validates, measures, and aggregates an `audit.md` coverage denominator. |
| [`eval-author-task-create`](skills/eval-author-task-create/SKILL.md) | Sub-flow. Turns one actionable uncovered tool into a Harbor-native task draft. |
| [`eval-author-task-close`](skills/eval-author-task-close/SKILL.md) | Sub-flow. Repairs and proves one generated task draft, then classifies coverage closure from measured ATIF repeats. |
| [`eval-author-inspect-trace`](skills/eval-author-inspect-trace/SKILL.md) | Sub-flow. Not user-invocable. Explains one Intake trace after `eval-author` selects it. |

## Where findings go

`eval-author-discover` leaves a report at `.eval-author/discovery.md`, carrying the
JSON as front matter so a later model reads the verdict without Harbor. It is
visible and worth committing: a teammate who reads it skips the discovery pass.

`eval-author-task-create` writes proposals and generated Harbor task drafts under
`.eval-author/`.

`eval-author-task-close` writes task runs, measurements, and closure reports
under `.eval-author/`. It may repair only the generated task draft it is closing.
It does not promote accepted drafts into the repository's canonical eval suite.

`eval-author-inspect-trace` leaves one report per trace under
`.eval-author/traces/`. The front matter carries Intake source metadata and the
exact read commands. Findings use `behavior`, `issue`, `recovery`, and
`uncertainty` categories.

Bundled scripts print JSON verdicts to stdout and write only the explicit output
paths named by the skill. Trace inspection contains instructions only.

## Why skills instead of an agent

Harbor tasks live in the customer's repository, so an agent that proposes changes
has to write to that repository. Customers were unwilling to grant that, sandboxed
or not. A skill inverts the arrangement: the customer's own agent does the work,
and this directory only supplies the instructions and the deterministic scripts.

The Eval Author agent that Experimentalist insight mode still uses lives in
[the Experimentalist plugin](../nemo-experimentalist/src/nemo_experimentalist_plugin/eval_author/README.md).

## Dependencies

Adding a runtime dependency to a bundled script is a breaking change for anyone who
copied the skill, so the contract test walks each script's imports and fails on
anything outside the standard library, a sibling module, or the explicitly allowed
third-party validators.

Trace inspection uses read-only `nemo intake` commands. The CLI handles its
contexts, authentication, transport, filters, pagination, and errors.

## Next Steps

- Start with [`eval-author`](skills/eval-author/SKILL.md) to select the right
  sub-flow and apply the shared evaluation standard.
- Use [`eval-author-discover`](skills/eval-author-discover/SKILL.md) to check
  whether a Harbor suite can run.
- Use [`eval-author-audit`](skills/eval-author-audit/SKILL.md) to validate an
  existing finite `audit.md` coverage denominator.
- Use [`eval-author-task-create`](skills/eval-author-task-create/SKILL.md) to
  scaffold one task draft from an actionable uncovered tool.
- Use [`eval-author-task-close`](skills/eval-author-task-close/SKILL.md) to
  prove or reject that generated task draft.
- After `eval-author` selects it, follow
  [`eval-author-inspect-trace`](skills/eval-author-inspect-trace/SKILL.md) to
  explain one Intake trace.
