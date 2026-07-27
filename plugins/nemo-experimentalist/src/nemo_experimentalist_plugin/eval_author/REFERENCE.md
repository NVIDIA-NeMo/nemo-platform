<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Eval Author Python Reference

## `EvalAuthorResult`

`run_eval_author(...)` returns an `EvalAuthorResult` with these fields:

| Field | Type | Description |
| --- | --- | --- |
| `train_dataset` | `Dataset` | Training dataset supplied to the run. Eval Author does not mutate it. |
| `validation_dataset` | `Dataset` | Validation dataset supplied to the run. Eval Author does not mutate it. |
| `insight_suite` | `Dataset \| None` | Finalized experiment-local Insight dataset for immediate evaluation by the optimization loop. |
| `insight_suite_identity` | `str \| None` | SHA-256 identity of the finalized Insight task and verifier content. |
| `summary` | `str` | Eval Author's analysis summary. |

When an Insight suite is materialized successfully, `insight_suite` and
`insight_suite_identity` are both populated. Callers can persist the identity
with candidate results and reuse those results only while the suite identity
continues to match.
