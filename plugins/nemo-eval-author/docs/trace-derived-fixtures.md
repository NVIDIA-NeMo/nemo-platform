<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Trace-derived fixtures

## Purpose

The trace-environment flow can reproduce external interactions without contacting
the original service when canonical ATIF contains enough evidence. A trace is an
example of one execution, not a specification of the complete dependency. The
fixture compiler therefore makes narrow claims, fails closed, and records every
unsupported dependency instead of inferring behavior.

The first implementation supports three stages:

1. inventory every paired tool call and observation from the safe ATIF;
2. assign an evidence-backed fixture disposition to every observed tool; and
3. generate a strict MCP replay fixture only for complete, explicitly read-only
   interactions.

## Data flow

```text
canonical source
  -> safe ATIF
  -> private/interaction-inventory.json
  -> private/fixture-plan.json
  -> task/environment/trace-fixtures/
       mcp_replay.py
       scenario.json
       integration.toml
       README.md
```

The inventory and plan remain private construction evidence. Generated fixture
files enter the task tree and are covered by the existing reproducibility,
contamination, publication-review, and export gates.

## Evidence model

For each observed tool, the inventory records:

- the original tool definition and whether it provides a usable input schema;
- the explicit MCP `annotations.readOnlyHint` value, when present;
- every function name, argument object, call ID, matching observation, and ATIF
  step ID; and
- uncertainties such as missing definitions, ambiguous definitions, missing
  observations, or non-object arguments.

The compiler accepts both MCP-shaped definitions (`name`, `inputSchema`, and
`annotations`) and OpenAI-shaped definitions (`function.name` and
`function.parameters`). Read-only behavior is never inferred from a tool name.

## Dispositions

Each tool receives exactly one disposition:

| Disposition | Meaning |
| --- | --- |
| `exact_replay` | Complete schema, explicit read-only annotation, object arguments, one textual result per call, and no conflicting responses for identical arguments. |
| `stateful_fixture_required` | The definition declares mutation, or identical arguments produced different results. A state model or real seeded dependency is needed. |
| `review_required` | The interaction may be replayable, but the trace does not establish whether it is read-only. |
| `insufficient_evidence` | A definition, schema, arguments, or result needed for replay is missing or ambiguous. |

Only `exact_replay` is materialized by the initial generator. Later versions can
add reviewed overrides, state machines, seeded services, HTTP adapters, clocks,
and deterministic randomness without weakening this default.

## Replay semantics

The generated server implements the MCP `initialize`, `ping`, `tools/list`, and
`tools/call` methods over stdio. A call matches only when its tool name and
canonical JSON arguments equal a recorded case. Unknown tools and unmatched
arguments return generic errors and never reveal an expected request. Repeated
identical recorded cases are collapsed only when their results agree.

The server has no live-service fallback and needs only the Python standard
library. An optional JSONL audit path records method, tool, arguments, and match
status for later verification.

The generated `integration.toml` is an example fragment. The task author must
copy the fixture into the runtime image and merge the MCP entry into the real
`task.toml`. A stdio fixture is inspectable by a shell-capable agent, so it is
appropriate only when its cases do not expose hidden verifier truth. A stronger
follow-up should run the same contract in a filesystem-isolated sidecar and
extend the integrity scanner to prove its image and effective network topology.

## Proof requirements

Trace-derived fixtures add proof obligations beyond the existing NOP, Oracle,
negative-control, and separate-verifier checks:

- the inventory must re-derive byte-for-byte from the current safe ATIF;
- the plan must re-derive byte-for-byte from the current inventory;
- generated file hashes and executable bits must match the generation receipt;
- recorded requests must match and return the recorded generalized observations;
- unknown requests must fail closed;
- fixture state must reset for every Harbor trial; and
- no generated fixture may contact a live service.

The current implementation establishes the first five properties for stateless
stdio replay. Per-trial process creation supplies reset behavior for this
stateless form. Harbor proof remains required before an environment is ready.

## Privacy and publication

Inventory and planning read only `safe/trace.atif.json`. Materialization requires
the contextual privacy review to be complete because generated files become
publishable task inputs. Redaction placeholders are evidence of unavailable
values, not synthetic fixture values; a tool case containing an unusable
placeholder should be generalized in a new workspace or left unsupported.

Publication review must inspect the generated tool names, schemas, arguments,
results, paths, and notes. It remains distinct from trace privacy review and the
human review needed for environment readiness.
