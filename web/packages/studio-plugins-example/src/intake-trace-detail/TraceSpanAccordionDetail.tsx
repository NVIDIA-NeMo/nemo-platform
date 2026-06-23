// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Span } from '@nemo/sdk/generated/platform/schema';
import { SpanMetadataAccordions } from '@nemo/studio-plugins-example/intake-trace-detail/SpanMetadataAccordions';
import type { FC } from 'react';

interface TraceSpanAccordionDetailProps {
  span: Span;
  workspace: string;
}

/** Plugin span detail: input/output accordions plus metadata sections. */
export const TraceSpanAccordionDetail: FC<TraceSpanAccordionDetailProps> = ({ span, workspace }) => (
  <SpanMetadataAccordions span={span} workspace={workspace} />
);
