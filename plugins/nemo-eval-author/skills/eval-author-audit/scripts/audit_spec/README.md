<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Audit Spec Measurement Assumptions

The audit-spec scripts treat `audit.md` as the coverage denominator. Measurement
reads one task trace, compares it to the audit items, and writes per-task,
per-method artifacts for later aggregation.

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
- The only implemented measurement method is `tool_calls`. It covers audit items
  with `kind: tool` by matching each tool item `name` against Harbor trajectory
  `ToolCall.function_name` values.
- Capability, flow, failure-case, boundary, policy, and LLM-judged coverage are
  intentionally out of scope for the current measurement method. Add those as
  separate methods that emit the same shared `coverage.json` shape plus their own
  method-specific `details.json`.
