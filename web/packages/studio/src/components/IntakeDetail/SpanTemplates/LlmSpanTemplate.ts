// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LlmSpanContent } from '@studio/components/IntakeDetail/SpanTemplates/LlmSpanContent';
import type { SpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/types';

/** LLM: model & params elevated; token usage/cost and messages live below. */
export const llmSpanTemplate: SpanTemplate = {
  Content: LlmSpanContent,
  sections: ['kind', 'llm', 'input', 'output', 'metadata', 'annotations'],
  // Usage (tokens/cost) starts collapsed; model params and messages stay open.
  defaultOpen: ['kind', 'input', 'output'],
  attributeNamespaces: ['llm'],
};
