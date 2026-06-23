// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeAccordion } from '@nemo/common/src/components/IntakeAccordion';
import type { Trace } from '@nemo/sdk/generated/platform/schema';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { KeyValueColumns } from '@nemo/studio-plugins-example/intake-trace-detail/KeyValueColumns';
import {
  buildExperimentContextEntries,
  buildTraceSummaryEntries,
} from '@nemo/studio-plugins-example/intake-trace-detail/traceKeyValues';
import { type FC, useMemo } from 'react';

const TRACE_SUMMARY_SECTION = 'trace-summary';
const EXPERIMENT_CONTEXT_SECTION = 'experiment-context';

interface TraceMetadataAccordionsProps {
  trace: Trace;
  workspace: string;
}

export const TraceMetadataAccordions: FC<TraceMetadataAccordionsProps> = ({ trace, workspace }) => {
  const summaryEntries = useMemo(
    () => buildTraceSummaryEntries(trace, { workspace }),
    [trace, workspace]
  );
  const experimentEntries = useMemo(
    () => buildExperimentContextEntries(trace.experiment_context),
    [trace.experiment_context]
  );

  return (
    <IntakeAccordion
      variant="section"
      defaultValue={[]}
      items={[
        {
          value: TRACE_SUMMARY_SECTION,
          slotLabel: <Text kind="body/semibold/sm">Metadata</Text>,
          slotContent: (
            <Stack className="min-w-0">
              <KeyValueColumns entries={summaryEntries} />
            </Stack>
          ),
        },
        ...(experimentEntries.length > 0
          ? [
              {
                value: EXPERIMENT_CONTEXT_SECTION,
                slotLabel: <Text kind="body/semibold/sm">Experiment Context</Text>,
                slotContent: (
                  <Stack className="min-w-0">
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
