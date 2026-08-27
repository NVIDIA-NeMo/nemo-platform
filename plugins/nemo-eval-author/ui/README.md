<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Eval Author Coverage Report UI

A small standalone viewer for `.eval-author/audit-coverage-report.json`.

Open `index.html` directly in a browser, then paste or open an aggregate report
with schema `nemo.eval_author.audit_coverage_report.v1`.

The viewer shows:

- overall and per-kind coverage
- measured input reports and warnings
- every uncovered audit item
- actionable uncovered tool gaps for the task-creation flow proposed in
  NVIDIA-NeMo/nemo-platform#1576

The UI does not execute commands, edit files, or call NeMo services.
