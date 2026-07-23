// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeTraceDetailView } from '@studio/components/IntakeDetail/TraceDetailView';
import { NotFound } from '@studio/components/Layouts/NotFound';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { type BreadcrumbsItemProps } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { type FC, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';

type TraceRouteParams = Record<typeof ROUTE_PARAMS.traceId, string | undefined>;

export const IntakeTraceDetailRoute: FC = () => {
  const { [ROUTE_PARAMS.traceId]: traceId } = useParams<TraceRouteParams>();

  if (!traceId) {
    return (
      <NotFound subheader="Trace Not Found" message="The trace route is missing a trace ID." />
    );
  }

  return <IntakeTraceDetailContent traceId={traceId} />;
};

export interface IntakeTraceDetailContentProps {
  traceId: string;
  /** Leading breadcrumb items. Defaults to the Intake root when omitted. */
  parentBreadcrumbs?: BreadcrumbsItemProps[];
  /** When true, shows "Test case: <test_case_id>" as the header instead of "Trace <name>". */
  showTestCaseTitle?: boolean;
  /** Forwarded to IntakeTraceDetailView's PageHeader slotActions. */
  slotPageHeaderActions?: React.ReactNode;
}

/**
 * Trace detail content with the workspace resolved from the path. Exported so
 * the experiment trace route can reuse it with its own breadcrumb trail.
 */
export const IntakeTraceDetailContent: FC<IntakeTraceDetailContentProps> = ({
  traceId,
  parentBreadcrumbs,
  showTestCaseTitle,
  slotPageHeaderActions,
}) => {
  const workspace = useWorkspaceFromPath();
  // Single-view URL binding: the linked span deep-links via ?spanId=. Compare
  // view bypasses this wrapper and keeps one selection slot per column instead.
  const [searchParams, setSearchParams] = useSearchParams();
  const linkedSpanId = searchParams.get(QUERY_PARAMETERS.spanId) || null;
  const handleLinkedSpanIdChange = useCallback(
    (spanId: string | null) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (spanId) next.set(QUERY_PARAMETERS.spanId, spanId);
          else next.delete(QUERY_PARAMETERS.spanId);
          return next;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  return (
    <IntakeTraceDetailView
      workspace={workspace}
      traceId={traceId}
      parentBreadcrumbs={parentBreadcrumbs}
      showTestCaseTitle={showTestCaseTitle}
      linkedSpanId={linkedSpanId}
      onLinkedSpanIdChange={handleLinkedSpanIdChange}
      slotPageHeaderActions={slotPageHeaderActions}
    />
  );
};
