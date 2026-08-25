// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RecentExperiment } from '@studio/routes/agents/AgentDetailRoute/overview/recentExperiments';
import { RecentExperimentsPanel } from '@studio/routes/agents/AgentDetailRoute/overview/RecentExperimentsPanel';
import { render, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

const experiment: RecentExperiment = {
  id: 'exp-1',
  name: 'v2 use cases',
  description: 'Dataset of early v2 use cases.',
  latestCreatedAt: '2026-08-10T00:00:00Z',
  evaluationCount: 3,
  series: [
    {
      id: 'solved',
      label: 'Solved',
      value: 0.16,
      // Already a relative change, in percent, as `toRecentExperiments` produces it.
      delta: 7.38,
      points: [
        { label: 'Aug 1', value: 0.1 },
        { label: 'Aug 10', value: 0.16 },
      ],
    },
    {
      id: 'tool_use',
      label: 'Tool Use',
      value: 0.9,
      points: [{ label: 'Aug 10', value: 0.9 }],
    },
  ],
};

describe('RecentExperimentsPanel', () => {
  it('renders a trend card per experiment with its latest score and delta', () => {
    render(<RecentExperimentsPanel experiments={[experiment]} onOpenExperiment={vi.fn()} />);

    expect(screen.getByText('Recent experiments')).toBeInTheDocument();
    expect(screen.getByText('v2 use cases')).toBeInTheDocument();
    expect(screen.getByText('Dataset of early v2 use cases.')).toBeInTheDocument();
    // The score is a bare float (no scale metadata); the delta is a relative change, so it is a
    // percentage regardless of that scale.
    expect(screen.getByText('0.16')).toBeInTheDocument();
    expect(screen.getByText('+7.4%')).toBeInTheDocument();
    expect(screen.getByText('vs. 7 days ago')).toBeInTheDocument();
  });

  it('switches the displayed value when another evaluator is selected', async () => {
    const user = userEvent.setup();
    render(<RecentExperimentsPanel experiments={[experiment]} onOpenExperiment={vi.fn()} />);

    await user.click(screen.getByText('Tool Use'));

    expect(screen.getByText('0.9')).toBeInTheDocument();
    // The selected evaluator has no week-old baseline, so no delta is claimed.
    expect(screen.queryByText('vs. 7 days ago')).not.toBeInTheDocument();
  });

  it('opens the experiment from its View action', async () => {
    const user = userEvent.setup();
    const onOpenExperiment = vi.fn();
    render(
      <RecentExperimentsPanel experiments={[experiment]} onOpenExperiment={onOpenExperiment} />
    );

    await user.click(screen.getByRole('button', { name: 'View' }));

    expect(onOpenExperiment).toHaveBeenCalledWith(experiment);
  });

  it('offers no View action for an experiment whose name never resolved', () => {
    render(
      <RecentExperimentsPanel
        experiments={[{ ...experiment, name: null }]}
        onOpenExperiment={vi.fn()}
      />
    );

    expect(screen.getByText('Unnamed experiment')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'View' })).not.toBeInTheDocument();
  });

  it('prompts for a first evaluation when the agent has no experiments', async () => {
    const user = userEvent.setup();
    const onRunEvaluation = vi.fn();
    render(
      <RecentExperimentsPanel
        experiments={[]}
        onOpenExperiment={vi.fn()}
        onRunEvaluation={onRunEvaluation}
      />
    );

    expect(screen.getByText('Measure agent performance')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Run evaluation' }));

    expect(onRunEvaluation).toHaveBeenCalled();
  });
});
