<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Eval Author

Three skills that an agent reads to work on the evaluation suites in a user's own
repository. There is no CLI, no service, and no importable code, so this directory
builds no package at all. A customer points their agent at `skills/` and nothing
gets installed.

## Prerequisites

Discovery imports nothing beyond the standard library and Harbor itself, so it
runs on whatever Python the customer already has. Audit validation needs PyYAML
to read the marked YAML block and jsonschema to enforce
`schemas/audit.schema.json`.

`tests/test_skill_contract.py` holds to the same boundary and imports nothing
from the platform, so `pytest`, `pyyaml`, and `jsonschema` are enough to run it.
The five tests that make Harbor judge a fixture suite skip when Harbor is absent,
which is why this directory declares no dependencies and appears in no dependency
group.

| Skill | Role |
| --- | --- |
| [`eval-author`](skills/eval-author/SKILL.md) | Core. Owns the standard every sub-flow follows and routes to one. |
| [`eval-author-discover`](skills/eval-author-discover/SKILL.md) | Sub-flow. Records whether a repository's Harbor evals are ready to run. |
| [`eval-author-audit`](skills/eval-author-audit/SKILL.md) | Sub-flow. Validates an existing finite `audit.md` coverage denominator. |

## Where findings go

`eval-author-discover` leaves a report at `.eval-author/discovery.md`, carrying the
JSON as front matter so a later model reads the verdict without Harbor. It is
visible and worth committing: a teammate who reads it skips the discovery pass.

The scripts write no files. They report to stdout and the skill tells the agent
where to save, because that is a judgement about someone's repository.

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

## Next Steps

- Start with [`eval-author`](skills/eval-author/SKILL.md) to select the right
  sub-flow and apply the shared evaluation standard.
- Use [`eval-author-discover`](skills/eval-author-discover/SKILL.md) to check
  whether a Harbor suite can run.
- Use [`eval-author-audit`](skills/eval-author-audit/SKILL.md) to validate an
  existing finite `audit.md` coverage denominator.
