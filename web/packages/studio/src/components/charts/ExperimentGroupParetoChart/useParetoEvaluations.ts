// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useListEvaluations } from '@nemo/sdk/generated/platform/api';
import type { EvaluationFilter } from '@nemo/sdk/generated/platform/schema';
import type { EvaluationRow } from '@studio/components/dataViews/ExperimentGroupDataView/useExperimentGroupEvaluations';
import { useMemo } from 'react';

/** The list endpoint caps page_size at 1000; a group's evaluation set is far smaller, so one page
 * covers every point the Pareto chart needs (the leaderboard, by contrast, is paginated). */
const MAX_EVALUATIONS = 1000;

export interface ParetoEvaluations {
  rows: EvaluationRow[];
  isLoading: boolean;
  isError: boolean;
}

/**
 * Loads every evaluation in a group in one unpaginated request for the Pareto chart. Reuses the
 * existing list endpoint — each evaluation already carries the cost/latency/evaluator rollup means the
 * chart plots — so no dedicated endpoint is needed.
 */
export function useParetoEvaluations(
  workspace: string,
  experimentGroupId: string,
  options?: { enabled?: boolean }
): ParetoEvaluations {
  // Callers disable the fetch when they already have the whole group loaded (a small group that fit on
  // the leaderboard's first page), so this all-evaluations request — which re-runs the same server-side
  // rollup — is skipped entirely.
  const enabled = (options?.enabled ?? true) && !!experimentGroupId;
  const { data, isLoading, isError } = useListEvaluations(
    workspace,
    {
      page: 1,
      page_size: MAX_EVALUATIONS,
      filter: { experiment_group_id: experimentGroupId } as EvaluationFilter,
    },
    { query: { enabled } }
  );

  const rows = useMemo<EvaluationRow[]>(
    () =>
      (data?.data ?? []).map((evaluation) => ({
        ...evaluation,
        id: evaluation.id ?? evaluation.name ?? '',
      })),
    [data]
  );

  return { rows, isLoading, isError };
}
