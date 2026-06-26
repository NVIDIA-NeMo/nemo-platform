// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Span } from '@nemo/sdk/generated/platform/schema';
import { EvaluatorSpanContent } from '@studio/components/IntakeDetail/SpanTemplates/EvaluatorSpanContent';
import {
  asBoolean,
  asNumber,
  asString,
  parseRawAttributes,
} from '@studio/components/IntakeDetail/SpanTemplates/rawAttributes';
import type {
  SpanHeaderBadge,
  SpanTemplate,
} from '@studio/components/IntakeDetail/SpanTemplates/types';

// The evaluator's identity is its `evaluator.name` (e.g. "faithfulness-judge"),
// which is more useful in the row header than the generic span name.
const headerTitle = (span: Span): string | undefined =>
  asString(parseRawAttributes(span.raw_attributes)['evaluator.name']);

// Surface the verdict in the row header: a numeric score, else pass/fail.
const headerBadge = (span: Span): SpanHeaderBadge | undefined => {
  const attributes = parseRawAttributes(span.raw_attributes);
  const score = asNumber(attributes['evaluator.score']);
  if (score !== undefined) {
    return { text: score.toFixed(3) };
  }
  const passed = asBoolean(attributes['evaluator.passed']);
  if (passed === undefined) {
    return undefined;
  }
  return { text: passed ? 'Pass' : 'Fail', color: passed ? 'green' : 'red' };
};

/** Evaluator: what was judged in, verdict out. Name + score elevated to the row header. */
export const evaluatorSpanTemplate: SpanTemplate = {
  Content: EvaluatorSpanContent,
  sections: ['kind', 'input', 'output', 'metadata', 'annotations'],
  defaultOpen: ['input'],
  headerTitle,
  headerBadge,
  attributeNamespaces: ['evaluator'],
};
