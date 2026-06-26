// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeAccordion } from '@nemo/common/src/components/IntakeAccordion';
import { useGetTrace } from '@nemo/sdk/generated/platform/api';
import { PageHeader, Stack, StatusMessage, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { KeyValueRows } from '@studio/components/IntakeDetail/IntakeComponents/KeyValueRows';
import { RawJsonDebug } from '@studio/components/IntakeDetail/IntakeComponents/RawJsonDebug';
import {
  buildExperimentContextEntries,
  buildTraceSummaryEntries,
} from '@studio/components/IntakeDetail/IntakeComponents/traceKeyValues';
import { TraceSummaryHeader } from '@studio/components/IntakeDetail/TraceDetailSummaryHeader';
import { TraceSpanAccordions } from '@studio/components/IntakeDetail/TraceSpanAccordions';
import { Loading } from '@studio/components/Layouts/Loading';
import { NotFound } from '@studio/components/Layouts/NotFound';
import {
  type BreadcrumbsItemProps,
  useBreadcrumbs,
} from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getIntakeTracesRoute } from '@studio/routes/utils';
import { getTraceDisplayName } from '@studio/util/intakeTelemetry';
import { CircleAlert } from 'lucide-react';
import { type FC, useEffect, useMemo } from 'react';

const TRACE_SUMMARY_SECTION = 'trace-summary';
const EXPERIMENT_CONTEXT_SECTION = 'experiment-context';

interface IntakeTraceDetailViewProps {
  workspace: string;
  traceId: string;
  /** Leading breadcrumb items. Defaults to the Intake root when omitted. */
  parentBreadcrumbs?: BreadcrumbsItemProps[];
}

/**
 * Trace detail view: collapsible summary sections above hierarchical span accordions.
 */
export const IntakeTraceDetailView: FC<IntakeTraceDetailViewProps> = ({
  workspace,
  traceId,
  parentBreadcrumbs,
}) => {
  const {
    data: trace,
    error,
    isLoading,
  } = useGetTrace(workspace, traceId, {
    mode: 'detailed',
  });

  const { setBreadcrumbs } = useBreadcrumbs();
  const traceBreadcrumbLabel = trace ? getTraceDisplayName(trace) : traceId;

  const summaryEntries = useMemo(
    () => (trace ? buildTraceSummaryEntries(trace, { workspace }) : []),
    [trace, workspace]
  );
  const experimentEntries = useMemo(
    () => (trace ? buildExperimentContextEntries(trace.experiment_context) : []),
    [trace]
  );

  useEffect(() => {
    const parent = parentBreadcrumbs ?? [
      { slotLabel: 'Intake', href: getIntakeTracesRoute(workspace) },
    ];
    setBreadcrumbs([...parent, { slotLabel: `Trace ${traceBreadcrumbLabel}` }]);
  }, [setBreadcrumbs, traceBreadcrumbLabel, workspace, parentBreadcrumbs]);

  if (error?.response?.status === 404) {
    return (
      <NotFound
        subheader="Trace Not Found"
        message="The trace does not exist or you do not have permission to view it."
      />
    );
  }

  if (isLoading) {
    return <Loading description="Loading trace..." />;
  }

  if (error) {
    return (
      <StatusMessage
        className="mx-auto mt-density-2xl"
        size="medium"
        slotMedia={<CircleAlert width={65} height={65} />}
        slotHeading="Error loading trace"
        slotSubheading={error.message}
      />
    );
  }

  if (!trace) {
    return null;
  }

  const title = getTraceDisplayName(trace);

  return (
    <AccessibleTitle title={`Trace ${title}`}>
      <Stack gap="density-2xl" padding="density-2xl" className="h-full overflow-auto">
        <PageHeader className="p-0" slotHeading={`Trace ${title}`} />
        <TraceSummaryHeader trace={trace} />
        <TraceSpanAccordions workspace={workspace} trace={trace} />
        <IntakeAccordion
          variant="section"
          defaultValue={[]}
          items={[
            {
              value: TRACE_SUMMARY_SECTION,
              slotLabel: <Text kind="body/semibold/sm">Metadata</Text>,
              slotContent: (
                <Stack className="min-w-0">
                  <KeyValueRows entries={summaryEntries} />
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
                        <KeyValueRows entries={experimentEntries} />
                      </Stack>
                    ),
                  },
                ]
              : []),
          ]}
        />
        <RawJsonDebug value={trace} />
      </Stack>
    </AccessibleTitle>
  );
};
