// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ChainSpanContent } from '@studio/components/IntakeDetail/SpanTemplates/ChainSpanContent';
import type { SpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/types';

/** Chain: orchestration in/out. */
export const chainSpanTemplate: SpanTemplate = {
  Content: ChainSpanContent,
  sections: ['kind', 'input', 'output', 'metadata', 'annotations'],
  attributeNamespaces: ['chain'],
};
