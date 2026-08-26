<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Eval Author

Three skills help an agent work on repository-owned evaluation suites and
understand traces from NeMo Intake. This directory builds no package. A
customer points their agent at `skills/`, and nothing gets installed.

| Skill | Role |
| --- | --- |
| [`eval-author`](skills/eval-author/SKILL.md) | Core. Owns the standard every sub-flow follows and routes to one. |
| [`eval-author-discover`](skills/eval-author-discover/SKILL.md) | Sub-flow. Records whether a repository's Harbor evals are ready to run. |
| [`eval-author-inspect-trace`](skills/eval-author-inspect-trace/SKILL.md) | Sub-flow. Not user-invocable. Explains one Intake trace after `eval-author` selects it. |

## Where findings go

`eval-author-discover` leaves a report at `.eval-author/discovery.md`, carrying the
JSON as front matter so a later model reads the verdict without Harbor. It is
visible and worth committing: a teammate who reads it skips the discovery pass.

`eval-author-inspect-trace` leaves one report per trace under
`.eval-author/traces/`. The front matter carries Intake source metadata and the
exact read commands. Findings use `behavior`, `issue`, `recovery`, and
`uncertainty` categories.

The discovery scripts write no files. They report to stdout, and the skill tells
the agent where to save its report. Trace inspection contains instructions only.

## Why skills instead of an agent

Harbor tasks live in the customer's repository, so an agent that proposes changes
has to write to that repository. Customers were unwilling to grant that, sandboxed
or not. A skill inverts the arrangement: the customer's own agent does the work,
and this directory supplies instructions and deterministic discovery scripts.

## Dependencies

Trace inspection requires the supported `nemo` CLI, an explicit workspace, and
read access to a configured local or remote NeMo Platform instance. It uses
read-only `nemo intake` commands. The CLI handles its contexts, authentication,
transport, filters, pagination, and errors.

Discovery scripts use the Python standard library. The Harbor validation ladder
also imports Harbor and its transitive dependencies. The discovery flow asks
Harbor to judge each configuration instead of guessing from file layout.

`tests/test_skill_contract.py` enforces the discovery dependency boundary. The
Harbor integration tests skip when Harbor is absent.
