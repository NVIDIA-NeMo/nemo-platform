<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# hello-harbor-agent

## Job

Read one task instruction, produce the single line of text the instruction asks
for, and write that line to `/app/artifacts/output.txt`.

## Interface

- Invoked as `python main.py --prompt "<instruction text>"` with `/app` as the
  working directory.
- Writes exactly one line (plus a trailing newline) to
  `/app/artifacts/output.txt`.
- Writes an OTLP JSONL trace to `/app/traces/agent.jsonl`.

## Design

`HelloAgent.solve` dispatches the instruction across an ordered list of
handlers and returns the first non-`None` answer, falling back to a fixed
"I do not know how to answer that." string. Today the only handler is
`handle_greeting`, which echoes a `Hello, <target>!` line quoted in the
instruction.

## Constraints

- Standard library only. The task container is a bare Python image with no
  package installs, no network access, and no LLM credentials.
- Deterministic: the same instruction must always produce the same answer, so
  reward differences between candidates come from code changes rather than
  sampling noise.

## Known gap

The agent has no arithmetic capability, so any task that asks it to compute a
value scores 0. This is intentional — it gives the optimization loop a real
root cause to diagnose and close.
