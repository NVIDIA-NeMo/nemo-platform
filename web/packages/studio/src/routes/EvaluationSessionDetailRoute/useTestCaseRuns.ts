// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  getListEvaluationSessionsQueryKey,
  listEvaluationSessions,
} from '@nemo/sdk/generated/platform/api';
import type { EvaluationSessionResponse } from '@nemo/sdk/generated/platform/schema';
import { useQueries } from '@tanstack/react-query';

/**
 * Every run (session) of `testCaseId` across the evaluations in an experiment group.
 *
 * The sessions endpoint is scoped to a single evaluation, so this fans out one
 * query per evaluation (Option A) and flattens the results. A group-scoped
 * endpoint is the eventual replacement.
 */
export function useTestCaseRuns({
  workspace,
  evaluationNames,
  testCaseId,
}: {
  workspace: string;
  evaluationNames: string[];
  testCaseId: string | null | undefined;
}): { runs: EvaluationSessionResponse[]; isLoading: boolean } {
  const enabled = Boolean(testCaseId) && evaluationNames.length > 0;

  const results = useQueries({
    queries: evaluationNames.map((name) => {
      const params = { filter: { test_case_id: testCaseId ?? '' }, page_size: 1000 };
      return {
        queryKey: getListEvaluationSessionsQueryKey(workspace, name, params),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          listEvaluationSessions(workspace, name, params, signal),
        enabled,
      };
    }),
  });

  const isLoading = enabled && results.some((r) => r.isLoading);
  const runs = results.flatMap((r) => r.data?.data ?? []);

  return { runs, isLoading };
}
