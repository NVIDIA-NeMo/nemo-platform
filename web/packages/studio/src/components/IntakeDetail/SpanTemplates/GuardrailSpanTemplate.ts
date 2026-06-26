// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Span } from '@nemo/sdk/generated/platform/schema';
import { GuardrailSpanContent } from '@studio/components/IntakeDetail/SpanTemplates/GuardrailSpanContent';
import {
  asBoolean,
  parseRawAttributes,
} from '@studio/components/IntakeDetail/SpanTemplates/rawAttributes';
import type {
  SpanHeaderBadge,
  SpanTemplate,
} from '@studio/components/IntakeDetail/SpanTemplates/types';

// Surface the rail decision in the row header: green when allowed, red when blocked.
const headerBadge = (span: Span): SpanHeaderBadge | undefined => {
  const blocked = asBoolean(parseRawAttributes(span.raw_attributes)['guardrail.blocked']);
  if (blocked === undefined) {
    return undefined;
  }
  return { text: blocked ? 'Blocked' : 'Allowed', color: blocked ? 'red' : 'green' };
};

/** Guardrail: checked content in, decision out; decision promoted to a row-header badge. */
export const guardrailSpanTemplate: SpanTemplate = {
  Content: GuardrailSpanContent,
  sections: ['kind', 'input', 'output', 'metadata', 'annotations'],
  headerBadge,
  attributeNamespaces: ['guardrail'],
};
