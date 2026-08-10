// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useListEvaluations } from '@nemo/sdk/generated/platform/api';
import type { EvaluationFilter } from '@nemo/sdk/generated/platform/schema';
import type { EvaluationRow } from '@studio/components/dataViews/ExperimentDataView/useExperimentEvaluations';
import { DEFAULT_LARGE_PAGE_SIZE } from '@studio/constants/constants';
import { useMemo } from 'react';

export interface ParetoEvaluations {
  rows: EvaluationRow[];
  isLoading: boolean;
  isError: boolean;
}

/** Loads every evaluation in a group in one request for the Pareto chart, reusing the list endpoint
 * (each evaluation already carries the rollup means the chart plots). */
export function useParetoEvaluations(
  workspace: string,
  experimentId: string,
  options?: { enabled?: boolean }
): ParetoEvaluations {
  // Disabled by callers that already hold the whole group, to avoid a redundant all-evaluations fetch.
  const enabled = (options?.enabled ?? true) && !!experimentId;
  const { data, isLoading, isError } = useListEvaluations(
    workspace,
    {
      page: 1,
      page_size: DEFAULT_LARGE_PAGE_SIZE,
      filter: { experiment_id: experimentId } as EvaluationFilter,
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
