// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useEvaluatorListEvaluateJobs } from '@nemo/sdk/generated/evaluator/api';
import type { EvaluatorListEvaluateJobsParams } from '@nemo/sdk/generated/evaluator/schema';

/**
 * Custom hook to fetch evaluation jobs filtered by configuration.
 * Jobs are sorted by most recently created.
 *
 * @example
 * const { data, isLoading } = useEvaluationsByConfig({
 *   page: 1,
 *   page_size: 10
 * });
 *
 * @returns TanStack Query result with evaluation jobs data
 */
export const useEvaluationsByConfig = (
  workspace: string,
  config: Partial<EvaluatorListEvaluateJobsParams>
) => {
  const params: EvaluatorListEvaluateJobsParams = {
    page: config.page,
    page_size: config.page_size,
    sort: 'created_at',
  };

  return useEvaluatorListEvaluateJobs(workspace, params);
};
