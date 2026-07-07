// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { type AgentEvalJob } from '@studio/routes/agents/AgentEvaluationsRoute/api';
import { CompareEvaluationsModal } from '@studio/routes/agents/AgentEvaluationsRoute/components/CompareEvaluationsModal';
import { render, screen } from '@studio/tests/util/render';

const fetchAgentEvalJobsMock = vi.fn();
vi.mock('@studio/routes/agents/AgentEvaluationsRoute/api', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@studio/routes/agents/AgentEvaluationsRoute/api')>();
  return {
    ...actual,
    fetchAgentEvalJobs: (...args: unknown[]) => fetchAgentEvalJobsMock(...args),
  };
});

const job = (overrides: Partial<AgentEvalJob> = {}): AgentEvalJob => ({
  name: 'eval-x',
  workspace: 'ws-a',
  status: 'completed',
  created_at: '2026-05-05T00:00:00Z',
  updated_at: '2026-05-05T00:01:00Z',
  spec: { agent: 'bot', eval_config: 'eval.yaml' },
  ...overrides,
});

const baseJob = job({ name: 'eval-base', spec: { agent: 'bot', eval_config: 'eval.yaml' } });

beforeEach(() => {
  fetchAgentEvalJobsMock.mockReset();
});

describe('CompareEvaluationsModal', () => {
  it('lists only terminal jobs that share the eval config, excluding the base job', async () => {
    fetchAgentEvalJobsMock.mockResolvedValue([
      baseJob, // excluded: same job the user is comparing from
      job({ name: 'match-completed', status: 'completed', spec: { eval_config: 'eval.yaml' } }),
      job({ name: 'other-config', status: 'completed', spec: { eval_config: 'different.yaml' } }),
      job({ name: 'still-running', status: 'running', spec: { eval_config: 'eval.yaml' } }),
    ]);

    render(
      <CompareEvaluationsModal
        open
        onClose={() => {}}
        workspace="ws-a"
        evalConfig="eval.yaml"
        baseJob={baseJob}
      />
    );

    expect(await screen.findByText('match-completed')).toBeInTheDocument();
    expect(screen.queryByText('eval-base')).not.toBeInTheDocument();
    expect(screen.queryByText('other-config')).not.toBeInTheDocument();
    expect(screen.queryByText('still-running')).not.toBeInTheDocument();
  });

  it('shows an empty message when no other completed evaluations share the config', async () => {
    fetchAgentEvalJobsMock.mockResolvedValue([baseJob]);

    render(
      <CompareEvaluationsModal
        open
        onClose={() => {}}
        workspace="ws-a"
        evalConfig="eval.yaml"
        baseJob={baseJob}
      />
    );

    expect(
      await screen.findByText('No other completed evaluations ran against this eval config yet.')
    ).toBeInTheDocument();
  });
});
