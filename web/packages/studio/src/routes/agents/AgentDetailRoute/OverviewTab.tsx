// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';
import { Flex, Stack } from '@nvidia/foundations-react-core';
import { AgentTraceStatistics } from '@studio/components/AgentTraceStatistics';
import type { TraceStatisticsRange } from '@studio/components/AgentTraceStatistics/types';
import { bucketAdverbForRange } from '@studio/components/AgentTraceStatistics/utils';
import { INTAKE_ENABLED } from '@studio/constants/environment';
import { AgentSummaryPanel } from '@studio/routes/agents/AgentDetailRoute/overview/AgentSummaryPanel';
import { useOverviewTraces } from '@studio/routes/agents/AgentDetailRoute/overview/useOverviewTraces';
import { getIntakeTracesRoute } from '@studio/routes/utils';
import { type FC, useState } from 'react';
import { useNavigate } from 'react-router';

interface OverviewTabProps {
  workspace: string;
  agent?: Agent;
  modelNames: string[];
  /** Jump to the chat tab so the agent emits its first traces. */
  onRunAgent: () => void;
}

/** Landing view for an agent: how it has been running, next to what it is. */
export const OverviewTab: FC<OverviewTabProps> = ({ workspace, agent, modelNames, onRunAgent }) => {
  const navigate = useNavigate();
  const [range, setRange] = useState<TraceStatisticsRange>('week');
  const { traces, isPending } = useOverviewTraces({ workspace, range, enabled: INTAKE_ENABLED });

  return (
    <Flex gap="density-2xl" align="start" wrap="wrap" className="w-full pb-6">
      <Stack gap="density-2xl" className="min-w-0 flex-1 basis-[32rem]">
        {INTAKE_ENABLED && (
          <AgentTraceStatistics
            traces={traces}
            range={range}
            onRangeChange={setRange}
            onViewTraces={() => navigate(getIntakeTracesRoute(workspace))}
            onRunAgent={onRunAgent}
            isPending={isPending}
            caption={`${bucketAdverbForRange(range)}`}
          />
        )}
      </Stack>
      <div className="w-full shrink-0 lg:w-80">
        <AgentSummaryPanel agent={agent} modelNames={modelNames} />
      </div>
    </Flex>
  );
};
