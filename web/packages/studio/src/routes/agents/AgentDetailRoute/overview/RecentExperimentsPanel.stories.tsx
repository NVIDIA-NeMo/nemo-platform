// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Meta, StoryObj } from '@storybook/react';
import { toRecentExperiments } from '@studio/routes/agents/AgentDetailRoute/overview/recentExperiments';
import { RecentExperimentsPanel } from '@studio/routes/agents/AgentDetailRoute/overview/RecentExperimentsPanel';
import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';

const DAY_MS = 24 * 60 * 60 * 1000;

/** Fixed rather than `Date.now()` so the stories render identically every run. */
const LATEST = Date.parse('2026-08-18T00:00:00Z');

interface RunOptions {
  experimentId: string;
  isFavorite?: boolean;
  showsEvaluationsOverTime?: boolean;
  experimentName: string;
  experimentDescription: string;
  /** How long before {@link LATEST} the run published. */
  daysAgo: number;
  scores: Record<string, number>;
}

/** Fixtures are pushed through the real `toRecentExperiments`, so the stories exercise the actual
 *  derivation (series ordering, delta window) rather than hand-built props. */
const run = ({
  experimentId,
  experimentName,
  experimentDescription,
  isFavorite = false,
  showsEvaluationsOverTime = true,
  daysAgo,
  scores,
}: RunOptions): AgentEvaluationRow =>
  ({
    id: `${experimentId}-${daysAgo}`,
    name: `${experimentId}-run-${daysAgo}`,
    workspace: 'default',
    experiment_ids: [experimentId],
    dataset_name: 'support-bench-v3',
    experiments: [
      {
        id: experimentId,
        name: experimentName,
        description: experimentDescription,
        isFavorite,
        showsEvaluationsOverTime,
      },
    ],
    created_at: new Date(LATEST - daysAgo * DAY_MS).toISOString(),
    aggregate_scores: Object.fromEntries(
      Object.entries(scores).map(([key, mean]) => [key, { mean }])
    ),
  }) as AgentEvaluationRow;

/** A run per week going back, each evaluator drifting by a fixed step so the trend is legible. */
const weeklyRuns = (
  experiment: Omit<RunOptions, 'daysAgo' | 'scores'>,
  evaluators: Record<string, { from: number; step: number }>,
  weeks = 8
): AgentEvaluationRow[] =>
  Array.from({ length: weeks }, (_, index) =>
    run({
      ...experiment,
      daysAgo: index * 7,
      scores: Object.fromEntries(
        Object.entries(evaluators).map(([name, { from, step }]) => [
          name,
          Number((from - index * step).toFixed(3)),
        ])
      ),
    })
  );

const evaluations: AgentEvaluationRow[] = [
  ...weeklyRuns(
    {
      experimentId: 'exp-v2',
      experimentName: 'v2 use cases',
      experimentDescription:
        'Dataset of early v2 use cases to support feature development ahead of the release.',
    },
    { solved: { from: 0.16, step: 0.011 }, helpfulness: { from: 0.84, step: 0.02 } }
  ),
  ...weeklyRuns(
    {
      experimentId: 'exp-primary',
      experimentName: 'Primary use cases',
      experimentDescription:
        'Continuously evaluate every merge to main against the full Support-Bench v3 benchmark.',
      isFavorite: true,
    },
    {
      solved: { from: 0.78, step: 0.02 },
      // Negative step: this one has regressed over the window, so its delta renders red and down.
      'llm-judge.tone': { from: 0.75, step: -0.01 },
    }
  ),
];

const meta: Meta<typeof RecentExperimentsPanel> = {
  title: 'Studio/RecentExperimentsPanel',
  component: RecentExperimentsPanel,
  args: {
    favorites: toRecentExperiments(evaluations).favorites,
    experiments: toRecentExperiments(evaluations).recent,
    onOpenExperiment: () => {},
    onRunEvaluation: () => {},
  },
  decorators: [
    (Story) => (
      <div className="max-w-4xl">
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof RecentExperimentsPanel>;

export const Default: Story = {};

/** A brand-new experiment: one published run, so there is a score but no trend and no delta. */
export const SingleRun: Story = {
  args: {
    favorites: [],
    experiments: toRecentExperiments([
      run({
        experimentId: 'exp-primary',
        experimentName: 'Primary use cases',
        experimentDescription:
          'Continuously evaluate every merge to main against the full Support-Bench v3 benchmark.',
        daysAgo: 0,
        scores: { solved: 0.78, accuracy: 0.91, 'llm-judge.tone': 0.75 },
      }),
    ]).recent,
  },
};

/** An experiment that does not track its evaluations over time: summarized rather than trended. */
export const NotShownOverTime: Story = {
  args: {
    favorites: [],
    experiments: toRecentExperiments([
      run({
        experimentId: 'exp-golden',
        experimentName: 'Golden dataset',
        experimentDescription:
          'Evaluates routing accuracy and response quality across the three primary support use cases: billing inquiries, returns & refunds, and product routing.',
        showsEvaluationsOverTime: false,
        daysAgo: 0,
        scores: { solved: 0.78 },
      }),
    ]).recent,
  },
};

export const Empty: Story = {
  args: { favorites: [], experiments: [] },
};

export const Loading: Story = {
  args: { isPending: true },
};
