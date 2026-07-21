// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useListEvaluationSessions } from '@nemo/sdk/generated/platform/api';
import type { EvaluationSessionResponse } from '@nemo/sdk/generated/platform/schema';

export type CompareSessionState =
  | { status: 'loading' }
  | { status: 'no-test-case-id' }
  | { status: 'not-found'; testCaseId: string }
  | { status: 'found'; session: EvaluationSessionResponse };

/**
 * Looks up the session in `compareEvaluationName` that matches `testCaseId`.
 *
 * Returns a discriminated union so callers can handle each case without
 * null-checking multiple fields.
 */
export function useCompareSession({
  workspace,
  compareEvaluationName,
  testCaseId,
  isTestCaseIdLoading = false,
}: {
  workspace: string;
  compareEvaluationName: string;
  testCaseId: string | null | undefined;
  /** True while the primary trace (the source of `testCaseId`) is still loading. */
  isTestCaseIdLoading?: boolean;
}): CompareSessionState {
  const enabled = Boolean(testCaseId);

  const { data, isLoading } = useListEvaluationSessions(
    workspace,
    compareEvaluationName,
    { filter: { test_case_id: testCaseId ?? '' }, page_size: 1 },
    { query: { enabled } }
  );

  if (isTestCaseIdLoading && !testCaseId) {
    return { status: 'loading' };
  }

  if (!testCaseId) {
    return { status: 'no-test-case-id' };
  }

  if (isLoading) {
    return { status: 'loading' };
  }

  const session = data?.data?.[0];
  if (!session) {
    return { status: 'not-found', testCaseId };
  }

  return { status: 'found', session };
}
