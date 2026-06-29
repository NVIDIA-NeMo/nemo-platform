// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TemplateKeyValues } from '@studio/components/IntakeDetail/SpanTemplates/templateFields';
import type { SpanTemplateContentProps } from '@studio/components/IntakeDetail/SpanTemplates/types';
import type { FC } from 'react';

/**
 * Fallback body for kinds without a dedicated template (e.g. UNKNOWN). It has no
 * kind-specific fields, so it shows only the common status/timing values that
 * every template surfaces at the top.
 */
export const DefaultSpanContent: FC<SpanTemplateContentProps> = ({ span }) => (
  <TemplateKeyValues span={span} fields={[]} />
);
