// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { groupByExperiment } from '@studio/routes/agents/AgentDetailRoute/evaluations/groupByExperiment';
import type {
  AgentEvaluationRow,
  EvaluationExperiment,
} from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';

const membership = (id: string, name: string | null = id): EvaluationExperiment => ({
  id,
  name,
  description: null,
  isFavorite: false,
  showsEvaluationsOverTime: false,
});

const evaluation = (
  name: string,
  experiments: EvaluationExperiment[],
  options: { createdAt?: string; runCount?: number } = {}
): AgentEvaluationRow =>
  ({
    id: `eval-${name}`,
    name,
    workspace: 'default',
    experiment_ids: experiments.map((experiment) => experiment.id),
    experiments,
    dataset_name: 'dataset',
    created_at: options.createdAt ?? '2026-08-01T00:00:00Z',
    run_count: options.runCount ?? 1,
  }) as AgentEvaluationRow;

describe('groupByExperiment', () => {
  it('rolls evaluations up by experiment, newest first', () => {
    const rows = groupByExperiment([
      evaluation('a', [membership('exp-1')], { createdAt: '2026-08-01T00:00:00Z' }),
      evaluation('b', [membership('exp-2')], { createdAt: '2026-08-05T00:00:00Z' }),
      evaluation('c', [membership('exp-1')], { createdAt: '2026-08-03T00:00:00Z', runCount: 2 }),
    ]);

    expect(rows.map((row) => row.id)).toEqual(['exp-2', 'exp-1']);
    expect(rows[1]).toMatchObject({
      evaluationCount: 2,
      runCount: 3,
      latestCreatedAt: '2026-08-03T00:00:00Z',
    });
  });

  it('counts an evaluation toward every experiment it belongs to', () => {
    const rows = groupByExperiment([
      evaluation('shared', [membership('exp-1'), membership('exp-2')], { runCount: 2 }),
      evaluation('solo', [membership('exp-2')], { runCount: 1 }),
    ]);

    // Same timestamp on both, so the sort is stable and insertion order stands.
    expect(rows.map((row) => [row.id, row.evaluationCount, row.runCount])).toEqual([
      ['exp-1', 1, 2],
      ['exp-2', 2, 3],
    ]);
  });

  it('keys on the id so an unresolved experiment keeps its row and its counts', () => {
    const [row] = groupByExperiment([evaluation('a', [membership('exp-1', null)])]);

    expect(row).toMatchObject({ id: 'exp-1', name: null, evaluationCount: 1 });
  });

  it('ignores evaluations that belong to no experiment', () => {
    expect(groupByExperiment([evaluation('orphan', [])])).toEqual([]);
  });
});
