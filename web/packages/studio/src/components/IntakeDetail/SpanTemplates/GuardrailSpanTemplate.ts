// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { GuardrailSpanContent } from '@studio/components/IntakeDetail/SpanTemplates/GuardrailSpanContent';
import type { SpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/types';

/** Guardrail: checked content in, decision out. */
export const guardrailSpanTemplate: SpanTemplate = {
  Content: GuardrailSpanContent,
  sections: ['kind', 'input', 'output', 'metadata', 'annotations'],
  attributeNamespaces: ['guardrail'],
};
