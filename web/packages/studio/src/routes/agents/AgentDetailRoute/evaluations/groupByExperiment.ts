// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';

export interface AgentExperimentRow {
  name: string;
  evaluationCount: number;
  runCount: number;
  latestCreatedAt: string | null;
}

/** Roll the agent's evaluations up by experiment.
 *
 *  Derived from the evaluations rather than queried: the experiments endpoint has no
 *  ``agent_name`` filter, so "which experiments cover this agent" is only answerable through the
 *  evaluations that name it. An experiment with no published evaluation therefore does not appear.
 *  Evaluations whose experiment could not be resolved are skipped — there is nothing to group or
 *  link them under. */
export const groupByExperiment = (evaluations: AgentEvaluationRow[]): AgentExperimentRow[] => {
  const byName = new Map<string, AgentExperimentRow>();

  for (const evaluation of evaluations) {
    if (!evaluation.experimentName) continue;
    const existing = byName.get(evaluation.experimentName) ?? {
      name: evaluation.experimentName,
      evaluationCount: 0,
      runCount: 0,
      latestCreatedAt: null,
    };
    existing.evaluationCount += 1;
    existing.runCount += evaluation.run_count ?? 0;
    if (
      evaluation.created_at &&
      (!existing.latestCreatedAt || evaluation.created_at > existing.latestCreatedAt)
    ) {
      existing.latestCreatedAt = evaluation.created_at;
    }
    byName.set(evaluation.experimentName, existing);
  }

  return [...byName.values()].sort((a, b) =>
    (b.latestCreatedAt ?? '').localeCompare(a.latestCreatedAt ?? '')
  );
};
