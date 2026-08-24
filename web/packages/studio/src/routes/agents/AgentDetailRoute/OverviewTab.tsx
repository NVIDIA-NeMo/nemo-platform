// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';
import { Flex, Stack } from '@nvidia/foundations-react-core';
import { AgentTraceStatistics } from '@studio/components/AgentTraceStatistics';
import type { TraceStatisticsRange } from '@studio/components/AgentTraceStatistics/types';
import { bucketAdverbForRange } from '@studio/components/AgentTraceStatistics/utils';
import { INTAKE_ENABLED } from '@studio/constants/environment';
import { AgentSummaryPanel } from '@studio/routes/agents/AgentDetailRoute/overview/AgentSummaryPanel';
import { useAgentTraceMetrics } from '@studio/routes/agents/AgentDetailRoute/overview/useAgentTraceMetrics';
import { getIntakeTracesRoute } from '@studio/routes/utils';
import { type FC, useState } from 'react';
import { useNavigate } from 'react-router';

interface OverviewTabProps {
  workspace: string;
  /**
   * From the route params, so the rollup query starts on the first render. Waiting on `agent.name`
   * would leave the statistics looking empty until the agent fetch lands.
   */
  agentName?: string;
  agent?: Agent;
  modelNames: string[];
  /** Jump to the chat tab so the agent emits its first traces. */
  onRunAgent: () => void;
}

/** Landing view for an agent: how it has been running, next to what it is. */
export const OverviewTab: FC<OverviewTabProps> = ({
  workspace,
  agentName,
  agent,
  modelNames,
  onRunAgent,
}) => {
  const navigate = useNavigate();
  const [range, setRange] = useState<TraceStatisticsRange>('week');
  const { summary, buckets, isPending } = useAgentTraceMetrics({
    workspace,
    agentName,
    range,
    enabled: INTAKE_ENABLED,
  });

  if (!INTAKE_ENABLED) {
    return (
      <div className="w-full pb-6">
        <AgentSummaryPanel agent={agent} modelNames={modelNames} />
      </div>
    );
  }

  return (
    <Flex gap="density-2xl" align="start" wrap="wrap" className="w-full pb-6">
      <Stack gap="density-2xl" className="min-w-0 flex-1 basis-[32rem]">
        <AgentTraceStatistics
          summary={summary}
          buckets={buckets}
          range={range}
          onRangeChange={setRange}
          onViewTraces={() => navigate(getIntakeTracesRoute(workspace))}
          onRunAgent={onRunAgent}
          isPending={isPending}
          caption={bucketAdverbForRange(range)}
        />
      </Stack>
      <div className="w-full shrink-0 lg:w-80">
        <AgentSummaryPanel agent={agent} modelNames={modelNames} />
      </div>
    </Flex>
  );
};
