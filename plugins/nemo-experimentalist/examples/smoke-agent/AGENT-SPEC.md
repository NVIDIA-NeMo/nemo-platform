<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# smoke-agent

## Job

Answer one question about the records file at `/app/data/records.json` and write
the single answer line to `/app/artifacts/output.txt`.

## Interface

- Invoked as `python main.py --prompt "<instruction text>"` with `/app` as the
  working directory.
- Writes exactly one line, plus a trailing newline, to
  `/app/artifacts/output.txt`.
- Writes an OTLP JSONL trace under `/app/traces/`.

## Design

`ReportAgent.solve` dispatches the instruction across an ordered list of
handlers and returns the first non-`None` answer, falling back to a fixed
string. Each handler matches the question with a regular expression, looks the
answer up in the records, and formats one line as `<field>=<value>`.

The records are a list of objects with `name`, `dept`, `role`, and `hours`.
`FIELD_ALIASES` maps the word a question uses to the key the records store it
under, so the answer line is always keyed by the canonical field name.

## Missing and empty values

A question may name a person the records do not contain, or ask for a field
whose stored value is an empty string. Both are answered the same way: the value
is the word `unknown`, so the line reads `dept=unknown`. This is part of the
output contract and is compared byte-for-byte like any other answer — the
sentinel is `unknown` exactly, not `n/a`, `none`, or the empty string.

## Answer keys

The key on the left of the `=` names what the answer *is*, not the field it came
from. The vocabulary is fixed:

- a value read from one record uses that field's own name — `dept=`, `role=`,
  `hours=`
- a sum over records is reported as **`total=`**, whatever field was summed and
  however the records were selected
- a number of records is reported as `count=`

Keys are compared byte-for-byte like the rest of the line, so `hours=42` is wrong
where `total=42` is expected, even though the number is right.

## Constraints — these are hard requirements

- **The agent is deterministic and offline.** The same instruction must always
  produce the same answer. Reward differences between candidates must come from
  code changes, never from sampling.
- **No LLM.** Do not add a `@strategy` method, an LLM-backed handler, a subagent
  with its own model, or a model swap. The task container has no network and no
  API key, so such a change fails outright — but more importantly, being
  reproducible is this agent's entire contract.
- Standard library plus NOOA only. No new dependencies.
- Do not edit `/app/data/records.json`. It is task-supplied input, not agent
  code, and it is not part of this directory.
- The output line is compared byte-for-byte against the task's expected value,
  so trailing whitespace, extra lines, and changes to the `<field>=<value>` form
  all count as wrong answers.
