<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Task template

Shape for tasks generated from an Insight's production traces. Three placeholders
are filled from the trace: `<QUESTION>` and `<FIELD>` in `instruction.md`, and
`<EXPECTED>` in `tests/expected.txt`.

## Constraints a generated task must respect

- **`<QUESTION>` must keep the grammar the agent already parses.** It recognises
  exactly three forms, and a question outside them fails for the wrong reason --
  it looks like the weakness under test but is really a phrasing miss:
  - `What is the <field> of <Name>?`
  - `How many people are in the <dept> department?`
  - `What is the total <field> for the <scope> department?`
- **`<EXPECTED>` is the answer a *correct* agent would give**, keyed by the
  canonical record field (`dept`, `role`, `hours`), never the word the question
  used. The verifier compares the whole file byte-for-byte.
- **Do not edit `tests/test.sh`.** It is synced from `dataset/_shared/` and emits
  the `reward` and `shape_ok` keys every task in a dataset must share.
- **Do not add `environment/Dockerfile`.** Tasks reference a prebuilt image via
  `[environment].docker_image`; the empty `environment/` directory exists only
  because Harbor requires the directory to be present.

The records available to the agent are at `/app/data/records.json` in the image:
six people across the `research` and `ops` departments, with `name`, `dept`,
`role`, and `hours` fields.
