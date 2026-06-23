// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Span } from '@nemo/sdk/generated/platform/schema';
import { SpanCallResultPanel } from '@nemo/studio-plugins-example/intake-trace-detail-agent00/SpanCallResultPanel';
import type { FC } from 'react';

interface TraceSpanAccordionDetailProps {
  span: Span;
}

/** Agent00 span detail: Call and Result only. */
export const TraceSpanAccordionDetail: FC<TraceSpanAccordionDetailProps> = ({ span }) => (
  <SpanCallResultPanel input={span.input} output={span.output} />
);
