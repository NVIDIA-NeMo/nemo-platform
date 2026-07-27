// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ComparisonTable } from '@studio/components/dataViews/ComparisonTable/ComparisonTable';
import type { ComparisonEntry } from '@studio/components/dataViews/ComparisonTable/types';
import { render, screen, within } from '@studio/tests/util/render';

const score = (name: string, mean: number) => ({
  name,
  count: 10,
  nan_count: 0,
  mean,
  min: 0,
  max: 1,
  score_type: 'range' as const,
});

const evaluations: ComparisonEntry[] = [
  {
    id: 'baseline-run',
    label: 'Baseline run',
    agentName: 'support-agent-v1',
    evaluationName: 'baseline-run',
    createdAt: '2026-07-20T09:15:00Z',
    scores: [score('correctness', 0.72), score('safety', 0.93), score('latency_s', 2.4)],
  },
  {
    id: 'eval:candidate.run',
    label: 'Candidate run',
    agentName: 'support-agent-v2',
    evaluationName: 'candidate-run',
    createdAt: '2026-07-22T14:30:00Z',
    scores: [score('correctness', 0.86), score('safety', 0.93), score('latency_s', 1.9)],
  },
];

const rowFor = (metricName: string): HTMLElement => {
  const cell = screen.getByText(metricName).closest('tr');
  if (!cell) throw new Error(`no row for metric ${metricName}`);
  return cell;
};

vi.mock('lucide-react', async () => {
  return (await import('@nemo/testing/mocks/lucide')).mockLucideReact(await import('react'));
});

describe('ComparisonTable', () => {
  it('renders one row per metric and pins the metric and baseline columns', () => {
    render(<ComparisonTable evaluations={evaluations} />);

    expect(screen.getByText('Metric')).toBeInTheDocument();
    expect(screen.getByText('Baseline')).toBeInTheDocument();
    expect(screen.getByText('Baseline run')).toBeInTheDocument();
    expect(screen.getByText('Candidate run')).toBeInTheDocument();

    const pinned = document.querySelectorAll('thead th[data-pinned="left"]');
    expect(pinned).toHaveLength(2);
    expect(within(rowFor('correctness')).getByText('0.720')).toBeInTheDocument();
  });

  it('marks a higher candidate score as an improvement and a lower one as a regression', () => {
    render(<ComparisonTable evaluations={evaluations} />);

    const correctness = within(rowFor('correctness')).getByText('0.140').closest('[data-delta]');
    expect(correctness).toHaveAttribute('data-delta', 'improved');

    const latency = within(rowFor('latency_s')).getByText('0.500').closest('[data-delta]');
    expect(latency).toHaveAttribute('data-delta', 'regressed');
  });

  it('inverts the delta direction for metrics where lower is better', () => {
    render(<ComparisonTable evaluations={evaluations} lowerIsBetterMetrics={['latency_s']} />);

    const latency = within(rowFor('latency_s')).getByText('0.500').closest('[data-delta]');
    expect(latency).toHaveAttribute('data-delta', 'improved');
  });

  it('shows no delta when a metric is unchanged from the baseline', () => {
    render(<ComparisonTable evaluations={evaluations} />);

    const safety = within(rowFor('safety')).getByLabelText('No change versus baseline');
    expect(safety).toHaveAttribute('data-delta', 'unchanged');
    expect(within(safety).getByTestId('equal-icon')).toBeInTheDocument();
  });

  it('keeps column ids distinct for run ids that sanitize to the same string', () => {
    const colliding: ComparisonEntry[] = [
      evaluations[0],
      { ...evaluations[1], id: 'run/one', label: 'Slash run' },
      { ...evaluations[1], id: 'run:one', label: 'Colon run' },
    ];

    render(<ComparisonTable evaluations={colliding} />);

    const headerIds = Array.from(
      document.querySelectorAll<HTMLElement>('thead th[id^="data-view-column-"]')
    ).map((header) => header.id);

    expect(headerIds).toHaveLength(4);
    expect(new Set(headerIds).size).toBe(4);
  });
});
