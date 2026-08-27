// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';

export interface AgentExperimentRow {
  id: string;
  name: string | null;
  evaluationCount: number;
  runCount: number;
  latestCreatedAt: string | null;
}

/** Roll the agent's evaluations up by experiment.
 *
 *  Derived from the evaluations rather than queried: the experiments endpoint has no
 *  ``agent_name`` filter, so "which experiments cover this agent" is only answerable through the
 *  evaluations that name it. An experiment with no published evaluation therefore does not appear.
 *
 *  Keyed on the experiment id, which every evaluation carries, rather than the resolved name,
 *  which is only known for experiments inside the fetched page. Grouping therefore never drops a
 *  row and the counts stay honest; an unresolved row loses only its label and its link.
 *
 *  An evaluation counts toward every experiment it belongs to, not just its first: membership is
 *  many-to-many, so counting only `experiment_ids[0]` would make every experiment that shares an
 *  evaluation under-report. */
export const groupByExperiment = (evaluations: AgentEvaluationRow[]): AgentExperimentRow[] => {
  const byId = new Map<string, AgentExperimentRow>();

  for (const evaluation of evaluations) {
    for (const experiment of evaluation.experiments) {
      const existing = byId.get(experiment.id) ?? {
        id: experiment.id,
        name: experiment.name,
        evaluationCount: 0,
        runCount: 0,
        latestCreatedAt: null,
      };
      existing.name ??= experiment.name;
      existing.evaluationCount += 1;
      existing.runCount += evaluation.run_count ?? 0;
      if (
        evaluation.created_at &&
        (!existing.latestCreatedAt || evaluation.created_at > existing.latestCreatedAt)
      ) {
        existing.latestCreatedAt = evaluation.created_at;
      }
      byId.set(experiment.id, existing);
    }
  }

  return [...byId.values()].sort((a, b) =>
    (b.latestCreatedAt ?? '').localeCompare(a.latestCreatedAt ?? '')
  );
};
