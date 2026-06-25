// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RetrieverSpanContent } from '@studio/components/IntakeDetail/SpanTemplates/RetrieverSpanContent';
import type { SpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/types';

/** Retriever: query + ranked documents live in the kind section; no output, no usage. */
export const retrieverSpanTemplate: SpanTemplate = {
  Content: RetrieverSpanContent,
  sections: ['kind', 'metadata', 'annotations'],
  attributeNamespaces: ['retrieval'],
};
