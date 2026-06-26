// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  RerankerSpanContent,
  rerankerCustomSections,
} from '@studio/components/IntakeDetail/SpanTemplates/RerankerSpanContent';
import type { SpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/types';

/** Reranker: key values in the kind body; ranked scores are an accordion section. */
export const rerankerSpanTemplate: SpanTemplate = {
  Content: RerankerSpanContent,
  sections: ['kind', 'metadata', 'annotations'],
  attributeNamespaces: ['reranker'],
  customSections: rerankerCustomSections,
};
