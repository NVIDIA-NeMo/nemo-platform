// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { Flex, PanelContent, PanelRoot, Stack, Text } from '@nvidia/foundations-react-core';
import type { RecentExperiment } from '@studio/routes/agents/AgentDetailRoute/overview/recentExperiments';
import type { FC } from 'react';

interface ExperimentSummaryCardProps {
  experiment: RecentExperiment;
  /** Omitted for an experiment whose name never resolved, since there is no route to open. */
  onOpen?: () => void;
}

/**
 * An experiment that does not track its evaluations over time, summarized: how much has run
 * against it, what it is, and when it last did.
 *
 * The count stands in for the trendline {@link MetricTrendPanel} shows on an experiment that does
 * track over time — without that flag the evaluations are not successive runs of one measurement,
 * so a line through their scores would draw a trend that does not exist. It keeps the same left
 * value column so the two card kinds read as one list.
 *
 * The whole card is the link, rather than the title: nothing inside it goes anywhere else, so an
 * underlined name would only advertise a target the entire surface already has.
 */
export const ExperimentSummaryCard: FC<ExperimentSummaryCardProps> = ({ experiment, onOpen }) => {
  const body = (
    <PanelContent>
      <Flex align="center" gap="density-2xl">
        <Stack gap="density-xs" className="w-30 shrink-0 text-center">
          <Text kind="display/lg">{experiment.evaluationCount}</Text>
          <Text kind="body/regular/md" className="text-disabled">
            {experiment.evaluationCount === 1 ? 'evaluation' : 'evaluations'}
          </Text>
        </Stack>

        <Stack gap="density-sm" className="min-w-0 flex-1 text-left">
          <Flex align="start" gap="density-lg">
            <Text kind="label/bold/xl" className="min-w-0 flex-1">
              {experiment.name ?? 'Unnamed experiment'}
            </Text>
            {experiment.latestCreatedAt && (
              <Text kind="body/regular/sm" className="shrink-0">
                <RelativeTime
                  datetime={experiment.latestCreatedAt}
                  underline={false}
                  focusableForTooltip={false}
                />
              </Text>
            )}
          </Flex>
          {experiment.description && (
            <Text kind="body/regular/md" className="text-secondary">
              {experiment.description}
            </Text>
          )}
        </Stack>
      </Flex>
    </PanelContent>
  );

  if (!onOpen) {
    return <PanelRoot elevation="mid">{body}</PanelRoot>;
  }

  return (
    <PanelRoot elevation="mid" asChild>
      <button
        type="button"
        onClick={onOpen}
        aria-label={experiment.name ?? undefined}
        className="w-full cursor-pointer text-left hover:border-(--border-color-hover)"
      >
        {body}
      </button>
    </PanelRoot>
  );
};
