<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Audit Spec Measurement And Coverage Assumptions

The audit-spec scripts treat `audit.md` as the coverage denominator. Measurement
reads one task trace, compares it to the audit items, and writes per-task,
per-run, per-method artifacts. Aggregation reads those coverage artifacts and
writes one coverage report.

Current assumptions:

- Measurement input is an ATIF trajectory JSON file. `measure.py` accepts either
  `--trace <trajectory.json>` or a Harbor trial directory containing
  `agent/trajectory.json`.
- ATIF parsing is delegated to Harbor via
  `harbor.models.trajectories.Trajectory.model_validate_json`. The scripts do not
  maintain a separate ATIF parser or schema mirror.
- Harbor is a required dependency for measurement. Use `requirements.txt` when
  running `measure.py` outside a repository environment that already provides
  Harbor.
- Reports are written under encoded path components:
  `<out-dir>/task=<task-id>/run=<run-id>/<method>/coverage.json` and
  `details.json`. The raw `task_id` and `run_id` remain in the JSON payloads.
  If no run id is provided by the CLI or Harbor result metadata, measurement
  derives one from the ATIF trajectory identity, then from the trace content
  digest.
- Aggregation input is one or more per-trace `coverage.json` files. `report.py`
  validates those files against `schemas/audit_coverage.schema.json`, rejects
  hard denominator mismatches against the current `audit.md`, and writes one
  `coverage_report.json` file.
- Aggregation treats audit status as review metadata, not denominator content.
  Status-only mismatches, such as measuring while an audit is `draft` and
  reporting after it becomes `approved`, are emitted in `warnings` without
  rejecting the input coverage file.
- Aggregation does not read ATIF traces, Harbor result files, or method-specific
  `details.json` files. It only unions stable audit item names from
  `coverage.json`.
- The aggregate report contains count summaries plus `uncovered_items`. Each
  uncovered item preserves the original audit item and adds generation-oriented
  context: the reason it is uncovered, a one-sentence focus, likely needed
  tools, and required evidence.
- The aggregate report records `measured_kinds` from the input coverage files.
  An uncovered item whose kind is absent from `measured_kinds` uses
  `reason: not_measured_by_any_method`; an uncovered item whose kind was measured
  uses `reason: not_covered_by_any_input_report`.
- Harbor's current `Trajectory` model is treated as the reader for now, but it
  may prove too strict for measurement if valid evaluator traces include producer
  extensions, omit fields that coverage does not consume, or move to a newer ATIF
  version before Harbor models are updated. If that happens, prefer contributing
  or adopting a permissive Harbor consumer reader before maintaining a local ATIF
  parser here.
- The only implemented measurement method is `tool_calls`. It covers audit items
  with `kind: tool` by matching each tool item `name` against Harbor trajectory
  `ToolCall.function_name` values.
- Capability, flow, failure-case, boundary, policy, and LLM-judged coverage are
  intentionally out of scope for the current measurement method. Add those as
  separate methods that emit the same shared `coverage.json` shape plus their own
  method-specific `details.json`.
