// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { GuardrailCheckEntity, Verdict } from '@studio/api/guardrail-checks/types';

/**
 * Overall status of a check's most recent run (the `status` returned by the
 * /checks endpoint). `undefined` means the check has never been run.
 */
export const getLatestRunStatus = (check: GuardrailCheckEntity): Verdict | undefined => {
  const { runs } = check.data;
  return runs.length ? runs[runs.length - 1].status : undefined;
};
