<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Eval Author Python Reference

## `EvalAuthorResult`

`run_eval_author(...)` returns an `EvalAuthorResult` with these fields:

| Field | Type | Description |
| --- | --- | --- |
| `train_dataset` | `Dataset` | Training dataset supplied to the run. Eval Author adds Insight metric keys to its verifiers; it changes no agent-visible input. |
| `validation_dataset` | `Dataset` | Validation dataset supplied to the run, augmented the same way. |
| `insight_train_suite` | `Dataset \| None` | Insight suite train half, at `dataset/insight-train`. Visible to the optimization loop. |
| `insight_train_suite_identity` | `str \| None` | SHA-256 identity of the train half's task and verifier content. |
| `insight_validation_suite` | `Dataset \| None` | Insight suite validation half, at `dataset/insight-validation`. Held out from optimization. |
| `insight_validation_suite_identity` | `str \| None` | SHA-256 identity of the validation half's task and verifier content. |
| `summary` | `str` | Eval Author's analysis summary. |

## The two Insight halves

The authored suite is materialized into two physically separate directories,
alternating tasks so any ordering bias in the source traces is spread across both.
The odd task goes to train. A single-task suite therefore leaves
`insight_validation_suite` as `None`.

The halves carry different evidentiary weight. The train half is visible to the
optimizing agent, so its scores are adaptive/development feedback only. The
validation half is relocated to hidden storage and blocked from shell access, so
its scores are independent evidence and enter candidate ranking.

Each half has its own identity computed over exactly its own tasks. Callers can
persist a half's identity with candidate results and reuse those results only
while that identity continues to match. The canonical authored suite stays under
`eval-and-optimize/eval_author/<slug>/insight-suite/` as the provenance home.

Both halves inherit one identical metric key set, shared with `train_dataset` and
`validation_dataset`, because the scores are compared against each other
downstream. A key present in one dataset but missing from another fails the run.
