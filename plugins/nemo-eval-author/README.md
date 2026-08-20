<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Eval Author

Two skills that an agent reads to work on the evaluation suites in a user's own
repository. There is no CLI and no service. A customer points their agent at
`skills/` and nothing gets installed.

| Skill | Role |
| --- | --- |
| [`eval-author`](src/nemo_eval_author_plugin/skills/eval-author/SKILL.md) | Core. Owns the standard every sub-flow follows and routes to one. |
| [`eval-author-discover`](src/nemo_eval_author_plugin/skills/eval-author-discover/SKILL.md) | Sub-flow. Records whether a repository's Harbor evals are ready to run. |

## Why skills instead of an agent

Harbor tasks live in the customer's repository, so an agent that proposes changes
has to write to that repository. Customers were unwilling to grant that, sandboxed
or not. A skill inverts the arrangement: the customer's own agent does the work,
and this package only supplies the instructions and the deterministic scripts.

The Eval Author agent that Experimentalist insight mode still uses lives in
[the Experimentalist plugin](../nemo-experimentalist/src/nemo_experimentalist_plugin/eval_author/README.md).

## Dependencies

The scripts under `skills/*/scripts/` import the standard library only, so they run
on whatever Python the customer already has. Where a real answer needs a provider,
the skill defers to the provider's own validators rather than guessing from file
layout, which is why `eval-author-discover` probes for an installed Harbor and asks
Harbor to judge each config.

The two declared dependencies serve `tests/test_skill_contract.py`, which reads the
skills with `pyyaml` and checks them against the platform's check helpers. Adding a
runtime dependency to a bundled script is a breaking change for anyone who copied
the skill, so the contract test guards against it.
