// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useGetExperiment, useListEvaluations } from '@nemo/sdk/generated/platform/api';
import { useSessionTrajectories } from '@studio/components/IntakeDetail/useSessionTrajectories';
import { useTestCaseRuns } from '@studio/routes/EvaluationSessionDetailRoute/useTestCaseRuns';
import { useMemo } from 'react';

/**
 * Every run of the current session's test case across the group's evaluations, plus
 * the test_case_id the session is keyed on.
 *
 * Shared by the compare view and the single session view's "Compare against…" entry
 * point. React Query dedupes the session/trace fetches when both the surrounding
 * route and the SessionDetailView read the same session.
 */
export function useSessionCompareRuns(
  workspace: string,
  experimentName: string,
  sessionId: string
): {
  testCaseId: string | undefined;
  runs: ReturnType<typeof useTestCaseRuns>['runs'];
  isRunsLoading: boolean;
} {
  // The session's traces supply the test_case_id every run is matched on.
  const { testCaseId } = useSessionTrajectories(workspace, sessionId);

  const { data: group } = useGetExperiment(workspace, experimentName);
  const { data: evaluationsPage } = useListEvaluations(
    workspace,
    { filter: { experiment_id: group?.id }, page_size: 1000 },
    { query: { enabled: Boolean(group?.id) } }
  );
  const evaluationNames = useMemo(
    () => evaluationsPage?.data?.map((e) => e.name) ?? [],
    [evaluationsPage]
  );

  const { runs, isLoading: isRunsLoading } = useTestCaseRuns({
    workspace,
    evaluationNames,
    testCaseId,
  });

  return { testCaseId, runs, isRunsLoading };
}
