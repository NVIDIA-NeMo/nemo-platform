// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTES } from '@studio/constants/routes';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { AgentEvaluationCompareRoute } from '@studio/routes/agents/AgentEvaluationsRoute';
import { type AgentEvalJob } from '@studio/routes/agents/AgentEvaluationsRoute/api';
import { getAgentEvaluationCompareRoute } from '@studio/routes/utils';
import { renderRoute, screen } from '@studio/tests/util/render';

const fetchAgentEvalJobMock = vi.fn();
vi.mock('@studio/routes/agents/AgentEvaluationsRoute/api', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@studio/routes/agents/AgentEvaluationsRoute/api')>();
  return {
    ...actual,
    fetchAgentEvalJob: (...args: unknown[]) => fetchAgentEvalJobMock(...args),
  };
});

const fetchEvalAverageScoresMock = vi.fn();
vi.mock('@studio/routes/agents/AgentSuggestionsRoute/api', () => ({
  fetchEvalAverageScores: (...args: unknown[]) => fetchEvalAverageScoresMock(...args),
}));

const workspace = workspace1.workspace;

const job = (overrides: Partial<AgentEvalJob> = {}): AgentEvalJob => ({
  name: 'eval-a',
  workspace,
  status: 'completed',
  created_at: '2026-05-05T00:00:00Z',
  updated_at: '2026-05-05T00:01:00Z',
  spec: { agent: 'support-bot', eval_config: 'eval.yaml', output: 'out-a' },
  ...overrides,
});

const renderCompare = (jobNames: string[]) =>
  renderRoute(<AgentEvaluationCompareRoute />, {
    history: getAgentEvaluationCompareRoute(workspace, jobNames),
    routes: [
      { path: ROUTES.workspace.agentEvaluationCompare, element: <AgentEvaluationCompareRoute /> },
    ],
  });

beforeEach(() => {
  fetchAgentEvalJobMock.mockReset();
  fetchEvalAverageScoresMock.mockReset();
});

describe('AgentEvaluationCompareRoute', () => {
  it('shows the empty state when no jobs are in the query param', async () => {
    renderCompare([]);
    expect(await screen.findByText('Nothing to compare')).toBeInTheDocument();
  });

  it('renders an aligned score matrix and marks the higher score as best', async () => {
    const jobs: Record<string, AgentEvalJob> = {
      'eval-a': job({
        name: 'eval-a',
        spec: { agent: 'bot', eval_config: 'eval.yaml', output: 'out-a' },
      }),
      'eval-b': job({
        name: 'eval-b',
        spec: { agent: 'bot', eval_config: 'eval.yaml', output: 'out-b' },
      }),
    };
    const scores: Record<string, { evaluator: string; averageScore: number }[]> = {
      'out-a': [{ evaluator: 'accuracy', averageScore: 0.9 }],
      'out-b': [{ evaluator: 'accuracy', averageScore: 0.5 }],
    };
    fetchAgentEvalJobMock.mockImplementation((_ws: string, name: string) =>
      Promise.resolve(jobs[name] ?? null)
    );
    fetchEvalAverageScoresMock.mockImplementation((_ws: string, fileset: string) =>
      Promise.resolve(scores[fileset] ?? [])
    );

    renderCompare(['eval-a', 'eval-b']);

    expect(await screen.findByText('Score comparison')).toBeInTheDocument();
    expect(screen.getAllByText('eval-a').length).toBeGreaterThan(0);
    expect(screen.getAllByText('eval-b').length).toBeGreaterThan(0);
    expect(screen.getByText('0.900')).toBeInTheDocument();
    expect(screen.getByText('0.500')).toBeInTheDocument();
    // Only the higher score of the single evaluator row is flagged as best.
    expect(screen.getAllByText('best')).toHaveLength(1);
  });

  it('warns when the compared jobs ran against different eval configs', async () => {
    const jobs: Record<string, AgentEvalJob> = {
      'eval-a': job({ name: 'eval-a', spec: { eval_config: 'config-1.yaml', output: 'out-a' } }),
      'eval-b': job({ name: 'eval-b', spec: { eval_config: 'config-2.yaml', output: 'out-b' } }),
    };
    fetchAgentEvalJobMock.mockImplementation((_ws: string, name: string) =>
      Promise.resolve(jobs[name] ?? null)
    );
    fetchEvalAverageScoresMock.mockResolvedValue([]);

    renderCompare(['eval-a', 'eval-b']);

    expect(await screen.findByText('Different eval configs')).toBeInTheDocument();
  });

  it('reports jobs that could not be found', async () => {
    fetchAgentEvalJobMock.mockResolvedValue(null);
    fetchEvalAverageScoresMock.mockResolvedValue([]);

    renderCompare(['ghost-1', 'ghost-2']);

    expect(await screen.findByText('Evaluations not found')).toBeInTheDocument();
  });
});
