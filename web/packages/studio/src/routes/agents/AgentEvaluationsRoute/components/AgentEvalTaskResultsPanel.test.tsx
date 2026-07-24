// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentEvalTaskDetail } from '@studio/api/evaluation/agent-evaluations';
import { AgentEvalTaskResultsPanel } from '@studio/routes/agents/AgentEvaluationsRoute/components/AgentEvalTaskResultsPanel';
import { fireEvent, render, screen } from '@studio/tests/util/render';

const task: AgentEvalTaskDetail = {
  taskId: 'email-0',
  instruction: 'Subject: Test Email\nClick this suspicious link.',
  reference: { label: 'phishing' },
  metadata: {},
  status: 'completed',
  responseText: 'phishing — the message asks the user to click a suspicious link.',
  scores: [{ name: 'llm-judge.accuracy', value: 1 }],
  diagnostics: [],
};

describe('AgentEvalTaskResultsPanel', () => {
  it('shows the empty state when there are no tasks', () => {
    render(<AgentEvalTaskResultsPanel tasks={[]} />);
    expect(
      screen.getByText('No per-task results recorded for this evaluation.')
    ).toBeInTheDocument();
  });

  it('renders a task row and opens a cell in a modal', async () => {
    render(<AgentEvalTaskResultsPanel tasks={[task]} />);

    fireEvent.click(screen.getByRole('button', { name: /Task Results \(1\)/ }));

    expect(await screen.findByText('llm-judge.accuracy: 1.000')).toBeInTheDocument();

    const expandButtons = screen.getAllByLabelText('Expand cell');
    fireEvent.click(expandButtons[expandButtons.length - 1]);

    expect(await screen.findByText('Task 1 — Agent Response')).toBeInTheDocument();
  });
});
