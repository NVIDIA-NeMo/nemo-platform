// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Trace } from '@nemo/sdk/generated/platform/schema';
import { Accordion, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { KeyValueColumns } from '@nemo/studio-plugins-example/intake-trace-detail-agent00/KeyValueColumns';
import {
  buildExperimentContextEntries,
  buildTraceSummaryEntries,
} from '@nemo/studio-plugins-example/intake-trace-detail-agent00/traceKeyValues';
import { Activity, Hash } from 'lucide-react';
import { type FC, useMemo } from 'react';

const TRACE_SUMMARY_SECTION = 'trace-summary';
const EXPERIMENT_CONTEXT_SECTION = 'experiment-context';

interface TraceMetadataAccordionsProps {
  trace: Trace;
  workspace: string;
}

export const TraceMetadataAccordions: FC<TraceMetadataAccordionsProps> = ({
  trace,
  workspace,
}) => {
  const summaryEntries = useMemo(
    () => buildTraceSummaryEntries(trace, { workspace }),
    [trace, workspace]
  );
  const experimentEntries = useMemo(
    () => buildExperimentContextEntries(trace.experiment_context),
    [trace.experiment_context]
  );

  return (
    <Accordion
      multiple
      chevronPosition="start"
      defaultValue={[]}
      items={[
        {
          value: TRACE_SUMMARY_SECTION,
          slotTrigger: (
            <Flex align="center" gap="density-sm" className="min-w-0">
              <Activity className="shrink-0" aria-hidden />
              <Text kind="body/semibold/sm">Metadata</Text>
            </Flex>
          ),
          slotContent: (
            <Stack padding="density-lg" className="min-w-0">
              <KeyValueColumns entries={summaryEntries} />
            </Stack>
          ),
        },
        ...(experimentEntries.length > 0
          ? [
              {
                value: EXPERIMENT_CONTEXT_SECTION,
                slotTrigger: (
                  <Flex align="center" gap="density-sm" className="min-w-0">
                    <Hash className="shrink-0" aria-hidden />
                    <Text kind="body/semibold/sm">Experiment Context</Text>
                  </Flex>
                ),
                slotContent: (
                  <Stack padding="density-lg" className="min-w-0">
                    <KeyValueColumns entries={experimentEntries} />
                  </Stack>
                ),
              },
            ]
          : []),
      ]}
    />
  );
};
