// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { IntakeTraceDetailBody } from '@studio/components/IntakeTraceDetailBody';
import { NotFound } from '@studio/components/Layouts/NotFound';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getIntakeTracesRoute } from '@studio/routes/utils';
import { type FC, useEffect } from 'react';
import { useParams } from 'react-router-dom';

const TRACE_DETAIL_SPANS_FILTER_TARGET_ID = 'trace-detail-spans-filter-action-target';

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

interface IntakeTraceDetailContentProps {
  traceId: string;
}

const IntakeTraceDetailContent: FC<IntakeTraceDetailContentProps> = ({ traceId }) => {
  const workspace = useWorkspaceFromPath();
  const { setBreadcrumbs } = useBreadcrumbs();

  useEffect(() => {
    setBreadcrumbs([
      {
        slotLabel: 'Intake',
        href: getIntakeTracesRoute(workspace),
      },
      {
        slotLabel: `Trace ${traceId}`,
      },
    ]);
  }, [setBreadcrumbs, traceId, workspace]);

  return (
    <AccessibleTitle title={`Trace ${traceId}`}>
      <Stack gap="density-2xl" padding="density-2xl" className="h-full overflow-auto">
        <PageHeader
          className="p-0"
          slotHeading={`Trace ${traceId}`}
          slotActions={
            <div
              id={TRACE_DETAIL_SPANS_FILTER_TARGET_ID}
              className="flex shrink-0 items-center justify-end"
            />
          }
        />
        <IntakeTraceDetailBody
          traceId={traceId}
          filterTogglePortalTargetId={TRACE_DETAIL_SPANS_FILTER_TARGET_ID}
        />
      </Stack>
    </AccessibleTitle>
  );
};
