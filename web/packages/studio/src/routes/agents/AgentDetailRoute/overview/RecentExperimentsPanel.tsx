// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatEvaluatorScore } from '@nemo/common/src/utils/formatters';
import {
  Anchor,
  Block,
  Button,
  Card,
  Flex,
  Stack,
  StatusMessage,
  Text,
} from '@nvidia/foundations-react-core';
import { MetricTrendPanel } from '@studio/components/charts/MetricTrendPanel';
import { StackedSkeleton } from '@studio/components/StackedSkeleton';
import { LINK_DOCS_EXPERIMENTS_CLI } from '@studio/constants/links';
import {
  DELTA_COMPARISON_LABEL,
  type RecentExperiment,
} from '@studio/routes/agents/AgentDetailRoute/overview/recentExperiments';
import { FlaskConical } from 'lucide-react';
import type { FC } from 'react';

interface RecentExperimentsPanelProps {
  /** Experiments the user pinned. Rendered as their own group above the recent ones. */
  favorites?: RecentExperiment[];
  experiments: RecentExperiment[];
  isPending?: boolean;
  /** Open an experiment's own route. Omitted for an experiment whose name never resolved. */
  onOpenExperiment: (experiment: RecentExperiment) => void;
  /** Empty-state action: submit an evaluation for this agent. */
  onRunEvaluation?: () => void;
}

/**
 * The score itself is a bare float with no scale metadata, so it renders as-is rather than as a
 * percentage — see {@link formatEvaluatorScore}. The delta is the opposite case: it is already a
 * relative change (a ratio of two same-unit scores), so the percent sign is accurate whatever the
 * underlying scale. One decimal keeps it to the width the tag has room for.
 */
const formatDelta = (delta: number): string =>
  `${delta > 0 ? '+' : delta < 0 ? '−' : ''}${Math.abs(delta).toFixed(1)}%`;

/**
 * How the agent is trending against each benchmark it is measured on, one card per experiment.
 *
 * Each card's pills are the evaluators that experiment reports, and the trendline is that
 * evaluator's mean across the experiment's published evaluations.
 */
export const RecentExperimentsPanel: FC<RecentExperimentsPanelProps> = ({
  favorites = [],
  experiments,
  isPending,
  onOpenExperiment,
  onRunEvaluation,
}) => {
  const card = (experiment: RecentExperiment) => (
    <MetricTrendPanel
      key={experiment.id}
      title={experiment.name ?? 'Unnamed experiment'}
      description={experiment.description ?? undefined}
      series={experiment.series}
      comparisonLabel={DELTA_COMPARISON_LABEL}
      valueLabel="Latest result"
      formatValue={formatEvaluatorScore}
      formatDelta={formatDelta}
      onViewClick={experiment.name ? () => onOpenExperiment(experiment) : undefined}
    />
  );

  if (isPending) {
    return (
      <Stack gap="4">
        <Text kind="title/md">Recent experiments</Text>
        <StackedSkeleton count={2} height={180} className="w-full" />
      </Stack>
    );
  }

  if (favorites.length === 0 && experiments.length === 0) {
    return (
      <Stack gap="4">
        <Text kind="title/md">Recent experiments</Text>
        <Card>
          <Flex justify="center" align="center" padding="density-2xl">
            <StatusMessage
              size="small"
              slotHeading="Measure agent performance"
              slotSubheading={
                <Block className="max-w-[650px]">
                  {
                    'Run evaluations for agents, models, and components with NeMo Evaluator and compare evaluations in Experiments. '
                  }
                  <Anchor href={LINK_DOCS_EXPERIMENTS_CLI} target="_blank">
                    Learn more
                  </Anchor>
                  .
                </Block>
              }
              slotFooter={
                onRunEvaluation ? (
                  <Button kind="tertiary" onClick={onRunEvaluation}>
                    <FlaskConical size={16} className="text-brand" aria-hidden />
                    Run evaluation
                  </Button>
                ) : null
              }
            />
          </Flex>
        </Card>
      </Stack>
    );
  }

  return (
    <Stack gap="density-2xl">
      {favorites.length > 0 && (
        <Stack gap="4">
          <Text kind="title/md">Favorites</Text>
          {favorites.map(card)}
        </Stack>
      )}
      {experiments.length > 0 && (
        <Stack gap="4">
          <Text kind="title/md">Recent experiments</Text>
          {experiments.map(card)}
        </Stack>
      )}
    </Stack>
  );
};
