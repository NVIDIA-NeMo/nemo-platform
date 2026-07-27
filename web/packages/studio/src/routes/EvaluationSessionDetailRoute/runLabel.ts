// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { EvaluationSessionResponse } from '@nemo/sdk/generated/platform/schema';

/** `Trial XXXXX`, where XXXXX is the last 5 chars of the session id. */
export const trialLabel = (run: EvaluationSessionResponse) => `Trial ${run.session_id.slice(-5)}`;

/** `<evaluation-name> · Trial XXXXX` — used for column headers where the run stands alone. */
export const runLabel = (run: EvaluationSessionResponse) =>
  `${run.evaluation_name} · ${trialLabel(run)}`;
