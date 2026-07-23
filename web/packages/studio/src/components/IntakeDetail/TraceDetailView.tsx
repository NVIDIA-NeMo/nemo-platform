// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeAccordion } from '@nemo/common/src/components/IntakeAccordion';
import { useGetTrace } from '@nemo/sdk/generated/platform/api';
import { PageHeader, Stack, StatusMessage, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { KeyValueRows } from '@studio/components/IntakeDetail/IntakeComponents/KeyValueRows';
import { RawJsonDebug } from '@studio/components/IntakeDetail/IntakeComponents/RawJsonDebug';
import {
  buildEvaluationContextEntries,
  buildTraceSummaryEntries,
} from '@studio/components/IntakeDetail/IntakeComponents/traceKeyValues';
import { TraceSummaryHeader } from '@studio/components/IntakeDetail/TraceDetailSummaryHeader';
import {
  TraceSpanAccordions,
  type SlotHeaderRenderProp,
} from '@studio/components/IntakeDetail/TraceSpanAccordions';
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
const EVALUATION_CONTEXT_SECTION = 'evaluation-context';

interface IntakeTraceDetailViewProps {
  workspace: string;
  traceId: string;
  /** Leading breadcrumb items. Defaults to the Intake root when omitted. */
  parentBreadcrumbs?: BreadcrumbsItemProps[];
  /** When true, shows "Test case: <test_case_id>" as the header instead of "Trace <name>". Falls back to "Trace <name>" when test_case_id is absent. */
  showTestCaseTitle?: boolean;
  /** When true, this instance does not update the breadcrumb trail. Use in compare mode where the parent controls breadcrumbs. */
  disableBreadcrumbs?: boolean;
  /** Currently linked (selected) span id, owned by the caller. Single view binds this to ?spanId=; compare view keeps one slot per column. */
  linkedSpanId: string | null;
  /** Called when the span selection changes. */
  onLinkedSpanIdChange: (spanId: string | null) => void;
  /** Rendered in the PageHeader's slotActions (e.g. a "Compare to…" selector). */
  slotPageHeaderActions?: React.ReactNode;
  /** When true, the PageHeader (trace title) is not rendered. Use in compare columns where the column card header serves that role. */
  hidePageHeader?: boolean;
  /** When true, forces list view in the span explorer and hides the Tree/List toggle. Pass in compare mode. */
  forceListView?: boolean;
  /** When true, opens the first span accordion by default once spans load. Pass in compare mode. */
  defaultOpenFirst?: boolean;
  /** Render prop receiving expandAll/collapseAll; replaces TraceSummaryHeader and is passed to TraceSpanAccordions as slotHeader. */
  slotSpanHeader?: SlotHeaderRenderProp;
}

/**
 * Trace detail view: collapsible summary sections above hierarchical span accordions.
 */
export const IntakeTraceDetailView: FC<IntakeTraceDetailViewProps> = ({
  workspace,
  traceId,
  parentBreadcrumbs,
  showTestCaseTitle,
  disableBreadcrumbs = false,
  linkedSpanId,
  onLinkedSpanIdChange,
  slotPageHeaderActions,
  hidePageHeader = false,
  forceListView = false,
  defaultOpenFirst = false,
  slotSpanHeader,
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
  const evaluationEntries = useMemo(
    () => (trace ? buildEvaluationContextEntries(trace.evaluation_context) : []),
    [trace]
  );

  useEffect(() => {
    if (disableBreadcrumbs) return;
    const parent = parentBreadcrumbs ?? [
      { slotLabel: 'Intake', href: getIntakeTracesRoute(workspace) },
    ];
    setBreadcrumbs([...parent, { slotLabel: `Trace ${traceBreadcrumbLabel}` }]);
  }, [disableBreadcrumbs, setBreadcrumbs, traceBreadcrumbLabel, workspace, parentBreadcrumbs]);

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

  const title =
    showTestCaseTitle && trace.experiment_context?.test_case_id
      ? `Test case: ${trace.experiment_context.test_case_id}`
      : `Trace ${getTraceDisplayName(trace)}`;

  return (
    <AccessibleTitle title={title}>
      <Stack gap="density-2xl" padding="density-2xl" className="h-full overflow-auto">
        {!hidePageHeader && (
          <PageHeader className="p-0" slotHeading={title} slotActions={slotPageHeaderActions} />
        )}
        {!slotSpanHeader && <TraceSummaryHeader trace={trace} />}
        <TraceSpanAccordions
          workspace={workspace}
          trace={trace}
          linkedSpanId={linkedSpanId}
          onLinkedSpanIdChange={onLinkedSpanIdChange}
          forceListView={forceListView}
          defaultOpenFirst={defaultOpenFirst}
          slotHeader={slotSpanHeader}
        />
        <IntakeAccordion
          variant="section"
          defaultValue={[]}
          items={[
            {
              value: TRACE_SUMMARY_SECTION,
              slotLabel: <Text kind="body/semibold/sm">Attributes</Text>,
              slotContent: (
                <Stack className="min-w-0">
                  <KeyValueRows entries={summaryEntries} />
                </Stack>
              ),
            },
            ...(evaluationEntries.length > 0
              ? [
                  {
                    value: EVALUATION_CONTEXT_SECTION,
                    slotLabel: <Text kind="body/semibold/sm">Evaluation Context</Text>,
                    slotContent: (
                      <Stack className="min-w-0">
                        <KeyValueRows entries={evaluationEntries} />
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
