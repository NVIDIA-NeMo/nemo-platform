// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FilterItem } from '@nemo/common/src/components/DataView/internal';
import type { GuardrailCheckEntity, Verdict } from '@studio/api/guardrail-checks/types';

/**
 * Overall status of a check's most recent run (the `status` returned by the
 * /checks endpoint). `undefined` means the check has never been run.
 */
export const getLatestRunStatus = (check: GuardrailCheckEntity): Verdict | undefined => {
  const { runs } = check.data;
  return runs.length ? runs[runs.length - 1].status : undefined;
};

/** The three result buckets the UI presents, keyed by their filter value. */
const RESULT_FILTER_VALUES = {
  guarded: 'blocked',
  allowed: 'success',
  notRun: 'not-run',
} as const;

/** Options for the "Result" single-select column filter. */
export const RESULT_FILTER_OPTIONS: FilterItem[] = [
  { value: RESULT_FILTER_VALUES.guarded, label: 'Guarded' },
  { value: RESULT_FILTER_VALUES.allowed, label: 'Allowed' },
  { value: RESULT_FILTER_VALUES.notRun, label: 'Not run' },
];

/**
 * Bucket a verdict for filtering. `StatusEnum` also carries `unknown`, which — like a check
 * that has never run — is presented as "Not run" rather than as its own result.
 */
export const getResultFilterValue = (status: Verdict | undefined): string => {
  if (status === RESULT_FILTER_VALUES.guarded) {
    return RESULT_FILTER_VALUES.guarded;
  }
  if (status === RESULT_FILTER_VALUES.allowed) {
    return RESULT_FILTER_VALUES.allowed;
  }
  return RESULT_FILTER_VALUES.notRun;
};

/** Ascending sort order for the Result column: guarded first, never-run last. */
const RESULT_SORT_RANK: Record<string, number> = {
  [RESULT_FILTER_VALUES.guarded]: 0,
  [RESULT_FILTER_VALUES.allowed]: 1,
  [RESULT_FILTER_VALUES.notRun]: 2,
};

/** Sort weight for a verdict, for the Result column's client-side sort. */
export const getResultSortRank = (status: Verdict | undefined): number =>
  RESULT_SORT_RANK[getResultFilterValue(status)];
