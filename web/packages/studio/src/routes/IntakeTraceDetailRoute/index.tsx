// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeTraceDetailView } from '@studio/components/IntakeDetail/TraceDetailView';
import { NotFound } from '@studio/components/Layouts/NotFound';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { type BreadcrumbsItemProps } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { type FC } from 'react';
import { useParams } from 'react-router-dom';

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
}

/**
 * Trace detail content with the workspace resolved from the path. Exported so
 * the experiment trace route can reuse it with its own breadcrumb trail.
 */
export const IntakeTraceDetailContent: FC<IntakeTraceDetailContentProps> = ({
  traceId,
  parentBreadcrumbs,
}) => {
  const workspace = useWorkspaceFromPath();

  return (
    <IntakeTraceDetailView
      workspace={workspace}
      traceId={traceId}
      parentBreadcrumbs={parentBreadcrumbs}
    />
  );
};
