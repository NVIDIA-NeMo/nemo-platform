// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useGetSpan } from '@nemo/sdk/generated/platform/api';
import { PageHeader, Stack, StatusMessage } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { SpanMetadataAccordions } from '@studio/components/IntakeDetail/SpanMetadataAccordions';
import { Loading } from '@studio/components/Layouts/Loading';
import { NotFound } from '@studio/components/Layouts/NotFound';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getIntakeTraceRoute, getIntakeTracesRoute } from '@studio/routes/utils';
import { getSpanDisplayName } from '@studio/util/intakeTelemetry';
import { CircleAlert } from 'lucide-react';
import { type FC, useEffect } from 'react';

interface IntakeSpanDetailViewProps {
  workspace: string;
  spanId: string;
}

/**
 * Span detail view: renders the same accordion sections used inline in the
 * trace detail view, so a standalone span page and an expanded span in a trace
 * look identical.
 */
export const IntakeSpanDetailView: FC<IntakeSpanDetailViewProps> = ({ workspace, spanId }) => {
  const { data: span, error, isLoading } = useGetSpan(workspace, spanId);

  const { setBreadcrumbs } = useBreadcrumbs();
  const spanBreadcrumbLabel = span ? getSpanDisplayName(span) : spanId;

  useEffect(() => {
    setBreadcrumbs([
      {
        slotLabel: 'Intake',
        href: getIntakeTracesRoute(workspace),
      },
      ...(span?.trace_id
        ? [
            {
              slotLabel: `Trace ${span.trace_id}`,
              href: getIntakeTraceRoute(workspace, span.trace_id),
            },
          ]
        : []),
      {
        slotLabel: `Span ${spanBreadcrumbLabel}`,
      },
    ]);
  }, [setBreadcrumbs, span?.trace_id, spanBreadcrumbLabel, workspace]);

  if (error?.response?.status === 404) {
    return (
      <NotFound
        subheader="Span Not Found"
        message="The span does not exist or you do not have permission to view it."
      />
    );
  }

  if (isLoading) {
    return <Loading description="Loading span..." />;
  }

  if (error) {
    return (
      <StatusMessage
        className="mx-auto mt-density-2xl"
        size="medium"
        slotMedia={<CircleAlert width={65} height={65} />}
        slotHeading="Error loading span"
        slotSubheading={error.message}
      />
    );
  }

  if (!span) {
    return null;
  }

  const title = getSpanDisplayName(span);

  return (
    <AccessibleTitle title={`Span ${title}`}>
      <Stack gap="density-2xl" padding="density-2xl" className="h-full overflow-auto">
        <PageHeader className="p-0" slotHeading={title} />
        <SpanMetadataAccordions span={span} workspace={workspace} />
      </Stack>
    </AccessibleTitle>
  );
};
