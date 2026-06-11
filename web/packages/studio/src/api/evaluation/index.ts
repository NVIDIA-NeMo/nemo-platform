// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
import { evaluatorListEvaluateJobs } from '@nemo/sdk/generated/evaluator/api';
import type { EvaluatorListEvaluateJobsParams } from '@nemo/sdk/generated/evaluator/schema';
import type { EvaluationJobWithTaskMetrics } from '@studio/api/evaluation/useEvaluationsWithMetrics';

export interface FetchEvaluationsWithMetricsOptions {
  workspace: string;
  query?: EvaluatorListEvaluateJobsParams;
  signal?: AbortSignal;
}

export const fetchEvaluationsWithMetrics = async ({
  workspace,
  query,
  signal,
}: FetchEvaluationsWithMetricsOptions) => {
  const evaluations = await evaluatorListEvaluateJobs(workspace, query, signal);
  if (evaluations.data?.length > 0) {
    const evaluationsWithMetrics = await Promise.all(
      evaluations.data.map(async (evaluation) => {
        try {
          if (!evaluation.workspace) {
            return evaluation;
          }
          if (!evaluation.name) {
            return evaluation;
          }

          const evaluationWithMetrics: EvaluationJobWithTaskMetrics = { ...evaluation, tasks: {} };
          return evaluationWithMetrics;
        } catch {
          return evaluation;
        }
      })
    );
    return { ...evaluations, data: evaluationsWithMetrics };
  }
  return evaluations;
};
