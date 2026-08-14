// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Button,
  Flex,
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { TraceStatisticsChart } from '@studio/components/AgentTraceStatistics/TraceStatisticsChart';
import { TraceStatisticsEmptyState } from '@studio/components/AgentTraceStatistics/TraceStatisticsEmptyState';
import { TraceStatisticsTiles } from '@studio/components/AgentTraceStatistics/TraceStatisticsTiles';
import type {
  TraceStatisticsRange,
  TraceStatisticsSample,
} from '@studio/components/AgentTraceStatistics/types';
import {
  RANGE_LABELS,
  bucketTraceAverages,
  summarizeTraces,
} from '@studio/components/AgentTraceStatistics/utils';
import { ListTree } from 'lucide-react';
import { type FC, useMemo } from 'react';

const RANGE_OPTIONS: TraceStatisticsRange[] = ['day', 'week', 'month'];

export interface AgentTraceStatisticsProps {
  /**
   * Traces already scoped to the selected range. The caller owns the query, so changing `range`
   * refetches rather than re-slicing a cached superset.
   */
  traces: TraceStatisticsSample[];
  range: TraceStatisticsRange;
  onRangeChange: (range: TraceStatisticsRange) => void;
  /** Omit to hide the "View traces" action. */
  onViewTraces?: () => void;
  /** Empty-state action: invoke the agent so it emits its first traces. */
  onRunAgent?: () => void;
  /** Empty-state action: open the tracing setup docs. */
  onLearnMore?: () => void;
  isPending?: boolean;
  chartHeight?: number;
}

export const AgentTraceStatistics: FC<AgentTraceStatisticsProps> = ({
  traces,
  range,
  onRangeChange,
  onViewTraces,
  onRunAgent,
  onLearnMore,
  isPending,
  chartHeight,
}) => {
  const summary = useMemo(() => summarizeTraces(traces), [traces]);
  const buckets = useMemo(() => bucketTraceAverages(traces, range), [traces, range]);
  const isEmpty = !isPending && traces.length === 0;

  return (
    <Stack gap="density-xl">
      <Flex justify="between" align="center" gap="density-md" wrap="wrap">
        <Text kind="title/md">Trace statistics</Text>
        <Flex gap="density-md" align="center">
          {onViewTraces && !isEmpty ? (
            <Button kind="secondary" onClick={onViewTraces}>
              <ListTree size={16} aria-hidden />
              View traces
            </Button>
          ) : null}
          <SelectRoot
            value={range}
            onValueChange={(value: string) => onRangeChange(value as TraceStatisticsRange)}
          >
            <SelectTrigger aria-label="Statistics range" className="w-32" />
            <SelectContent className="min-w-40">
              <SelectListbox>
                {RANGE_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {RANGE_LABELS[option]}
                  </SelectItem>
                ))}
              </SelectListbox>
            </SelectContent>
          </SelectRoot>
        </Flex>
      </Flex>

      {isEmpty ? (
        <TraceStatisticsEmptyState
          onRunAgent={onRunAgent}
          onLearnMore={onLearnMore}
          onExpandRange={range === 'month' ? undefined : () => onRangeChange('month')}
        />
      ) : (
        <>
          <TraceStatisticsTiles summary={summary} isPending={isPending} />
          <TraceStatisticsChart
            buckets={buckets}
            range={range}
            isPending={isPending}
            height={chartHeight}
          />
        </>
      )}
    </Stack>
  );
};
