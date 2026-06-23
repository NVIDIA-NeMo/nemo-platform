// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useGetTrace } from '@nemo/sdk/generated/platform/api';
import { Stack, StatusMessage } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { Loading } from '@studio/components/Layouts/Loading';
import { NotFound } from '@studio/components/Layouts/NotFound';
import { getAgent00TraceSubject } from '@nemo/studio-plugins-example/intake-trace-detail-agent00/agent00Subject';
import { TraceSpanAccordions } from '@nemo/studio-plugins-example/intake-trace-detail-agent00/TraceSpanAccordions';
import type { ViewContextMap } from '@studio/plugins/types';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getIntakeTracesRoute } from '@studio/routes/utils';
import { CircleAlert } from 'lucide-react';
import { type FC, useEffect } from 'react';

/** Agent00 trace detail: span accordions labeled by subject, Call/Result payloads only. */
export const IntakeTraceDetailView: FC<ViewContextMap['intake.trace.detail']> = ({
  workspace,
  traceId,
}) => {
  const {
    data: trace,
    error,
    isLoading,
  } = useGetTrace(workspace, traceId, {
    mode: 'detailed',
  });

  const { setBreadcrumbs } = useBreadcrumbs();
  const traceSubject = trace ? getAgent00TraceSubject(trace) : traceId;

  useEffect(() => {
    setBreadcrumbs([
      {
        slotLabel: 'Intake',
        href: getIntakeTracesRoute(workspace),
      },
      {
        slotLabel: traceSubject,
      },
    ]);
  }, [setBreadcrumbs, traceSubject, workspace]);

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

  return (
    <AccessibleTitle title={traceSubject}>
      <Stack gap="density-2xl" padding="density-2xl" className="min-w-0">
        <TraceSpanAccordions
          workspace={workspace}
          traceId={trace.id}
          spanCount={trace.span_count}
        />
      </Stack>
    </AccessibleTitle>
  );
};
