// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatEvaluatorScore } from '@nemo/common/src/utils/formatters';
import { Button, Card, Flex, Stack, StatusMessage, Text } from '@nvidia/foundations-react-core';
import { MetricTrendPanel } from '@studio/components/charts/MetricTrendPanel';
import { StackedSkeleton } from '@studio/components/StackedSkeleton';
import { LINK_DOCS_EXPERIMENTS_CLI } from '@studio/constants/links';
import {
  DELTA_COMPARISON_LABEL,
  type RecentExperiment,
} from '@studio/routes/agents/AgentDetailRoute/overview/recentExperiments';
import type { FC } from 'react';

interface RecentExperimentsPanelProps {
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
  experiments,
  isPending,
  onOpenExperiment,
  onRunEvaluation,
}) => (
  <Stack gap="4">
    <Text kind="title/md">Recent experiments</Text>

    {isPending ? (
      <StackedSkeleton count={2} height={180} className="w-full" />
    ) : experiments.length === 0 ? (
      <Card>
        <Flex justify="center" padding="density-2xl">
          <StatusMessage
            slotHeading="No experiments"
            slotSubheading={
              <>
                {'Review changes and compare multiple evaluation runs with experiments. '}
                <a
                  href={LINK_DOCS_EXPERIMENTS_CLI}
                  target="_blank"
                  rel="noreferrer"
                  className="text-brand underline"
                >
                  Learn more
                </a>
                .
              </>
            }
            slotFooter={
              onRunEvaluation ? (
                <Button color="brand" onClick={onRunEvaluation}>
                  Run evaluation
                </Button>
              ) : null
            }
          />
        </Flex>
      </Card>
    ) : (
      experiments.map((experiment) => (
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
      ))
    )}
  </Stack>
);
