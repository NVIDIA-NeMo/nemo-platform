// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { EvaluationSessionResponse } from '@nemo/sdk/generated/platform/schema';

/** `<evaluation-name> · Trial XXXXX` where XXXXX is the last 5 chars of the session id. */
export const runLabel = (run: EvaluationSessionResponse) =>
  `${run.evaluation_name} · Trial ${run.session_id.slice(-5)}`;
