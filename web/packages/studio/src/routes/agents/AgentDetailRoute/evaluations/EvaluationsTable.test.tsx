// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EvaluationsTable } from '@studio/routes/agents/AgentDetailRoute/evaluations/EvaluationsTable';
import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';
import { LG_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';

const makeEval = (overrides: Partial<AgentEvaluationRow> & { name: string }): AgentEvaluationRow =>
  ({
    experimentName: null,
    created_at: '2024-12-17T16:08:56.880768',
    metadata: {},
    ...overrides,
  }) as AgentEvaluationRow;

const renderTable = (evaluations: AgentEvaluationRow[]) =>
  render(
    <TestProviders>
      <MemoryRouter>
        <EvaluationsTable workspace="default" evaluations={evaluations} jobs={[]} />
      </MemoryRouter>
    </TestProviders>
  );

describe('EvaluationsTable Duration column', () => {
  it('formats the recorded run duration from eval_duration_sec metadata', async () => {
    renderTable([makeEval({ name: 'eval-with-duration', metadata: { eval_duration_sec: '12' } })]);

    expect(
      await screen.findByText('Duration', undefined, { timeout: LG_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    // 12s only comes from eval_duration_sec=12 -> 12000ms -> formatDurationMs -> "12s".
    expect(
      await screen.findByText('12s', undefined, { timeout: LG_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
  });
});
