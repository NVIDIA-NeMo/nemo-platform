// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DefaultSpanContent } from '@studio/components/IntakeDetail/SpanTemplates/DefaultSpanContent';
import type { SpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/types';

/**
 * Fallback template for kinds without a dedicated one (e.g. UNKNOWN). Its kind
 * body shows only the common status/timing values; the rest are shared sections.
 * The registry stays total so the span view never special-cases "no template".
 */
export const defaultSpanTemplate: SpanTemplate = {
  Content: DefaultSpanContent,
  sections: ['kind', 'input', 'output', 'metadata', 'annotations'],
};
