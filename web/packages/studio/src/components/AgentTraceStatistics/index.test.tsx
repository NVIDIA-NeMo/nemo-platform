// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AgentTraceStatistics } from '@studio/components/AgentTraceStatistics/index';
import type { TraceStatisticsSample } from '@studio/components/AgentTraceStatistics/types';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

const TRACES: TraceStatisticsSample[] = [
  {
    startedAt: new Date('2026-07-01T00:00:00Z'),
    durationMs: 2000,
    totalTokens: 1000,
    costUsd: 0.02,
  },
  {
    startedAt: new Date('2026-07-02T00:00:00Z'),
    durationMs: 3000,
    totalTokens: 2000,
    costUsd: 0.04,
  },
];

const noop = () => {};

describe('AgentTraceStatistics', () => {
  it('renders the summary tiles from the traces it is given', () => {
    renderRoute(
      <AgentTraceStatistics traces={TRACES} range="week" onRangeChange={noop} onViewTraces={noop} />
    );

    expect(screen.getByText('Trace statistics')).toBeInTheDocument();
    expect(screen.getByText('Total traces')).toBeInTheDocument();
    // Avg token count across the two traces.
    expect(screen.getByText('1,500')).toBeInTheDocument();
    expect(screen.getByText('$0.03')).toBeInTheDocument();
  });

  it('replaces the tiles and chart with actionable guidance when there are no traces', () => {
    renderRoute(
      <AgentTraceStatistics
        traces={[]}
        range="week"
        onRangeChange={noop}
        onViewTraces={noop}
        onRunAgent={noop}
        onLearnMore={noop}
      />
    );

    expect(screen.getByText('No traces yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /run the agent/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /set up tracing/i })).toBeInTheDocument();
    expect(screen.queryByText('Total traces')).not.toBeInTheDocument();
    // Nothing to navigate to when the range is empty.
    expect(screen.queryByRole('button', { name: /view traces/i })).not.toBeInTheDocument();
  });

  it('offers to widen a narrow empty range and reports the change', async () => {
    const onRangeChange = vi.fn();
    renderRoute(<AgentTraceStatistics traces={[]} range="week" onRangeChange={onRangeChange} />);

    await userEvent.click(screen.getByRole('button', { name: /look back a month/i }));
    expect(onRangeChange).toHaveBeenCalledWith('month');
  });

  it('does not offer to widen when already on the longest range', () => {
    renderRoute(<AgentTraceStatistics traces={[]} range="month" onRangeChange={noop} />);

    expect(screen.queryByRole('button', { name: /look back a month/i })).not.toBeInTheDocument();
  });
});
