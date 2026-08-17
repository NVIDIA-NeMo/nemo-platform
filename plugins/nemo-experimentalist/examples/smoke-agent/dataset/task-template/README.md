<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Task template

Shape for tasks generated from an Insight's production traces. Three placeholders
are filled from the trace: `<QUESTION>` and `<FIELD>` in `instruction.md`, and
`<EXPECTED>` in `tests/expected.txt`.

## Constraints a generated task must respect

- **`<QUESTION>` must keep the grammar the tasks already use.** A question outside
  it fails for the wrong reason -- it looks like the weakness under test but is
  really a phrasing miss:
  - `What is the <field> of <Name>?`
  - `How many people are in the <dept> department?`
  - `What is the total <field> in the <scope> department?`
  - `What is the total <field> in the <role> role?`

  The last two say **`in the`**, not `for the`. That is deliberate: the agent's own
  `LIST_RE` and `COUNT_RE` prime `in the ... department`, so a total question phrased
  with `for` asks the Coder to guess a preposition it was never shown, and the round
  then measures luck rather than capability. Scoping by `role` as well as by
  `department` is what makes a general fix reachable and a hardcoded one fail
  validation.
- **`<EXPECTED>` is the answer a *correct* agent would give**, keyed by the
  canonical record field (`dept`, `role`, `hours`), never the word the question
  used. The verifier compares the whole file byte-for-byte.

  **Compute it from `records.json` in this directory.** The trace cannot supply it:
  it holds the question and the agent's *wrong* answer, never the right one — that
  is what makes it a failure. So read the records, work out what a correct agent
  would answer, and write that. A task left with `<EXPECTED>` in place scores 0 for
  every agent, repaired or not, and the run then reads as a failed repair when it
  measured nothing at all.

  Worked example: for `What is the total hours in the engineer role?`, sum `hours`
  across records whose `role` is `engineer` and write `total=<sum>`.
- **Do not edit `tests/test.sh`.** It is synced from `dataset/_shared/` and emits
  the `reward` and `shape_ok` keys every task in a dataset must share.
- **Do not add `environment/Dockerfile`.** Tasks reference a prebuilt image via
  `[environment].docker_image`; the empty `environment/` directory exists only
  because Harbor requires the directory to be present.

The records available to the agent are at `/app/data/records.json` in the image:
six people across the `research` and `ops` departments, with `name`, `dept`,
`role`, and `hours` fields.
