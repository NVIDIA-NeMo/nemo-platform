<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Eval Author

Three skills help an agent work on repository-owned evaluation suites and
understand traces from supported sources. This directory builds no package.
A customer points their agent at `skills/`, and nothing gets installed.

| Skill | Role |
| --- | --- |
| [`eval-author`](skills/eval-author/SKILL.md) | Core. Owns the standard every sub-flow follows and routes to one. |
| [`eval-author-discover`](skills/eval-author-discover/SKILL.md) | Sub-flow. Records whether a repository's Harbor evals are ready to run. |
| [`eval-author-inspect-trace`](skills/eval-author-inspect-trace/SKILL.md) | Sub-flow. Explains one source-qualified trace without presuming that it failed. |

## Where findings go

`eval-author-discover` leaves a report at `.eval-author/discovery.md`, carrying the
JSON as front matter so a later model reads the verdict without Harbor. It is
visible and worth committing: a teammate who reads it skips the discovery pass.

`eval-author-inspect-trace` leaves one report per trace under
`.eval-author/traces/`. The report preserves the source identity and complete
trace bundle in its front matter. Its findings use `behavior`, `issue`,
`recovery`, and `uncertainty` categories.

The scripts write no files. They report to stdout and the skill tells the agent
where to save because that is a judgment about someone's repository.

## Why skills instead of an agent

Harbor tasks live in the customer's repository, so an agent that proposes changes
has to write to that repository. Customers were unwilling to grant that, sandboxed
or not. A skill inverts the arrangement: the customer's own agent does the work,
and this directory only supplies the instructions and the deterministic scripts.

The Eval Author agent that Experimentalist insight mode still uses lives in
[the Experimentalist plugin](../nemo-experimentalist/src/nemo_experimentalist_plugin/eval_author/README.md).

## Dependencies

The trace entry point and source adapters use only the Python standard library.
The Harbor validation ladder also imports Harbor and its transitive
dependencies. The discovery flow asks Harbor to judge each configuration
instead of guessing from file layout.

Intake is the first supported trace source. Its adapter reads `NMP_BASE_URL` and
`NMP_ACCESS_TOKEN`. It permits HTTP only for loopback targets, rejects
redirects, and makes read-only requests under
`/apis/intake/v2/workspaces/{workspace}`.

`tests/test_skill_contract.py` enforces the same dependency boundary.
`tests/test_intake_scripts.py` tests the HTTP client against a local fake server.
Neither test module imports the Platform. The five Harbor integration tests skip
when Harbor is absent.

Adding a runtime dependency to a bundled script is a breaking change for anyone who
copied the skill, so the contract test walks each script's imports and fails on
anything outside the standard library, a sibling module, or Harbor.
