// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EmbeddingSpanContent } from '@studio/components/IntakeDetail/SpanTemplates/EmbeddingSpanContent';
import type { SpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/types';

/** Embedding: model/dimensions/tokens + embedded text live in the kind section. */
export const embeddingSpanTemplate: SpanTemplate = {
  Content: EmbeddingSpanContent,
  sections: ['kind', 'metadata', 'annotations'],
  attributeNamespaces: ['embedding'],
};
