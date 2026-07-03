// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EvaluatorSpanContent } from '@studio/components/IntakeDetail/SpanTemplates/EvaluatorSpanContent';
import type { SpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/types';

/** Evaluator: what was judged in, verdict out. */
export const evaluatorSpanTemplate: SpanTemplate = {
  Content: EvaluatorSpanContent,
  sections: ['kind', 'input', 'output', 'metadata', 'annotations'],
  defaultOpen: ['input'],
  attributeNamespaces: ['evaluator'],
};
