// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Span } from '@nemo/sdk/generated/platform/schema';
import { useGetSpan } from '@nemo/sdk/generated/platform/api';
import { Spinner, Stack, StatusMessage } from '@nvidia/foundations-react-core';
import { mergeSpanDetails } from '@nemo/studio-plugins-example/intake-trace-detail/spanKeyValues';
import { TraceSpanAccordionDetail } from '@nemo/studio-plugins-example/intake-trace-detail/TraceSpanAccordionDetail';
import { CircleAlert } from 'lucide-react';
import { type FC, useMemo } from 'react';

interface TraceSpanAccordionContentProps {
  workspace: string;
  spanId: string;
  summarySpan?: Span;
}

/** Loads full span detail when an accordion section is expanded. */
export const TraceSpanAccordionContent: FC<TraceSpanAccordionContentProps> = ({
  workspace,
  spanId,
  summarySpan,
}) => {
  const { data: detailSpan, error, isLoading } = useGetSpan(workspace, spanId);
  const span = useMemo(
    () => (detailSpan ? mergeSpanDetails(summarySpan, detailSpan) : summarySpan),
    [detailSpan, summarySpan]
  );

  if (!span && isLoading) {
    return (
      <Stack
        gap="density-md"
        padding="density-xl"
        className="items-center justify-center min-h-[200px]"
      >
        <Spinner size="medium" />
      </Stack>
    );
  }

  if (error && !span) {
    return (
      <StatusMessage
        size="small"
        slotMedia={<CircleAlert width={40} height={40} />}
        slotHeading="Error loading span"
        slotSubheading={error.message}
      />
    );
  }

  if (!span) {
    return null;
  }

  return (
    <Stack className="min-w-0">
      <TraceSpanAccordionDetail span={span} workspace={workspace} />
    </Stack>
  );
};
